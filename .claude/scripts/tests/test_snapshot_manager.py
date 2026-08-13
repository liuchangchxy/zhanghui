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