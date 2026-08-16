#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import json


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