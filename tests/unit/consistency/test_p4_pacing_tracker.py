from scripts.consistency.patches.p4_pacing_tracker import P4PacingTracker
from scripts.consistency.core.patch_base import CheckContext
from pathlib import Path


CLEAN_STATE = {
    "story_craft": {
        "pacing_history": {
            "version": 1,
            "history": [
                {"chapter": 1, "tier": "fast", "event_types": ["conflict_thrill"]},
                {"chapter": 2, "tier": "medium", "event_types": ["tension_escalation"]},
                {"chapter": 3, "tier": "slow", "event_types": ["bond_deepening"]},
                {"chapter": 4, "tier": "fast", "event_types": ["conflict_thrill"]}
            ],
            "rules": {"max_consecutive_fast": 1, "slow_per_4_chapters_min": 1}
        }
    }
}

DRIFT_STATE = {
    "story_craft": {
        "pacing_history": {
            "version": 1,
            "history": [
                {"chapter": 1, "tier": "fast", "event_types": ["conflict_thrill"]},
                {"chapter": 2, "tier": "fast", "event_types": ["conflict_thrill"]},
                {"chapter": 3, "tier": "fast", "event_types": ["conflict_thrill"]},
                {"chapter": 4, "tier": "fast", "event_types": ["conflict_thrill"]}
            ],
            "rules": {"max_consecutive_fast": 1, "slow_per_4_chapters_min": 1}
        }
    }
}


def _ctx(state, chapter=4):
    return CheckContext(project_root=Path("/tmp"), chapter_num=chapter, state=state, chapter_outline=None, previous_chapters=[], chapter_text=None)


def test_clean_pacing_passes():
    p = P4PacingTracker()
    blockers = p.check(_ctx(CLEAN_STATE, chapter=4))
    assert blockers == []


def test_consecutive_fast_overlimit_blocks():
    p = P4PacingTracker()
    blockers = p.check(_ctx(DRIFT_STATE, chapter=4))
    assert any("连续" in b.message and "快档" in b.message for b in blockers)


def test_slow_quota_missing_blocks():
    p = P4PacingTracker()
    blockers = p.check(_ctx(DRIFT_STATE, chapter=4))
    assert any("慢档" in b.message for b in blockers)


def test_empty_history_passes():
    p = P4PacingTracker()
    state = {"story_craft": {"pacing_history": {"history": [], "rules": {"max_consecutive_fast": 1, "slow_per_4_chapters_min": 1}}}}
    blockers = p.check(_ctx(state, chapter=5))
    assert blockers == []


def test_missing_field_fails():
    p = P4PacingTracker()
    blockers = p.check(_ctx({}, chapter=5))
    assert any("未初始化" in b.message or "pacing_history" in b.message for b in blockers)
