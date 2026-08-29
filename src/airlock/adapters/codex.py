"""Read-only Codex CLI adapter."""

from __future__ import annotations

from airlock.adapters.base import AgentAdapter
from airlock.models import AgentMode, AgentRequest


class CodexAdapter(AgentAdapter):
    executable = "codex"

    def command(self, request: AgentRequest) -> list[str]:
        sandbox = "workspace-write" if request.mode is AgentMode.WRITE else "read-only"
        command = [
            self.executable,
            "exec",
            "--sandbox",
            sandbox,
            "--ephemeral",
            "--cd",
            str(request.cwd),
        ]
        if request.mode is AgentMode.READ:
            if request.schema_path is None:
                raise ValueError("read mode requires an output schema")
            command.extend(["--output-schema", str(request.schema_path)])
        command.append("-")
        return command
