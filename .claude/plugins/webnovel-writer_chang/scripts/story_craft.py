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


def set_character_arc(state: dict, arc: dict) -> dict:
    """Set/replace character_arc. Required: name, starting_state, ending_state, transformation."""
    for field in ("name", "starting_state", "ending_state", "transformation"):
        if field not in arc:
            raise ValueError(f"{field} required for character_arc")
    state["story_craft"]["character_arc"] = {
        **arc,
        "key_moments": arc.get("key_moments", [])
    }
    return state


def _next_thematic_echo_id(echoes: list) -> str:
    used = {item.get("id", "") for item in echoes}
    n = 1
    while f"TE-{n:03d}" in used:
        n += 1
    return f"TE-{n:03d}"


def add_thematic_echo(state: dict, premise: str, chapter: int, manifestation: str) -> dict:
    """Add thematic echo. If premise already exists, append to its echoes list."""
    echoes = state["story_craft"]["thematic_echoes"]
    for item in echoes:
        if item["premise"] == premise:
            item["echoes"].append({
                "chapter": chapter,
                "manifestation": manifestation
            })
            return state
    echoes.append({
        "id": _next_thematic_echo_id(echoes),
        "premise": premise,
        "echoes": [{"chapter": chapter, "manifestation": manifestation}]
    })
    return state


VALID_HOOK_TYPES = {"悬念式", "反转式", "情绪炸弹式", "信息投放式", "留白式", "反讽式"}

ALLOWED_CHAPTER_META_FIELDS = {
    "beat_position", "hook_type",
    "scene_goal", "scene_conflict", "scene_setback", "scene_resolution",
    "sequel_reaction", "sequel_dilemma", "sequel_decision",
    "foreshadow_buried", "foreshadow_paid_off",
}


def set_chapter_meta(state: dict, chapter: int, **fields) -> dict:
    """Set chapter_meta fields. Validates hook_type if non-None. Enforces field allowlist.

    Allowed fields: beat_position, hook_type, scene_goal, scene_conflict,
    scene_setback, scene_resolution, sequel_reaction, sequel_dilemma,
    sequel_decision, foreshadow_buried, foreshadow_paid_off.

    Any field whose value is None is ignored (no-op) — caller can safely
    pass None for fields they don't want to update.
    """
    if not isinstance(chapter, int) or chapter < 1:
        raise ValueError(f"chapter must be a positive integer, got {chapter}")
    unknown = set(fields.keys()) - ALLOWED_CHAPTER_META_FIELDS
    if unknown:
        raise ValueError(
            f"unknown fields: {unknown}. Allowed: {sorted(ALLOWED_CHAPTER_META_FIELDS)}"
        )
    if fields.get("hook_type") is not None and fields["hook_type"] not in VALID_HOOK_TYPES:
        raise ValueError(f"hook_type must be one of {VALID_HOOK_TYPES}")
    meta = state.setdefault("chapter_meta", {})
    key = str(chapter)
    existing = meta.get(key, {})
    existing.update({k: v for k, v in fields.items() if v is not None})
    meta[key] = existing
    return state


def check_scene_sequel(chapter_meta: dict) -> list:
    """Return list of issues. BLOCKER for goal/conflict/decision missing;
    WARNING for other 4 steps missing."""
    issues = []
    blockers = ["scene_goal", "scene_conflict", "sequel_decision"]
    warnings = ["scene_setback", "scene_resolution", "sequel_reaction", "sequel_dilemma"]
    for field in blockers:
        if not chapter_meta.get(field):
            issues.append(f"BLOCKER: {field} required")
    for field in warnings:
        if not chapter_meta.get(field):
            issues.append(f"WARN: {field} recommended")
    return issues


VALID_BEATS = [
    "Opening Image", "Theme Stated", "Setup", "Catalyst", "Debate",
    "Break Into Two", "B Story", "Fun and Games", "Midpoint",
    "Bad Guys Close In", "All Is Lost", "Dark Night of the Soul",
    "Break Into Three", "Finale", "Final Image"
]


