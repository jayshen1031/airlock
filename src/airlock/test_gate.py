"""Configured, bounded repository test gate."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import threading
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO


CONFIG_PATH = Path(".airlock/config.toml")
MAX_CONFIG_BYTES = 65_536
DEFAULT_TIMEOUT_SECONDS = 300.0
MAX_TIMEOUT_SECONDS = 3_600.0
MAX_CAPTURE_CHARS = 20_000
TERMINATION_GRACE_SECONDS = 1.0


class TestGateConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TestGateConfig:
    command: tuple[str, ...]
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class TestResult:
    command: tuple[str, ...]
    exit_code: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str | None = None
    output_truncated: bool = False

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and self.error is None

    @property
    def infrastructure_failure(self) -> bool:
        return self.timed_out or self.error is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
            "passed": self.passed,
            "timed_out": self.timed_out,
            "error": self.error,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "output_truncated": self.output_truncated,
        }


def load_test_gate(repository: Path) -> TestGateConfig | None:
    path = repository / CONFIG_PATH
    if not path.exists():
        return None
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_CONFIG_BYTES + 1)
        if len(raw) > MAX_CONFIG_BYTES:
            raise TestGateConfigError(
                f"{CONFIG_PATH} exceeds the {MAX_CONFIG_BYTES}-byte limit"
            )
        document = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise TestGateConfigError(f"cannot read {CONFIG_PATH}: {exc}") from exc
    try:
        tests = document["gates"]["tests"]
    except (KeyError, TypeError) as exc:
        raise TestGateConfigError(
            f"{CONFIG_PATH} must define [gates.tests]"
        ) from exc
    if not isinstance(tests, dict):
        raise TestGateConfigError(f"{CONFIG_PATH} [gates.tests] must be a table")
    unknown = set(tests) - {"command", "timeout_seconds"}
    if unknown:
        raise TestGateConfigError(
            f"{CONFIG_PATH} [gates.tests] has unknown keys: {', '.join(sorted(unknown))}"
        )
    command = tests.get("command")
    if (
        not isinstance(command, list)
        or not command
        or any(
            not isinstance(part, str) or not part or "\0" in part
            for part in command
        )
    ):
        raise TestGateConfigError(
            f"{CONFIG_PATH} gates.tests.command must be a non-empty string array without NUL characters"
        )
    timeout = tests.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
        or timeout > MAX_TIMEOUT_SECONDS
    ):
        raise TestGateConfigError(
            f"{CONFIG_PATH} gates.tests.timeout_seconds must be between 0 and {MAX_TIMEOUT_SECONDS}"
        )
    return TestGateConfig(tuple(command), float(timeout))


def _drain_stream(stream: TextIO, capture: list[str], stats: dict[str, int]) -> None:
    captured = 0
    total = 0
    try:
        while chunk := stream.read(8192):
            total += len(chunk)
            remaining = MAX_CAPTURE_CHARS - captured
            if remaining > 0:
                kept = chunk[:remaining]
                capture.append(kept)
                captured += len(kept)
    except (OSError, ValueError):
        pass
    finally:
        stats["total"] = total


def _captured_output(capture: list[str], stats: dict[str, int]) -> tuple[str, bool]:
    value = "".join(capture)
    if stats.get("total", len(value)) <= MAX_CAPTURE_CHARS:
        return value, False
    return value + f"\n...[truncated at {MAX_CAPTURE_CHARS} characters]", True


def _stop_process(process: subprocess.Popen[str]) -> None:
    if os.name != "posix":
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            process.wait()
        return

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (PermissionError, ProcessLookupError):
        return
    time.sleep(TERMINATION_GRACE_SECONDS)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (PermissionError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_test_gate(repository: Path, config: TestGateConfig) -> TestResult:
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            config.command,
            cwd=repository,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            start_new_session=os.name == "posix",
        )
    except (OSError, ValueError) as exc:
        return TestResult(
            command=config.command,
            exit_code=None,
            duration_seconds=time.monotonic() - started,
            stdout="",
            stderr="",
            error=str(exc),
        )
    assert process.stdout is not None and process.stderr is not None
    stdout_capture: list[str] = []
    stderr_capture: list[str] = []
    stdout_stats: dict[str, int] = {}
    stderr_stats: dict[str, int] = {}
    readers = (
        threading.Thread(
            target=_drain_stream,
            args=(process.stdout, stdout_capture, stdout_stats),
            daemon=True,
        ),
        threading.Thread(
            target=_drain_stream,
            args=(process.stderr, stderr_capture, stderr_stats),
            daemon=True,
        ),
    )
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        process.wait(timeout=config.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _stop_process(process)
    else:
        if os.name == "posix":
            _stop_process(process)
    capture_error = None
    streams = (process.stdout, process.stderr)
    for reader in readers:
        reader.join(timeout=TERMINATION_GRACE_SECONDS)
    if any(reader.is_alive() for reader in readers) and os.name != "posix":
        _stop_process(process)
        for reader in readers:
            reader.join(timeout=TERMINATION_GRACE_SECONDS)
    for reader, stream in zip(readers, streams, strict=True):
        if reader.is_alive():
            capture_error = "test process left an output pipe open after termination"
        else:
            stream.close()
    stdout, stdout_truncated = _captured_output(stdout_capture, stdout_stats)
    stderr, stderr_truncated = _captured_output(stderr_capture, stderr_stats)
    return TestResult(
        command=config.command,
        exit_code=process.returncode,
        duration_seconds=time.monotonic() - started,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        error=capture_error,
        output_truncated=stdout_truncated or stderr_truncated,
    )
