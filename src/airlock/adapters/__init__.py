"""Provider adapter registry."""

from airlock.adapters.base import AgentAdapter, ProviderError
from airlock.adapters.agy import AgyAdapter
from airlock.adapters.claude import ClaudeAdapter
from airlock.adapters.codex import CodexAdapter
from airlock.provider_errors import ProviderErrorKind

__all__ = [
    "AgentAdapter",
    "AgyAdapter",
    "ClaudeAdapter",
    "CodexAdapter",
    "ProviderError",
    "ProviderErrorKind",
]
