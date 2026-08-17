from scripts.consistency.patches.p3_event_matrix import P3EventMatrix
from scripts.consistency.core.patch_base import CheckContext
from pathlib import Path


CLEAN_STATE = {
    "story_craft": {
        "event_matrix_state": {
            "version": 1,
            "types": {
                "conflict_thrill": {"cooldown": 2, "last_used_chapter": 0},
                "tension_escalation": {"cooldown": 2, "last_used_chapter": 0},
                "bond_deepening": {"cooldown": 4, "last_used_chapter": 0},
                "faction_building": {"cooldown": 4, "last_used_chapter": 0},
                "world_painting": {"cooldown": 3, "last_used_chapter": 0}
            },
            "history": [
                {"chapter": 1, "types": ["conflict_thrill"], "primary": "conflict_thrill"},
                {"chapter": 2, "types": ["bond_deepening"], "primary": "bond_deepening"},
                {"chapter": 3, "types": ["world_painting"], "primary": "world_painting"},
                {"chapter": 4, "types": ["conflict_thrill"], "primary": "conflict_thrill"}
            ],
            "gentle_window": 5,
            "max_consecutive_fast": 2
        }
    }
}

BREAK_STATE = {
    "story_craft": {
        "event_matrix_state": {
            "version": 1,
            "types": {
                "conflict_thrill": {"cooldown": 2, "last_used_chapter": 0},
                "tension_escalation": {"cooldown": 2, "last_used_chapter": 0},
                "bond_deepening": {"cooldown": 4, "last_used_chapter": 0},
                "faction_building": {"cooldown": 4, "last_used_chapter": 0},
                "world_painting": {"cooldown": 3, "last_used_chapter": 0}
            },
            "history": [
                {"chapter": 1, "types": ["conflict_thrill"], "primary": "conflict_thrill"},
                {"chapter": 2, "types": ["conflict_thrill"], "primary": "conflict_thrill"},
                {"chapter": 3, "types": ["conflict_thrill"], "primary": "conflict_thrill"},
                {"chapter": 4, "types": ["conflict_thrill"], "primary": "conflict_thrill"},
                {"chapter": 5, "types": ["conflict_thrill"], "primary": "conflict_thrill"}
            ],
            "gentle_window": 5,
            "max_consecutive_fast": 2
        }
    }
}


def _ctx(state, chapter=5):
    return CheckContext(project_root=Path("/tmp"), chapter_num=chapter, state=state, chapter_outline=None, previous_chapters=[], chapter_text=None)


def test_clean_history_passes():
    p = P3EventMatrix()
    blockers = p.check(_ctx(CLEAN_STATE, chapter=4))
    assert blockers == []


def test_consecutive_fast_overlimit_blocks():
    p = P3EventMatrix()
    # At chapter 5 with 5 consecutive conflict_thrill → max_consecutive_fast=2 violated
    blockers = p.check(_ctx(BREAK_STATE, chapter=5))
    assert any("连续" in b.message and "快档" in b.message for b in blockers)


def test_gentle_quota_missing_blocks():
    p = P3EventMatrix()
    # The 5 most recent chapters all fast → no soft → gentle quota violation
    blockers = p.check(_ctx(BREAK_STATE, chapter=5))
    assert any("soft" in b.message or "gentle" in b.message for b in blockers)


def test_empty_history_passes():
    p = P3EventMatrix()
    state = {"story_craft": {"event_matrix_state": {"history": [], "gentle_window": 5, "max_consecutive_fast": 2}}}
    blockers = p.check(_ctx(state, chapter=5))
    assert blockers == []


def test_missing_field_fails():
    p = P3EventMatrix()
    blockers = p.check(_ctx({}, chapter=5))
    assert any("未初始化" in b.message or "event_matrix_state" in b.message for b in blockers)