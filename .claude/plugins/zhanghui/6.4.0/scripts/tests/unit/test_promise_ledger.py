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


# ===== Phase 1 fixes: I1 mark_overdue, I2 audit_log, I3 type whitelist, I4 notes cap =====


def test_type_must_be_whitelisted():
    """I3: type must be one of {foreshadow, promise, callback}."""
    now = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="type must be one of"):
        ForeshadowEntry(
            id="fs_badtype", type="easter_egg",  # not whitelisted
            depth=1, planted_chapter=10, planted_volume=1,
            expected_payoff_chapter=100, expected_payoff_volume=2,
            status=ForeshadowStatus.PENDING,
            created_at=now, updated_at=now,
        )


def test_notes_max_length_enforced():
    """I4: notes must not exceed 4096 chars."""
    now = datetime.now(timezone.utc).isoformat()
    huge_notes = "x" * 4097
    with pytest.raises(ValueError, match="notes exceeds 4096"):
        ForeshadowEntry(
            id="fs_huge", type="foreshadow", depth=1,
            planted_chapter=10, planted_volume=1,
            expected_payoff_chapter=100, expected_payoff_volume=2,
            status=ForeshadowStatus.PENDING,
            created_at=now, updated_at=now,
            notes=huge_notes,
        )


def test_notes_at_exactly_4096_is_allowed():
    """I4: 4096 chars exactly must be accepted (boundary)."""
    now = datetime.now(timezone.utc).isoformat()
    e = ForeshadowEntry(
        id="fs_ok_len", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at=now, updated_at=now,
        notes="x" * 4096,
    )
    assert len(e.notes) == 4096


def test_mark_overdue_sets_status():
    """I1: ledger.mark_overdue flips eligible entries to OVERDUE."""
    ledger = PromiseLedger()
    ledger.upsert(ForeshadowEntry(
        id="fs_mo", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    ledger.mark_overdue("fs_mo")
    assert ledger.entries[0].status == ForeshadowStatus.OVERDUE


def test_mark_overdue_skips_paid_off():
    """I1: PAID_OFF entries must NOT be flipped to OVERDUE."""
    ledger = PromiseLedger()
    ledger.upsert(ForeshadowEntry(
        id="fs_paid", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PAID_OFF,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    ledger.mark_overdue("fs_paid")
    # Untouched
    assert ledger.entries[0].status == ForeshadowStatus.PAID_OFF


def test_mark_overdue_raises_for_unknown_id():
    """I1: unknown id raises KeyError."""
    ledger = PromiseLedger()
    with pytest.raises(KeyError, match="foreshadow not found"):
        ledger.mark_overdue("nope")


def test_advance_records_audit_log():
    """I2: advance() must record an audit_log entry with at_chapter."""
    ledger = PromiseLedger()
    ledger.upsert(ForeshadowEntry(
        id="fs_audit", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    assert ledger.entries[0].audit_log == []
    ledger.advance("fs_audit", at_chapter=50)
    log = ledger.entries[0].audit_log
    assert len(log) == 1
    assert log[0]["action"] == "advance"
    assert log[0]["chapter"] == 50
    assert "ts" in log[0]


def test_payoff_records_audit_log():
    """I2: payoff() must record an audit_log entry with at_chapter."""
    ledger = PromiseLedger()
    ledger.upsert(ForeshadowEntry(
        id="fs_paylog", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.ADVANCED,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    ledger.payoff("fs_paylog", at_chapter=98)
    log = ledger.entries[0].audit_log
    assert len(log) == 1
    assert log[0]["action"] == "payoff"
    assert log[0]["chapter"] == 98


def test_audit_log_round_trips_through_dict():
    """I2: audit_log survives to_dict → from_dict round-trip."""
    ledger = PromiseLedger()
    ledger.upsert(ForeshadowEntry(
        id="fs_roundtrip", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    ledger.advance("fs_roundtrip", at_chapter=50)
    ledger.payoff("fs_roundtrip", at_chapter=98)
    d = ledger.entries[0].to_dict()
    assert "audit_log" in d and len(d["audit_log"]) == 2
    # Round-trip via from_dict
    rebuilt = ForeshadowEntry.from_dict(d)
    assert rebuilt.audit_log == d["audit_log"]
    assert rebuilt.audit_log[0]["action"] == "advance"
    assert rebuilt.audit_log[1]["action"] == "payoff"


def test_audit_log_default_empty_for_backcompat():
    """I2: entries created without audit_log default to empty list (back-additive)."""
    now = datetime.now(timezone.utc).isoformat()
    e = ForeshadowEntry(
        id="fs_nolog", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at=now, updated_at=now,
    )
    assert e.audit_log == []