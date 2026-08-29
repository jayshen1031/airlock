import json
from pathlib import Path

from airlock.adapters.claude import ClaudeAdapter
from airlock.adapters.codex import CodexAdapter
from airlock.models import AgentMode, AgentRequest


def request(tmp_path: Path) -> AgentRequest:
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"type": "object"}), encoding="utf-8")
    return AgentRequest("review", tmp_path, schema, 10)


def test_codex_is_explicitly_read_only(tmp_path: Path) -> None:
    command = CodexAdapter().command(request(tmp_path))
    assert command[:4] == ["codex", "exec", "--sandbox", "read-only"]
    assert "--ephemeral" in command
    assert "--output-schema" in command


def test_claude_has_only_read_tools(tmp_path: Path) -> None:
    command = ClaudeAdapter().command(request(tmp_path))
    assert command[0:2] == ["claude", "--print"]
    assert command[command.index("--tools") + 1] == "Read,Glob,Grep"
    assert "--no-session-persistence" in command
    assert command[-1] == "--no-session-persistence"
    assert "Edit" not in command and "Write" not in command and "Bash" not in command


def test_codex_write_mode_is_workspace_scoped(tmp_path: Path) -> None:
    write_request = AgentRequest(
        "repair", tmp_path, None, 10, mode=AgentMode.WRITE
    )
    command = CodexAdapter().command(write_request)
    assert command[:4] == ["codex", "exec", "--sandbox", "workspace-write"]
    assert "--output-schema" not in command
    assert "--dangerously-bypass-approvals-and-sandbox" not in command


def test_claude_write_mode_has_explicit_local_tools(tmp_path: Path) -> None:
    write_request = AgentRequest(
        "repair", tmp_path, None, 10, mode=AgentMode.WRITE
    )
    command = ClaudeAdapter().command(write_request)
    assert command[command.index("--permission-mode") + 1] == "acceptEdits"
    assert command[command.index("--tools") + 1] == "Read,Glob,Grep,Edit,Write"
    assert "--json-schema" not in command
    assert "--dangerously-skip-permissions" not in command
    assert "Bash" not in command
