import json
import subprocess
from pathlib import Path

from airlock.adapters.base import AgentAdapter, ProviderError
from airlock.models import (
    AgentMode,
    AgentRequest,
    AgentResult,
    Finding,
    ReviewResult,
    Severity,
    Verdict,
)
from airlock.repair import build_repair_prompt, repair_repository


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


def rejection(issue: str = "value is wrong") -> ReviewResult:
    return ReviewResult(
        Verdict.REJECT,
        issue,
        (Finding(Severity.HIGH, issue, "file.py", 1, "fix the value"),),
    )


def minor_rejection(issue: str = "minor naming issue") -> ReviewResult:
    return ReviewResult(
        Verdict.REJECT,
        issue,
        (Finding(Severity.LOW, issue, "file.py", 1, "consider a clearer name"),),
        ("the behavior is correct",),
    )


class ReviewStore:
    def __init__(self, path: Path) -> None:
        self.artifact_path = path


class FakeReviewer(AgentAdapter):
    executable = "reviewer"

    def __init__(self, results: list[ReviewResult]) -> None:
        self.results = results
        self.calls = 0

    def command(self, request: AgentRequest) -> list[str]:
        return ["reviewer"]


class FakeWriter(AgentAdapter):
    executable = "writer"

    def __init__(
        self,
        changes: list[str],
        commit: bool = False,
        tamper_artifacts: bool = False,
    ) -> None:
        self.changes = changes
        self.commit = commit
        self.tamper_artifacts = tamper_artifacts
        self.requests: list[AgentRequest] = []

    def command(self, request: AgentRequest) -> list[str]:
        return ["writer"]

    def run(self, request: AgentRequest) -> AgentResult:
        self.requests.append(request)
        if self.changes:
            (request.cwd / "file.py").write_text(self.changes.pop(0))
        if self.commit:
            git(request.cwd, "add", "file.py")
            git(request.cwd, "commit", "-qm", "forbidden writer commit")
        if self.tamper_artifacts:
            for state in (request.cwd / ".airlock" / "runs").glob("*/state.json"):
                state.write_text('{"status":"tampered"}\n')
        return AgentResult("fixed", "", 0, 0.1, ("writer",))


class FailingWriter(FakeWriter):
    def run(self, request: AgentRequest) -> AgentResult:
        if self.tamper_artifacts:
            for state in (request.cwd / ".airlock" / "runs").glob("*/state.json"):
                state.write_text('{"status":"tampered"}\n')
        raise ProviderError(
            "writer exited with 9",
            {
                "command": ["writer", "--fix"],
                "exit_code": 9,
                "duration_seconds": 1.25,
                "timed_out": False,
                "stderr": "failed",
                "output": "partial",
                "error": "writer exited with 9",
            },
        )


class CanceledWriter(FakeWriter):
    def run(self, request: AgentRequest) -> AgentResult:
        if self.tamper_artifacts:
            for state in (request.cwd / ".airlock" / "runs").glob("*/state.json"):
                state.write_text('{"status":"tampered"}\n')
        raise KeyboardInterrupt


class HistoricalTamperWriter(FakeWriter):
    def run(self, request: AgentRequest) -> AgentResult:
        result = super().run(request)
        if len(self.requests) == 2:
            (
                request.cwd
                / ".airlock"
                / "fake-reviews"
                / "review-1"
                / "evidence.json"
            ).write_text("tampered\n")
        return result


def install_reviews(monkeypatch, reviewer: FakeReviewer, tmp_path: Path) -> None:
    def fake_review_repository(**kwargs):
        result = reviewer.results[reviewer.calls]
        reviewer.calls += 1
        path = tmp_path / ".airlock" / "fake-reviews" / f"review-{reviewer.calls}"
        path.mkdir(parents=True)
        (path / "evidence.json").write_text(
            json.dumps(result.to_dict(), sort_keys=True)
        )
        return result, ReviewStore(path)

    monkeypatch.setattr("airlock.repair.review_repository", fake_review_repository)


