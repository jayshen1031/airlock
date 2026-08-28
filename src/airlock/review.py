"""Review-only application service."""

from __future__ import annotations

from pathlib import Path

from airlock.adapters.base import AgentAdapter
from airlock.git_workspace import GitWorkspace
from airlock.models import AgentRequest, ReviewResult, Verdict
from airlock.run_store import RunStore, RunStoreIntegrityError
from airlock.schema import REVIEW_SCHEMA, parse_review_json


class ReviewerMutationError(RuntimeError):
    pass


def build_prompt(task: str, material: str) -> str:
    return f"""You are the independent, read-only reviewer in Airlock.

Review the current uncommitted Git changes for correctness, regressions,
security, missing tests, and violations of the stated task. Do not modify any
file and do not suggest approval when evidence is unavailable. Return only the
JSON object required by the supplied schema.

Verdict rules:
- approve: no actionable findings remain; findings must be empty.
- reject: at least one actionable finding exists.
- blocked: the available repository evidence cannot support a reliable review.

Task:
{task}

Repository changes:
{material}
"""


def review_repository(
    repository: Path,
    task: str,
    adapter: AgentAdapter,
    timeout_seconds: float = 600,
) -> tuple[ReviewResult, RunStore]:
    workspace = GitWorkspace(repository)
    store = RunStore(workspace.root)
    material = workspace.review_material()
    prompt = build_prompt(task, material)
    store.write_text("task.md", task.strip() + "\n")
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
    if before.fingerprint != after.fingerprint:
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
