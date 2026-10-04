"""Tests for check-plan-artifacts CLI.

See Task 10 of Phase 4 (SKILL.md 落地脚本).

check_plan_artifacts.py should scan plan/init/review rerun-relevant .md
artifacts and return a JSON inventory so SKILL.md can reason about
file existence before deciding to overwrite.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path("/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang")


@pytest.fixture
def proj_with_md(tmp_path):
    project = tmp_path / "proj"
    (project / "大纲").mkdir(parents=True)
    (project / "大纲" / "第1卷-节拍表.md").write_text("# V1 节拍", encoding="utf-8")
    (project / "大纲" / "第1卷-时间线.md").write_text("# V1 时间线", encoding="utf-8")
    # 第1卷-详细大纲.md 故意缺失
    return project


def test_no_md_returns_empty_list(tmp_path):
    project = tmp_path / "empty"
    project.mkdir()
    result = subprocess.run(
        [sys.executable, "scripts/check_plan_artifacts.py",
         "--project-root", str(project), "--volume", "1"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["artifacts"] == []


def test_partial_md_lists_existing(proj_with_md):
    result = subprocess.run(
        [sys.executable, "scripts/check_plan_artifacts.py",
         "--project-root", str(proj_with_md), "--volume", "1"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    paths = [a["path"] for a in data["artifacts"]]
    assert "大纲/第1卷-节拍表.md" in paths
    assert "大纲/第1卷-时间线.md" in paths
    assert "大纲/第1卷-详细大纲.md" not in paths  # 缺失不计入


def test_output_includes_last_modified(proj_with_md):
    result = subprocess.run(
        [sys.executable, "scripts/check_plan_artifacts.py",
         "--project-root", str(proj_with_md), "--volume", "1"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    for a in data["artifacts"]:
        assert "last_modified" in a
        assert a["last_modified"]  # 非空