"""Promise ledger for cross-volume foreshadowing.

Spec: docs/superpowers/specs/2026-08-19-macro-upfront-micro-chunked-design.md §5.1.

Openwrite / neuro-book / QMAI 模式: 任意时刻状态推算 + 可审计.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum


class ForeshadowStatus(str, Enum):
    PENDING = "pending"
    ADVANCED = "advanced"
    PAID_OFF = "paid_off"
    OVERDUE = "overdue"


@dataclass
class ForeshadowEntry:
    id: str
    type: str  # 'foreshadow' | 'promise' | 'callback'
    depth: int
    planted_chapter: int
    planted_volume: int
    expected_payoff_chapter: int
    expected_payoff_volume: int
    status: ForeshadowStatus = ForeshadowStatus.PENDING
    created_at: str = ""
    updated_at: str = ""
    notes: str = ""

    def __post_init__(self):
        if self.planted_volume > self.expected_payoff_volume:
            raise ValueError(
                f"planted_volume ({self.planted_volume}) must precede "
                f"expected_payoff_volume ({self.expected_payoff_volume})"
            )
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class PromiseLedger:
    """List of ForeshadowEntry + helper methods.

    Owned state lives in state.json.project_info.promise_ledger (list[dict]).
    """
    entries: list[ForeshadowEntry] = field(default_factory=list)

    def to_list(self) -> list[dict]:
        return [e.to_dict() for e in self.entries]