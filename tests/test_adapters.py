import json
from pathlib import Path

from airlock.adapters.claude import ClaudeAdapter
from airlock.adapters.codex import CodexAdapter
from airlock.models import AgentRequest


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
