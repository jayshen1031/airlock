"""Minimal subprocess adapter contract."""

from __future__ import annotations

import shutil
import subprocess
import time
from abc import ABC, abstractmethod

from airlock.models import AgentRequest, AgentResult


class ProviderError(RuntimeError):
    pass


class AgentAdapter(ABC):
    executable: str

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    @abstractmethod
    def command(self, request: AgentRequest) -> list[str]:
        raise NotImplementedError

    def run(self, request: AgentRequest) -> AgentResult:
        if not self.available():
            raise ProviderError(f"provider executable not found: {self.executable}")
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
            raise ProviderError(
                f"{self.executable} timed out after {request.timeout_seconds:g}s"
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
            raise ProviderError(
                f"{self.executable} exited with {result.exit_code}: {detail}"
            )
        return result
