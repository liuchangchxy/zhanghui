"""Tests for P1 Foreshadow DAG validation patch.

Source: original (TDD for Phase 1 Task 7)
Path in references: N/A
"""
from scripts.consistency.patches.p1_foreshadow_dag import P1ForeshadowDAG
from scripts.consistency.core.patch_base import CheckContext, ApplyContext, PatchFinding
from pathlib import Path
from copy import deepcopy

CLEAN_STATE = {
    "story_craft": {
        "foreshadow_chain": {
            "version": 1,
            "dag": [
                {"id": "fs_001", "content": "ok", "level": "表层", "planted_chapter": 1, "paid_off_chapter": None, "status": "active", "depends_on": [], "introduced_by": "init"}
            ],
            "validated_at": None,
            "validation_history": []
        }
    }
}

VIOLATION_STATE = {
    "story_craft": {
        "foreshadow_chain": {
            "version": 1,
            "dag": [
                {"id": "fs_001", "content": "环A", "planted_chapter": 1, "paid_off_chapter": 5, "status": "active", "depends_on": ["fs_002"], "level": "中层", "introduced_by": "init"},
                {"id": "fs_002", "content": "环B", "planted_chapter": 1, "paid_off_chapter": 5, "status": "active", "depends_on": ["fs_001"], "level": "中层", "introduced_by": "init"},
                {"id": "fs_003", "content": "提前", "planted_chapter": 5, "paid_off_chapter": 3, "status": "active", "depends_on": [], "level": "表层", "introduced_by": "init"},
                {"id": "fs_004", "content": "超期", "planted_chapter": 1, "paid_off_chapter": 5, "status": "active", "depends_on": [], "level": "深层", "introduced_by": "init"}
            ],
            "validated_at": None,
            "validation_history": []
        }
    }
}


def _ctx(state, chapter=10):
    return CheckContext(project_root=Path("/tmp"), chapter_num=chapter, state=state, chapter_outline=None, previous_chapters=[], chapter_text=None)


def test_clean_dag_passes():
    p = P1ForeshadowDAG()
    findings = p.check(_ctx(CLEAN_STATE, chapter=5))
    assert findings == []


def test_dag_with_cycle_fails():
    p = P1ForeshadowDAG()
    findings = p.check(_ctx(VIOLATION_STATE, chapter=5))
    assert any("循环" in b.message for b in findings)


def test_dag_with_early_payoff_fails():
    p = P1ForeshadowDAG()
    findings = p.check(_ctx(VIOLATION_STATE, chapter=5))
    assert any("提前" in b.message or "planted" in b.message for b in findings)


def test_dag_with_overdue_fails():
    """Use chapter=100 to clear the OVERDUE_TOLERANCE=50 threshold."""
    p = P1ForeshadowDAG()
    findings = p.check(_ctx(VIOLATION_STATE, chapter=100))
    assert any("超期" in b.message or "fs_004" in b.message for b in findings)


def test_missing_foreshadow_chain_fails():
    p = P1ForeshadowDAG()
    findings = p.check(_ctx({}, chapter=5))
    assert any("未初始化" in b.message or "foreshadow_chain" in b.message for b in findings)


def test_dag_with_missing_id_does_not_crash():
    p = P1ForeshadowDAG()
    state = {
        "story_craft": {
            "foreshadow_chain": {
                "version": 1,
                "dag": [
                    {"content": "no id"},  # missing id
                    {"id": "fs_001", "content": "ok"},
                ],
                "validated_at": None,
                "validation_history": []
            }
        }
    }
    findings = p.check(_ctx(state, chapter=5))
    assert any("缺少 id" in b.message for b in findings)


def test_real_list_format_dag_passes():
    """Real migrate_story_craft.py format: foreshadow_chain is a list, not wrapped in {dag: ...}."""
    p = P1ForeshadowDAG()
    state = {
        "story_craft": {
            "foreshadow_chain": [
                {"id": "fs_001", "content": "ok", "planted_chapter": 1, "paid_off_chapter": None, "status": "active", "depends_on": []}
            ]
        }
    }
    findings = p.check(_ctx(state, chapter=5))
    assert findings == []


def test_real_list_format_detects_cycle():
    """Cycle detection must work in the real list-of-dicts format too."""
    p = P1ForeshadowDAG()
    state = {
        "story_craft": {
            "foreshadow_chain": [
                {"id": "fs_001", "planted_chapter": 1, "paid_off_chapter": 5, "status": "active", "depends_on": ["fs_002"]},
                {"id": "fs_002", "planted_chapter": 1, "paid_off_chapter": 5, "status": "active", "depends_on": ["fs_001"]},
            ]
        }
    }
    findings = p.check(_ctx(state, chapter=5))
    assert any("循环" in b.message for b in findings)


