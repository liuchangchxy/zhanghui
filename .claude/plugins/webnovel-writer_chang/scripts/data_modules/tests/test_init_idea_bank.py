#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import json


def _minimal_schema() -> dict:
    """Minimal valid init_reference_research schema for tree builder tests."""
    return {
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "reader_promise": "",
        "opening_hook_patterns": [],
        "cool_point_loops": [],
        "protagonist_patterns": "",
        "antagonist_pressure_patterns": "",
        "pacing_notes": "",
        "narrative_function": "",
        "boundary_reason": {},
        "protagonist_action_chain": [],
        "emotion_curve": [],
        "satisfaction_point": [],
        "foreshadowing": [],
        "gains_costs": [],
        "character_changes": [],
        "borrowable_structures": [],
        "differentiation_requirements": "",
        "init_candidates": {},
        "do_not_copy": [],
        "canon_contamination_warnings": [],
        "quality": {"passed": True, "confidence": 0.5, "coverage": 0.5},
    }


# --- Lite plan Task 3: 4 base validation tests ---

def test_validate_idea_bank_accepts_minimal_valid_payload():
    from init_project import _validate_idea_bank_payload
    payload = {
        "version": 1,
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {"title": "", "one_liner": "", "anti_trope": "", "hard_constraints": []},
        "constraints_inherited": {"anti_trope": "", "hard_constraints": [], "protagonist_flaw": "", "antagonist_mirror": "", "opening_hook": ""},
        "borrowed_patterns": [],
        "do_not_copy": [],
        "canon_contamination_warnings": [],
    }
    parsed = _validate_idea_bank_payload(json.dumps(payload))
    assert parsed["version"] == 1
    assert parsed["source"]["reference_title"] == "X"


def test_validate_idea_bank_rejects_non_object():
    from init_project import _validate_idea_bank_payload
    with pytest.raises(ValueError, match="must be a JSON object"):
        _validate_idea_bank_payload('"just a string"')


def test_validate_idea_bank_rejects_wrong_version():
    from init_project import _validate_idea_bank_payload
    bad = {"version": 2, "source": {}, "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": []}
    with pytest.raises(ValueError, match="version"):
        _validate_idea_bank_payload(json.dumps(bad))


