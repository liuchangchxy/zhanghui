"""Tests for check-volume .md existence check (P0 修复).

See Task 9 of Phase 3 (plan script fixes).

check-volume should emit BLOCKER for missing 大纲/第{volume}卷-*.md artifacts.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path("/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang")


@pytest.fixture
def proj_no_md(tmp_path):
    project = tmp_path / "proj"
    (project / ".webnovel").mkdir(parents=True)
    (project / ".webnovel" / "state.json").write_text(
        '{"story_craft": {"volume_beat": {"volume": 1, "total_chapters": 50, '
        '"beats": []}}, "chapter_meta": {}}'
    )
    # 没有 大纲/ 目录 → 所有 .md 缺失
    return project


def test_check_volume_warns_missing_md(proj_no_md):
    result = subprocess.run(
        [sys.executable, "scripts/webnovel.py",
         "--project-root", str(proj_no_md),
         "story-craft", "check-volume", "--volume", "1"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    # .md 缺失应该被报为 BLOCKER（exit code != 0）
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "节拍表" in output or "时间线" in output or "详细大纲" in output
    assert "BLOCKER" in output