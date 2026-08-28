from pathlib import Path

import pytest

from airlock import cli
from airlock.models import ReviewResult, Verdict


class Store:
    path = Path("/tmp/airlock-test-run")


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
