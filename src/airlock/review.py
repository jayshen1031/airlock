"""Review-only application service."""

from __future__ import annotations

from pathlib import Path

from airlock.adapters.base import AgentAdapter
from airlock.git_workspace import GitWorkspace, GitWorkspaceError
from airlock.models import AgentRequest, Finding, ReviewResult, Severity, Verdict
from airlock.run_store import RunStore, RunStoreIntegrityError
from airlock.schema import REVIEW_SCHEMA, parse_review_json
from airlock.test_gate import TestResult, load_test_gate, run_test_gate


class ReviewerMutationError(RuntimeError):
    pass


def build_prompt(
    task: str,
    material: str,
    test_result: TestResult | None = None,
) -> str:
    test_evidence = "No test gate was configured."
    if test_result is not None:
        test_evidence = (
            f"Command: {list(test_result.command)!r}\n"
            f"Exit code: {test_result.exit_code}\n"
            f"Timed out: {test_result.timed_out}\n"
            f"Error: {test_result.error}\n"
            f"Stdout:\n{test_result.stdout}\n"
            f"Stderr:\n{test_result.stderr}"
        )
    return f"""You are the independent, read-only reviewer in Airlock.

Review the current uncommitted Git changes for correctness, regressions,
security, missing tests, and violations of the stated task. Do not modify any
file and do not suggest approval when evidence is unavailable. Return only the
JSON object required by the supplied schema.

Verdict rules:
- approve: no actionable findings remain; findings must be empty.
- reject: at least one actionable finding exists.
- blocked: the available repository evidence cannot support a reliable review.
- Never approve when the configured test gate failed, timed out, or could not run.

Task:
{task}

Repository changes:
{material}

Test gate evidence:
{test_evidence}
"""


def _enforce_test_gate(
    result: ReviewResult,
    test_result: TestResult | None,
) -> ReviewResult:
    if test_result is None or test_result.passed:
        return result
    if test_result.infrastructure_failure:
        detail = "timed out" if test_result.timed_out else test_result.error
        return ReviewResult(
            verdict=Verdict.BLOCKED,
            summary=f"Configured test gate could not complete: {detail}",
        )
    if result.verdict is Verdict.REJECT:
        return result
    return ReviewResult(
        verdict=Verdict.REJECT,
        summary="Configured test gate failed; approval is not permitted.",
        findings=(
            Finding(
                severity=Severity.HIGH,
                issue=f"Configured test command exited with {test_result.exit_code}.",
                suggestion="Inspect test-result.json and fix the failing tests.",
            ),
        ),
    )


def _recover_test_gate_failure(
    store: RunStore,
    test_result: TestResult,
    reason: str,
) -> ReviewResult:
    result = ReviewResult(
        verdict=Verdict.BLOCKED,
        summary=f"Test gate audit failed closed: {reason}",
    )
    store.write_recovery_json(
        {
            "run_id": store.run_id,
            "state": {"status": "blocked", "reason": reason},
            "review": result.to_dict(),
            "test_result": test_result.to_dict(),
        }
    )
    return result


