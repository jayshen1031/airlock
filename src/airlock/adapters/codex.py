"""Read-only Codex CLI adapter."""

from __future__ import annotations

from airlock.adapters.base import AgentAdapter
from airlock.models import AgentRequest


class CodexAdapter(AgentAdapter):
    executable = "codex"

    def command(self, request: AgentRequest) -> list[str]:
        return [
            self.executable,
            "exec",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--output-schema",
            str(request.schema_path),
            "--cd",
            str(request.cwd),
            "-",
        ]
