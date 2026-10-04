"""Multi-volume beat sheet using sibling key `volume_beats` for V2+.

Spec 2026-08-19 §6.1 + redesign plan: V1 沿用 legacy `volume_beat`,
V2+ 走 sibling `volume_beats: dict[str, beat_sheet]`.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from story_craft import init_volume_beat, fill_beat, check_volume_beat


def test_init_volume_beat_v1_keeps_legacy_field():
    """V1 init must populate legacy `volume_beat` (top-level dict with beats[])."""
    state: dict = {}
    init_volume_beat(state, volume=1, total_chapters=80)
    vb = state["story_craft"]["volume_beat"]
    assert vb["volume"] == 1
    assert isinstance(vb["beats"], list)
    assert len(vb["beats"]) == 15
    # V1 不会写 volume_beats
    assert "volume_beats" not in state["story_craft"]


def test_init_volume_beat_v2_writes_sibling_key():
    """V2 init must populate `volume_beats['2']`, NOT touch legacy `volume_beat`."""
    state: dict = {}
    init_volume_beat(state, volume=1, total_chapters=80)
    init_volume_beat(state, volume=2, total_chapters=80)
    # V1 legacy intact
    assert state["story_craft"]["volume_beat"]["volume"] == 1
    # V2 in sibling key
    vb2 = state["story_craft"]["volume_beats"]["2"]
    assert vb2["volume"] == 2
    assert len(vb2["beats"]) == 15


def test_fill_beat_v2_routes_to_sibling():
    """fill_beat for V2 must update volume_beats['2'].beats, not volume_beat.beats."""
    state: dict = {}
    init_volume_beat(state, volume=1, total_chapters=80)
    init_volume_beat(state, volume=2, total_chapters=80)
    fill_beat(state, volume=2, beat_name="Midpoint", chapter=40, notes="V2 midpoint")
    # V1 untouched
    v1_midpoint = next(b for b in state["story_craft"]["volume_beat"]["beats"] if b["name"] == "Midpoint")
    assert v1_midpoint["filled"] is False
    # V2 filled
    v2_midpoint = next(b for b in state["story_craft"]["volume_beats"]["2"]["beats"] if b["name"] == "Midpoint")
    assert v2_midpoint["filled"] is True
    assert v2_midpoint["chapter"] == 40


def test_check_volume_beat_v2_works():
    """check_volume_beat for V2 must read from volume_beats, return issues list."""
    state: dict = {}
    init_volume_beat(state, volume=1, total_chapters=80)
    init_volume_beat(state, volume=2, total_chapters=80)
    issues = check_volume_beat(state, volume=2, current_chapter=20)
    # Midpoint/All Is Lost BLOCKERs when past threshold
    assert isinstance(issues, list)


def test_check_volume_beat_v1_still_uses_legacy():
    """V1 check must still work via legacy volume_beat path."""
    state: dict = {}
    init_volume_beat(state, volume=1, total_chapters=80)
    issues = check_volume_beat(state, volume=1, current_chapter=20)
    assert isinstance(issues, list)


def test_init_volume_beat_v1_idempotent():
    """V1 re-init is no-op (legacy behavior preserved)."""
    state: dict = {}
    init_volume_beat(state, volume=1, total_chapters=80)
    # Mark a beat filled
    state["story_craft"]["volume_beat"]["beats"][10]["filled"] = True
    # Re-init
    init_volume_beat(state, volume=1, total_chapters=80)
    # Filled state preserved
    assert state["story_craft"]["volume_beat"]["beats"][10]["filled"] is True


def test_init_volume_beat_v2_idempotent():
    """V2 re-init is no-op."""
    state: dict = {}
    init_volume_beat(state, volume=2, total_chapters=80)
    state["story_craft"]["volume_beats"]["2"]["beats"][10]["filled"] = True
    init_volume_beat(state, volume=2, total_chapters=80)
    assert state["story_craft"]["volume_beats"]["2"]["beats"][10]["filled"] is True