def init_volume_beat(state: dict, volume: int, total_chapters: int) -> dict:
    """Initialize volume_beat with empty 15-beat skeleton.

    Beat chapters are auto-distributed by percentage.

    Behavior (sibling-key schema, 2026-08-19):
    - Volume 1 uses legacy top-level 'volume_beat' field (dict with beats[])
      so V1 callers (review_pipeline.py, dashboard/app.py) keep working
      unchanged.
    - Volume 2+ uses sibling 'volume_beats: dict[str, beat_sheet]' so
      multiple volumes can coexist.
    - Re-init for the same volume is a no-op (idempotent).
    - Re-init for V1 when legacy is already present for a different volume
      raises ValueError (legacy single-slot invariant preserved).
    """
    percentages = [0.01, 0.05, 0.10, 0.10, 0.20, 0.20, 0.22, 0.50, 0.50, 0.75, 0.75, 0.80, 0.80, 0.99, 1.00]
    if len(percentages) != 15:
        raise ValueError("internal: percentages must match 15 beats")
    sc = state.setdefault("story_craft", {})

    if volume == 1:
        # Legacy path — V1 stays at top-level 'volume_beat'
        existing = sc.get("volume_beat")
        if existing is not None:
            if existing.get("volume") == volume:
                return state  # idempotent
            raise ValueError(
                f"volume_beat already initialized for volume {existing.get('volume')}; "
                f"multi-volume not yet supported (requested volume {volume})"
            )
        beats = []
        for name, pct in zip(VALID_BEATS, percentages):
            ch = max(1, round(pct * total_chapters))
            beats.append({"name": name, "chapter": ch, "filled": False, "notes": None})
        sc["volume_beat"] = {
            "volume": volume,
            "total_chapters": total_chapters,
            "beats": beats,
        }
        return state

    # V2+ via sibling key 'volume_beats'
    vb_sibling = sc.setdefault("volume_beats", {})
    if str(volume) in vb_sibling:
        return state  # idempotent
    beats = []
    for name, pct in zip(VALID_BEATS, percentages):
        ch = max(1, round(pct * total_chapters))
        beats.append({"name": name, "chapter": ch, "filled": False, "notes": None})
    vb_sibling[str(volume)] = {
        "volume": volume,
        "total_chapters": total_chapters,
        "beats": beats,
    }
    return state


def fill_beat(state: dict, volume: int, beat_name: str, chapter: int, notes: str) -> dict:
    sc = state.get("story_craft", {})
    if volume == 1:
        # Legacy path
        vb = sc.get("volume_beat")
        if vb is None or vb.get("volume") != volume:
            raise ValueError(f"volume {volume} not initialized; run init-volume-beat first")
        beats = vb["beats"]
    else:
        vb_sibling = sc.get("volume_beats", {})
        vb = vb_sibling.get(str(volume))
        if vb is None:
            raise ValueError(f"volume {volume} not initialized; run init-volume-beat first")
        beats = vb["beats"]
    for beat in beats:
        if beat["name"] == beat_name:
            beat["filled"] = True
            beat["chapter"] = chapter
            beat["notes"] = notes
            return state
    raise ValueError(f"beat {beat_name} not found")


def _check_beats(beats: list, volume: int, current_chapter: int | None) -> list:
    """Pure logic on a beats list. Shared by V1 (legacy) and V2+ (sibling)."""
    tolerance = 2
    issues = []
    for beat in beats:
        is_critical = beat["name"] in ("Midpoint", "All Is Lost")
        if not beat["filled"]:
            if is_critical:
                if current_chapter is not None:
                    if current_chapter >= beat["chapter"] - tolerance:
                        issues.append(f"BLOCKER: {beat['name']} must be filled")
                    # else: not yet due
                else:
                    issues.append(f"BLOCKER: {beat['name']} must be filled")
            else:
                issues.append(f"WARN: {beat['name']} not yet filled")
    return issues


def check_volume_beat(state: dict, volume: int, current_chapter: int | None = None) -> list:
    """Return issues. BLOCKER for Midpoint/All Is Lost when current chapter >= beat's chapter.

    Behavior (sibling-key schema, 2026-08-19):
    - V1 reads from legacy 'volume_beat'; V2+ reads from sibling 'volume_beats'.
    - If the requested volume's beat sheet is not initialized, return a
      friendly BLOCKER list (does not raise) so callers can display the issue.
    - For Midpoint/All Is Lost, BLOCKER is only emitted when current_chapter
      is provided AND current_chapter >= beat['chapter'] - tolerance (2).
      If current_chapter is None, BLOCKER is always emitted (legacy behavior,
      used by callers that have no chapter context).
    - Non-critical beats always emit WARN when unfilled.
    """
    sc = state.get("story_craft", {})
    if volume == 1:
        vb = sc.get("volume_beat")
        if vb is None or vb.get("volume") != volume:
            return [f"BLOCKER: story_craft.volume_beat not initialized for volume {volume} — run init-volume-beat first"]
    else:
        vb = sc.get("volume_beats", {}).get(str(volume))
        if vb is None:
            return [f"BLOCKER: story_craft.volume_beats not initialized for volume {volume} — run init-volume-beat first"]
    return _check_beats(vb["beats"], volume, current_chapter)