def test_validate_idea_bank_rejects_bad_reference_source_enum():
    from init_project import _validate_idea_bank_payload
    bad = {
        "version": 1,
        "source": {"reference_title": "X", "reference_source": "BAD_ENUM", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": []
    }
    with pytest.raises(ValueError, match="reference_source"):
        _validate_idea_bank_payload(json.dumps(bad))


# --- P0-Full Task 5: 2 new tests for optional field ---

def test_validate_idea_bank_accepts_optional_reference_research_path():
    from init_project import _validate_idea_bank_payload
    payload = {
        "version": 1,
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {"title": "", "one_liner": "", "anti_trope": "", "hard_constraints": []},
        "constraints_inherited": {"anti_trope": "", "hard_constraints": [], "protagonist_flaw": "", "antagonist_mirror": "", "opening_hook": ""},
        "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
        "reference_research_path": ".webnovel/reference_research/foo/",
    }
    parsed = _validate_idea_bank_payload(json.dumps(payload))
    assert parsed["reference_research_path"] == ".webnovel/reference_research/foo/"


def test_validate_idea_bank_accepts_missing_reference_research_path():
    """Backward compatibility: existing payloads without the field still validate."""
    from init_project import _validate_idea_bank_payload
    payload = {
        "version": 1,
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
    }
    parsed = _validate_idea_bank_payload(json.dumps(payload))
    assert "reference_research_path" not in parsed


# --- P0-Full Task 6: 4 new tests for --reference-research-dir / --reference-overwrite ---

def test_init_validates_reference_research_dir_when_flag_present(tmp_path, monkeypatch):
    """With --reference-research-dir pointing to a valid pre-built tree, init succeeds."""
    import init_project as init_project_module
    from init_reference_tree import build_reference_tree

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"

    # Build a valid tree in a separate location
    source_tree_root = tmp_path / "src_ws"
    source_tree_root.mkdir()
    schema = {
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
        "reader_promise": "", "opening_hook_patterns": [], "cool_point_loops": [], "protagonist_patterns": "", "antagonist_pressure_patterns": "", "pacing_notes": "",
        "narrative_function": "", "boundary_reason": {}, "protagonist_action_chain": [], "emotion_curve": [], "satisfaction_point": [], "foreshadowing": [], "gains_costs": [], "character_changes": [],
        "borrowable_structures": [], "differentiation_requirements": "", "init_candidates": {}, "quality": {"passed": True, "confidence": 0.5, "coverage": 0.5},
    }
    tree = build_reference_tree(source_tree_root, schema, "X")

    init_project_module.init_project(
        str(project_root), title="T", genre="仙侠", protagonist_name="P",
        reference_research_dir=str(tree),
    )
    # Tree should have been copied (or at least validated) — assert source tree still validates
    assert (tree / "_schema.json").is_file()
    # Project should have a copy under .webnovel/reference_research/x/
    assert (project_root / ".webnovel" / "reference_research" / "x" / "_schema.json").is_file()


def test_init_refuses_missing_reference_research_dir(tmp_path, monkeypatch):
    """Nonexistent --reference-research-dir triggers hard error."""
    import init_project as init_project_module

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"
    nonexistent = tmp_path / "does_not_exist"

    with pytest.raises(SystemExit):
        init_project_module.init_project(
            str(project_root), title="T", genre="仙侠", protagonist_name="P",
            reference_research_dir=str(nonexistent),
        )


def test_init_refuses_overwrite_existing_reference_research_without_force(tmp_path, monkeypatch):
    """Existing tree without --reference-overwrite refuses to overwrite."""
    import init_project as init_project_module
    from init_reference_tree import build_reference_tree
    import shutil

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"

    schema = {
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
        "reader_promise": "", "opening_hook_patterns": [], "cool_point_loops": [], "protagonist_patterns": "", "antagonist_pressure_patterns": "", "pacing_notes": "",
        "narrative_function": "", "boundary_reason": {}, "protagonist_action_chain": [], "emotion_curve": [], "satisfaction_point": [], "foreshadowing": [], "gains_costs": [], "character_changes": [],
        "borrowable_structures": [], "differentiation_requirements": "", "init_candidates": {}, "quality": {"passed": True, "confidence": 0.5, "coverage": 0.5},
    }
    src_tree = build_reference_tree(tmp_path / "src", schema, "X")
    project_root.mkdir()
    target_tree = project_root / ".webnovel" / "reference_research" / "x"
    # Pre-create the target tree by copying src_tree
    shutil.copytree(src_tree, target_tree)
    sentinel = target_tree / "_schema.json"

    with pytest.raises(SystemExit):
        init_project_module.init_project(
            str(project_root), title="T", genre="仙侠", protagonist_name="P",
            reference_research_dir=str(src_tree),
        )

    # Original sentinel should be unchanged
    assert sentinel.read_text(encoding="utf-8") == src_tree.joinpath("_schema.json").read_text(encoding="utf-8")


def test_init_refuses_symlink_reference_research_dir(tmp_path, monkeypatch):
    """Symlink at --reference-research-dir target raises SystemExit."""
    import init_project as init_project_module
    from init_reference_tree import build_reference_tree
    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)

    # Create a real reference_research tree, then a symlink pointing to it.
    # When the user passes the symlink path as --reference-research-dir, init
    # MUST refuse with a SystemExit mentioning "Symlink" (C3 fix).
    real_tree = tmp_path / "real_book"
    real_tree.mkdir()
    schema = _minimal_schema()
    real_tree_path = build_reference_tree(real_tree, schema, "X")  # creates real_tree/X/

    # Pass --reference-research-dir through a symlink — this is the actual C3 attack vector
    symlink_target = tmp_path / "link_to_real"
    symlink_target.symlink_to(real_tree_path)

    project_root = tmp_path / "book"
    with pytest.raises(SystemExit, match="[Ss]ymlink"):
        init_project_module.init_project(
            str(project_root), title="T", genre="仙侠", protagonist_name="P",
            reference_research_dir=str(symlink_target),
        )


