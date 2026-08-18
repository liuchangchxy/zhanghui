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
from data_modules.promise_ledger import ForeshadowEntry, ForeshadowStatus, PromiseLedger


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
    ([1, 2, 4], 5),  # hole: missing 3 — must reject adding 5 even though 5 == 4+1
])
def test_index_continuity_invariant(fresh_state, existing, new_index):
    mgr = VolumeStateManager(fresh_state)
    # Seed existing state directly so we can also test the case where the hole
    # already exists in state (e.g. legacy data) and the next insert must still
    # be rejected. The strict contiguity check makes it impossible to build a
    # hole via the public API, so we bypass it here.
    for idx in existing:
        fresh_state["volumes"].append(
            confirmed_v1(index=idx, title=f"V{idx}").to_dict()
        )
    rec = confirmed_v1(index=new_index, title="X")
    with pytest.raises(ValueError, match="index continuity"):
        mgr.append_or_update(rec)


def test_later_volumes_status_deferred_by_default(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    mgr.append_or_update(confirmed_v1())
    horizon = mgr.get_planning_horizon()
    assert horizon.later_volumes_status == LaterVolumesStatus.DEFERRED


# ===== Issue 2 (Critical): DRAFT must NOT persist via append_or_update =====


def test_append_or_update_rejects_draft_status(fresh_state):
    """Spec invariant: drafts never persist; use append_draft() / confirm_volume()."""
    from data_modules.volume_state import VolumeStatus
    mgr = VolumeStateManager(fresh_state)
    rec = VolumeRecord(
        index=1, title="X", core_conflict="A", climax="B",
        status=VolumeStatus.DRAFT, source=VolumeSource.HUMAN,
    )
    with pytest.raises(ValueError, match="status=DRAFT"):
        mgr.append_or_update(rec)
    assert fresh_state["volumes"] == []


# ===== Issue 3 (Critical): AI cannot overwrite CONFIRMED via append_or_update =====


def test_append_or_update_rejects_ai_overwrite_of_confirmed(fresh_state):
    """Defense in depth: even if AI source is passed, confirmed record stays."""
    mgr = VolumeStateManager(fresh_state)
    mgr.append_or_update(confirmed_v1(title="V1", core_conflict="X", climax="Y"))
    ai_rec = VolumeRecord(
        index=1, title="AI覆盖", core_conflict="Z", climax="W",
        status=VolumeStatus.CONFIRMED, source=VolumeSource.AI,
    )
    with pytest.raises(ValueError, match="AI cannot overwrite confirmed"):
        mgr.append_or_update(ai_rec)
    # Original V1 preserved
    assert fresh_state["volumes"][0]["title"] == "V1"
    assert fresh_state["volumes"][0]["core_conflict"] == "X"


# ===== Issue 4 (Critical): AI cannot overwrite DEFERRED via confirm_volume =====


def test_confirm_volume_ai_cannot_overwrite_deferred(fresh_state):
    """Spec invariant: deferred is user-controlled; AI draft must not overwrite."""
    mgr = VolumeStateManager(fresh_state)
    # Seed deferred record
    mgr.append_or_update(confirmed_v1())
    mgr.set_deferred(1)
    assert fresh_state["volumes"][0]["status"] == "deferred"
    # AI draft for same index
    cand = CandidateVolume(
        index=1, title="AI覆盖", core_conflict="Z", climax="W",
    )
    mgr.append_draft(cand)
    mgr.confirm_volume(1)  # must refuse silently
    assert fresh_state["volumes"][0]["status"] == "deferred"
    assert fresh_state["volumes"][0]["title"] == "V1"


# ===== Issue 5 (Critical): get_planning_horizon recomputes from volumes[] =====


def test_get_planning_horizon_recomputes_confirmed_through(fresh_state):
    """Even if cached field is wrong, horizon reflects current volumes[] state."""
    mgr = VolumeStateManager(fresh_state)
    # Add V1, V2, V3 confirmed
    for i in (1, 2, 3):
        mgr.append_or_update(confirmed_v1(index=i, title=f"V{i}"))
    # Corrupt the cached field to simulate stale state
    fresh_state["project_info"]["confirmed_through_volume"] = 999
    horizon = mgr.get_planning_horizon()
    assert horizon.confirmed_through_volume == 3  # recomputed, not 999


# ===== Issue 7 (Important): revise_volume API =====


def test_revise_volume_updates_fields(fresh_state):
    """User can revise specific fields of a record."""
    mgr = VolumeStateManager(fresh_state)
    mgr.append_or_update(confirmed_v1(core_conflict="old"))
    mgr.revise_volume(1, {"core_conflict": "new", "climax": "new climax"})
    assert fresh_state["volumes"][0]["core_conflict"] == "new"
    assert fresh_state["volumes"][0]["climax"] == "new climax"


def test_revise_volume_rejects_ai_source_on_confirmed(fresh_state):
    """AI source for confirmed record must be rejected."""
    mgr = VolumeStateManager(fresh_state)
    mgr.append_or_update(confirmed_v1())
    with pytest.raises(ValueError, match="Cannot revise"):
        mgr.revise_volume(1, {"source": VolumeSource.AI})


def test_revise_volume_raises_on_missing(fresh_state):
    """revise_volume on nonexistent index raises ValueError."""
    mgr = VolumeStateManager(fresh_state)
    with pytest.raises(ValueError, match="No record"):
        mgr.revise_volume(99, {"title": "X"})


# ===== Task 3: VolumeStateManager owns promise_ledger =====


def test_volume_state_owns_promise_ledger(fresh_state):
    """VolumeStateManager must read/write promise_ledger via project_info."""
    from data_modules.volume_state import VolumeStateManager
    mgr = VolumeStateManager(fresh_state)
    e = ForeshadowEntry(
        id="fs_001", type="foreshadow", depth=3,
        planted_chapter=12, planted_volume=1,
        expected_payoff_chapter=145, expected_payoff_volume=3,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    mgr.upsert_promise_entry(e)
    # Persisted to state.json
    assert "promise_ledger" in fresh_state["project_info"]
    assert fresh_state["project_info"]["promise_ledger"][0]["id"] == "fs_001"
    # Round-trip: new manager reads from same state
    mgr2 = VolumeStateManager(fresh_state)
    ledger = mgr2.get_promise_ledger()
    assert len(ledger.entries) == 1
    assert ledger.entries[0].id == "fs_001"


def test_volume_state_list_overdue_foreshadows(fresh_state):
    """VolumeStateManager.list_overdue_foreshadows uses current chapter/volume."""
    from data_modules.volume_state import VolumeStateManager
    mgr = VolumeStateManager(fresh_state)
    # Plant in V1, expected payoff V2 ch100
    e = ForeshadowEntry(
        id="fs_over", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    mgr.upsert_promise_entry(e)
    # No overdue at V1 ch50
    assert mgr.list_overdue_foreshadows(current_chapter=50, current_volume=1) == []
    # Overdue at V2 ch110 — payoff at V2 ch100 has been passed
    overdue = mgr.list_overdue_foreshadows(current_chapter=110, current_volume=2)
    assert len(overdue) == 1
    assert overdue[0].id == "fs_over"


def test_volume_state_payoff_writes_back(fresh_state):
    """mgr.payoff_foreshadow must persist status=paid_off to state.json."""
    from data_modules.volume_state import VolumeStateManager
    mgr = VolumeStateManager(fresh_state)
    mgr.upsert_promise_entry(ForeshadowEntry(
        id="fs_p", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    mgr.payoff_foreshadow("fs_p", at_chapter=98)
    assert fresh_state["project_info"]["promise_ledger"][0]["status"] == "paid_off"