"""Standalone agy hook: deny every capability outside the authorized file scope."""

from __future__ import annotations

import json
import sys
from pathlib import Path


READ_PATHS = {
    "view_file": "AbsolutePath",
    "grep_search": "SearchPath",
    "list_dir": "DirectoryPath",
}
WRITE_PATHS = {
    "replace_file_content": "TargetFile",
    "multi_replace_file_content": "TargetFile",
    "write_to_file": "TargetFile",
}


def allowed_tool(call: dict, root: Path, writing: bool) -> bool:
    name = call.get("name")
    # agy submits --json-schema results through this side-effect-free control tool.
    if name == "finish":
        return isinstance(call.get("args"), dict)
    fields = READ_PATHS | (WRITE_PATHS if writing else {})
    if name not in fields or not isinstance(call.get("args"), dict):
        return False
    value = call["args"].get(fields[name])
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        return False
    try:
        relative = Path(value).resolve().relative_to(root.resolve())
    except (ValueError, OSError, RuntimeError):
        return False
    if name in WRITE_PATHS and (not relative.parts or
                              any(part in {".git", ".airlock"} for part in relative.parts)):
        return False
    return True


def main() -> None:
    decision = {"decision": "deny", "reason": "Airlock capability boundary"}
    try:
        config_path = Path(sys.argv[1])
        config = json.loads(config_path.read_text(encoding="utf-8"))
        active = config_path.parent / "gate-active"
        denied = config_path.parent / "gate-denied"
        payload = json.load(sys.stdin)
        if sys.argv[2] == "activate":
            active.write_text("active", encoding="utf-8")
            decision = {"injectSteps": [{"ephemeralMessage": (
                "Airlock permits finish for returning results, and only view_file, grep_search, list_dir within "
                + config["root"]
                + ("; file edits within that repository are also permitted." if config["writing"] else
                   ". All writes are forbidden.")
                + " Use absolute paths. Shell, MCP, browser, and subagents are forbidden."
            )}]}
        elif active.is_file() and allowed_tool(payload.get("toolCall", {}),
                                              Path(config["root"]), config["writing"]):
            # Preserve provider permission rules; do not grant additional permissions.
            decision = {"decision": "allow" if payload["toolCall"]["name"] == "finish"
                        else "deny_unless_prior_grant"}
        else:
            call = payload.get("toolCall", {})
            denied.write_text(str(call.get("name", "unknown")), encoding="utf-8")
    except Exception:
        # A malformed payload or hook configuration never authorizes execution.
        try:
            (Path(sys.argv[1]).parent / "gate-denied").write_text("hook_error", encoding="utf-8")
        except Exception:
            pass
    print(json.dumps(decision))


if __name__ == "__main__":
    main()
