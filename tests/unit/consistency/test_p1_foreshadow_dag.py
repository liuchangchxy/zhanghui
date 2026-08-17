"""Tests for P1 Foreshadow DAG validation patch.

Source: original (TDD for Phase 1 Task 7)
Path in references: N/A
"""
from scripts.consistency.patches.p1_foreshadow_dag import P1ForeshadowDAG
from scripts.consistency.core.patch_base import CheckContext, ApplyContext
from pathlib import Path

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
    blockers = p.check(_ctx(CLEAN_STATE, chapter=5))
    assert blockers == []


def test_dag_with_cycle_fails():
    p = P1ForeshadowDAG()
    blockers = p.check(_ctx(VIOLATION_STATE, chapter=5))
    assert any("循环" in b.message for b in blockers)


def test_dag_with_early_payoff_fails():
    p = P1ForeshadowDAG()
    blockers = p.check(_ctx(VIOLATION_STATE, chapter=5))
    assert any("提前" in b.message or "planted" in b.message for b in blockers)


def test_dag_with_overdue_fails():
    """Use chapter=100 to clear the OVERDUE_TOLERANCE=50 threshold."""
    p = P1ForeshadowDAG()
    blockers = p.check(_ctx(VIOLATION_STATE, chapter=100))
    assert any("超期" in b.message or "fs_004" in b.message for b in blockers)


def test_missing_foreshadow_chain_fails():
    p = P1ForeshadowDAG()
    blockers = p.check(_ctx({}, chapter=5))
    assert any("未初始化" in b.message or "foreshadow_chain" in b.message for b in blockers)


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
    blockers = p.check(_ctx(state, chapter=5))
    assert any("缺少 id" in b.message for b in blockers)