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

from story_craft import (
    init_story_craft,
    StoryCraftFieldError,
    add_foreshadow,
    payoff_foreshadow,
    add_timed_lock,
    fulfill_timed_lock,
    check_timed_lock_deadlines,
    record_emotion_peak,
    check_rhythm_status,
    increment_chapters_since_peak,
)  # noqa: E402


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


def test_add_foreshadow_creates_item():
    state = {"story_craft": {"foreshadow_chain": []}}
    item = {
        "id": "FS-001",
        "type": "物谶",
        "depth": "中层",
        "content": "血玉蜘蛛蛛丝",
        "buried_chapter": 5,
        "expected_payoff_chapter": 25,
        "payoff_method": "虚天鼎钥匙",
        "linked_entities": ["韩立", "血玉蜘蛛"]
    }
    result = add_foreshadow(state, item)
    assert len(result["story_craft"]["foreshadow_chain"]) == 1
    assert result["story_craft"]["foreshadow_chain"][0]["id"] == "FS-001"
    assert result["story_craft"]["foreshadow_chain"][0]["status"] == "active"


def test_add_foreshadow_assigns_next_id():
    state = {"story_craft": {"foreshadow_chain": [{"id": "FS-001"}]}}
    result = add_foreshadow(state, {"type": "物谶", "depth": "表层"})
    assert result["story_craft"]["foreshadow_chain"][1]["id"] == "FS-002"


def test_add_foreshadow_validates_depth():
    state = {"story_craft": {"foreshadow_chain": []}}
    with __import__("pytest").raises(ValueError):
        add_foreshadow(state, {"type": "物谶", "depth": "invalid"})


def test_payoff_foreshadow_marks_paid_off():
    state = {"story_craft": {"foreshadow_chain": [
        {"id": "FS-001", "status": "active"}
    ]}}
    result = payoff_foreshadow(state, "FS-001", chapter=25, quality="强")
    assert result["story_craft"]["foreshadow_chain"][0]["status"] == "paid_off"
    assert result["story_craft"]["foreshadow_chain"][0]["payoff_chapter"] == 25
    assert result["story_craft"]["foreshadow_chain"][0]["payoff_quality"] == "强"


def test_payoff_foreshadow_raises_if_already_paid():
    state = {"story_craft": {"foreshadow_chain": [
        {"id": "FS-001", "status": "paid_off"}
    ]}}
    with __import__("pytest").raises(ValueError):
        payoff_foreshadow(state, "FS-001", chapter=25, quality="强")


def test_add_timed_lock_creates_item():
    state = {"story_craft": {"timed_locks": []}}
    item = {
        "id": "TL-001",
        "description": "玄幻主角 3 章内出村",
        "deadline_chapter": 3
    }
    result = add_timed_lock(state, item)
    assert len(result["story_craft"]["timed_locks"]) == 1
    assert result["story_craft"]["timed_locks"][0]["status"] == "active"


def test_fulfill_timed_lock_marks_done():
    state = {"story_craft": {"timed_locks": [
        {"id": "TL-001", "status": "active"}
    ]}}
    result = fulfill_timed_lock(state, "TL-001", chapter=2)
    assert result["story_craft"]["timed_locks"][0]["status"] == "fulfilled"
    assert result["story_craft"]["timed_locks"][0]["fulfilled_chapter"] == 2


def test_check_timed_lock_deadlines_returns_overdue():
    state = {"story_craft": {"timed_locks": [
        {"id": "TL-001", "deadline_chapter": 3, "status": "active"},
        {"id": "TL-002", "deadline_chapter": 10, "status": "active"},
        {"id": "TL-003", "deadline_chapter": 5, "status": "fulfilled"}
    ]}}
    overdue = check_timed_lock_deadlines(state, current_chapter=7)
    ids = [t["id"] for t in overdue]
    assert "TL-001" in ids
    assert "TL-002" not in ids  # not yet overdue
    assert "TL-003" not in ids  # already fulfilled


def test_record_emotion_peak_resets_counter():
    state = {"story_craft": {"rhythm_curve": {
        "last_emotion_peak_chapter": 5,
        "chapters_since_peak": 3,
        "warning_threshold": 3,
        "block_threshold": 5,
        "history": []
    }}}
    result = record_emotion_peak(state, chapter=8, intensity=7, type_="medium_cool_point")
    assert result["story_craft"]["rhythm_curve"]["last_emotion_peak_chapter"] == 8
    assert result["story_craft"]["rhythm_curve"]["chapters_since_peak"] == 0
    assert len(result["story_craft"]["rhythm_curve"]["history"]) == 1


def test_check_rhythm_returns_warning_when_over_threshold():
    state = {"story_craft": {"rhythm_curve": {
        "last_emotion_peak_chapter": 1,
        "chapters_since_peak": 4,
        "warning_threshold": 3,
        "block_threshold": 5,
        "history": []
    }}}
    status = check_rhythm_status(state)
    assert status == "warning"


def test_check_rhythm_returns_block_when_over_block_threshold():
    state = {"story_craft": {"rhythm_curve": {
        "last_emotion_peak_chapter": 1,
        "chapters_since_peak": 6,
        "warning_threshold": 3,
        "block_threshold": 5,
        "history": []
    }}}
    status = check_rhythm_status(state)
    assert status == "block"


def test_check_rhythm_returns_ok_when_within_threshold():
    state = {"story_craft": {"rhythm_curve": {
        "last_emotion_peak_chapter": 1,
        "chapters_since_peak": 1,
        "warning_threshold": 3,
        "block_threshold": 5,
        "history": []
    }}}
    status = check_rhythm_status(state)
    assert status == "ok"