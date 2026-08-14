"""Tests for story_craft module (story_craft state.json field operations)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# 让 import 能找到 story_craft.py
_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from story_craft import init_story_craft, StoryCraftFieldError  # noqa: E402


def test_init_story_craft_creates_empty_structure():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
        json.dump({"project_info": {}, "progress": {}}, f)
        path = f.name

    try:
        result = init_story_craft(path)
        assert "story_craft" in result
        assert result["story_craft"]["foreshadow_chain"] == []
        assert result["story_craft"]["timed_locks"] == []
        assert result["story_craft"]["rhythm_curve"]["chapters_since_peak"] == 0
        assert result["story_craft"]["thematic_echoes"] == []
        assert result["story_craft"]["character_arc"] is None
    finally:
        Path(path).unlink()


def test_init_story_craft_is_idempotent():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
        json.dump({"project_info": {}, "progress": {}}, f)
        path = f.name

    try:
        first = init_story_craft(path)
        second = init_story_craft(path)
        assert first["story_craft"] == second["story_craft"]
    finally:
        Path(path).unlink()


def test_init_story_craft_preserves_existing():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
        json.dump({
            "project_info": {"title": "Test"},
            "story_craft": {"rhythm_curve": {"chapters_since_peak": 5}}
        }, f)
        path = f.name

    try:
        result = init_story_craft(path)
        assert result["project_info"]["title"] == "Test"
        assert result["story_craft"]["rhythm_curve"]["chapters_since_peak"] == 5
    finally:
        Path(path).unlink()


def test_init_story_craft_raises_file_not_found_when_missing():
    nonexistent = Path(tempfile.gettempdir()) / "definitely_not_a_real_state_file_xyz_12345.json"
    if nonexistent.exists():
        nonexistent.unlink()

    try:
        try:
            init_story_craft(nonexistent)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("Expected FileNotFoundError but no exception was raised")
    finally:
        if nonexistent.exists():
            nonexistent.unlink()


def test_init_story_craft_raises_field_error_when_not_dict():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
        json.dump({"project_info": {}, "story_craft": "not a dict"}, f)
        path = f.name

    try:
        try:
            init_story_craft(path)
        except StoryCraftFieldError:
            pass
        else:
            raise AssertionError("Expected StoryCraftFieldError but no exception was raised")
    finally:
        Path(path).unlink()