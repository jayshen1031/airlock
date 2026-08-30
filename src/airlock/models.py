"""Validated domain models for review results and provider invocations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class Verdict(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    BLOCKED = "blocked"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AgentMode(str, Enum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    issue: str
    file: str | None = None
    line: int | None = None
    suggestion: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Finding:
        if not isinstance(value, dict):
            raise ValueError("each finding must be an object")
        required = {"severity", "file", "line", "issue", "suggestion"}
        if set(value) != required:
            raise ValueError(
                "finding must contain exactly severity, file, line, issue, and suggestion"
            )
        issue = value.get("issue")
        if not isinstance(issue, str) or not issue.strip():
            raise ValueError("finding.issue must be a non-empty string")
        try:
            severity = Severity(value.get("severity"))
        except ValueError as exc:
            raise ValueError(
                "finding.severity must be critical, high, medium, or low"
            ) from exc
        file = value.get("file")
        if file is not None and not isinstance(file, str):
            raise ValueError("finding.file must be a string or null")
        line = value.get("line")
        if line is not None and (
            isinstance(line, bool) or not isinstance(line, int) or line < 1
        ):
            raise ValueError("finding.line must be a positive integer or null")
        suggestion = value.get("suggestion")
        if suggestion is not None and not isinstance(suggestion, str):
            raise ValueError("finding.suggestion must be a string or null")
        return cls(
            severity=severity,
            issue=issue.strip(),
            file=file,
            line=line,
            suggestion=suggestion,
        )


@dataclass(frozen=True)
class ReviewResult:
    verdict: Verdict
    summary: str
    findings: tuple[Finding, ...] = ()
    reasonable: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ReviewResult:
        if not isinstance(value, dict):
            raise ValueError("review result must be an object")
        required = {"verdict", "summary", "findings"}
        allowed = required | {"reasonable"}
        if not required.issubset(value) or not set(value).issubset(allowed):
            raise ValueError(
                "review result must contain exactly verdict, summary, findings, "
                "and optional reasonable observations"
            )
        try:
            verdict = Verdict(value.get("verdict"))
        except ValueError as exc:
            raise ValueError("verdict must be approve, reject, or blocked") from exc
        summary = value.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("summary must be a non-empty string")
        raw_findings = value["findings"]
        if not isinstance(raw_findings, list):
            raise ValueError("findings must be an array")
        findings = tuple(Finding.from_dict(item) for item in raw_findings)
        if verdict is Verdict.REJECT and not findings:
            raise ValueError("reject verdict requires at least one finding")
        if verdict is Verdict.APPROVE and findings:
            raise ValueError("approve verdict cannot include findings")
        raw_reasonable = value.get("reasonable", [])
        if not isinstance(raw_reasonable, list) or any(
            not isinstance(item, str) or not item.strip() for item in raw_reasonable
        ):
            raise ValueError("reasonable must be an array of non-empty strings")
        reasonable = tuple(item.strip() for item in raw_reasonable)
        return cls(
            verdict=verdict,
            summary=summary.strip(),
            findings=findings,
            reasonable=reasonable,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "summary": self.summary,
            "reasonable": list(self.reasonable),
            "findings": [
                {
                    **asdict(finding),
                    "severity": finding.severity.value,
                }
                for finding in self.findings
            ],
        }


@dataclass(frozen=True)
class AgentRequest:
    prompt: str
    cwd: Path
    schema_path: Path | None
    timeout_seconds: float
    mode: AgentMode = AgentMode.READ


@dataclass(frozen=True)
class AgentResult:
    output: str
    stderr: str
    exit_code: int
    duration_seconds: float
    command: tuple[str, ...]
