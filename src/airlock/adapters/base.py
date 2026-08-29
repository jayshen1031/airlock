"""Minimal subprocess adapter contract."""

from __future__ import annotations

import shutil
import subprocess
import time
from abc import ABC, abstractmethod

from airlock.models import AgentRequest, AgentResult


class ProviderError(RuntimeError):
    def __init__(self, message: str, evidence: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.evidence = evidence or {"error": message}


class AgentAdapter(ABC):
    executable: str

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    @abstractmethod
    def command(self, request: AgentRequest) -> list[str]:
        raise NotImplementedError

    def run(self, request: AgentRequest) -> AgentResult:
        if not self.available():
            message = f"provider executable not found: {self.executable}"
            raise ProviderError(
                message,
                {
                    "command": [self.executable],
                    "exit_code": None,
                    "duration_seconds": 0.0,
                    "timed_out": False,
                    "stderr": "",
                    "output": "",
                    "error": message,
                },
            )
        command = self.command(request)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=request.cwd,
                input=request.prompt,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=request.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - started
            message = f"{self.executable} timed out after {request.timeout_seconds:g}s"
            raise ProviderError(
                message,
                {
                    "command": command,
                    "exit_code": None,
                    "duration_seconds": duration,
                    "timed_out": True,
                    "stderr": exc.stderr or "",
                    "output": exc.stdout or "",
                    "error": message,
                },
            ) from exc
        duration = time.monotonic() - started
        result = AgentResult(
            output=completed.stdout.strip(),
            stderr=completed.stderr,
            exit_code=completed.returncode,
            duration_seconds=duration,
            command=tuple(command),
        )
        if result.exit_code != 0:
            detail = result.stderr.strip() or result.output or "no provider output"
            message = f"{self.executable} exited with {result.exit_code}: {detail}"
            raise ProviderError(
                message,
                {
                    "command": list(result.command),
                    "exit_code": result.exit_code,
                    "duration_seconds": result.duration_seconds,
                    "timed_out": False,
                    "stderr": result.stderr,
                    "output": result.output,
                    "error": message,
                },
            )
        return result
