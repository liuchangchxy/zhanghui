"""Integration tests for init_project() with volume_skeleton parameter.

RED phase (Task 5 of multi-volume-init plan): these tests must FAIL until
Task 6 adds the `volume_skeleton` parameter to init_project(). The expected
failure mode is TypeError on unexpected keyword argument.

See: docs/superpowers/plans/2026-08-18-multi-volume-init.md Task 5
"""

import sys
import json
import tempfile
from pathlib import Path

# File: scripts/tests/integration/test_init_multi_volume.py
# Path bug to avoid: do NOT append "/scripts" — parents[2] IS the scripts dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from init_project import init_project


def test_init_writes_multi_volume_outline_when_volumes_provided():
    """When volume_skeleton provided, 总纲.md has one row per volume + state.json has volumes[]."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        init_project(
            project_dir=str(project_path),
            title="Test",
            genre="玄幻",
            target_chapters=300,
            target_words=900000,
            # 3 confirmed volumes
            volume_skeleton=[
                {"index": 1, "title": "起势", "chapter_range": [1, 80],
                 "core_conflict": "宗门考核", "climax": "夺得首席",
                 "status": "confirmed", "source": "human"},
                {"index": 2, "title": "深入", "chapter_range": [81, 180],
                 "core_conflict": "敌派入侵", "climax": "师尊受伤",
                 "status": "confirmed", "source": "human"},
                {"index": 3, "title": "反转", "chapter_range": [181, 300],
                 "core_conflict": "身份揭露", "climax": "退宗",
                 "status": "confirmed", "source": "human"},
            ],
        )
        # state.json should contain all 3 volumes
        state = json.loads((project_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
        assert len(state["volumes"]) == 3
        assert state["volumes"][0]["title"] == "起势"
        assert state["project_info"]["confirmed_through_volume"] == 3

        # 总纲 should have 3 rows
        outline = (project_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
        assert "### 第1卷" in outline
        assert "### 第2卷" in outline
        assert "### 第3卷" in outline

        # planning_horizon defaults per spec §4.1
        assert state["project_info"]["later_volumes_status"] == "deferred"


def test_init_no_volumes_writes_empty_outline():
    """When volume_skeleton is None, no volumes in state.json and no V2+ rows pre-generated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        init_project(
            project_dir=str(project_path),
            title="Test",
            genre="玄幻",
            target_chapters=300,
            target_words=900000,
            volume_skeleton=None,
        )
        state = json.loads((project_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
        assert state["volumes"] == []
        assert state["project_info"]["confirmed_through_volume"] == 0

        outline = (project_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
        # No pre-generated V2-VN rows
        assert "### 第2卷" not in outline

        # planning_horizon defaults per spec §4.1
        assert state["project_info"]["later_volumes_status"] == "deferred"


def test_init_single_volume_does_not_fabricate_v2():
    """V1-only case: V2 row must not appear in 总纲 (spec §7 key invariant)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        init_project(
            project_dir=str(project_path),
            title="Single V1",
            genre="都市",
            target_chapters=100,
            target_words=300000,
            volume_skeleton=[
                {"index": 1, "title": "起势", "chapter_range": [1, 100],
                 "core_conflict": "入门", "climax": "独立",
                 "status": "confirmed", "source": "human"},
            ],
        )
        state = json.loads((project_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
        assert len(state["volumes"]) == 1
        assert state["project_info"]["confirmed_through_volume"] == 1
        assert state["project_info"]["later_volumes_status"] == "deferred"

        outline = (project_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
        assert "### 第1卷" in outline
        assert "### 第2卷" not in outline  # not pre-generated


def test_init_rejects_hole_in_skeleton():
    """Skeleton with index gap (e.g. [1, 3]) must raise ValueError (spec §4.2)."""
    import pytest
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        with pytest.raises(ValueError):
            init_project(
                project_dir=str(project_path),
                title="Hole",
                genre="玄幻",
                target_chapters=100,
                target_words=300000,
                volume_skeleton=[
                    {"index": 1, "title": "V1", "chapter_range": [1, 50],
                     "core_conflict": "A", "climax": "B",
                     "status": "confirmed", "source": "human"},
                    {"index": 3, "title": "V3", "chapter_range": [81, 100],
                     "core_conflict": "X", "climax": "Y",
                     "status": "confirmed", "source": "human"},
                ],
            )


def test_init_rejects_invalid_status():
    """Invalid status string in skeleton must raise ValueError (fail-fast)."""
    import pytest
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        with pytest.raises(ValueError):
            init_project(
                project_dir=str(project_path),
                title="BadStatus",
                genre="玄幻",
                target_chapters=100,
                target_words=300000,
                volume_skeleton=[
                    {"index": 1, "title": "V1", "chapter_range": [1, 100],
                     "core_conflict": "A", "climax": "B",
                     "status": "INVALID_ENUM_VALUE", "source": "human"},
                ],
            )


# ===== Issue 1 (Critical): re-init must not silently overwrite confirmed volumes =====


def test_init_rejects_reinit_when_confirmed_volumes_exist():
    """Spec invariant: re-init on a project with confirmed volumes must refuse."""
    import pytest
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        # First init: confirm V1
        init_project(
            project_dir=str(project_path),
            title="First",
            genre="玄幻",
            target_chapters=100,
            target_words=300000,
            volume_skeleton=[
                {"index": 1, "title": "V1", "chapter_range": [1, 100],
                 "core_conflict": "A", "climax": "B",
                 "status": "confirmed", "source": "human"},
            ],
        )
        # Second init: must refuse
        with pytest.raises(ValueError, match="Refusing to re-init"):
            init_project(
                project_dir=str(project_path),
                title="Second",
                genre="玄幻",
                target_chapters=100,
                target_words=300000,
                volume_skeleton=[
                    {"index": 1, "title": "V1-改", "chapter_range": [1, 100],
                     "core_conflict": "X", "climax": "Y",
                     "status": "confirmed", "source": "human"},
                ],
            )


def test_init_reinit_with_force_overrides():
    """force=True allows re-init even when confirmed volumes exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        init_project(
            project_dir=str(project_path),
            title="First",
            genre="玄幻",
            target_chapters=100,
            target_words=300000,
            volume_skeleton=[
                {"index": 1, "title": "V1", "chapter_range": [1, 100],
                 "core_conflict": "A", "climax": "B",
                 "status": "confirmed", "source": "human"},
            ],
        )
        # force=True should bypass guard
        init_project(
            project_dir=str(project_path),
            title="Second",
            genre="玄幻",
            target_chapters=100,
            target_words=300000,
            force=True,
        )


# ===== Issue 11 (Important): markdown escape in _render_volume_skeleton_outline =====


def test_init_renders_markdown_escaping_for_table_breaking_chars():
    """Pipe character in user-supplied title must be escaped to avoid breaking tables."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        init_project(
            project_dir=str(project_path),
            title="Esc",
            genre="玄幻",
            target_chapters=100,
            target_words=300000,
            volume_skeleton=[
                {"index": 1, "title": "V1|A", "chapter_range": [1, 100],
                 "core_conflict": "C|D", "climax": "X|Y",
                 "status": "confirmed", "source": "human"},
            ],
        )
        outline = (project_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
        # Pipe characters must be escaped with backslash
        assert "V1\\|A" in outline
        assert "C\\|D" in outline
        assert "X\\|Y" in outline