def review_repository(
    repository: Path,
    task: str,
    adapter: AgentAdapter,
    timeout_seconds: float = 600,
) -> tuple[ReviewResult, RunStore]:
    workspace = GitWorkspace(repository)
    store = RunStore(workspace.root)
    store.write_text("task.md", task.strip() + "\n")
    try:
        test_config = load_test_gate(workspace.root)
    except ValueError as exc:
        result = ReviewResult(
            verdict=Verdict.BLOCKED,
            summary=f"Configured test gate is invalid: {exc}",
        )
        store.write_text("diff.patch", workspace.review_material())
        store.write_json("review.json", result.to_dict())
        store.write_json(
            "state.json",
            {
                "run_id": store.run_id,
                "status": "blocked",
                "reason": str(exc),
            },
        )
        return result, store
    test_result = None
    if test_config is not None:
        store.write_json(
            "state.json",
            {"run_id": store.run_id, "status": "testing", "head": workspace.head()},
        )
        before_test = workspace.snapshot()
        before_test_revision = workspace.revision_identity()
        test_result = run_test_gate(workspace.root, test_config)
        try:
            after_test = workspace.snapshot()
            after_test_revision = workspace.revision_identity()
            store.write_json("test-result.json", test_result.to_dict())
        except (GitWorkspaceError, RunStoreIntegrityError, OSError) as exc:
            return _recover_test_gate_failure(store, test_result, str(exc)), store
        if (
            before_test.fingerprint != after_test.fingerprint
            or before_test_revision != after_test_revision
        ):
            result = ReviewResult(
                verdict=Verdict.BLOCKED,
                summary=(
                    "Configured test gate changed the workspace; Airlock left the "
                    "changes intact and did not invoke the reviewer."
                ),
            )
            try:
                store.write_json("review.json", result.to_dict())
                store.write_json(
                    "state.json",
                    {
                        "run_id": store.run_id,
                        "status": "blocked",
                        "reason": "test gate mutated the workspace",
                    },
                )
            except RunStoreIntegrityError as exc:
                return _recover_test_gate_failure(store, test_result, str(exc)), store
            return result, store
    material = workspace.review_material()
    prompt = build_prompt(task, material, test_result)
    store.write_text("diff.patch", material)
    schema_path = store.write_json("review-schema.json", REVIEW_SCHEMA)
    store.write_json(
        "state.json",
        {
            "run_id": store.run_id,
            "status": "reviewing",
            "reviewer": adapter.executable,
            "head": workspace.head(),
        },
    )

    before = workspace.snapshot()
    before_revision = workspace.revision_identity()
    provider_result = None
    provider_error: Exception | None = None
    try:
        provider_result = adapter.run(
            AgentRequest(
                prompt=prompt,
                cwd=workspace.root,
                schema_path=schema_path,
                timeout_seconds=timeout_seconds,
            )
        )
    except Exception as exc:
        provider_error = exc
    finally:
        after = workspace.snapshot()
        after_revision = workspace.revision_identity()
    if (
        before.fingerprint != after.fingerprint
        or before_revision != after_revision
    ):
        failure = {
            "run_id": store.run_id,
            "status": "failed",
            "reason": "reviewer mutated the workspace",
        }
        recovery_path = None
        try:
            store.write_json("state.json", failure)
        except RunStoreIntegrityError:
            recovery_path = store.write_recovery_json(failure)
        detail = "reviewer changed the workspace; Airlock left the changes intact"
        if recovery_path is not None:
            detail += f"; recovery artifact: {recovery_path}"
        raise ReviewerMutationError(
            detail
        ) from provider_error
    if provider_error is not None:
        result = ReviewResult(
            verdict=Verdict.BLOCKED,
            summary=f"Reviewer unavailable: {provider_error}",
        )
        store.write_json("review.json", result.to_dict())
        store.write_json(
            "state.json",
            {
                "run_id": store.run_id,
                "status": "blocked",
                "reason": str(provider_error),
            },
        )
        return result, store

    assert provider_result is not None

    store.write_json(
        "provider.json",
        {
            "command": list(provider_result.command),
            "exit_code": provider_result.exit_code,
            "duration_seconds": provider_result.duration_seconds,
            "stderr": provider_result.stderr,
        },
    )
    try:
        result = parse_review_json(provider_result.output)
    except ValueError as exc:
        result = ReviewResult(
            verdict=Verdict.BLOCKED,
            summary=f"Reviewer returned an invalid verdict: {exc}",
        )
        store.write_json("review.json", result.to_dict())
        store.write_json(
            "state.json",
            {
                "run_id": store.run_id,
                "status": "blocked",
                "reason": str(exc),
            },
        )
        return result, store
    result = _enforce_test_gate(result, test_result)
    store.write_json("review.json", result.to_dict())
    store.write_json(
        "state.json",
        {
            "run_id": store.run_id,
            "status": result.verdict.value,
            "reviewer": adapter.executable,
            "head": workspace.head(),
        },
    )
    return result, store
