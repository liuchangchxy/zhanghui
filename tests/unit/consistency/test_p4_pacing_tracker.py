from scripts.consistency.patches.p4_pacing_tracker import P4PacingTracker
from scripts.consistency.core.patch_base import CheckContext
from scripts.consistency.core.patch_base import PatchFinding
from pathlib import Path
from copy import deepcopy


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
    findings = p.check(_ctx(CLEAN_STATE, chapter=4))
    assert findings == []


def test_consecutive_fast_overlimit_blocks():
    p = P4PacingTracker()
    findings = p.check(_ctx(DRIFT_STATE, chapter=4))
    assert any("连续" in b.message and "快档" in b.message for b in findings)


def test_slow_quota_missing_blocks():
    p = P4PacingTracker()
    findings = p.check(_ctx(DRIFT_STATE, chapter=4))
    assert any("慢档" in b.message for b in findings)


def test_empty_history_passes():
    p = P4PacingTracker()
    state = {"story_craft": {"pacing_history": {"history": [], "rules": {"max_consecutive_fast": 1, "slow_per_4_chapters_min": 1}}}}
    findings = p.check(_ctx(state, chapter=5))
    assert findings == []


def test_missing_field_fails():
    p = P4PacingTracker()
    findings = p.check(_ctx({}, chapter=5))
    assert any("未初始化" in b.message or "pacing_history" in b.message for b in findings)


def test_p4_findings_are_typed_evidenced_and_read_only():
    cases = [
        ({"_load_error": "ignored display detail"}, "invalid_state", None, {"source", "error_type"}),
        ({}, "invalid_state", None, {"source_field", "reason"}),
        ({"story_craft": {"pacing_history": {"history": [], "rules": {"max_consecutive_fast": "many"}}}},
         "invalid_state", None, {"source_field", "reason", "actual_type"}),
        ({"story_craft": {"pacing_history": {"history": "bad"}}}, "malformed_history", None,
         {"source_field", "reason", "actual_type"}),
        (DRIFT_STATE, "consecutive_fast", None, {"observed", "maximum"}),
        (DRIFT_STATE, "slow_quota", None, {"window_size", "observed_slow_count", "required_slow_count"}),
    ]
    patch = P4PacingTracker()
    for state, code, subject, evidence_keys in cases:
        before = deepcopy(state)
        finding = next(item for item in patch.check(_ctx(state, chapter=4)) if item.issue_code == code)
        assert isinstance(finding, PatchFinding)
        assert finding.subject_id == subject
        assert evidence_keys <= finding.evidence.keys()
        assert finding.checker_id == "pacing_tracker"
        assert state == before
