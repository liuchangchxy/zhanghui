"""Story Craft state.json field operations.

Handles all read/write operations for the story_craft top-level field
introduced in 2026-08-14 story-craft-engine design.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StoryCraftFieldError(Exception):
    """Raised when state.json story_craft field is malformed."""


EMPTY_STORY_CRAFT: dict[str, Any] = {
    "rhythm_curve": {
        "last_emotion_peak_chapter": 0,
        "chapters_since_peak": 0,
        "warning_threshold": 3,
        "block_threshold": 5,
        "history": []
    },
    "foreshadow_chain": [],
    "timed_locks": [],
    "thematic_echoes": [],
    "character_arc": None
}


def _load_state(path: str | Path) -> dict:
    """Load state.json from path."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"state.json not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def init_story_craft(path: str | Path) -> dict:
    """Initialize story_craft field if missing; return full state.

    Idempotent: preserves existing story_craft content.
    Preserves all other state.json fields.

    Note: This function loads and mutates in-memory only. Caller is responsible
    for writing the result back to disk (use security_utils.atomic_write_json).
    """
    state = _load_state(path)
    if "story_craft" not in state:
        state["story_craft"] = json.loads(json.dumps(EMPTY_STORY_CRAFT))
    elif not isinstance(state["story_craft"], dict):
        raise StoryCraftFieldError("story_craft is not a dict")
    return state