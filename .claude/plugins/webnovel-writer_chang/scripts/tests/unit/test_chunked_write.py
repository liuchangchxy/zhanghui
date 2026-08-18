import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_modules.chunked_write import (
    ChunkedWritePolicy,
    should_take_snapshot,
    evaluate_pre_write_gates,
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