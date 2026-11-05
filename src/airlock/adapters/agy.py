"""Antigravity CLI with isolated, explicitly bounded agent toolsets."""

from __future__ import annotations

import json
import shlex
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from airlock.adapters.base import AgentAdapter, ProviderError
from airlock.models import AgentMode, AgentRequest, AgentResult


class _Invocation(AgentAdapter):
    executable = "agy"

    def __init__(self, command: list[str]) -> None:
        self._command = command

    def command(self, request: AgentRequest) -> list[str]:
        return self._command


class AgyAdapter(AgentAdapter):
    executable = "agy"

    def command(self, request: AgentRequest) -> list[str]:
        command = [
            self.executable,
            f"--print=Target repository: {request.cwd.resolve()}\n\n{request.prompt}",
            "--output-format", "json",
            "--disable-slash-commands",
            "--sandbox",
            "--add-dir", str(request.cwd.resolve()),
            "--print-timeout", f"{request.timeout_seconds:g}s",
        ]
        if request.mode is AgentMode.READ:
            if request.schema_path is None:
                raise ValueError("read mode requires an output schema")
            command.extend(["--json-schema", str(request.schema_path.resolve())])
        else:
            command.extend(["--mode", "accept-edits"])
        return command

    def run(self, request: AgentRequest) -> AgentResult:
        command = self.command(request)
        writing = request.mode is AgentMode.WRITE
        # Do not install agents or alter provider permissions in the user's repository.
        with tempfile.TemporaryDirectory(prefix="airlock-agy-") as directory:
            launch_path = Path(directory)
            customizations = launch_path / ".agents"
            customizations.mkdir()
            policy = launch_path / "gate.py"
            policy.write_text(Path(__file__).with_name("agy_gate.py").read_text(encoding="utf-8"),
                              encoding="utf-8")
            config = launch_path / "gate-config.json"
            config.write_text(json.dumps({"root": str(request.cwd.resolve()), "writing": writing}),
                              encoding="utf-8")
            gate = shlex.join([sys.executable, str(policy), str(config)])
            hooks = {"airlock-capability-gate": {
                "PreInvocation": [{"type": "command", "command": gate + " activate", "timeout": 5}],
                "PreToolUse": [{"matcher": "*", "hooks": [
                    {"type": "command", "command": gate + " check", "timeout": 5},
                ]}],
            }}
            (customizations / "hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
            invocation = replace(
                request,
                cwd=launch_path,
                prompt=f"Target repository: {request.cwd.resolve()}\n\n{request.prompt}",
            )
            result = _Invocation(command).run(invocation)
            gate_active = (launch_path / "gate-active").is_file()
            gate_denied = (launch_path / "gate-denied").is_file()
            denied_tool = ((launch_path / "gate-denied").read_text(encoding="utf-8")
                           if gate_denied else "")
        try:
            if not gate_active:
                raise ValueError("agy did not activate the Airlock capability hook")
            if gate_denied:
                raise ValueError(f"agy attempted a forbidden tool operation: {denied_tool}")
            envelope = json.loads(result.output)
            if not isinstance(envelope, dict) or envelope.get("status") != "SUCCESS":
                raise ValueError("agy did not return a SUCCESS result")
            if envelope.get("error"):
                raise ValueError("agy returned a provider error")
            if writing:
                if not isinstance(envelope.get("response"), str) or not envelope["response"].strip():
                    raise ValueError("agy returned an empty repair response")
            elif not isinstance(envelope.get("structured_output"), dict):
                raise ValueError("agy did not return a structured review")
        except (ValueError, TypeError) as exc:
            raise ProviderError(
                f"invalid agy output: {exc}",
                {
                    "command": list(result.command), "exit_code": result.exit_code,
                    "duration_seconds": result.duration_seconds, "timed_out": False,
                    "stderr": result.stderr, "output": result.output, "error": str(exc),
                },
            ) from exc
        return result
