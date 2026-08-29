"""Read-only Claude Code CLI adapter."""

from __future__ import annotations

import json

from airlock.adapters.base import AgentAdapter
from airlock.models import AgentMode, AgentRequest


class ClaudeAdapter(AgentAdapter):
    executable = "claude"

    def command(self, request: AgentRequest) -> list[str]:
        if request.mode is AgentMode.WRITE:
            return [
                self.executable,
                "--print",
                "--output-format",
                "text",
                "--permission-mode",
                "acceptEdits",
                "--tools",
                "Read,Glob,Grep,Edit,Write",
                "--no-session-persistence",
            ]
        if request.schema_path is None:
            raise ValueError("read mode requires an output schema")
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
