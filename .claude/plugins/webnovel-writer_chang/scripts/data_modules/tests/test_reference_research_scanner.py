#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pytest


def test_scanner_finds_valid_trees(tmp_path):
    """Scanner returns all valid reference_research trees in project."""
    from data_modules.reference_research_scanner import scan_reference_research_trees
    import init_reference_tree

    schema = {"source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
              "reader_promise": "", "opening_hook_patterns": [], "cool_point_loops": [],
              "protagonist_patterns": "", "antagonist_pressure_patterns": "", "pacing_notes": "",
              "narrative_function": "", "boundary_reason": {}, "protagonist_action_chain": [],
              "emotion_curve": [], "satisfaction_point": [], "foreshadowing": [],
              "gains_costs": [], "character_changes": [], "borrowable_structures": [],
              "differentiation_requirements": "", "init_candidates": {},
              "do_not_copy": [], "canon_contamination_warnings": [],
              "quality": {"passed": True, "confidence": 0.5, "coverage": 0.5}}
    init_reference_tree.build_reference_tree(tmp_path, schema, "A")
    init_reference_tree.build_reference_tree(tmp_path, schema, "B")

    trees = scan_reference_research_trees(tmp_path)
    assert len(trees) == 2
    assert any("a" in str(t) for t in trees)
    assert any("b" in str(t) for t in trees)


def test_scanner_filters_invalid_paths(tmp_path):
    """Scanner skips directories missing required files."""
    from data_modules.reference_research_scanner import scan_reference_research_trees
    import init_reference_tree

    schema = {"source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
              "reader_promise": "", "opening_hook_patterns": [], "cool_point_loops": [],
              "protagonist_patterns": "", "antagonist_pressure_patterns": "", "pacing_notes": "",
              "narrative_function": "", "boundary_reason": {}, "protagonist_action_chain": [],
              "emotion_curve": [], "satisfaction_point": [], "foreshadowing": [],
              "gains_costs": [], "character_changes": [], "borrowable_structures": [],
              "differentiation_requirements": "", "init_candidates": {},
              "do_not_copy": [], "canon_contamination_warnings": [],
              "quality": {"passed": True, "confidence": 0.5, "coverage": 0.5}}
    init_reference_tree.build_reference_tree(tmp_path, schema, "valid")

    # Create invalid dir (no _schema.json)
    invalid = tmp_path / ".webnovel" / "reference_research" / "invalid"
    invalid.mkdir(parents=True)
    (invalid / "report.md").write_text("garbage", encoding="utf-8")

    trees = scan_reference_research_trees(tmp_path)
    assert len(trees) == 1
    assert "valid" in str(trees[0])


def test_scanner_returns_empty_when_no_dir(tmp_path):
    """Scanner returns [] when .webnovel/reference_research doesn't exist."""
    from data_modules.reference_research_scanner import scan_reference_research_trees
    trees = scan_reference_research_trees(tmp_path)
    assert trees == []


def test_scanner_validates_idea_bank_pointer():
    from data_modules.reference_research_scanner import validate_idea_bank_pointer

    assert validate_idea_bank_pointer(".webnovel/reference_research/foo/") == ".webnovel/reference_research/foo/"
    with pytest.raises(ValueError, match="absolute"):
        validate_idea_bank_pointer("/etc/passwd")
    with pytest.raises(ValueError, match=r"\.\."):
        validate_idea_bank_pointer("../etc/passwd")
    with pytest.raises(ValueError, match="string"):
        validate_idea_bank_pointer(123)
    with pytest.raises(ValueError, match="string"):
        validate_idea_bank_pointer(None)