import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path("/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang")


@pytest.fixture
def fake_snapshot_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "大纲").mkdir()
    (project / "大纲" / "总纲.md").write_text("# dummy", encoding="utf-8")
    snap_dir = project / ".webnovel" / "snapshots" / "ch0001"
    snap_dir.mkdir(parents=True)
    (snap_dir / "old.txt").write_text("OLD", encoding="utf-8")
    return project


def test_default_refuses_rmtree(fake_snapshot_project):
    """默认（不传 --on-conflict）应报错，不 rmtree 现有 snapshot dir。"""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/snapshot_manager.py",
            "freeze",
            "--project-root",
            str(fake_snapshot_project),
            "1",
        ],
        cwd=PLUGIN_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert (
        fake_snapshot_project
        / ".webnovel"
        / "snapshots"
        / "ch0001"
        / "old.txt"
    ).exists()


def test_skip_keeps_existing_snapshot(fake_snapshot_project):
    """--on-conflict=skip 应保持旧 snapshot dir 不变。"""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/snapshot_manager.py",
            "freeze",
            "--project-root",
            str(fake_snapshot_project),
            "--on-conflict",
            "skip",
            "1",
        ],
        cwd=PLUGIN_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    old_file = (
        fake_snapshot_project
        / ".webnovel"
        / "snapshots"
        / "ch0001"
        / "old.txt"
    )
    assert old_file.exists()
    assert old_file.read_text(encoding="utf-8") == "OLD"


def test_overwrite_replaces_snapshot(fake_snapshot_project):
    """--on-conflict=overwrite 应清空旧 snapshot dir 并重建。"""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/snapshot_manager.py",
            "freeze",
            "--project-root",
            str(fake_snapshot_project),
            "--on-conflict",
            "overwrite",
            "1",
        ],
        cwd=PLUGIN_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    snap_dir = fake_snapshot_project / ".webnovel" / "snapshots" / "ch0001"
    assert not (snap_dir / "old.txt").exists()
    assert (snap_dir / "manifest.json").exists()
