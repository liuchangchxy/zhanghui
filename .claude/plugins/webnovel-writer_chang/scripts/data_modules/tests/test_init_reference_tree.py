#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pytest


def _minimal_schema() -> dict:
    """Minimal valid init_reference_research JSON for tree builder tests."""
    return {
        "source": {"reference_title": "《测试书》", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.9},
        "reader_promise": "测试读者承诺",
        "opening_hook_patterns": ["钩子A", "钩子B"],
        "cool_point_loops": ["爽点循环A"],
        "protagonist_patterns": "主角原型A",
        "antagonist_pressure_patterns": "反派压力A",
        "pacing_notes": "节奏备注A",
        "narrative_function": "升级流",
        "boundary_reason": {"first_arc_start": 1, "first_arc_end": 5, "reason": "前期铺垫"},
        "protagonist_action_chain": [{"trigger": "T1", "action": "A1", "result": "R1"}],
        "emotion_curve": [{"chapter": 1, "intensity": 0.7, "label": "紧张"}],
        "satisfaction_point": ["亮点1"],
        "foreshadowing": [{"setup_chapter": 1, "payoff_chapter_estimate": 5, "content": "伏笔A"}],
        "gains_costs": [{"chapter": 1, "gain": "实力+", "cost": "认知-", "category": "实力"}],
        "character_changes": [{"chapter": 1, "character": "主角", "before": "弱", "after": "觉醒"}],
        "borrowable_structures": ["结构A"],
        "differentiation_requirements": "差异化要求A",
        "init_candidates": {
            "one_liner": "一句话",
            "anti_trope": "反套路",
            "hard_constraints": ["硬约束1"],
            "protagonist_flaw": "缺陷",
            "antagonist_mirror": "镜像",
            "opening_hook": "钩子",
        },
        "do_not_copy": ["不要抄人物名"],
        "canon_contamination_warnings": ["原作人物名:张三"],
        "quality": {"passed": True, "confidence": 0.9, "coverage": 0.85},
    }


def test_sanitize_book_title_basic():
    from init_reference_tree import sanitize_book_title
    assert sanitize_book_title("《凡人修仙传》") == "fanren-xiuxian-chuan"
    assert sanitize_book_title("My Book Title") == "my-book-title"


def test_sanitize_book_title_empty_raises():
    from init_reference_tree import sanitize_book_title
    with pytest.raises(ValueError):
        sanitize_book_title("///")


def test_sanitize_book_title_max_length():
    from init_reference_tree import sanitize_book_title
    long = "a" * 100
    assert len(sanitize_book_title(long)) <= 64


def test_build_reference_tree_creates_all_files(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    tree = build_reference_tree(tmp_path, schema, "《测试书》")

    assert tree.is_dir()
    assert (tree / "_schema.json").is_file()
    assert (tree / "report.md").is_file()
    assert (tree / "do_not_copy.md").is_file()
    assert (tree / "canon_contamination_warnings.md").is_file()
    assert (tree / "_progress.json").is_file()
    assert not (tree / "opening_chapters").exists()  # No excerpts → skip


def test_build_reference_tree_schema_is_verbatim(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    tree = build_reference_tree(tmp_path, schema, "《测试书》")
    written = json.loads((tree / "_schema.json").read_text(encoding="utf-8"))
    assert written["reader_promise"] == "测试读者承诺"
    assert written["narrative_function"] == "升级流"
    assert written["init_candidates"]["hard_constraints"] == ["硬约束1"]


def test_build_reference_tree_report_contains_sections(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    tree = build_reference_tree(tmp_path, schema, "《测试书》")
    report = (tree / "report.md").read_text(encoding="utf-8")
    assert "拆书报告" in report
    assert "读者承诺" in report
    assert "升级流" in report
    assert "亮点1" in report


def test_build_reference_tree_do_not_copy_verbatim(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    tree = build_reference_tree(tmp_path, schema, "《测试书》")
    dnc = (tree / "do_not_copy.md").read_text(encoding="utf-8")
    assert "不要抄人物名" in dnc


def test_build_reference_tree_progress_has_version(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    tree = build_reference_tree(tmp_path, schema, "《测试书》")
    progress = json.loads((tree / "_progress.json").read_text(encoding="utf-8"))
    assert progress["schema_version"] == 1
    assert progress["reference_title"] == "《测试书》"
    assert progress["quality_flags"]["passed"] is True


def test_validate_reference_tree_accepts_valid_tree(tmp_path):
    from init_reference_tree import build_reference_tree, validate_reference_tree

    schema = _minimal_schema()
    tree = build_reference_tree(tmp_path, schema, "《测试书》")
    assert validate_reference_tree(tree) is True


def test_validate_reference_tree_rejects_missing_files(tmp_path):
    from init_reference_tree import validate_reference_tree
    assert validate_reference_tree(tmp_path) is False


def test_build_reference_tree_refuses_overwrite_without_flag(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    build_reference_tree(tmp_path, schema, "《测试书》")
    with pytest.raises(FileExistsError):
        build_reference_tree(tmp_path, schema, "《测试书》")


def test_build_reference_tree_with_minimal_init_candidates():
    """init_candidates must be an OBJECT (not a list) for template to render."""
    from init_reference_tree import build_reference_tree
    import json, pathlib, tempfile
    schema = _minimal_schema()
    # Schema's _minimal_schema() already uses init_candidates as object — verify it stays so
    assert isinstance(schema["init_candidates"], dict), \
        "_minimal_schema() fixture must use OBJECT init_candidates (not list)"

    with tempfile.TemporaryDirectory() as td:
        tree = build_reference_tree(pathlib.Path(td), schema, "X")
        report = (tree / "report.md").read_text(encoding="utf-8")
        # Must contain the actual values (not empty due to type mismatch)
        assert "一句话" in report, "report.md must render init_candidates.one_liner value"
        assert "硬约束1" in report, "report.md must render init_candidates.hard_constraints items"


def test_build_reference_tree_refuses_symlink_target(tmp_path):
    """Symlink at target path raises SystemExit."""
    from init_reference_tree import build_reference_tree
    # Pre-create a symlink at the final tree path: <project>/.webnovel/reference_research/<safe>
    real_dir = tmp_path / "real_target"
    real_dir.mkdir()
    sym_target = tmp_path / "project" / ".webnovel" / "reference_research" / "x"
    sym_target.parent.mkdir(parents=True)
    sym_target.symlink_to(real_dir)

    schema = _minimal_schema()
    with pytest.raises(SystemExit, match="[Ss]ymlink"):
        build_reference_tree(tmp_path / "project", schema, "X")


def test_build_reference_tree_overwrites_with_flag(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    build_reference_tree(tmp_path, schema, "《测试书》")
    # Should not raise
    tree = build_reference_tree(tmp_path, schema, "《测试书》", overwrite=True)
    assert tree.is_dir()
