"""Verify the spec §5.4 contract:
  - plan V1 does NOT pre-generate 第N卷-详细大纲.md / 节拍表.md / 时间线.md for N >= 2
  - V+1 row in 总纲.md is filled iff V+1 is confirmed in state.json
  - V+1 row is empty / omitted iff V+1 is deferred or absent

See: docs/superpowers/plans/2026-08-18-multi-volume-init.md Task 10
"""

import sys
import tempfile
from pathlib import Path

# File: scripts/tests/integration/test_plan_v_plus_one_anchor.py
# Path bug to avoid: do NOT append "/scripts" — parents[2] IS the scripts dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from init_project import init_project


def _init_project(tmp_path, skeleton):
    init_project(
        project_dir=str(tmp_path),
        title="Anchor Test",
        genre="玄幻",
        target_chapters=100,
        target_words=300000,
        volume_skeleton=skeleton,
    )


def test_plan_v1_no_v2_confirmation_omits_v2_row(tmp_path):
    """Only V1 confirmed → V2 row NOT pre-generated in 总纲."""
    _init_project(tmp_path, [
        {"index": 1, "title": "V1", "chapter_range": [1, 100],
         "core_conflict": "A", "climax": "B",
         "status": "confirmed", "source": "human"},
    ])
    outline = (tmp_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
    assert "### 第1卷" in outline
    assert "### 第2卷" not in outline
    # No detailed outline auto-generated for V2
    assert not (tmp_path / "大纲" / "第2卷-详细大纲.md").exists()
    assert not (tmp_path / "大纲" / "第2卷-节拍表.md").exists()
    assert not (tmp_path / "大纲" / "第2卷-时间线.md").exists()


def test_plan_v1_with_v2_confirmed_writes_v2_row_only(tmp_path):
    """V2 confirmed → V2 row filled, but still no detailed outline."""
    _init_project(tmp_path, [
        {"index": 1, "title": "V1", "chapter_range": [1, 50],
         "core_conflict": "A", "climax": "B",
         "status": "confirmed", "source": "human"},
        {"index": 2, "title": "V2-深入", "chapter_range": [51, 100],
         "core_conflict": "C", "climax": "D",
         "status": "confirmed", "source": "human"},
    ])
    outline = (tmp_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
    assert "### 第1卷" in outline
    assert "### 第2卷" in outline
    # Title from state.json propagates
    assert "V2-深入" in outline
    # Detailed outline STILL not auto-generated (the hard constraint)
    assert not (tmp_path / "大纲" / "第2卷-详细大纲.md").exists()
    assert not (tmp_path / "大纲" / "第2卷-节拍表.md").exists()
    assert not (tmp_path / "大纲" / "第2卷-时间线.md").exists()


def test_plan_v1_three_volumes_no_v4_row(tmp_path):
    """Three volumes confirmed → V4+ NOT pre-generated."""
    _init_project(tmp_path, [
        {"index": i, "title": f"V{i}", "chapter_range": [(i-1)*30+1, i*30],
         "core_conflict": "X", "climax": "Y",
         "status": "confirmed", "source": "human"}
        for i in range(1, 4)
    ])
    outline = (tmp_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
    for i in range(1, 4):
        assert f"### 第{i}卷" in outline
    assert "### 第4卷" not in outline
