import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from airlock.adapters.base import AgentAdapter
from airlock.models import AgentRequest, AgentResult, Verdict
from airlock.review import ReviewerMutationError, review_repository


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def repository(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "file.py").write_text("value = 1\n")
    git(tmp_path, "add", "file.py")
    git(tmp_path, "commit", "-qm", "initial")
    (tmp_path / "file.py").write_text("value = 2\n")
    return tmp_path


class FakeAdapter(AgentAdapter):
    executable = "fake"

    def __init__(self, payload: dict, mutate: bool = False) -> None:
        self.payload = payload
        self.mutate = mutate

    def available(self) -> bool:
        return True

    def command(self, request: AgentRequest) -> list[str]:
        return ["fake"]

    def run(self, request: AgentRequest) -> AgentResult:
        if self.mutate:
            (request.cwd / "file.py").write_text("mutated = True\n")
        return AgentResult(json.dumps(self.payload), "", 0, 0.1, ("fake",))


class FailingAdapter(FakeAdapter):
    def run(self, request: AgentRequest) -> AgentResult:
        raise RuntimeError("provider failed")


class IgnoredFileMutatingAdapter(FakeAdapter):
    def run(self, request: AgentRequest) -> AgentResult:
        (request.cwd / ".env").write_text("CHANGED=1\n")
        return super().run(request)


class EmptyDirectoryMutatingAdapter(FakeAdapter):
    def run(self, request: AgentRequest) -> AgentResult:
        (request.cwd / "unexpected-empty-directory").mkdir()
        return super().run(request)


class ActiveRunDeletingAdapter(FakeAdapter):
    def run(self, request: AgentRequest) -> AgentResult:
        shutil.rmtree(request.schema_path.parent)
        return super().run(request)


class ActiveRunSymlinkAdapter(FakeAdapter):
    def __init__(self, payload: dict, outside: Path) -> None:
        super().__init__(payload)
        self.outside = outside

    def run(self, request: AgentRequest) -> AgentResult:
        shutil.rmtree(request.schema_path.parent)
        self.outside.mkdir()
        os.symlink(self.outside, request.schema_path.parent)
        return super().run(request)


def test_review_writes_auditable_result(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    result, store = review_repository(
        repo,
        "change value",
        FakeAdapter({"verdict": "approve", "summary": "clean", "findings": []}),
    )
    assert result.verdict is Verdict.APPROVE
    assert json.loads((store.path / "review.json").read_text())["verdict"] == "approve"
    assert json.loads((store.path / "state.json").read_text())["status"] == "approve"


def test_reviewer_mutation_fails_without_reverting(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    with pytest.raises(ReviewerMutationError):
        review_repository(
            repo,
            "change value",
            FakeAdapter(
                {"verdict": "approve", "summary": "clean", "findings": []},
                mutate=True,
            ),
        )
    assert (repo / "file.py").read_text() == "mutated = True\n"


def test_provider_failure_becomes_blocked_result(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    result, store = review_repository(repo, "change value", FailingAdapter({}))
    state = json.loads((store.path / "state.json").read_text())
    assert result.verdict is Verdict.BLOCKED
    assert state["status"] == "blocked"
    assert state["reason"] == "provider failed"
    assert json.loads((store.path / "review.json").read_text())["verdict"] == "blocked"


def test_malformed_output_becomes_blocked_result(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    result, store = review_repository(repo, "change value", FakeAdapter({}))
    assert result.verdict is Verdict.BLOCKED
    assert json.loads((store.path / "state.json").read_text())["status"] == "blocked"


def test_reviewer_mutation_of_ignored_file_is_detected(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    (repo / ".gitignore").write_text(".env\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore env")
    (repo / ".env").write_text("ORIGINAL=1\n")
    with pytest.raises(ReviewerMutationError):
        review_repository(
            repo,
            "change value",
            IgnoredFileMutatingAdapter(
                {"verdict": "approve", "summary": "clean", "findings": []}
            ),
        )
    assert (repo / ".env").read_text() == "CHANGED=1\n"


def test_reviewer_creation_of_empty_directory_is_detected(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    with pytest.raises(ReviewerMutationError):
        review_repository(
            repo,
            "change value",
            EmptyDirectoryMutatingAdapter(
                {"verdict": "approve", "summary": "clean", "findings": []}
            ),
        )
    assert (repo / "unexpected-empty-directory").is_dir()


def test_active_run_deletion_uses_recovery_artifact(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    with pytest.raises(ReviewerMutationError, match="recovery artifact"):
        review_repository(
            repo,
            "change value",
            ActiveRunDeletingAdapter(
                {"verdict": "approve", "summary": "clean", "findings": []}
            ),
        )
    recovery = list(repo.glob(".airlock-recovery-*.json"))
    assert len(recovery) == 1
    assert json.loads(recovery[0].read_text())["status"] == "failed"


def test_active_run_symlink_never_writes_outside_repository(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = repository(repo_path)
    outside = tmp_path / "outside"
    with pytest.raises(ReviewerMutationError, match="recovery artifact"):
        review_repository(
            repo,
            "change value",
            ActiveRunSymlinkAdapter(
                {"verdict": "approve", "summary": "clean", "findings": []},
                outside,
            ),
        )
    assert not (outside / "state.json").exists()
    assert len(list(repo.glob(".airlock-recovery-*.json"))) == 1