def test_dag_with_duplicate_ids_blocks():
    p = P1ForeshadowDAG()
    state = {
        "story_craft": {
            "foreshadow_chain": {
                "version": 1,
                "dag": [
                    {"id": "fs_001", "content": "first"},
                    {"id": "fs_001", "content": "second"},  # duplicate
                ]
            }
        }
    }
    findings = p.check(_ctx(state, chapter=5))
    assert any("重复" in b.message for b in findings)


def test_dag_with_depends_on_none_does_not_crash():
    """depends_on=None should be handled, not raise TypeError on iteration."""
    p = P1ForeshadowDAG()
    state = {
        "story_craft": {
            "foreshadow_chain": {
                "version": 1,
                "dag": [
                    {"id": "fs_001", "depends_on": None, "planted_chapter": 1, "paid_off_chapter": None, "status": "active"},
                ]
            }
        }
    }
    # Should not raise; should pass (no cycle, no overdue)
    findings = p.check(_ctx(state, chapter=5))
    # No cycle because depends_on is None
    assert not any("循环" in b.message for b in findings)


def test_load_error_reports_finding():
    """If state has _load_error (corrupt JSON), P1 should report it."""
    p = P1ForeshadowDAG()
    state = {"_load_error": "JSONDecodeError: bad json"}
    findings = p.check(_ctx(state, chapter=5))
    assert any("无法读取 state.json" in b.message for b in findings)


def test_unknown_foreshadow_chain_format_blocks():
    p = P1ForeshadowDAG()
    state = {"story_craft": {"foreshadow_chain": "some string"}}
    findings = p.check(_ctx(state, chapter=5))
    assert any("格式未知" in b.message for b in findings)


def test_every_p1_observation_has_typed_code_evidence_and_real_subject_semantics():
    patch = P1ForeshadowDAG()
    cases = [
        ({"story_craft": {"foreshadow_chain": [{"content": "missing id"}]}}, "missing_id", None),
        ({"story_craft": {"foreshadow_chain": [{"id": "D"}, {"id": "D"}]}}, "duplicate_id", None),
        ({"story_craft": {"foreshadow_chain": [
            {"id": "A", "depends_on": ["B"]}, {"id": "B", "depends_on": ["A"]},
        ]}}, "cycle", "cycle:A,B"),
        ({"story_craft": {"foreshadow_chain": [
            {"id": "EARLY", "planted_chapter": 5, "paid_off_chapter": 3},
        ]}}, "chronology", "foreshadow:EARLY"),
        ({"story_craft": {"foreshadow_chain": [
            {"id": "LATE", "status": "active", "paid_off_chapter": 1},
        ]}}, "overdue", "foreshadow:LATE"),
        ({"story_craft": {"foreshadow_chain": "invalid"}}, "invalid_state", None),
    ]
    for state, expected_code, expected_subject in cases:
        original = deepcopy(state)
        findings = patch.check(_ctx(state, chapter=100))
        match = next(f for f in findings if f.issue_code == expected_code)
        assert all(isinstance(finding, PatchFinding) for finding in findings)
        assert match.subject_id == expected_subject
        assert match.evidence
        assert match.checker_id == "foreshadow_dag"
        assert match.input_ref == {"source": "state.story_craft.foreshadow_chain"}
        assert state == original


def test_cycle_evidence_and_identity_are_independent_of_traversal_order():
    patch = P1ForeshadowDAG()
    first = {"story_craft": {"foreshadow_chain": [
        {"id": "A", "depends_on": ["B"]}, {"id": "B", "depends_on": ["A"]},
    ]}}
    reordered = {"story_craft": {"foreshadow_chain": [
        {"id": "B", "depends_on": ["A"]}, {"id": "A", "depends_on": ["B"]},
    ]}}
    left = next(f for f in patch.check(_ctx(first, chapter=5)) if f.issue_code == "cycle")
    right = next(f for f in patch.check(_ctx(reordered, chapter=5)) if f.issue_code == "cycle")
    assert left.subject_id == right.subject_id == "cycle:A,B"
    assert left.evidence == right.evidence
    assert left.evidence["cycle_ids"] == ["A", "B"]
    assert left.evidence["cycle_edges"] == [["A", "B"], ["B", "A"]]