def test_repair_hands_only_structured_findings_to_write_mode(
    monkeypatch, tmp_path: Path
) -> None:
    repo = repository(tmp_path)
    reviewer = FakeReviewer([rejection(), ReviewResult(Verdict.APPROVE, "clean")])
    writer = FakeWriter(["value = 3\n"])
    install_reviews(monkeypatch, reviewer, tmp_path)

    result, store = repair_repository(repo, "fix value", writer, reviewer, 2)

    assert result.verdict is Verdict.APPROVE
    assert len(writer.requests) == 1
    assert writer.requests[0].mode is AgentMode.WRITE
    assert writer.requests[0].schema_path is None
    assert '"issue": "value is wrong"' in writer.requests[0].prompt
    assert "reviewer conversation" in writer.requests[0].prompt
    state = json.loads((store.path / "state.json").read_text())
    assert state["status"] == "approved"
    assert (store.path / "iteration-01-writer.json").exists()
    assert (store.path / "iteration-02-review.json").exists()
    report = (store.path / "review-report.md").read_text()
    assert "## 原始输入" in report
    assert "## 第 1 轮" in report
    assert "## 第 2 轮" in report
    assert "### 合理" in report
    assert "### 不合理" in report
    assert "### 建议" in report
    assert "上一轮结构化审查结果" in report


def test_repair_stops_when_only_low_severity_findings_remain(
    monkeypatch, tmp_path: Path
) -> None:
    repo = repository(tmp_path)
    reviewer = FakeReviewer([minor_rejection()])
    writer = FakeWriter(["value = 3\n"])
    install_reviews(monkeypatch, reviewer, tmp_path)

    result, store = repair_repository(repo, "fix value", writer, reviewer, 3)

    assert result.verdict is Verdict.REJECT
    assert writer.requests == []
    state = json.loads((store.path / "state.json").read_text())
    assert state["status"] == "minor_findings"
    assert "human acceptance required" in state["reason"]
    report = (store.path / "review-report.md").read_text()
    assert "the behavior is correct" in report
    assert "minor naming issue" in report
    assert "consider a clearer name" in report


def test_repair_blocks_when_writer_makes_no_progress(monkeypatch, tmp_path: Path) -> None:
    repo = repository(tmp_path)
    reviewer = FakeReviewer([rejection()])
    writer = FakeWriter([])
    install_reviews(monkeypatch, reviewer, tmp_path)

    result, _ = repair_repository(repo, "fix value", writer, reviewer)

    assert result.verdict is Verdict.BLOCKED
    assert "no auditable progress" in result.summary


def test_repair_blocks_repeated_findings_before_second_write(
    monkeypatch, tmp_path: Path
) -> None:
    repo = repository(tmp_path)
    reviewer = FakeReviewer([rejection(), rejection()])
    writer = FakeWriter(["value = 3\n"])
    install_reviews(monkeypatch, reviewer, tmp_path)

    result, _ = repair_repository(repo, "fix value", writer, reviewer, 3)

    assert result.verdict is Verdict.BLOCKED
    assert "repeated the same findings" in result.summary
    assert len(writer.requests) == 1


def test_repair_stops_at_max_iterations(monkeypatch, tmp_path: Path) -> None:
    repo = repository(tmp_path)
    reviewer = FakeReviewer([rejection("first"), rejection("second")])
    writer = FakeWriter(["value = 3\n"])
    install_reviews(monkeypatch, reviewer, tmp_path)

    result, store = repair_repository(repo, "fix value", writer, reviewer, 1)

    assert result.verdict is Verdict.REJECT
    assert len(writer.requests) == 1
    assert json.loads((store.path / "state.json").read_text())["status"] == "exhausted"


def test_repair_blocks_writer_commit_without_reverting(monkeypatch, tmp_path: Path) -> None:
    repo = repository(tmp_path)
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    reviewer = FakeReviewer([rejection()])
    writer = FakeWriter(["value = 3\n"], commit=True)
    install_reviews(monkeypatch, reviewer, tmp_path)

    result, _ = repair_repository(repo, "fix value", writer, reviewer)

    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert result.verdict is Verdict.BLOCKED
    assert "revision identity" in result.summary
    assert after != before


