import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from data_modules.volume_state import (
    VolumeStateManager,
    VolumeRecord,
    VolumeStatus,
    VolumeSource,
    CandidateVolume,
    LaterVolumesStatus,
    PlanningHorizon,
)


@pytest.fixture
def fresh_state():
    return {"project_info": {}, "volumes": []}


def test_append_human_volume_persists(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    rec = VolumeRecord(
        index=1,
        title="起势",
        chapter_range=[1, 80],
        core_conflict="宗门考核",
        climax="夺得首席",
        status=VolumeStatus.CONFIRMED,
        source=VolumeSource.HUMAN,
    )
    mgr.append_or_update(rec)
    assert fresh_state["volumes"][0]["title"] == "起势"
    assert fresh_state["volumes"][0]["status"] == "confirmed"
    assert fresh_state["project_info"]["confirmed_through_volume"] == 1


def test_append_draft_does_not_persist(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    cand = CandidateVolume(
        index=2,
        title="AI 起草",
        core_conflict="伏魔",
        climax="封印松动",
    )
    mgr.append_draft(cand)
    # Drafts live in memory only
    assert fresh_state["volumes"] == []
    assert mgr.has_pending_draft(2)


def test_confirm_volume_promotes_draft(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    cand = CandidateVolume(index=1, title="X", core_conflict="A", climax="B")
    mgr.append_draft(cand)
    mgr.confirm_volume(1)
    assert fresh_state["volumes"][0]["status"] == "confirmed"
    assert fresh_state["volumes"][0]["source"] == "ai"


def test_ai_cannot_overwrite_confirmed(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    rec = VolumeRecord(
        index=1, title="V1", core_conflict="X", climax="Y",
        status=VolumeStatus.CONFIRMED, source=VolumeSource.HUMAN,
    )
    mgr.append_or_update(rec)
    # New AI draft for same index
    cand = CandidateVolume(index=1, title="AI 试图覆盖", core_conflict="Z", climax="W")
    mgr.append_draft(cand)
    mgr.confirm_volume(1)  # should refuse, not overwrite
    assert fresh_state["volumes"][0]["title"] == "V1"
    assert fresh_state["volumes"][0]["core_conflict"] == "X"


def test_set_deferred(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    rec = VolumeRecord(
        index=1, title="V1", core_conflict="X", climax="Y",
        status=VolumeStatus.CONFIRMED, source=VolumeSource.HUMAN,
    )
    mgr.append_or_update(rec)
    mgr.set_deferred(1)
    assert fresh_state["volumes"][0]["status"] == "deferred"


def test_index_continuity_invariant(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    # Try to add index=3 with no index=1,2 — must reject
    rec = VolumeRecord(
        index=3, title="V3", status=VolumeStatus.CONFIRMED, source=VolumeSource.HUMAN,
    )
    with pytest.raises(ValueError, match="index continuity"):
        mgr.append_or_update(rec)


def test_later_volumes_status_deferred_by_default(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    rec = VolumeRecord(
        index=1, title="V1", core_conflict="X", climax="Y",
        status=VolumeStatus.CONFIRMED, source=VolumeSource.HUMAN,
    )
    mgr.append_or_update(rec)
    horizon = mgr.get_planning_horizon()
    assert horizon.later_volumes_status == LaterVolumesStatus.DEFERRED