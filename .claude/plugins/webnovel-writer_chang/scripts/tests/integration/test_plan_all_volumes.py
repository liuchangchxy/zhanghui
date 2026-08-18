"""Spec 2026-08-19 §6.2: --all-volumes mode generates N volume blueprint triplets."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from init_project import init_project, generate_volume_blueprints


def _init_project_with_3_vols(tmp_path):
    init_project(
        project_dir=str(tmp_path),
        title="All Volumes Test",
        genre="玄幻",
        target_chapters=240,
        target_words=720000,
        volume_skeleton=[
            {"index": 1, "title": "V1", "chapter_range": [1, 80],
             "core_conflict": "A", "climax": "B",
             "status": "confirmed", "source": "human"},
            {"index": 2, "title": "V2", "chapter_range": [81, 160],
             "core_conflict": "C", "climax": "D",
             "status": "confirmed", "source": "human"},
            {"index": 3, "title": "V3", "chapter_range": [161, 240],
             "core_conflict": "E", "climax": "F",
             "status": "confirmed", "source": "human"},
        ],
    )


def test_generate_volume_blueprints_creates_3_triplets(tmp_path):
    """--all-volumes mode: 3 confirmed volumes → 3 blueprint triplets."""
    _init_project_with_3_vols(tmp_path)
    written = generate_volume_blueprints(tmp_path, all_volumes=True)
    assert written == 3
    # Each volume gets 详细大纲 + 15节拍 + 时间线
    for vol in (1, 2, 3):
        assert (tmp_path / "大纲" / f"第{vol}卷-详细大纲.md").is_file()
        assert (tmp_path / "大纲" / f"第{vol}卷-15节拍.md").is_file()
        assert (tmp_path / "大纲" / f"第{vol}卷-时间线.md").is_file()


def test_generate_volume_blueprints_default_no_op(tmp_path):
    """Default (all_volumes=False) must NOT create any per-volume blueprints (regression)."""
    _init_project_with_3_vols(tmp_path)
    written = generate_volume_blueprints(tmp_path, all_volumes=False)
    assert written == 0
    for vol in (1, 2, 3):
        assert not (tmp_path / "大纲" / f"第{vol}卷-详细大纲.md").exists()


def test_generate_volume_blueprints_skips_deferred(tmp_path):
    """Only confirmed volumes get blueprints; deferred ones are skipped."""
    init_project(
        project_dir=str(tmp_path),
        title="Deferred Test", genre="玄幻",
        target_chapters=160, target_words=480000,
        volume_skeleton=[
            {"index": 1, "title": "V1", "chapter_range": [1, 80],
             "core_conflict": "A", "climax": "B",
             "status": "confirmed", "source": "human"},
            {"index": 2, "title": "V2-deferred", "chapter_range": [81, 160],
             "core_conflict": "C", "climax": "D",
             "status": "deferred", "source": "human"},
        ],
    )
    written = generate_volume_blueprints(tmp_path, all_volumes=True)
    # Only V1 confirmed → only V1 blueprint triplet
    assert written == 1
    assert (tmp_path / "大纲" / "第1卷-详细大纲.md").is_file()
    assert not (tmp_path / "大纲" / "第2卷-详细大纲.md").exists()
