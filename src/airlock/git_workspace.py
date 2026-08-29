"""Read-only Git workspace capture and reviewer mutation detection."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitWorkspaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkspaceSnapshot:
    fingerprint: str
    status: str


class GitWorkspace:
    _AUDIT_EXCLUDED_PARTS = {
        ".git",
        ".sandbox",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "build",
        "dist",
    }

    def __init__(self, start: Path) -> None:
        root = self._git(start, "rev-parse", "--show-toplevel").strip()
        self.root = Path(root).resolve()

    @staticmethod
    def _git(cwd: Path, *args: str, check: bool = True) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and completed.returncode != 0:
            detail = completed.stderr.strip() or "git command failed"
            raise GitWorkspaceError(detail)
        return completed.stdout

    @staticmethod
    def _git_paths(cwd: Path, *args: str) -> list[str]:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            detail = os.fsdecode(completed.stderr).strip() or "git command failed"
            raise GitWorkspaceError(detail)
        return [os.fsdecode(item) for item in completed.stdout.split(b"\0") if item]

    def head(self) -> str:
        return self._git(self.root, "rev-parse", "HEAD").strip()

    def revision_identity(self) -> str:
        ref = self._git(
            self.root,
            "symbolic-ref",
            "--quiet",
            "HEAD",
            check=False,
        ).strip()
        return f"{self.head()}\n{ref or '(detached)'}"

    def status(self) -> str:
        return self._git(
            self.root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            ".",
            ":(exclude).airlock",
        )

    @classmethod
    def _audit_excluded(cls, relative: str) -> bool:
        return any(
            part in cls._AUDIT_EXCLUDED_PARTS or part.endswith(".egg-info")
            for part in Path(relative).parts
        )

    @staticmethod
    def _digest_field(digest: "hashlib._Hash", label: bytes, value: bytes) -> None:
        """Add an unambiguously framed field to a workspace fingerprint."""
        digest.update(len(label).to_bytes(2, "big"))
        digest.update(label)
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)

    @staticmethod
    def _sanitize_tracked_diff(diff: str) -> str:
        """Redact targets from Git sections involving tracked symlinks."""
        if not diff:
            return diff
        sections: list[str] = []
        current: list[str] = []
        for line in diff.splitlines(keepends=True):
            if line.startswith("diff --git ") and current:
                sections.append("".join(current))
                current = []
            current.append(line)
        if current:
            sections.append("".join(current))

        sanitized: list[str] = []
        for section in sections:
            header, _, remainder = section.partition("\n")
            metadata = "\n" + remainder
            if any(
                marker in metadata
                for marker in (
                    " 120000\n",
                    "new file mode 120000\n",
                    "deleted file mode 120000\n",
                    "old mode 120000\n",
                    "new mode 120000\n",
                )
            ):
                sanitized.append(
                    header
                    + "\nAirlock: tracked symlink target and diff content omitted\n"
                )
            else:
                sanitized.append(section)
        return "".join(sanitized)

    def review_material(self, max_untracked_bytes: int = 100_000) -> str:
        tracked = self._sanitize_tracked_diff(
            self._git(self.root, "diff", "--binary", "HEAD", "--")
        )
        untracked = self._git_paths(
            self.root,
            "ls-files",
            "-z",
            "--others",
            "--exclude-standard",
            "--",
            ".",
            ":(exclude).airlock",
        )
        parts = ["## Tracked and staged diff\n", tracked or "(no tracked diff)\n"]
        budget = max_untracked_bytes
        for relative in untracked:
            path = self.root / relative
            display_path = json.dumps(relative, ensure_ascii=True)
            if path.is_symlink():
                parts.append(
                    f"\n## Untracked symlink: {display_path}\n"
                    "(target and content omitted)\n"
                )
                continue
            if not path.is_file():
                continue
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            parts.append(
                f"\n## Untracked file: {display_path}\nsha256: {digest}\n"
            )
            if budget <= 0:
                parts.append("(content omitted: untracked content budget exhausted)\n")
                continue
            chunk = data[:budget]
            budget -= len(chunk)
            try:
                text = chunk.decode("utf-8")
            except UnicodeDecodeError:
                parts.append("(binary content omitted)\n")
            else:
                parts.extend(["```\n", text, "\n```\n"])
                if len(chunk) < len(data):
                    parts.append("(content truncated)\n")
        return "".join(parts)

    def snapshot(self) -> WorkspaceSnapshot:
        status = self.status()
        digest = hashlib.sha256()
        self._digest_field(digest, b"status", status.encode())
        self._digest_field(
            digest,
            b"tracked-diff",
            self._git(self.root, "diff", "--binary", "HEAD", "--").encode(),
        )
        for relative in self._git_paths(
            self.root,
            "ls-files",
            "-z",
            "--others",
            "--exclude-standard",
            "--",
            ".",
        ):
            path = self.root / relative
            self._digest_field(digest, b"untracked-path", os.fsencode(relative))
            if path.is_symlink():
                self._digest_field(
                    digest, b"untracked-symlink", os.fsencode(os.readlink(path))
                )
            elif path.is_file():
                self._digest_field(digest, b"untracked-file", path.read_bytes())
        ignored = self._git_paths(
            self.root,
            "ls-files",
            "-z",
            "--others",
            "--ignored",
            "--exclude-standard",
        )
        for relative in ignored:
            path = self.root / relative
            if self._audit_excluded(relative):
                continue
            self._digest_field(digest, b"ignored-path", os.fsencode(relative))
            if path.is_symlink():
                self._digest_field(
                    digest, b"ignored-symlink", os.fsencode(os.readlink(path))
                )
            elif path.is_file():
                self._digest_field(digest, b"ignored-file", path.read_bytes())
        for current, directories, _ in os.walk(self.root, followlinks=False):
            current_path = Path(current)
            kept: list[str] = []
            for name in sorted(directories):
                relative = (current_path / name).relative_to(self.root).as_posix()
                if self._audit_excluded(relative):
                    continue
                kept.append(name)
                self._digest_field(
                    digest, b"workspace-directory", os.fsencode(relative)
                )
            directories[:] = kept
        return WorkspaceSnapshot(fingerprint=digest.hexdigest(), status=status)
