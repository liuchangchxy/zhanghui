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
)


@pytest.fixture
def fresh_state():
    return {"project_info": {}, "volumes": []}


def confirmed_v1(**overrides) -> VolumeRecord:
    """Build a confirmed V1 record with sensible defaults; pass fields to override."""
    defaults = dict(
        index=1, title="V1", core_conflict="X", climax="Y",
        status=VolumeStatus.CONFIRMED, source=VolumeSource.HUMAN,
    )
    defaults.update(overrides)
    return VolumeRecord(**defaults)


def test_append_human_volume_persists(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    rec = confirmed_v1(title="起势", chapter_range=[1, 80], core_conflict="宗门考核", climax="夺得首席")
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
    # Negative control: unrelated index should not have a draft
    assert not mgr.has_pending_draft(3)
    assert not mgr.has_pending_draft(1)


def test_confirm_volume_promotes_draft(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    cand = CandidateVolume(index=1, title="X", core_conflict="A", climax="B")
    mgr.append_draft(cand)
    mgr.confirm_volume(1)
    assert fresh_state["volumes"][0]["status"] == "confirmed"
    assert fresh_state["volumes"][0]["source"] == "ai"


def test_ai_cannot_overwrite_confirmed(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    rec = confirmed_v1(
        chapter_range=[1, 50],
        key_cool_points=["KP1"],
        characters_to_appear=["Char1"],
        foreshadowing=["FS1"],
    )
    mgr.append_or_update(rec)
    cand = CandidateVolume(
        index=1, title="AI 试图覆盖", chapter_range=[100, 200],
        core_conflict="Z", climax="W",
        key_cool_points=["Z1"], characters_to_appear=["Z2"],
        foreshadowing=["Z3"],
    )
    mgr.append_draft(cand)
    mgr.confirm_volume(1)  # should refuse, not overwrite
    # All originally-confirmed fields must be preserved
    assert fresh_state["volumes"][0]["title"] == "V1"
    assert fresh_state["volumes"][0]["chapter_range"] == [1, 50]
    assert fresh_state["volumes"][0]["core_conflict"] == "X"
    assert fresh_state["volumes"][0]["climax"] == "Y"
    assert fresh_state["volumes"][0]["key_cool_points"] == ["KP1"]
    assert fresh_state["volumes"][0]["characters_to_appear"] == ["Char1"]
    assert fresh_state["volumes"][0]["foreshadowing"] == ["FS1"]
    assert fresh_state["volumes"][0]["status"] == "confirmed"
    assert fresh_state["volumes"][0]["source"] == "human"


def test_set_deferred(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    rec = confirmed_v1()
    mgr.append_or_update(rec)
    mgr.set_deferred(1)
    assert fresh_state["volumes"][0]["status"] == "deferred"


def test_set_deferred_updates_confirmed_through_volume(fresh_state):
    """Setting a confirmed volume to deferred must drop confirmed_through_volume
    to the next-highest confirmed index (spec §4.2 invariant).
    """
    mgr = VolumeStateManager(fresh_state)
    for i in (1, 2):
        mgr.append_or_update(confirmed_v1(index=i, title=f"V{i}"))
    assert fresh_state["project_info"]["confirmed_through_volume"] == 2
    mgr.set_deferred(2)
    assert fresh_state["project_info"]["confirmed_through_volume"] == 1


@pytest.mark.parametrize("existing,new_index", [
    ([], 0),         # first volume can't be 0
    ([1], 3),        # hole: missing 2
    ([1, 2], 4),     # hole: missing 3
    ([1, 2, 3], 5),  # hole: missing 4
])
def test_index_continuity_invariant(fresh_state, existing, new_index):
    mgr = VolumeStateManager(fresh_state)
    for idx in existing:
        mgr.append_or_update(confirmed_v1(index=idx, title=f"V{idx}"))
    rec = confirmed_v1(index=new_index, title="X")
    with pytest.raises(ValueError, match="index continuity"):
        mgr.append_or_update(rec)


def test_later_volumes_status_deferred_by_default(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    mgr.append_or_update(confirmed_v1())
    horizon = mgr.get_planning_horizon()
    assert horizon.later_volumes_status == LaterVolumesStatus.DEFERRED