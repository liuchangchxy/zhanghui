"""Chunked write policy + pre-write gate evaluator.

Spec: docs/superpowers/specs/2026-08-19-macro-upfront-micro-chunked-design.md §6.4.

denova chapter-group mode + oh-story 中途快照模式 + tianming 六道门禁模式.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid runtime import cycles
    from data_modules.promise_ledger import ForeshadowEntry


@dataclass
class ChunkedWritePolicy:
    chunk_size: int = 5            # denova default 3-8 章/批
    snapshot_every: int = 3        # oh-story 每 3 章检查点
    fore_check_threshold: int = 50 # 距离伏笔回收 N 章 BLOCKER 警告阈值


def should_take_snapshot(chapter: int, snapshot_every: int = 3) -> bool:
    """oh-story pattern: 每 N 章强制 snapshot."""
    if snapshot_every <= 0:
        return False
    return chapter % snapshot_every == 0 and chapter > 0


def evaluate_pre_write_gates(
    chapter: int,
    current_volume: int,
    overdue_foreshadows: list,
) -> list[str]:
    """tianming 六道门禁模式: 写前检查跨卷伏笔 overdue.

    Returns advisory issue strings for overdue foreshadows. This observation
    never prevents writing; explicit user constraints are handled separately.
    """
    issues: list[str] = []
    for entry in overdue_foreshadows:
        issues.append(
            f"ADVISORY: foreshadow {entry.id} is overdue — consider the plan deviation "
            f"while writing chapter {chapter} (volume {current_volume})"
        )
    return issues


def evaluate_pre_write_gates_with_threshold(
    chapter: int,
    current_volume: int,
    ledger,  # PromiseLedger — runtime-typed to break circular import
    threshold: int = 50,
) -> list[str]:
    """I9: forward-looking variant of evaluate_pre_write_gates.

    In addition to the overdue check (delegated to evaluate_pre_write_gates),
    this also BLOCKERs any non-PAID_OFF foreshadow whose `expected_payoff_volume`
    equals `current_volume` and whose payoff is within `threshold` chapters of
    the current chapter — a pre-overdue warning so writers can be reminded to
    schedule the payoff.

    The default `threshold=50` matches `ChunkedWritePolicy.fore_check_threshold`.

    Backward-compatible: callers that only need the overdue behavior should
    keep using evaluate_pre_write_gates. This function exists to honor
    spec §6.4's `fore_check_threshold` semantics explicitly.
    """
    # Use the existing helper for the overdue list so semantics stay unified.
    from data_modules.promise_ledger import ForeshadowStatus
    overdue = ledger.list_overdue(chapter, current_volume)
    issues = evaluate_pre_write_gates(chapter, current_volume, overdue)

    # Pre-overdue: entries not yet overdue but within `threshold` chapters
    # of their expected payoff chapter (same volume).
    for e in ledger.entries:
        if e.status == ForeshadowStatus.PAID_OFF:
            continue
        if e.expected_payoff_volume == current_volume:
            remaining = e.expected_payoff_chapter - chapter
            if 0 < remaining <= threshold:
                issues.append(
                    f"ADVISORY: foreshadow {e.id} approaching payoff "
                    f"({remaining} chapters away, threshold={threshold})"
                )
    return issues
