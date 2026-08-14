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


VALID_DEPTHS = {"表层", "中层", "深层"}
VALID_TYPES = {"物谶", "诗谶", "戏谶", "灯谜", "环境", "习惯", "对话双关"}


def _next_foreshadow_id(chain: list) -> str:
    used = {item.get("id", "") for item in chain}
    n = 1
    while f"FS-{n:03d}" in used:
        n += 1
    return f"FS-{n:03d}"


def add_foreshadow(state: dict, item: dict) -> dict:
    """Add foreshadow item to chain. Validates required fields.

    Required: type, depth
    Optional: id (auto-assigned if missing), content, buried_chapter,
              expected_payoff_chapter, payoff_method, linked_entities
    """
    if item.get("depth") not in VALID_DEPTHS:
        raise ValueError(f"depth must be one of {VALID_DEPTHS}, got {item.get('depth')}")
    if item.get("type") not in VALID_TYPES:
        raise ValueError(f"type must be one of {VALID_TYPES}, got {item.get('type')}")

    chain = state.setdefault("story_craft", {}).setdefault("foreshadow_chain", [])
    new_item = {
        "id": item.get("id") or _next_foreshadow_id(chain),
        "type": item["type"],
        "depth": item["depth"],
        "content": item.get("content", ""),
        "buried_chapter": item.get("buried_chapter"),
        "expected_payoff_chapter": item.get("expected_payoff_chapter"),
        "payoff_method": item.get("payoff_method", ""),
        "linked_entities": item.get("linked_entities", []),
        "status": "active",
        "buried_quality": item.get("buried_quality"),
        "payoff_chapter": None,
        "payoff_quality": None,
    }
    chain.append(new_item)
    return state


def payoff_foreshadow(state: dict, foreshadow_id: str, chapter: int, quality: str) -> dict:
    """Mark foreshadow as paid off at given chapter.

    Raises ValueError if not found or already paid off.
    """
    chain = state["story_craft"]["foreshadow_chain"]
    for item in chain:
        if item["id"] == foreshadow_id:
            if item["status"] == "paid_off":
                raise ValueError(f"{foreshadow_id} already paid off")
            item["status"] = "paid_off"
            item["payoff_chapter"] = chapter
            item["payoff_quality"] = quality
            return state
    raise ValueError(f"foreshadow {foreshadow_id} not found")


def _next_timed_lock_id(locks: list) -> str:
    used = {item.get("id", "") for item in locks}
    n = 1
    while f"TL-{n:03d}" in used:
        n += 1
    return f"TL-{n:03d}"


def add_timed_lock(state: dict, item: dict) -> dict:
    """Add timed lock to state. Required: description, deadline_chapter."""
    if "deadline_chapter" not in item:
        raise ValueError("deadline_chapter required")
    locks = state.setdefault("story_craft", {}).setdefault("timed_locks", [])
    new_item = {
        "id": item.get("id") or _next_timed_lock_id(locks),
        "description": item.get("description", ""),
        "trigger_chapter": item.get("trigger_chapter"),
        "deadline_chapter": item["deadline_chapter"],
        "status": "active",
        "fulfilled_chapter": None,
    }
    locks.append(new_item)
    return state


def fulfill_timed_lock(state: dict, lock_id: str, chapter: int) -> dict:
    locks = state["story_craft"]["timed_locks"]
    for item in locks:
        if item["id"] == lock_id:
            if item["status"] == "fulfilled":
                raise ValueError(f"{lock_id} already fulfilled")
            item["status"] = "fulfilled"
            item["fulfilled_chapter"] = chapter
            return state
    raise ValueError(f"timed_lock {lock_id} not found")


def check_timed_lock_deadlines(state: dict, current_chapter: int) -> list:
    """Return list of overdue timed locks (deadline passed, not fulfilled)."""
    return [
        item for item in state["story_craft"]["timed_locks"]
        if item["status"] == "active"
        and item["deadline_chapter"] <= current_chapter
    ]


def record_emotion_peak(state: dict, chapter: int, intensity: int, type_: str) -> dict:
    """Record an emotion peak and reset chapters_since_peak counter."""
    curve = state["story_craft"]["rhythm_curve"]
    curve["last_emotion_peak_chapter"] = chapter
    curve["chapters_since_peak"] = 0
    curve["history"].append({
        "chapter": chapter,
        "intensity": intensity,
        "type": type_
    })
    return state


def check_rhythm_status(state: dict) -> str:
    """Return rhythm status: 'ok' | 'warning' | 'block'.

    Updates chapters_since_peak based on current chapter (if provided).
    Caller is expected to pass state with up-to-date chapters_since_peak.
    """
    curve = state["story_craft"]["rhythm_curve"]
    n = curve["chapters_since_peak"]
    if n >= curve["block_threshold"]:
        return "block"
    if n >= curve["warning_threshold"]:
        return "warning"
    return "ok"


def increment_chapters_since_peak(state: dict, chapter: int) -> dict:
    """Increment chapters_since_peak if chapter > last_emotion_peak_chapter."""
    curve = state["story_craft"]["rhythm_curve"]
    if chapter > curve["last_emotion_peak_chapter"]:
        curve["chapters_since_peak"] = chapter - curve["last_emotion_peak_chapter"]
    return state