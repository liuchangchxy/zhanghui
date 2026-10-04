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


# === verify ===
def test_verify_returns_ok_when_unchanged(tmp_path: Path):
    """freeze 后立即 verify → exit 0, ok=true。"""
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("v1", encoding="utf-8")
    assert run_snapshot("freeze", "1", cwd=tmp_path).returncode == 0
    result = run_snapshot("verify", "1", cwd=tmp_path)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["ok"] is True
    assert out["drifted_files"] == []
    assert out["missing_files"] == []
    assert out["added_files"] == []


def test_verify_detects_modified_file(tmp_path: Path):
    """modify 一个文件后 verify → exit 1, drifted_files 列出该文件。"""
    (tmp_path / "大纲").mkdir()
    f = tmp_path / "大纲" / "总纲.md"
    f.write_text("v1", encoding="utf-8")
    run_snapshot("freeze", "1", cwd=tmp_path)
    f.write_text("v2 — 修改过", encoding="utf-8")
    result = run_snapshot("verify", "1", cwd=tmp_path)
    assert result.returncode == 1
    out = json.loads(result.stdout)
    assert out["ok"] is False
    assert "大纲/总纲.md" in out["drifted_files"]


def test_verify_detects_added_and_deleted_files(tmp_path: Path):
    """新增/删除文件 → added_files / missing_files 反映。"""
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("x", encoding="utf-8")
    (tmp_path / "设定集").mkdir()
    (tmp_path / "设定集" / "陈默.md").write_text("y", encoding="utf-8")
    run_snapshot("freeze", "1", cwd=tmp_path)
    # 新增一个
    (tmp_path / "设定集" / "王玄之.md").write_text("z", encoding="utf-8")
    # 删除一个
    (tmp_path / "设定集" / "陈默.md").unlink()

    result = run_snapshot("verify", "1", cwd=tmp_path)
    assert result.returncode == 1
    out = json.loads(result.stdout)
    assert "设定集/王玄之.md" in out["added_files"]
    assert "设定集/陈默.md" in out["missing_files"]


def test_verify_fails_when_snapshot_missing(tmp_path: Path):
    """不存在的章节 → exit 2。"""
    (tmp_path / "大纲").mkdir()
    result = run_snapshot("verify", "999", cwd=tmp_path)
    assert result.returncode == 2


# === list ===
def test_list_returns_all_snapshots(tmp_path: Path):
    """freeze 多个章节 → list 全部返回。"""
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("x", encoding="utf-8")
    for n in (1, 3, 7):
        run_snapshot("freeze", str(n), cwd=tmp_path)
    result = run_snapshot("list", cwd=tmp_path)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    chapters = {s["chapter"] for s in out["snapshots"]}
    assert chapters == {1, 3, 7}


# === diff ===
def test_diff_shows_drifted_file_list(tmp_path: Path):
    """diff 输出当前 vs snapshot 的差异文件清单（包含状态）。"""
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("v1", encoding="utf-8")
    run_snapshot("freeze", "1", cwd=tmp_path)
    (tmp_path / "大纲" / "总纲.md").write_text("v2", encoding="utf-8")
    result = run_snapshot("diff", "1", cwd=tmp_path)
    assert result.returncode in (0, 1)  # diff 本身不强制失败
    out = json.loads(result.stdout)
    statuses = {f["path"]: f["status"] for f in out["files"]}
    assert statuses.get("大纲/总纲.md") == "modified"


# === C1: CLI argument parsing ===
def test_project_root_flag_after_subcommand(tmp_path: Path):
    """--project-root 必须跟在 subcommand 之后（用户实际使用方式）。"""
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("x", encoding="utf-8")
    result = run_snapshot("freeze", "1", "--project-root", str(tmp_path))
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_path / ".webnovel" / "snapshots" / "ch0001").is_dir()


def test_usage_error_returns_exit_code_3(tmp_path: Path):
    """未知的 subcommand → 退出码 3（用法错误），不与 EXIT_INFRA=2 冲突。"""
    result = run_snapshot("bogus", "1", cwd=tmp_path)
    assert result.returncode == 3


def test_usage_error_missing_chapter_arg(tmp_path: Path):
    """freeze 缺 chapter 参数 → 退出码 3。"""
    (tmp_path / "大纲").mkdir()
    result = run_snapshot("freeze", cwd=tmp_path)
    assert result.returncode == 3


# === C7 / I7: freeze clears stale snapshot dir ===
def test_freeze_clears_stale_files_from_prior_freeze(tmp_path: Path):
    """重复 freeze 不同文件时，第二次 freeze 后目录里只含第二次的文件。"""
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("v1", encoding="utf-8")
    (tmp_path / "设定集").mkdir()
    (tmp_path / "设定集" / "陈默.md").write_text("v1", encoding="utf-8")

    # 第一次 freeze
    r1 = run_snapshot("freeze", "1", cwd=tmp_path)
    assert r1.returncode == 0
    snap = tmp_path / ".webnovel" / "snapshots" / "ch0001"
    assert (snap / "设定集" / "陈默.md").is_file()

    # 删除原文（模拟"改设定后重新 freeze"）
    (tmp_path / "设定集" / "陈默.md").unlink()
    # 第二次 freeze 显式覆盖 → 不应残留陈默.md
    r2 = run_snapshot("freeze", "1", "--on-conflict", "overwrite", cwd=tmp_path)
    assert r2.returncode == 0
    assert not (snap / "设定集" / "陈默.md").exists(), "ghost file should be cleared"
    assert (snap / "大纲" / "总纲.md").is_file()


# === I8: project_root 必须是相对路径，不是绝对路径 ===
def test_manifest_project_root_is_relative(tmp_path: Path):
    """manifest.project_root 应为 '.'（相对），不暴露本机绝对路径。"""
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("x", encoding="utf-8")
    r = run_snapshot("freeze", "1", cwd=tmp_path)
    assert r.returncode == 0
    manifest = json.loads(
        (tmp_path / ".webnovel" / "snapshots" / "ch0001" / "manifest.json").read_text()
    )
    assert manifest["project_root"] == "."
    assert not manifest["project_root"].startswith("/"), "不应暴露绝对路径"