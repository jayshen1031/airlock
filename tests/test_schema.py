import json

from airlock.models import Verdict
from airlock.schema import REVIEW_SCHEMA, parse_review_json


def test_provider_schema_uses_portable_subset() -> None:
    assert "$schema" not in REVIEW_SCHEMA


def test_parse_plain_result() -> None:
    result = parse_review_json(
        json.dumps(
            {"verdict": "approve", "summary": "clean", "findings": []}
        )
    )
    assert result.verdict is Verdict.APPROVE


def test_parse_claude_structured_output_envelope() -> None:
    result = parse_review_json(
        json.dumps(
            {
                "type": "result",
                "structured_output": {
                    "verdict": "blocked",
                    "summary": "missing evidence",
                    "findings": [],
                },
            }
        )
    )
    assert result.verdict is Verdict.BLOCKED
