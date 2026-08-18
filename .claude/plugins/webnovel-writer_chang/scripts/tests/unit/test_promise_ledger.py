import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from data_modules.promise_ledger import (
    ForeshadowEntry,
    ForeshadowStatus,
    PromiseLedger,
)


def test_foreshadow_entry_required_fields():
    """ForeshadowEntry must carry planted_volume, expected_payoff_volume, expected_payoff_chapter."""
    now = datetime.now(timezone.utc).isoformat()
    e = ForeshadowEntry(
        id="fs_001",
        type="foreshadow",
        depth=3,
        planted_chapter=12,
        planted_volume=1,
        expected_payoff_chapter=145,
        expected_payoff_volume=3,
        status=ForeshadowStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    assert e.planted_volume == 1
    assert e.expected_payoff_volume == 3
    assert e.id == "fs_001"


def test_planted_must_precede_payoff():
    """planted_volume > expected_payoff_volume should raise."""
    now = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="planted_volume.*must precede.*expected_payoff_volume"):
        ForeshadowEntry(
            id="fs_bad",
            type="foreshadow", depth=1,
            planted_chapter=100, planted_volume=3,
            expected_payoff_chapter=50, expected_payoff_volume=1,  # backwards!
            status=ForeshadowStatus.PENDING,
            created_at=now, updated_at=now,
        )


def test_planted_eq_payoff_allowed_within_volume():
    """Same-volume plant and payoff is valid (same arc)."""
    now = datetime.now(timezone.utc).isoformat()
    e = ForeshadowEntry(
        id="fs_002",
        type="foreshadow", depth=2,
        planted_chapter=10, planted_volume=2,
        expected_payoff_chapter=50, expected_payoff_volume=2,  # same volume OK
        status=ForeshadowStatus.PENDING,
        created_at=now, updated_at=now,
    )
    assert e.planted_volume == e.expected_payoff_volume


# --- Below: T1 adversarial review fixes (7 new tests) ---


def test_id_must_be_non_empty():
    now = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="id must be non-empty"):
        ForeshadowEntry(
            id="", type="foreshadow", depth=1,
            planted_chapter=10, planted_volume=1,
            expected_payoff_chapter=100, expected_payoff_volume=2,
            status=ForeshadowStatus.PENDING,
            created_at=now, updated_at=now,
        )


def test_depth_must_be_positive():
    now = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="depth must be >= 1"):
        ForeshadowEntry(
            id="fs_d0", type="foreshadow", depth=0,
            planted_chapter=10, planted_volume=1,
            expected_payoff_chapter=100, expected_payoff_volume=2,
            status=ForeshadowStatus.PENDING,
            created_at=now, updated_at=now,
        )


def test_planted_chapter_must_be_positive():
    now = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="planted_chapter must be >= 1"):
        ForeshadowEntry(
            id="fs_c0", type="foreshadow", depth=1,
            planted_chapter=0, planted_volume=1,
            expected_payoff_chapter=100, expected_payoff_volume=2,
            status=ForeshadowStatus.PENDING,
            created_at=now, updated_at=now,
        )


def test_same_volume_chapter_must_precede():
    """planted=10, payoff=5 within same volume must reject."""
    now = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="planted_chapter must precede"):
        ForeshadowEntry(
            id="fs_rev", type="foreshadow", depth=1,
            planted_chapter=10, planted_volume=2,
            expected_payoff_chapter=5, expected_payoff_volume=2,
            status=ForeshadowStatus.PENDING,
            created_at=now, updated_at=now,
        )


def test_ledger_rejects_duplicate_ids():
    """PromiseLedger must reject duplicate id in entries."""
    now = datetime.now(timezone.utc).isoformat()
    e1 = ForeshadowEntry(
        id="dup", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at=now, updated_at=now,
    )
    e2 = ForeshadowEntry(
        id="dup", type="foreshadow", depth=2,
        planted_chapter=20, planted_volume=2,
        expected_payoff_chapter=200, expected_payoff_volume=3,
        status=ForeshadowStatus.PENDING,
        created_at=now, updated_at=now,
    )
    with pytest.raises(ValueError, match="duplicate id"):
        PromiseLedger(entries=[e1, e2])


def test_to_dict_then_from_dict_round_trip():
    """Serialization contract: to_dict → from_dict must equal original."""
    now = datetime.now(timezone.utc).isoformat()
    e = ForeshadowEntry(
        id="fs_rt", type="foreshadow", depth=2,
        planted_chapter=12, planted_volume=1,
        expected_payoff_chapter=145, expected_payoff_volume=3,
        status=ForeshadowStatus.PENDING,
        created_at=now, updated_at=now,
        notes="test notes",
    )
    d = e.to_dict()
    assert d["status"] == "pending"  # str, not enum
    e2 = ForeshadowEntry.from_dict(d)
    assert e2.id == e.id
    assert e2.status == ForeshadowStatus.PENDING
    assert e2.notes == "test notes"


def test_to_list_empty_ledger():
    """Empty PromiseLedger.to_list() must return []."""
    assert PromiseLedger().to_list() == []


# --- Below: T2 cross-volume ledger API (6 new tests) ---


def test_ledger_upsert_new_entry():
    ledger = PromiseLedger()
    e = ForeshadowEntry(
        id="fs_x", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    ledger.upsert(e)
    assert len(ledger.entries) == 1
    assert ledger.entries[0].id == "fs_x"


def test_ledger_upsert_existing_replaces():
    ledger = PromiseLedger()
    e1 = ForeshadowEntry(
        id="fs_x", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    e2 = ForeshadowEntry(
        id="fs_x", type="foreshadow", depth=2,  # depth changed
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.ADVANCED,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T01:00:00+00:00",
    )
    ledger.upsert(e1)
    ledger.upsert(e2)
    assert len(ledger.entries) == 1
    assert ledger.entries[0].depth == 2
    assert ledger.entries[0].status == ForeshadowStatus.ADVANCED


def test_advance_then_payoff():
    ledger = PromiseLedger()
    e = ForeshadowEntry(
        id="fs_y", type="foreshadow", depth=2,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    ledger.upsert(e)
    ledger.advance("fs_y", at_chapter=50)
    assert ledger.entries[0].status == ForeshadowStatus.ADVANCED
    ledger.payoff("fs_y", at_chapter=98)
    assert ledger.entries[0].status == ForeshadowStatus.PAID_OFF


def test_overdue_detection_by_chapter():
    ledger = PromiseLedger()
    # Expected payoff at ch 100, but current is 110 — overdue
    e = ForeshadowEntry(
        id="fs_over", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    ledger.upsert(e)
    overdue = ledger.list_overdue(current_chapter=110, current_volume=2)
    assert len(overdue) == 1
    assert overdue[0].id == "fs_over"


def test_no_overdue_when_paid_off():
    ledger = PromiseLedger()
    e = ForeshadowEntry(
        id="fs_z", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PAID_OFF,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    ledger.upsert(e)
    overdue = ledger.list_overdue(current_chapter=200, current_volume=3)
    assert overdue == []


def test_filter_by_volume():
    ledger = PromiseLedger()
    for vol in (1, 2, 3):
        ledger.upsert(ForeshadowEntry(
            id=f"fs_v{vol}", type="foreshadow", depth=1,
            planted_chapter=10, planted_volume=vol,
            expected_payoff_chapter=100, expected_payoff_volume=vol,
            status=ForeshadowStatus.PENDING,
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        ))
    in_vol_2 = ledger.list_for_volume(2)
    assert len(in_vol_2) == 1
    assert in_vol_2[0].id == "fs_v2"