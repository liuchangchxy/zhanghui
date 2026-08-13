"""snapshot_manager.py 单元测试。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SNAPSHOT_SCRIPT = Path(__file__).resolve().parent.parent / "snapshot_manager.py"


def run_snapshot(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SNAPSHOT_SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd,
    )


# === Manifest schema ===
def test_manifest_has_required_fields(tmp_path):
    """manifest.json 必须包含: chapter, frozen_at, files[]。"""
    from snapshot_manager import build_manifest
    # 准备真实文件（build_manifest 跳过不存在的路径）
    (tmp_path / "设定集").mkdir()
    target = tmp_path / "设定集" / "陈默.md"
    target.write_text("x", encoding="utf-8")
    m = build_manifest(
        chapter=1,
        files=["设定集/陈默.md"],
        project_root=tmp_path,
    )
    assert m.chapter == 1
    assert m.frozen_at  # 非空字符串
    assert len(m.files) == 1
    assert m.files[0].path == "设定集/陈默.md"
    d = m.to_dict()
    assert "chapter" in d and "frozen_at" in d and "files" in d


def test_manifest_serializes_to_json(tmp_path):
    """to_dict() 输出可被 json.dumps 序列化。"""
    from snapshot_manager import build_manifest
    (tmp_path / "x").write_text("y", encoding="utf-8")
    m = build_manifest(chapter=42, files=["x"], project_root=tmp_path)
    s = json.dumps(m.to_dict(), ensure_ascii=False)
    parsed = json.loads(s)
    assert parsed["chapter"] == 42


# === discover_files ===
def test_discover_files_finds_md_under_settings_and_outline(tmp_path: Path):
    """discover_files 应递归扫描 设定集/ 与 大纲/ 下所有 .md 文件。"""
    (tmp_path / "设定集").mkdir()
    (tmp_path / "大纲").mkdir()
    (tmp_path / "设定集" / "角色库").mkdir()
    (tmp_path / "设定集" / "角色库" / "陈默.md").write_text("x", encoding="utf-8")
    (tmp_path / "大纲" / "总纲.md").write_text("y", encoding="utf-8")
    # 噪声：应被忽略
    (tmp_path / "设定集" / ".DS_Store").write_text("z", encoding="utf-8")
    (tmp_path / "大纲" / "note.txt").write_text("w", encoding="utf-8")

    from snapshot_manager import discover_files
    found = discover_files(tmp_path)
    rels = sorted(f.relative_to(tmp_path).as_posix() for f in found)
    assert rels == ["大纲/总纲.md", "设定集/角色库/陈默.md"]


# === freeze 命令（端到端） ===
def test_freeze_creates_snapshot_dir_and_copies_files(tmp_path: Path):
    """freeze N 在 .webnovel/snapshots/ch{NNNN}/ 创建目录并复制所有 .md + manifest.json。"""
    # 准备项目结构
    (tmp_path / "设定集").mkdir()
    (tmp_path / "大纲").mkdir()
    (tmp_path / "设定集" / "陈默.md").write_text("角色状态", encoding="utf-8")
    (tmp_path / "大纲" / "总纲.md").write_text("大纲", encoding="utf-8")

    result = run_snapshot("freeze", "1", cwd=tmp_path)
    assert result.returncode == 0, f"stderr: {result.stderr}"

    snap_dir = tmp_path / ".webnovel" / "snapshots" / "ch0001"
    assert snap_dir.is_dir()
    assert (snap_dir / "设定集" / "陈默.md").is_file()
    assert (snap_dir / "大纲" / "总纲.md").is_file()
    assert (snap_dir / "manifest.json").is_file()
    manifest = json.loads((snap_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["chapter"] == 1
    assert manifest["version"] == 1
    file_paths = {f["path"] for f in manifest["files"]}
    assert file_paths == {"设定集/陈默.md", "大纲/总纲.md"}


def test_freeze_uses_4digit_chapter_number(tmp_path: Path):
    """freeze 12 → ch0012；freeze 100 → ch0100。"""
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("大纲", encoding="utf-8")
    result = run_snapshot("freeze", "12", cwd=tmp_path)
    assert result.returncode == 0
    assert (tmp_path / ".webnovel" / "snapshots" / "ch0012").is_dir()


def test_freeze_fails_when_no_settings_or_outline(tmp_path: Path):
    """既无 设定集/ 也无 大纲/ → 退出码 2（infrastructure error）。"""
    result = run_snapshot("freeze", "1", cwd=tmp_path)
    assert result.returncode == 2
    assert "no snapshot-eligible files" in result.stderr.lower() or "找不到" in result.stderr