import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path("/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang")


@pytest.fixture
def fake_project(tmp_path):
    """构造一个最小可跑项目：state.json + 大纲/总纲.md 含 V2 row。"""
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".webnovel").mkdir()
    (project / "大纲").mkdir()

    # state.json
    (project / ".webnovel" / "state.json").write_text(
        '{"project_info": {"title": "T", "genre": "玄幻"}, '
        '"volumes": [{"index": 1, "status": "confirmed"}, '
        '{"index": 2, "status": "confirmed", "title": "V2", '
        '"core_conflict": "old", "climax": "old"}]}'
    )

    # 总纲.md 含 V2 row
    outline = project / "大纲" / "总纲.md"
    outline.write_text(
        "# 总纲\n\n## 卷划分\n"
        "| 卷号 | 卷名 | 章节范围 | 核心冲突 | 卷末高潮 |\n"
        "|------|------|----------|----------|----------|\n"
        "| 2 | V2 | 81-160 | old | old |\n"
    )

    # 总纲写回 JSON
    (project / "大纲" / "第1卷-总纲写回.json").write_text(
        '{"next_volume_anchor": {"volume": 2, "volume_name": "V2", '
        '"chapters_range": "81-160", "core_conflict": "NEW", '
        '"volume_end_climax": "NEW"}}'
    )

    # current volume planning artifacts (avoid pre-check failure before conflict logic)
    for artifact in ("节拍表", "时间线", "详细大纲"):
        (project / "大纲" / f"第1卷-{artifact}.md").write_text(f"# stub {artifact}\n")
    return project


def test_default_runs_raises_file_exists_error(fake_project):
    """默认（不传 --on-conflict）应报错且不修改文件。"""
    result = subprocess.run(
        [sys.executable, "scripts/update_master_outline.py",
         "--project-root", str(fake_project), "--volume", "1"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0
    # Error is JSON-emitted to stdout (master_outline.py wraps MasterOutlineSyncError into JSON)
    combined_output = result.stdout + result.stderr
    assert "已存在" in combined_output or "请传 --on-conflict" in combined_output, (
        f"默认错误信息应包含 '已存在' 或 '请传 --on-conflict'，实际: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # V2 row 仍未被覆盖
    content = (fake_project / "大纲" / "总纲.md").read_text()
    assert "old" in content


def test_skip_does_not_modify(fake_project):
    result = subprocess.run(
        [sys.executable, "scripts/update_master_outline.py",
         "--project-root", str(fake_project), "--volume", "1",
         "--on-conflict", "skip"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    content = (fake_project / "大纲" / "总纲.md").read_text()
    assert "old" in content


def test_overwrite_modifies(fake_project):
    result = subprocess.run(
        [sys.executable, "scripts/update_master_outline.py",
         "--project-root", str(fake_project), "--volume", "1",
         "--on-conflict", "overwrite"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    content = (fake_project / "大纲" / "总纲.md").read_text()
    assert "NEW" in content
