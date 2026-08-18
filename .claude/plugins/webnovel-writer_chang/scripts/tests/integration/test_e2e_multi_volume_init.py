"""End-to-end smoke test: init with multi-volume skeleton + verify final shape."""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from init_project import init_project


def test_e2e_3_volume_project():
    """Full multi-volume init: state.json shape + 总纲 rows + no fabricated details."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        init_project(
            project_dir=str(project_path),
            title="E2E Test",
            genre="修仙",
            target_chapters=240,
            target_words=720000,
            volume_skeleton=[
                {"index": 1, "title": "出村", "chapter_range": [1, 80],
                 "core_conflict": "宗门入门考核", "climax": "夺得内门资格",
                 "key_cool_points": ["首战告捷"],
                 "status": "confirmed", "source": "human"},
                {"index": 2, "title": "深入", "chapter_range": [81, 160],
                 "core_conflict": "敌派渗透", "climax": "师尊负伤",
                 "status": "confirmed", "source": "human"},
                {"index": 3, "title": "反转", "chapter_range": [161, 240],
                 "core_conflict": "身世揭露", "climax": "退宗出走",
                 "status": "confirmed", "source": "human"},
            ],
        )

        # Verify state.json shape
        state = json.loads((project_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
        assert len(state["volumes"]) == 3
        assert state["project_info"]["confirmed_through_volume"] == 3
        assert state["project_info"]["later_volumes_status"] == "deferred"

        # Verify 总纲 has all 3 volumes
        outline = (project_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
        for i in range(1, 4):
            assert f"### 第{i}卷" in outline

        # Verify no auto-generated detailed outline for V2, V3
        assert not (project_path / "大纲" / "第2卷-详细大纲.md").exists()
        assert not (project_path / "大纲" / "第3卷-详细大纲.md").exists()


def test_e2e_user_stops_at_v1():
    """User explicitly defers V2+: only V1 in state, no V2 stub."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        init_project(
            project_dir=str(project_path),
            title="Single Vol",
            genre="都市",
            target_chapters=100,
            target_words=300000,
            volume_skeleton=[
                {"index": 1, "title": "V1", "chapter_range": [1, 100],
                 "core_conflict": "A", "climax": "B",
                 "status": "confirmed", "source": "human"},
            ],
        )
        state = json.loads((project_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
        assert len(state["volumes"]) == 1
        assert state["project_info"]["confirmed_through_volume"] == 1

        outline = (project_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
        assert "### 第1卷" in outline
        assert "### 第2卷" not in outline  # NOT pre-filled