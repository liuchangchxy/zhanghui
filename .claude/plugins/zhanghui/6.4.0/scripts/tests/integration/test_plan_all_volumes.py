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
    """--all-volumes mode: 3 confirmed volumes → 9 blueprint files (3 vols × 3 files)."""
    _init_project_with_3_vols(tmp_path)
    written = generate_volume_blueprints(tmp_path, all_volumes=True)
    assert written == 9
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
    # Only V1 confirmed → 3 files (1 vol × 3 files)
    assert written == 3
    assert (tmp_path / "大纲" / "第1卷-详细大纲.md").is_file()
    assert not (tmp_path / "大纲" / "第2卷-详细大纲.md").exists()


# ===== Phase 3 fixes: C1 (idempotent + atomic), C2 (cross_volume_beat_map), I5 (range validation) =====


def test_generate_volume_blueprints_idempotent(tmp_path):
    """C1: running --all-volumes a second time must NOT overwrite existing files."""
    _init_project_with_3_vols(tmp_path)
    first = generate_volume_blueprints(tmp_path, all_volumes=True)
    assert first == 9  # 3 volumes × 3 files

    # Tamper with V1's 详细大纲.md (simulate user edits)
    detailed = tmp_path / "大纲" / "第1卷-详细大纲.md"
    user_content = "USER EDIT\n" + detailed.read_text(encoding="utf-8")
    detailed.write_text(user_content, encoding="utf-8")

    # Second run must NOT overwrite (idempotent)
    second = generate_volume_blueprints(tmp_path, all_volumes=True)
    assert second == 0
    assert detailed.read_text(encoding="utf-8").startswith("USER EDIT")


def test_generate_volume_blueprints_force_overwrites(tmp_path):
    """C1: force=True must overwrite existing files."""
    _init_project_with_3_vols(tmp_path)
    first = generate_volume_blueprints(tmp_path, all_volumes=True)
    assert first == 9

    detailed = tmp_path / "大纲" / "第1卷-详细大纲.md"
    detailed.write_text("USER EDIT\n", encoding="utf-8")

    # force=True should overwrite
    second = generate_volume_blueprints(tmp_path, all_volumes=True, force=True)
    assert second == 9
    # Content replaced by auto-generated
    assert not detailed.read_text(encoding="utf-8").startswith("USER EDIT")


def test_chapter_range_reversed_raises(tmp_path):
    """I5: reversed chapter_range (start > end) must raise before any file write."""
    import pytest
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        '{"project_info": {"target_chapters": 240}, "volumes": [{"index": 1, '
        '"title": "V1", "chapter_range": [80, 1], "core_conflict": "X", '
        '"climax": "Y", "status": "confirmed", "source": "human"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="chapter_range is reversed"):
        generate_volume_blueprints(tmp_path, all_volumes=True)
    # No file should have been written
    outline_dir = tmp_path / "大纲"
    if outline_dir.is_dir():
        assert not list(outline_dir.glob("第1卷-*.md"))


def test_generate_volume_blueprints_writes_cross_volume_beat_map(tmp_path):
    """C2: --all-volumes writes cross_volume_beat_map to state.json with linear
    adjacency (one edge per consecutive confirmed volume pair).
    """
    import json
    _init_project_with_3_vols(tmp_path)
    generate_volume_blueprints(tmp_path, all_volumes=True)
    state = json.loads(
        (tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8")
    )
    beat_map = state["project_info"]["cross_volume_beat_map"]
    # 3 confirmed volumes → 2 edges: 1→2 and 2→3
    assert len(beat_map) == 2
    assert beat_map[0] == {"from": 1, "to": 2, "edge_id": "v1_to_v2"}
    assert beat_map[1] == {"from": 2, "to": 3, "edge_id": "v2_to_v3"}


def test_generate_volume_blueprints_2_vols_one_edge(tmp_path):
    """C2 boundary: 2 confirmed volumes → exactly 1 edge (1→2)."""
    import json
    init_project(
        project_dir=str(tmp_path),
        title="Two Vols", genre="玄幻",
        target_chapters=160, target_words=480000,
        volume_skeleton=[
            {"index": 1, "title": "V1", "chapter_range": [1, 80],
             "core_conflict": "A", "climax": "B",
             "status": "confirmed", "source": "human"},
            {"index": 2, "title": "V2", "chapter_range": [81, 160],
             "core_conflict": "C", "climax": "D",
             "status": "confirmed", "source": "human"},
        ],
    )
    generate_volume_blueprints(tmp_path, all_volumes=True)
    state = json.loads(
        (tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8")
    )
    beat_map = state["project_info"]["cross_volume_beat_map"]
    assert len(beat_map) == 1
    assert beat_map[0] == {"from": 1, "to": 2, "edge_id": "v1_to_v2"}


def test_generate_volume_blueprints_atomic_no_partial_files(tmp_path):
    """C1: atomic write — on a successful run there must be no leftover *.tmp files."""
    _init_project_with_3_vols(tmp_path)
    generate_volume_blueprints(tmp_path, all_volumes=True)
    # No .tmp files anywhere in outline dir
    leftover = list((tmp_path / "大纲").glob("*.tmp"))
    assert leftover == [], f"unexpected tmp leftovers: {leftover}"