def test_repair_detects_writer_artifact_tampering_and_uses_recovery(
    monkeypatch, tmp_path: Path
) -> None:
    repo = repository(tmp_path)
    reviewer = FakeReviewer([rejection()])
    writer = FakeWriter(["value = 3\n"], tamper_artifacts=True)
    install_reviews(monkeypatch, reviewer, tmp_path)

    result, store = repair_repository(repo, "fix value", writer, reviewer)

    assert result.verdict is Verdict.BLOCKED
    assert "protected Airlock artifacts" in result.summary
    assert store.recovery_path is not None
    recovery = json.loads(store.recovery_path.read_text())
    assert recovery["writer"]["exit_code"] == 0
    assert recovery["state"]["status"] == "blocked"


def test_repair_persists_failed_writer_invocation_evidence(
    monkeypatch, tmp_path: Path
) -> None:
    repo = repository(tmp_path)
    reviewer = FakeReviewer([rejection()])
    writer = FailingWriter([])
    install_reviews(monkeypatch, reviewer, tmp_path)

    result, store = repair_repository(repo, "fix value", writer, reviewer)

    assert result.verdict is Verdict.BLOCKED
    evidence = json.loads(
        (store.path / "iteration-01-writer.json").read_text()
    )
    assert evidence["command"] == ["writer", "--fix"]
    assert evidence["exit_code"] == 9
    assert evidence["duration_seconds"] == 1.25
    assert evidence["stderr"] == "failed"


def test_repair_failure_after_artifact_tampering_uses_recovery(
    monkeypatch, tmp_path: Path
) -> None:
    repo = repository(tmp_path)
    reviewer = FakeReviewer([rejection()])
    writer = FailingWriter([], tamper_artifacts=True)
    install_reviews(monkeypatch, reviewer, tmp_path)

    result, store = repair_repository(repo, "fix value", writer, reviewer)

    assert result.verdict is Verdict.BLOCKED
    assert "protected Airlock artifacts" in result.summary
    assert store.recovery_path is not None
    recovery = json.loads(store.recovery_path.read_text())
    assert recovery["writer"]["exit_code"] == 9


def test_repair_persists_writer_cancellation_evidence(
    monkeypatch, tmp_path: Path
) -> None:
    repo = repository(tmp_path)
    reviewer = FakeReviewer([rejection()])
    writer = CanceledWriter([])
    install_reviews(monkeypatch, reviewer, tmp_path)

    result, store = repair_repository(repo, "fix value", writer, reviewer)

    assert result.verdict is Verdict.BLOCKED
    evidence = json.loads(
        (store.path / "iteration-01-writer.json").read_text()
    )
    assert evidence["command"] == ["writer"]
    assert evidence["exit_code"] is None
    assert evidence["canceled"] is True
    assert json.loads((store.path / "state.json").read_text())["status"] == "canceled"


def test_repair_cancellation_after_artifact_tampering_uses_recovery(
    monkeypatch, tmp_path: Path
) -> None:
    repo = repository(tmp_path)
    reviewer = FakeReviewer([rejection()])
    writer = CanceledWriter([], tamper_artifacts=True)
    install_reviews(monkeypatch, reviewer, tmp_path)

    result, store = repair_repository(repo, "fix value", writer, reviewer)

    assert result.verdict is Verdict.BLOCKED
    assert store.recovery_path is not None
    recovery = json.loads(store.recovery_path.read_text())
    assert recovery["state"]["status"] == "canceled"
    assert recovery["writer"]["command"] == ["writer"]
    assert recovery["writer"]["canceled"] is True


def test_later_writer_cannot_tamper_with_earlier_reviewer_artifacts(
    monkeypatch, tmp_path: Path
) -> None:
    repo = repository(tmp_path)
    reviewer = FakeReviewer([rejection("first"), rejection("second")])
    writer = HistoricalTamperWriter(["value = 3\n", "value = 4\n"])
    install_reviews(monkeypatch, reviewer, tmp_path)

    result, store = repair_repository(repo, "fix value", writer, reviewer, 3)

    assert result.verdict is Verdict.BLOCKED
    assert "protected Airlock artifacts" in result.summary
    assert len(writer.requests) == 2
    assert store.recovery_path is not None
    recovery = json.loads(store.recovery_path.read_text())
    assert recovery["writer"]["exit_code"] == 0


def test_repair_prompt_forbids_git_side_effects() -> None:
    prompt = build_repair_prompt("task", rejection())
    for operation in ("commit", "push", "merge", "reset", "checkout"):
        assert operation in prompt
