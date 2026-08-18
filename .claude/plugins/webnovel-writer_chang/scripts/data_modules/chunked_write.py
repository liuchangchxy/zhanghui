"""Chunked write policy + pre-write gate evaluator.

Spec: docs/superpowers/specs/2026-08-19-macro-upfront-micro-chunked-design.md §6.4.

denova chapter-group mode + oh-story 中途快照模式 + tianming 六道门禁模式.
"""
from __future__ import annotations

from dataclasses import dataclass


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

    Returns a list of issue strings. BLOCKER if any overdue foreshadow
    exists. Empty list means gates passed.
    """
    issues: list[str] = []
    for entry in overdue_foreshadows:
        issues.append(
            f"BLOCKER: foreshadow {entry.id} overdue — must be paid off before "
            f"writing chapter {chapter} (volume {current_volume})"
        )
    return issues