import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from airlock.adapters.base import AgentAdapter
from airlock.models import (
    AgentRequest,
    AgentResult,
    Finding,
    ReviewResult,
    Severity,
    Verdict,
)
from airlock.review import (
    ReviewerMutationError,
    build_prompt,
    render_review_markdown,
    review_repository,
)


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
        self.request = request
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


class RevisionMutatingAdapter(FakeAdapter):
    def run(self, request: AgentRequest) -> AgentResult:
        git(request.cwd, "commit", "--allow-empty", "-qm", "reviewer mutation")
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
    assert "### 合理" in (store.path / "review.md").read_text()


def test_readable_review_groups_reasonable_findings_and_suggestions() -> None:
    result = ReviewResult(
        Verdict.REJECT,
        "one issue",
        (Finding(Severity.HIGH, "state leaks", "file.py", 2, "restore state"),),
        ("tests cover the main path",),
    )

    report = render_review_markdown(
        "fix state",
        result,
        round_number=2,
        prior_review=result,
    )

    assert "## 第 2 轮" in report
    assert "上一轮结构化审查结果" in report
    assert "tests cover the main path" in report
    assert "state leaks" in report
    assert "restore state" in report


def test_configured_test_gate_writes_evidence_and_reaches_reviewer(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    config = repo / ".airlock" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        f'[gates.tests]\ncommand = ["{sys.executable}", "-c", "print(123)"]\n'
    )
    adapter = FakeAdapter(
        {"verdict": "approve", "summary": "clean", "findings": []}
    )
    result, store = review_repository(repo, "change value", adapter)
    evidence = json.loads((store.path / "test-result.json").read_text())
    assert result.verdict is Verdict.APPROVE
    assert evidence["passed"] is True
    assert "123" in evidence["stdout"]
    assert "Test gate evidence" in adapter.request.prompt
    assert "123" in adapter.request.prompt


def test_failed_test_gate_overrides_false_approval(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    config = repo / ".airlock" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        f'[gates.tests]\ncommand = ["{sys.executable}", "-c", "raise SystemExit(4)"]\n'
    )
    result, store = review_repository(
        repo,
        "change value",
        FakeAdapter({"verdict": "approve", "summary": "clean", "findings": []}),
    )
    assert result.verdict is Verdict.REJECT
    assert result.findings[0].severity.value == "high"
    assert json.loads((store.path / "state.json").read_text())["status"] == "reject"


def test_test_infrastructure_failure_overrides_false_approval(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    config = repo / ".airlock" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        '[gates.tests]\ncommand = ["airlock-command-that-does-not-exist"]\n'
    )
    result, _ = review_repository(
        repo,
        "change value",
        FakeAdapter({"verdict": "approve", "summary": "clean", "findings": []}),
    )
    assert result.verdict is Verdict.BLOCKED


