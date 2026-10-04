#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pytest


def test_schema_version_required():
    """Payload missing schema_version raises ValueError."""
    from data_modules.marked_references import validate_marked_references
    with pytest.raises(ValueError, match="schema_version"):
        validate_marked_references({"references": []})


def test_minimal_valid_payload():
    """Minimal valid payload: {schema_version: 1, references: []}."""
    from data_modules.marked_references import validate_marked_references
    payload = {"schema_version": 1, "references": []}
    parsed = validate_marked_references(payload)
    assert parsed["schema_version"] == 1
    assert parsed["references"] == []


def test_reference_must_have_platform_and_title():
    """Reference missing platform or title raises ValueError."""
    from data_modules.marked_references import validate_marked_references
    with pytest.raises(ValueError, match="platform"):
        validate_marked_references({"schema_version": 1, "references": [{"title": "X"}]})
    with pytest.raises(ValueError, match="title"):
        validate_marked_references({"schema_version": 1, "references": [{"platform": "qidian"}]})


def test_roundtrip_via_disk(tmp_path):
    """write_marked_references + load_marked_references round-trip preserves data."""
    from data_modules.marked_references import write_marked_references, load_marked_references
    path = tmp_path / "marked-references.json"
    payload = {
        "schema_version": 1,
        "marked_at": "2026-08-16T12:34:56Z",
        "references": [
            {"platform": "qidian", "title": "凡人修仙传", "author": "忘语", "category": "仙侠"},
        ],
    }
    write_marked_references(payload, path)
    loaded = load_marked_references(path)
    assert loaded == payload


def test_load_returns_none_if_file_missing(tmp_path):
    """load_marked_references returns None when file absent (not error)."""
    from data_modules.marked_references import load_marked_references
    result = load_marked_references(tmp_path / "does_not_exist.json")
    assert result is None


# --- P0-Full Adversarial I1: strict type validation ---

def test_marked_references_rejects_empty_string_title():
    """I1: Empty-string title must raise ValueError mentioning 'title'."""
    from data_modules.marked_references import validate_marked_references
    with pytest.raises(ValueError, match="title"):
        validate_marked_references({"schema_version": 1, "references": [{"platform": "qidian", "title": ""}]})


def test_marked_references_rejects_whitespace_only_title():
    """I1: Whitespace-only title must raise ValueError mentioning 'title'."""
    from data_modules.marked_references import validate_marked_references
    with pytest.raises(ValueError, match="title"):
        validate_marked_references({"schema_version": 1, "references": [{"platform": "qidian", "title": "   "}]})


def test_marked_references_rejects_non_string_platform():
    """I1: Non-string platform (e.g. integer) must raise ValueError mentioning 'platform'."""
    from data_modules.marked_references import validate_marked_references
    with pytest.raises(ValueError, match="platform"):
        validate_marked_references({"schema_version": 1, "references": [{"platform": 123, "title": "X"}]})
