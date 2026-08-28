import os
import shutil
from pathlib import Path

import pytest

from airlock.run_store import RunStore, RunStoreIntegrityError


def replace_with_external_symlink(store: RunStore, outside: Path) -> None:
    shutil.rmtree(store.path)
    outside.mkdir()
    os.symlink(outside, store.path)


@pytest.mark.parametrize("replacement_check", [1, 2])
def test_run_writes_cannot_escape_replaced_parent(
    tmp_path: Path, monkeypatch, replacement_check: int
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    store = RunStore(repository)
    outside = tmp_path / "outside"
    original_verify = store._verify_directory
    calls = 0

    def racing_verify() -> None:
        nonlocal calls
        calls += 1
        original_verify()
        if calls == replacement_check:
            replace_with_external_symlink(store, outside)

    monkeypatch.setattr(store, "_verify_directory", racing_verify)
    with pytest.raises((RunStoreIntegrityError, FileNotFoundError)):
        store.write_text("state.json", "{}\n")
    assert not (outside / "state.json").exists()
    assert not any(outside.iterdir())