def test_init_overwrite_preserves_old_schema_outside_target(tmp_path, monkeypatch):
    """--reference-overwrite must preserve old _schema.json OUTSIDE target_tree."""
    import init_project as init_project_module
    from init_reference_tree import build_reference_tree
    import shutil, json as _json

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)

    schema_v1 = _minimal_schema()
    schema_v1["reader_promise"] = "VERSION_1"
    schema_v2 = _minimal_schema()
    schema_v2["reader_promise"] = "VERSION_2"

    project_root = tmp_path / "book"
    project_root.mkdir()
    # Pre-build v1 in target
    target = project_root / ".webnovel" / "reference_research" / "x"
    build_reference_tree(project_root, schema_v1, "X")

    # Build v2 in separate source dir
    src_v2_root = tmp_path / "src2"
    src_v2_root.mkdir()
    src_v2 = build_reference_tree(src_v2_root, schema_v2, "X")

    # Run init with --reference-overwrite
    init_project_module.init_project(
        str(project_root), title="T", genre="仙侠", protagonist_name="P",
        reference_research_dir=str(src_v2),
        reference_overwrite=True,
    )

    # Old _schema.json must be preserved SOMEWHERE (not in target which is overwritten)
    # Check backup directory or in-place backup pattern
    target_schema = _json.loads((target / "_schema.json").read_text(encoding="utf-8"))
    assert target_schema["reader_promise"] == "VERSION_2"  # new is in target

    # Old must be preserved — check backups/ or in-place .bak
    backups_dir = project_root / ".webnovel" / "backups"
    has_backup = (
        backups_dir.exists() and any(backups_dir.glob("*x*"))
        or any(target.parent.glob("*.bak-*"))
        or any(target.glob("_schema.json.bak-*"))
    )
    assert has_backup, "old _schema.json must be preserved in backup location"


def test_init_overwrites_with_explicit_force_flag(tmp_path, monkeypatch):
    """With --reference-overwrite, the diff path overwrites."""
    import init_project as init_project_module
    from init_reference_tree import build_reference_tree
    import shutil
    import json as _json

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"

    schema_v1 = {
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
        "reader_promise": "VERSION_1", "opening_hook_patterns": [], "cool_point_loops": [], "protagonist_patterns": "", "antagonist_pressure_patterns": "", "pacing_notes": "",
        "narrative_function": "", "boundary_reason": {}, "protagonist_action_chain": [], "emotion_curve": [], "satisfaction_point": [], "foreshadowing": [], "gains_costs": [], "character_changes": [],
        "borrowable_structures": [], "differentiation_requirements": "", "init_candidates": {}, "quality": {"passed": True, "confidence": 0.5, "coverage": 0.5},
    }
    schema_v2 = dict(schema_v1)
    schema_v2["reader_promise"] = "VERSION_2"

    src_v1 = build_reference_tree(tmp_path / "src1", schema_v1, "X")
    src_v2 = build_reference_tree(tmp_path / "src2", schema_v2, "X")

    project_root.mkdir()
    target = project_root / ".webnovel" / "reference_research" / "x"
    shutil.copytree(src_v1, target)

    init_project_module.init_project(
        str(project_root), title="T", genre="仙侠", protagonist_name="P",
        reference_research_dir=str(src_v2),
        reference_overwrite=True,
    )

    written = _json.loads((target / "_schema.json").read_text(encoding="utf-8"))
    assert written["reader_promise"] == "VERSION_2"
