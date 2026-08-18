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