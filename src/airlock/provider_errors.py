"""Conservative provider failure classification for bounded retries."""

from __future__ import annotations

import re
from enum import Enum

from airlock.adapters.base import ProviderError


class ProviderErrorKind(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


_PERMANENT_PROVIDER_MARKERS = (
    "authentication",
    "authorization",
    "unauthorized",
    "forbidden",
    "permission denied",
    "access denied",
    "invalid api key",
    "invalid token",
    "schema",
    "invalid json",
)
_CONNECTION_INTERRUPTION_MARKERS = (
    "connection aborted",
    "connection closed",
    "connection interrupted",
    "connection refused",
    "connection reset",
    "connection terminated",
    "broken pipe",
    "remote end closed",
    "server disconnected",
    "network connection was lost",
)
_RETRYABLE_HTTP_STATUS = re.compile(
    r"\b(?:http(?:/\d(?:\.\d)?)?|status(?:\s+code)?|response)\D{0,20}(429|502|503)\b",
    re.IGNORECASE,
)


def classify_provider_error(
    error: BaseException,
) -> tuple[ProviderErrorKind, str]:
    """Classify conservatively: only an explicit retry allowlist is transient."""
    if not isinstance(error, ProviderError):
        return ProviderErrorKind.PERMANENT, "unclassified"
    evidence = error.evidence
    if evidence.get("timed_out") is True:
        return ProviderErrorKind.PERMANENT, "timeout"
    detail = "\n".join(
        str(value)
        for value in (
            str(error),
            evidence.get("error", ""),
            evidence.get("stderr", ""),
            evidence.get("output", ""),
        )
        if value
    ).lower()
    if any(marker in detail for marker in _PERMANENT_PROVIDER_MARKERS):
        return ProviderErrorKind.PERMANENT, "authentication_or_permission_or_schema"
    status = _RETRYABLE_HTTP_STATUS.search(detail)
    if status is not None:
        return ProviderErrorKind.TRANSIENT, f"http_{status.group(1)}"
    if any(marker in detail for marker in _CONNECTION_INTERRUPTION_MARKERS):
        return ProviderErrorKind.TRANSIENT, "connection_interrupted"
    return ProviderErrorKind.PERMANENT, "unclassified"
