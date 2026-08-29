"""Bounded findings-driven repair loop."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from pathlib import Path

from airlock.adapters.base import AgentAdapter
from airlock.git_workspace import GitWorkspace, GitWorkspaceError
from airlock.models import AgentMode, AgentRequest, ReviewResult, Verdict
from airlock.review import review_repository
from airlock.run_store import RunStore, RunStoreIntegrityError


def build_repair_prompt(task: str, review: ReviewResult) -> str:
    findings = json.dumps(review.to_dict(), indent=2, ensure_ascii=False)
    return f"""You are the writer in an Airlock repair iteration.

Modify the current repository to address only the structured review findings
below while preserving the stated task. Inspect the repository as needed and
let Airlock run the configured test gate after the edit. Do not commit, push,
merge, reset, checkout, or discard unrelated user changes. Do not rely on or
request reviewer conversation history. Leave the repaired files in the working
tree and finish with a brief summary.

Task:
{task}

Structured review:
{findings}
"""


def _findings_fingerprint(review: ReviewResult) -> str:
    payload = review.to_dict()["findings"]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _progress_fingerprint(workspace: GitWorkspace) -> str:
    digest = hashlib.sha256()
    digest.update(workspace.revision_identity().encode())
    digest.update(b"\0")
    digest.update(workspace.review_material().encode())
    return digest.hexdigest()


def _artifact_fingerprint(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()

    def visit(path: Path, label: str) -> None:
        digest.update(label.encode())
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            digest.update(b"\0missing")
            return
        digest.update(f"\0{metadata.st_dev}:{metadata.st_ino}:{metadata.st_mode}".encode())
        if stat.S_ISLNK(metadata.st_mode):
            digest.update(b"\0symlink\0" + os.fsencode(os.readlink(path)))
            return
        if stat.S_ISREG(metadata.st_mode):
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                    raise RunStoreIntegrityError("protected artifact changed while hashing")
                while chunk := os.read(descriptor, 65_536):
                    digest.update(chunk)
            finally:
                os.close(descriptor)
            return
        if stat.S_ISDIR(metadata.st_mode):
            with os.scandir(path) as entries:
                children = sorted(entries, key=lambda entry: entry.name)
            for child in children:
                visit(Path(child.path), f"{label}/{child.name}")

    for index, path in enumerate(paths):
        visit(path, f"root-{index}")
    return digest.hexdigest()


def _blocked(summary: str) -> ReviewResult:
    return ReviewResult(verdict=Verdict.BLOCKED, summary=summary)


def _write_state(store: RunStore, **state: object) -> None:
    store.write_json("state.json", {"run_id": store.run_id, **state})


def repair_repository(
    repository: Path,
    task: str,
    writer: AgentAdapter,
    reviewer: AgentAdapter,
    max_iterations: int = 3,
    timeout_seconds: float = 600,
) -> tuple[ReviewResult, RunStore]:
    if max_iterations < 1 or max_iterations > 10:
        raise ValueError("max_iterations must be between 1 and 10")
    if writer.executable == reviewer.executable:
        raise ValueError("writer and reviewer must be different providers")

    workspace = GitWorkspace(repository)
    store = RunStore(workspace.root)
    store.write_text("task.md", task.strip() + "\n")
    events: list[dict[str, object]] = []
    seen_findings: set[str] = set()
    seen_progress = {_progress_fingerprint(workspace)}
    prior_review: ReviewResult | None = None
    protected_artifact_paths = [store.path]

    def transition(status: str, **detail: object) -> None:
        event = {"sequence": len(events) + 1, "status": status, **detail}
        events.append(event)
        store.write_json("events.json", events)
        _write_state(store, status=status, **detail)

    try:
        for review_number in range(1, max_iterations + 2):
            transition(
                "reviewing",
                review_number=review_number,
                repairs_used=review_number - 1,
                reviewer=reviewer.executable,
            )
            review, review_store = review_repository(
                repository=workspace.root,
                task=task,
                adapter=reviewer,
                timeout_seconds=timeout_seconds,
                prior_review=prior_review,
            )
            protected_artifact_paths.append(review_store.artifact_path)
            store.write_json(
                f"iteration-{review_number:02d}-review.json",
                {
                    "artifact_path": str(review_store.artifact_path),
                    "result": review.to_dict(),
                },
            )
            if review.verdict is Verdict.APPROVE:
                transition("approved", review_number=review_number)
                return review, store
            if review.verdict is Verdict.BLOCKED:
                transition(
                    "blocked",
                    review_number=review_number,
                    reason=review.summary,
                )
                return review, store

            findings_fingerprint = _findings_fingerprint(review)
            if findings_fingerprint in seen_findings:
                result = _blocked("Repair loop is stuck: reviewer repeated the same findings.")
                transition("blocked", reason=result.summary, review_number=review_number)
                return result, store
            seen_findings.add(findings_fingerprint)

            repairs_used = review_number - 1
            if repairs_used >= max_iterations:
                transition(
                    "exhausted",
                    review_number=review_number,
                    repairs_used=repairs_used,
                )
                return review, store

            transition(
                "repairing",
                repair_number=review_number,
                writer=writer.executable,
            )
            before_progress = _progress_fingerprint(workspace)
            before_revision = workspace.revision_identity()
            protected_paths = tuple(protected_artifact_paths)
            before_artifacts = _artifact_fingerprint(protected_paths)
            writer_request = AgentRequest(
                prompt=build_repair_prompt(task, review),
                cwd=workspace.root,
                schema_path=None,
                timeout_seconds=timeout_seconds,
                mode=AgentMode.WRITE,
            )
            planned_command = [writer.executable]
            writer_started = time.monotonic()
            try:
                planned_command = writer.command(writer_request)
                writer_result = writer.run(writer_request)
            except KeyboardInterrupt:
                result = _blocked("Repair loop canceled by user.")
                evidence = {
                    "command": planned_command,
                    "exit_code": None,
                    "duration_seconds": time.monotonic() - writer_started,
                    "timed_out": False,
                    "canceled": True,
                    "stderr": "",
                    "output": "",
                    "error": "writer canceled by user",
                }
                if _artifact_fingerprint(protected_paths) != before_artifacts:
                    store.write_recovery_json(
                        {
                            "run_id": store.run_id,
                            "state": {"status": "canceled", "reason": result.summary},
                            "review": result.to_dict(),
                            "writer": evidence,
                            "events": events,
                        }
                    )
                    return result, store
                store.write_json(
                    f"iteration-{review_number:02d}-writer.json",
                    evidence,
                )
                transition("canceled", repair_number=review_number)
                return result, store
            except Exception as exc:
                evidence = getattr(
                    exc,
                    "evidence",
                    {
                        "command": [writer.executable],
                        "exit_code": None,
                        "duration_seconds": None,
                        "timed_out": False,
                        "stderr": "",
                        "output": "",
                        "error": str(exc),
                    },
                )
                if _artifact_fingerprint(protected_paths) != before_artifacts:
                    result = _blocked(
                        "Writer changed protected Airlock artifacts and then failed; "
                        "changes were left intact."
                    )
                    store.write_recovery_json(
                        {
                            "run_id": store.run_id,
                            "state": {"status": "blocked", "reason": result.summary},
                            "review": result.to_dict(),
                            "writer": evidence,
                            "events": events,
                        }
                    )
                    return result, store
                store.write_json(
                    f"iteration-{review_number:02d}-writer.json",
                    evidence,
                )
                result = _blocked(f"Writer unavailable: {exc}")
                transition("blocked", reason=str(exc), repair_number=review_number)
                return result, store

            after_revision = workspace.revision_identity()
            after_progress = _progress_fingerprint(workspace)
            after_artifacts = _artifact_fingerprint(protected_paths)
            writer_evidence = {
                "command": list(writer_result.command),
                "exit_code": writer_result.exit_code,
                "duration_seconds": writer_result.duration_seconds,
                "timed_out": False,
                "stderr": writer_result.stderr,
                "output": writer_result.output,
                "error": None,
            }
            if before_artifacts != after_artifacts:
                result = _blocked(
                    "Writer changed protected Airlock artifacts; changes were left intact."
                )
                store.write_recovery_json(
                    {
                        "run_id": store.run_id,
                        "state": {"status": "blocked", "reason": result.summary},
                        "review": result.to_dict(),
                        "writer": writer_evidence,
                        "events": events,
                    }
                )
                return result, store
            store.write_json(
                f"iteration-{review_number:02d}-writer.json",
                writer_evidence,
            )
            if before_revision != after_revision:
                result = _blocked(
                    "Writer changed Git revision identity; Airlock left the changes intact."
                )
                transition("blocked", reason=result.summary, repair_number=review_number)
                return result, store
            if before_progress == after_progress:
                result = _blocked("Repair loop is stuck: writer made no auditable progress.")
                transition("blocked", reason=result.summary, repair_number=review_number)
                return result, store
            if after_progress in seen_progress:
                result = _blocked(
                    "Repair loop is stuck: workspace returned to a previously reviewed state."
                )
                transition("blocked", reason=result.summary, repair_number=review_number)
                return result, store
            seen_progress.add(after_progress)
            prior_review = review
    except KeyboardInterrupt:
        result = _blocked("Repair loop canceled by user.")
        try:
            transition("canceled")
        except RunStoreIntegrityError:
            store.write_recovery_json(
                {
                    "run_id": store.run_id,
                    "state": {"status": "canceled"},
                    "review": result.to_dict(),
                    "events": events,
                }
            )
        return result, store
    except (GitWorkspaceError, RunStoreIntegrityError, OSError) as exc:
        result = _blocked(f"Repair run store failed closed: {exc}")
        store.write_recovery_json(
            {
                "run_id": store.run_id,
                "state": {"status": "blocked", "reason": str(exc)},
                "review": result.to_dict(),
                "events": events,
            }
        )
        return result, store

    raise AssertionError("bounded repair loop ended without a verdict")
