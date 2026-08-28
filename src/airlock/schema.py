"""JSON schema and strict parsing for reviewer output."""

from __future__ import annotations

import json
from typing import Any

from airlock.models import ReviewResult


REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "summary", "findings"],
    "properties": {
        "verdict": {"type": "string", "enum": ["approve", "reject", "blocked"]},
        "summary": {"type": "string", "minLength": 1},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "severity",
                    "file",
                    "line",
                    "issue",
                    "suggestion",
                ],
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                    },
                    "file": {"type": ["string", "null"]},
                    "line": {"type": ["integer", "null"], "minimum": 1},
                    "issue": {"type": "string", "minLength": 1},
                    "suggestion": {"type": ["string", "null"]},
                },
            },
        },
    },
}


def parse_review_json(output: str) -> ReviewResult:
    """Parse a provider's final JSON, tolerating Claude's JSON envelope."""
    try:
        value = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError(f"reviewer returned invalid JSON: {exc.msg}") from exc

    if isinstance(value, dict) and "structured_output" in value:
        value = value["structured_output"]
    elif isinstance(value, dict) and set(value) != {
        "verdict",
        "summary",
        "findings",
    }:
        result = value.get("result")
        if isinstance(result, str):
            try:
                value = json.loads(result)
            except json.JSONDecodeError:
                pass
    return ReviewResult.from_dict(value)
