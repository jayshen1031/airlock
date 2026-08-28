import os
import subprocess
from pathlib import Path

from airlock.git_workspace import GitWorkspace


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    ).stdout


def repository(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "tracked.txt").write_text("before\n", encoding="utf-8")
    git(tmp_path, "add", "tracked.txt")
    git(tmp_path, "commit", "-qm", "initial")
    return tmp_path


def test_material_includes_tracked_and_untracked_changes(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    (repo / "tracked.txt").write_text("after\n", encoding="utf-8")
    (repo / "new.txt").write_text("new content\n", encoding="utf-8")
    material = GitWorkspace(repo).review_material()
    assert "+after" in material
    assert 'Untracked file: "new.txt"' in material
    assert "new content" in material


def test_snapshot_tracks_airlock_artifact_mutation(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    workspace = GitWorkspace(repo)
    (repo / ".airlock" / "runs").mkdir(parents=True)
    artifact = repo / ".airlock" / "runs" / "event.json"
    artifact.write_text("{}")
    before = workspace.snapshot()
    artifact.write_text('{"changed": true}')
    assert workspace.snapshot().fingerprint != before.fingerprint


def test_material_does_not_follow_untracked_symlink(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("DO NOT DISCLOSE\n", encoding="utf-8")
    os.symlink(outside, repo / "linked-secret.txt")
    material = GitWorkspace(repo).review_material()
    assert 'Untracked symlink: "linked-secret.txt"' in material
    assert "DO NOT DISCLOSE" not in material
    assert str(outside) not in material


def test_material_redacts_staged_tracked_symlink_target(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    secret_target = "/private/sensitive/location/credential.txt"
    os.symlink(secret_target, repo / "tracked-link")
    git(repo, "add", "tracked-link")
    material = GitWorkspace(repo).review_material()
    assert "diff --git a/tracked-link b/tracked-link" in material
    assert "tracked symlink target and diff content omitted" in material
    assert secret_target not in material


def test_material_redacts_tracked_symlink_target_change(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    link = repo / "tracked-link"
    os.symlink("first-sensitive-target", link)
    git(repo, "add", "tracked-link")
    git(repo, "commit", "-qm", "add link")
    link.unlink()
    os.symlink("second-sensitive-target", link)
    material = GitWorkspace(repo).review_material()
    assert "tracked symlink target and diff content omitted" in material
    assert "first-sensitive-target" not in material
    assert "second-sensitive-target" not in material


def test_snapshot_tracks_ignored_file_with_newline_name(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    (repo / ".gitignore").write_text("*.env\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore env files")
    unusual = repo / "配置\nsecret.env"
    unusual.write_text("ORIGINAL=1\n")
    workspace = GitWorkspace(repo)
    before = workspace.snapshot()
    unusual.write_text("CHANGED=1\n")
    assert workspace.snapshot().fingerprint != before.fingerprint


def test_snapshot_frames_ignored_path_and_content_boundaries(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    (repo / ".gitignore").write_text("a*\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore collision fixtures")
    first = repo / "a"
    first.write_text("bc")
    workspace = GitWorkspace(repo)
    before = workspace.snapshot()
    first.unlink()
    (repo / "ab").write_text("c")
    assert workspace.snapshot().fingerprint != before.fingerprint
