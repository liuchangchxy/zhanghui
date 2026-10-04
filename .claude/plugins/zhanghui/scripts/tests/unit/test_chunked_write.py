import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_modules.chunked_write import (
    ChunkedWritePolicy,
    should_take_snapshot,
    evaluate_pre_write_gates,
    evaluate_pre_write_gates_with_threshold,
)
from data_modules.promise_ledger import (
    ForeshadowEntry,
    ForeshadowStatus,
    PromiseLedger,
)


def test_should_snapshot_every_3_chapters():
    assert should_take_snapshot(3, snapshot_every=3) is True
    assert should_take_snapshot(6, snapshot_every=3) is True
    assert should_take_snapshot(2, snapshot_every=3) is False
    assert should_take_snapshot(7, snapshot_every=3) is False


def test_policy_default():
    p = ChunkedWritePolicy()
    assert p.chunk_size == 5
    assert p.snapshot_every == 3
    assert p.fore_check_threshold == 50


def test_evaluate_pre_write_gates_no_overdue():
    """Empty overdue list → no blockers."""
    issues = evaluate_pre_write_gates(
        chapter=10, current_volume=1,
        overdue_foreshadows=[],
    )
    assert issues == []


def test_evaluate_pre_write_gates_with_overdue_returns_blocker():
    """Any overdue foreshadow → BLOCKER list."""
    # Mock entry-like object with .id attribute
    class FakeEntry:
        id = "fs_over1_1"
    issues = evaluate_pre_write_gates(
        chapter=110, current_volume=2,
        overdue_foreshadows=[FakeEntry()],
    )
    assert len(issues) == 1
    assert "BLOCKER" in issues[0]
    assert "fs_over1_1" in issues[0]


# ===== I9: fore_check_threshold honored via evaluate_pre_write_gates_with_threshold =====


def test_evaluate_pre_write_gates_with_threshold_warns_near_payoff():
    """I9: entries whose expected_payoff_chapter is within `threshold` of
    `chapter` (and same volume) trigger BLOCKER even when not yet overdue.
    """
    ledger = PromiseLedger()
    # Planted V1 ch10, payoff V2 ch110 — at ch 80 (current V2) it's 30 chapters
    # away, well within default threshold=50 → pre-overdue BLOCKER.
    ledger.upsert(ForeshadowEntry(
        id="fs_near", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=110, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    issues = evaluate_pre_write_gates_with_threshold(
        chapter=80, current_volume=2, ledger=ledger,
    )
    # Should produce a BLOCKER about the foreshadow approaching payoff.
    approaching = [i for i in issues if "approaching payoff" in i]
    assert len(approaching) == 1
    assert "fs_near" in approaching[0]
    assert "30 chapters away" in approaching[0]


def test_evaluate_pre_write_gates_with_threshold_skips_far_payoff():
    """I9: if remaining chapters > threshold, no BLOCKER from pre-overdue path."""
    ledger = PromiseLedger()
    ledger.upsert(ForeshadowEntry(
        id="fs_far", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=200, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    issues = evaluate_pre_write_gates_with_threshold(
        chapter=80, current_volume=2, ledger=ledger, threshold=50,
    )
    # 200 - 80 = 120 > 50 → no approaching BLOCKER
    approaching = [i for i in issues if "approaching payoff" in i]
    assert approaching == []


def test_evaluate_pre_write_gates_with_threshold_skips_paid_off():
    """I9: PAID_OFF entries must NOT trigger pre-overdue BLOCKERs."""
    ledger = PromiseLedger()
    ledger.upsert(ForeshadowEntry(
        id="fs_paidpre", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=110, expected_payoff_volume=2,
        status=ForeshadowStatus.PAID_OFF,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    issues = evaluate_pre_write_gates_with_threshold(
        chapter=80, current_volume=2, ledger=ledger,
    )
    approaching = [i for i in issues if "approaching payoff" in i]
    assert approaching == []


def test_evaluate_pre_write_gates_with_threshold_default_disabled_for_old_helper():
    """I9: legacy evaluate_pre_write_gates (no threshold) is unchanged — only
    overdue entries raise BLOCKER. pre-overdue path does NOT activate here.
    """
    ledger = PromiseLedger()
    ledger.upsert(ForeshadowEntry(
        id="fs_legacyok", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=110, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    # At ch 80, current V2: not yet overdue (payoff 110 > 80), but within 30 chs
    # of the threshold default 50. The OLD helper must NOT catch this:
    issues = evaluate_pre_write_gates(
        chapter=80, current_volume=2, overdue_foreshadows=[],
    )
    assert issues == []


def test_evaluate_pre_write_gates_with_threshold_combines_overdue_and_pre():
    """I9: with_threshold path surfaces BOTH overdue and pre-overdue BLOCKERs."""
    ledger = PromiseLedger()
    # Overdue entry (payoff in past)
    ledger.upsert(ForeshadowEntry(
        id="fs_o", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    # Pre-overdue entry (within threshold)
    ledger.upsert(ForeshadowEntry(
        id="fs_p", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=120, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    issues = evaluate_pre_write_gates_with_threshold(
        chapter=110, current_volume=2, ledger=ledger, threshold=50,
    )
    # Both BLOCKERs present
    assert any("fs_o" in i and "overdue" in i for i in issues)
    assert any("fs_p" in i and "approaching payoff" in i for i in issues)