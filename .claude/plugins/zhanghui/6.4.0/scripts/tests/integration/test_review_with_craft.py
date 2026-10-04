"""Integration test: review_pipeline.run_craft_checks pulls in story_craft checks."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 让 import 能找到 review_pipeline.py 和 story_craft.py
_SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS / "data_modules"))

from story_craft import (
    init_story_craft,
    add_foreshadow,
    add_timed_lock,
    record_emotion_peak,
    set_chapter_meta,
)
from review_pipeline import run_craft_checks


# init_story_craft() requires a real file on disk. Provide a fixture path.
_DUMMY_STATE = Path("/tmp/dummy.json")


def _ensure_dummy_state() -> Path:
    """Create /tmp/dummy.json with minimal content if missing."""
    if not _DUMMY_STATE.exists():
        _DUMMY_STATE.write_text(
            json.dumps({"project_info": {}, "progress": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
    return _DUMMY_STATE


def test_run_craft_checks_flags_missing_hook():
    _ensure_dummy_state()
    state = init_story_craft(str(_DUMMY_STATE))
    state["chapter_meta"] = {}
    state["chapter_meta"]["1"] = {
        "scene_goal": "ok", "scene_conflict": "ok", "sequel_decision": "ok"
    }
    issues = run_craft_checks(state, chapter=1)
    assert any("hook_type" in b for b in issues["blockers"])


def test_run_craft_checks_flags_overdue_timed_lock():
    _ensure_dummy_state()
    state = init_story_craft(str(_DUMMY_STATE))
    add_timed_lock(state, {"description": "test", "deadline_chapter": 3})
    issues = run_craft_checks(state, chapter=5)
    assert any("定时锁逾期" in b for b in issues["blockers"])


def test_run_craft_checks_flags_rhythm_block():
    _ensure_dummy_state()
    state = init_story_craft(str(_DUMMY_STATE))
    state["story_craft"]["rhythm_curve"]["chapters_since_peak"] = 6
    state["story_craft"]["rhythm_curve"]["block_threshold"] = 5
    issues = run_craft_checks(state, chapter=10)
    assert any("节奏曲线 BLOCK" in b for b in issues["blockers"])