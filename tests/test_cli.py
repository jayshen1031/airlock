from pathlib import Path

import pytest

from airlock import cli
from airlock.models import ReviewResult, Verdict


class Store:
    path = Path("/tmp/airlock-test-run")
    artifact_path = path


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        (Verdict.APPROVE, cli.EXIT_APPROVED),
        (Verdict.REJECT, cli.EXIT_REJECTED),
        (Verdict.BLOCKED, cli.EXIT_BLOCKED),
    ],
)
def test_cli_exit_codes(monkeypatch, verdict: Verdict, expected: int) -> None:
    findings = ()
    if verdict is Verdict.REJECT:
        from airlock.models import Finding, Severity

        findings = (Finding(Severity.HIGH, "broken"),)
    monkeypatch.setattr(
        cli,
        "review_repository",
        lambda **kwargs: (ReviewResult(verdict, "summary", findings), Store()),
    )
    assert cli.main(["review", "--reviewer", "codex"]) == expected


def test_cli_prints_recovery_artifact(monkeypatch, capsys, tmp_path: Path) -> None:
    recovery = tmp_path / ".airlock-recovery-random.json"

    class RecoveryStore:
        artifact_path = recovery

    monkeypatch.setattr(
        cli,
        "review_repository",
        lambda **kwargs: (
            ReviewResult(Verdict.BLOCKED, "recovered"),
            RecoveryStore(),
        ),
    )
    assert cli.main(["review", "--reviewer", "codex"]) == cli.EXIT_BLOCKED
    assert f"Artifacts: {recovery}" in capsys.readouterr().out
