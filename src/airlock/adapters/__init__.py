"""Provider adapter registry."""

from airlock.adapters.base import AgentAdapter, ProviderError
from airlock.adapters.claude import ClaudeAdapter
from airlock.adapters.codex import CodexAdapter

__all__ = ["AgentAdapter", "ClaudeAdapter", "CodexAdapter", "ProviderError"]
