"""Atomic, local, inspectable artifacts for one review invocation."""

from __future__ import annotations

import json
import os
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class RunStoreIntegrityError(RuntimeError):
    pass


class RunStore:
    def __init__(self, repository: Path) -> None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
        self.path = repository / ".airlock" / "runs" / self.run_id
        self.path.mkdir(parents=True, exist_ok=False)
        directory_stat = os.lstat(self.path)
        self._directory_identity = (directory_stat.st_dev, directory_stat.st_ino)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_NOFOLLOW", 0)
        self._repository_fd = os.open(repository, directory_flags)
        self._run_fd = os.open(self.path, directory_flags)
        run_stat = os.fstat(self._run_fd)
        if (run_stat.st_dev, run_stat.st_ino) != self._directory_identity:
            raise RunStoreIntegrityError("active run directory changed during setup")

    def __del__(self) -> None:
        for attribute in ("_run_fd", "_repository_fd"):
            descriptor = getattr(self, attribute, None)
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                setattr(self, attribute, None)

    def _verify_directory(self) -> None:
        try:
            current = os.lstat(self.path)
        except FileNotFoundError as exc:
            raise RunStoreIntegrityError("active run directory was removed") from exc
        identity = (current.st_dev, current.st_ino)
        if not stat.S_ISDIR(current.st_mode) or identity != self._directory_identity:
            raise RunStoreIntegrityError("active run directory was replaced")

    def write_text(self, name: str, value: str) -> Path:
        self._verify_directory()
        if Path(name).name != name:
            raise ValueError("run artifact name must not contain path separators")
        target = self.path / name
        temporary = f".{name}.{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600, dir_fd=self._run_fd)
        try:
            data = value.encode("utf-8")
            while data:
                written = os.write(descriptor, data)
                data = data[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            self._verify_directory()
            os.replace(
                temporary,
                name,
                src_dir_fd=self._run_fd,
                dst_dir_fd=self._run_fd,
            )
            self._verify_directory()
        except OSError as exc:
            try:
                self._verify_directory()
            except RunStoreIntegrityError as integrity_error:
                raise integrity_error from exc
            raise
        return target

    def write_json(self, name: str, value: Any) -> Path:
        return self.write_text(
            name,
            json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        )

    def write_recovery_json(self, value: Any) -> Path:
        """Persist failure evidence through the trusted repository descriptor."""
        name = f".airlock-recovery-{self.run_id}.json"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(name, flags, 0o600, dir_fd=self._repository_fd)
        try:
            data = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
            while data:
                written = os.write(descriptor, data)
                data = data[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return self.path.parents[2] / name
