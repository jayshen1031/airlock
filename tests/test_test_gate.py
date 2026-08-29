import os
import sys
from pathlib import Path

import pytest

from airlock.test_gate import (
    MAX_CAPTURE_CHARS,
    TestGateConfig as GateConfig,
    TestGateConfigError as GateConfigError,
    load_test_gate,
    run_test_gate,
    _stop_process as stop_process,
)


def write_config(repository: Path, body: str) -> None:
    config = repository / ".airlock" / "config.toml"
    config.parent.mkdir()
    config.write_text(body)


def test_missing_config_disables_gate(tmp_path: Path) -> None:
    assert load_test_gate(tmp_path) is None


def test_loads_explicit_argv_and_timeout(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        '[gates.tests]\ncommand = ["python", "-m", "pytest", "-q"]\n'
        "timeout_seconds = 12.5\n",
    )
    config = load_test_gate(tmp_path)
    assert config == GateConfig(("python", "-m", "pytest", "-q"), 12.5)


@pytest.mark.parametrize(
    "body",
    [
        "[gates.tests]\ncommand = []\n",
        '[gates.tests]\ncommand = "pytest"\n',
        '[gates.tests]\ncommand = ["pytest"]\ntimeout_seconds = 0\n',
        '[gates.tests]\ncommand = ["pytest"]\ntimeout_seconds = inf\n',
        '[gates.tests]\ncommand = ["pytest"]\ntimeout_seconds = -inf\n',
        '[gates.tests]\ncommand = ["pytest"]\ntimeout_seconds = nan\n',
        '[gates.tests]\ncommand = ["pytest"]\ntimeout_seconds = 3601\n',
        '[gates.tests]\ncommand = ["pytest", "\\u0000"]\n',
        '[gates.tests]\ncommand = ["pytest"]\nsurprise = true\n',
    ],
)
def test_rejects_unsafe_or_ambiguous_config(tmp_path: Path, body: str) -> None:
    write_config(tmp_path, body)
    with pytest.raises(GateConfigError):
        load_test_gate(tmp_path)


def test_runs_command_and_captures_failure(tmp_path: Path) -> None:
    result = run_test_gate(
        tmp_path,
        GateConfig(
            (sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(7)"),
            5,
        ),
    )
    assert result.exit_code == 7
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"
    assert not result.passed
    assert not result.infrastructure_failure


def test_timeout_is_infrastructure_failure(tmp_path: Path) -> None:
    result = run_test_gate(
        tmp_path,
        GateConfig((sys.executable, "-c", "import time; time.sleep(30)"), 0.05),
    )
    assert result.timed_out
    assert result.infrastructure_failure
    assert not result.passed


def test_timeout_termination_tolerates_already_exited_process(monkeypatch) -> None:
    class ExitedProcess:
        pid = 12345

        @staticmethod
        def wait(timeout=None):
            return 0

    def already_exited(*args) -> None:
        raise ProcessLookupError

    monkeypatch.setattr("airlock.test_gate.os.killpg", already_exited)
    stop_process(ExitedProcess())


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX process groups")
def test_timeout_kills_descendant_that_ignores_sigterm(tmp_path: Path) -> None:
    child = tmp_path / "child.py"
    child.write_text(
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('child ready', flush=True)\n"
        "time.sleep(30)\n"
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(child)!r}])\n"
        "time.sleep(30)\n"
    )
    result = run_test_gate(
        tmp_path,
        GateConfig((sys.executable, str(parent)), 0.1),
    )
    assert result.timed_out
    assert result.error is None
    assert "child ready" in result.stdout
    assert result.duration_seconds < 4


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX process groups")
def test_successful_parent_does_not_leave_pipe_holding_descendant(
    tmp_path: Path,
) -> None:
    child = tmp_path / "child.py"
    child.write_text(
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('orphan ready', flush=True)\n"
        "time.sleep(30)\n"
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(child)!r}])\n"
        "time.sleep(0.2)\n"
    )
    result = run_test_gate(
        tmp_path,
        GateConfig((sys.executable, str(parent)), 5),
    )
    assert result.exit_code == 0
    assert result.error is None
    assert result.passed
    assert "orphan ready" in result.stdout
    assert result.duration_seconds < 4


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX process groups")
def test_successful_parent_does_not_leave_detached_output_descendant(
    tmp_path: Path,
) -> None:
    pid_path = tmp_path / "child.pid"
    child = tmp_path / "quiet-child.py"
    child.write_text(
        "import os, time\n"
        "from pathlib import Path\n"
        f"Path({str(pid_path)!r}).write_text(str(os.getpid()))\n"
        "os.close(1)\n"
        "os.close(2)\n"
        "time.sleep(30)\n"
    )
    parent = tmp_path / "quiet-parent.py"
    parent.write_text(
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(child)!r}])\n"
        "time.sleep(0.2)\n"
    )
    result = run_test_gate(
        tmp_path,
        GateConfig((sys.executable, str(parent)), 5),
    )
    assert result.exit_code == 0
    assert result.error is None
    child_pid = int(pid_path.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_missing_executable_is_captured(tmp_path: Path) -> None:
    result = run_test_gate(
        tmp_path,
        GateConfig(("airlock-command-that-does-not-exist",), 1),
    )
    assert result.exit_code is None
    assert result.error
    assert result.infrastructure_failure


def test_launch_value_error_is_captured(tmp_path: Path) -> None:
    result = run_test_gate(
        tmp_path,
        GateConfig((sys.executable, "\0"), 1),
    )
    assert result.exit_code is None
    assert result.error
    assert result.infrastructure_failure


def test_large_output_is_truncated(tmp_path: Path) -> None:
    result = run_test_gate(
        tmp_path,
        GateConfig(
            (sys.executable, "-c", f"print('x' * {MAX_CAPTURE_CHARS + 10})"),
            5,
        ),
    )
    assert result.output_truncated
    assert "truncated" in result.stdout
    assert len(result.stdout) < MAX_CAPTURE_CHARS + 100
