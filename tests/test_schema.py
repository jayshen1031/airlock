import json

from airlock.models import Verdict
from airlock.schema import REVIEW_SCHEMA, parse_review_json


def test_provider_schema_uses_portable_subset() -> None:
    assert "$schema" not in REVIEW_SCHEMA


def test_every_object_schema_requires_all_properties_for_codex_strict_mode() -> None:
    def visit(schema: object) -> None:
        if isinstance(schema, dict):
            properties = schema.get("properties")
            if isinstance(properties, dict):
                assert set(schema.get("required", [])) == set(properties)
            for value in schema.values():
                visit(value)
        elif isinstance(schema, list):
            for value in schema:
                visit(value)

    visit(REVIEW_SCHEMA)


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
