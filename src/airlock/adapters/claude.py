"""Read-only Claude Code CLI adapter."""

from __future__ import annotations

import json

from airlock.adapters.base import AgentAdapter
from airlock.models import AgentRequest


class ClaudeAdapter(AgentAdapter):
    executable = "claude"

    def command(self, request: AgentRequest) -> list[str]:
        schema = json.loads(request.schema_path.read_text(encoding="utf-8"))
        return [
            self.executable,
            "--print",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema, separators=(",", ":")),
            "--permission-mode",
            "dontAsk",
            "--tools",
            "Read,Glob,Grep",
            "--no-session-persistence",
        ]