def test_malformed_test_gate_config_is_auditable_blocked_result(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    config = repo / ".airlock" / "config.toml"
    config.parent.mkdir()
    config.write_text('[gates.tests]\ncommand = "pytest"\n')
    adapter = FakeAdapter(
        {"verdict": "approve", "summary": "clean", "findings": []}
    )
    result, store = review_repository(repo, "change value", adapter)
    assert result.verdict is Verdict.BLOCKED
    assert not hasattr(adapter, "request")
    assert (store.path / "task.md").exists()
    assert (store.path / "diff.patch").exists()
    assert json.loads((store.path / "review.json").read_text())["verdict"] == "blocked"
    assert json.loads((store.path / "state.json").read_text())["status"] == "blocked"


def test_non_utf8_test_gate_config_is_auditable_blocked_result(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    config = repo / ".airlock" / "config.toml"
    config.parent.mkdir()
    config.write_bytes(b"\xff\xfe")
    adapter = FakeAdapter(
        {"verdict": "approve", "summary": "clean", "findings": []}
    )
    result, store = review_repository(repo, "change value", adapter)
    assert result.verdict is Verdict.BLOCKED
    assert not hasattr(adapter, "request")
    assert json.loads((store.path / "review.json").read_text())["verdict"] == "blocked"
    assert json.loads((store.path / "state.json").read_text())["status"] == "blocked"


def test_oversized_test_gate_config_is_auditable_blocked_result(
    tmp_path: Path,
) -> None:
    from airlock.test_gate import MAX_CONFIG_BYTES

    repo = repository(tmp_path)
    config = repo / ".airlock" / "config.toml"
    config.parent.mkdir()
    config.write_bytes(b"#" * (MAX_CONFIG_BYTES + 1))
    adapter = FakeAdapter(
        {"verdict": "approve", "summary": "clean", "findings": []}
    )
    result, store = review_repository(repo, "change value", adapter)
    assert result.verdict is Verdict.BLOCKED
    assert not hasattr(adapter, "request")
    assert json.loads((store.path / "review.json").read_text())["verdict"] == "blocked"
    assert json.loads((store.path / "state.json").read_text())["status"] == "blocked"


def test_test_gate_workspace_mutation_blocks_review(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    config = repo / ".airlock" / "config.toml"
    config.parent.mkdir()
    code = "from pathlib import Path; Path('file.py').write_text('changed by tests' + chr(10))"
    config.write_text(
        f'[gates.tests]\ncommand = ["{sys.executable}", "-c", "{code}"]\n'
    )
    adapter = FakeAdapter(
        {"verdict": "approve", "summary": "clean", "findings": []}
    )
    result, store = review_repository(repo, "change value", adapter)
    assert result.verdict is Verdict.BLOCKED
    assert not hasattr(adapter, "request")
    assert (repo / "file.py").read_text() == "changed by tests\n"
    state = json.loads((store.path / "state.json").read_text())
    assert state["reason"] == "test gate mutated the workspace"


def test_test_gate_empty_commit_blocks_review(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    config = repo / ".airlock" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        '[gates.tests]\ncommand = ["git", "commit", "--allow-empty", "-m", "gate"]\n'
    )
    adapter = FakeAdapter(
        {"verdict": "approve", "summary": "clean", "findings": []}
    )
    result, store = review_repository(repo, "change value", adapter)
    assert result.verdict is Verdict.BLOCKED
    assert not hasattr(adapter, "request")
    state = json.loads((store.path / "state.json").read_text())
    assert state["reason"] == "test gate mutated the workspace"


def test_test_gate_active_run_deletion_uses_blocked_recovery(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    deleter = repo / "delete-run.py"
    deleter.write_text(
        "import shutil\n"
        "from pathlib import Path\n"
        "for path in Path('.airlock/runs').iterdir():\n"
        "    Path(f'.airlock-recovery-{path.name}.json').write_text('occupied')\n"
        "    shutil.rmtree(path)\n"
    )
    config = repo / ".airlock" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        f'[gates.tests]\ncommand = ["{sys.executable}", "{deleter}"]\n'
    )
    adapter = FakeAdapter(
        {"verdict": "approve", "summary": "clean", "findings": []}
    )
    result, store = review_repository(repo, "change value", adapter)
    assert result.verdict is Verdict.BLOCKED
    assert not hasattr(adapter, "request")
    assert store.recovery_path is not None
    assert store.artifact_path == store.recovery_path
    recovery = json.loads(store.recovery_path.read_text())
    assert recovery["state"]["status"] == "blocked"
    assert recovery["review"]["verdict"] == "blocked"
    assert recovery["test_result"]["exit_code"] == 0
    predictable = repo / f".airlock-recovery-{store.run_id}.json"
    assert predictable.read_text() == "occupied"
    assert store.recovery_path != predictable


def test_prompt_marks_absent_test_gate() -> None:
    assert "No test gate was configured" in build_prompt("task", "diff")


def test_repair_verification_prompt_allows_reverted_rejected_change() -> None:
    prior = ReviewResult(
        Verdict.REJECT,
        "regression",
        (
            Finding(
                Severity.HIGH,
                "addition became subtraction",
                "calc.py",
                2,
                "restore addition",
            ),
        ),
    )
    prompt = build_prompt("restore add", "(no tracked diff)\n", prior_review=prior)
    assert "repair verification" in prompt
    assert "same original task" in prompt
    assert "restore add" in prompt
    assert "reverted a rejected change back to HEAD" in prompt
    assert "addition became subtraction" in prompt


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


def test_reviewer_revision_mutation_is_detected(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    with pytest.raises(ReviewerMutationError):
        review_repository(
            repo,
            "change value",
            RevisionMutatingAdapter(
                {"verdict": "approve", "summary": "clean", "findings": []}
            ),
        )
    assert subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() != before


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
