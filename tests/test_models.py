import pytest

from airlock.models import ReviewResult, Verdict


def test_reject_requires_finding() -> None:
    with pytest.raises(ValueError, match="requires at least one"):
        ReviewResult.from_dict(
            {"verdict": "reject", "summary": "problem", "findings": []}
        )


def test_valid_result_round_trip() -> None:
    result = ReviewResult.from_dict(
        {
            "verdict": "reject",
            "summary": "one issue",
            "findings": [
                {
                    "severity": "high",
                    "file": "src/example.py",
                    "line": 4,
                    "issue": "state is not restored",
                    "suggestion": "restore state in a finally block",
                }
            ],
        }
    )
    assert result.verdict is Verdict.REJECT
    assert result.to_dict()["findings"][0]["severity"] == "high"


@pytest.mark.parametrize(
    "payload",
    [
        {"verdict": "approve", "summary": "clean"},
        {
            "verdict": "approve",
            "summary": "clean",
            "findings": [],
            "unexpected": True,
        },
        {
            "verdict": "reject",
            "summary": "problem",
            "findings": [{"severity": "high", "issue": "missing fields"}],
        },
    ],
)
def test_schema_required_and_additional_properties_are_enforced(payload) -> None:
    with pytest.raises(ValueError, match="exactly"):
        ReviewResult.from_dict(payload)


@pytest.mark.parametrize("line", [True, False])
def test_boolean_is_not_a_valid_line_number(line: bool) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        ReviewResult.from_dict(
            {
                "verdict": "reject",
                "summary": "problem",
                "findings": [
                    {
                        "severity": "high",
                        "file": "example.py",
                        "line": line,
                        "issue": "bad line",
                        "suggestion": None,
                    }
                ],
            }
        )
