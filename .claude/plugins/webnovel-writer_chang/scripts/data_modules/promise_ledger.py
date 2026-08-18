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


@dataclass(frozen=True)
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
        # Boundary checks (Critical 2)
        if not self.id:
            raise ValueError("id must be non-empty")
        if self.depth < 1:
            raise ValueError("depth must be >= 1")
        if self.planted_chapter < 1:
            raise ValueError("planted_chapter must be >= 1")
        if self.expected_payoff_chapter < 1:
            raise ValueError("expected_payoff_chapter must be >= 1")

        # Volume order first, then within-volume chapter order (avoids boundary conflicts)
        if self.planted_volume > self.expected_payoff_volume:
            raise ValueError(
                f"planted_volume ({self.planted_volume}) must precede "
                f"expected_payoff_volume ({self.expected_payoff_volume})"
            )
        if (
            self.planted_volume == self.expected_payoff_volume
            and self.planted_chapter >= self.expected_payoff_chapter
        ):
            raise ValueError(
                "planted_chapter must precede expected_payoff_chapter when same volume"
            )

        # Auto-fill timestamps via object.__setattr__ (frozen=True disallows normal self.x = ...)
        if not self.created_at:
            object.__setattr__(
                self, "created_at", datetime.now(timezone.utc).isoformat()
            )
        if not self.updated_at:
            object.__setattr__(self, "updated_at", self.created_at)

    def to_dict(self) -> dict:
        d = asdict(self)
        # asdict already converts ForeshadowStatus(str, Enum).value → str, no manual conversion needed
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ForeshadowEntry":
        return cls(
            id=d["id"],
            type=d["type"],
            depth=d["depth"],
            planted_chapter=d["planted_chapter"],
            planted_volume=d["planted_volume"],
            expected_payoff_chapter=d["expected_payoff_chapter"],
            expected_payoff_volume=d["expected_payoff_volume"],
            status=ForeshadowStatus(d["status"]),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            notes=d.get("notes", ""),
        )


@dataclass
class PromiseLedger:
    """List of ForeshadowEntry + helper methods.

    Owned state lives in state.json.project_info.promise_ledger (list[dict]).
    """
    entries: list[ForeshadowEntry] = field(default_factory=list)

    def __post_init__(self):
        ids = [e.id for e in self.entries]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate id in entries")

    def to_list(self) -> list[dict]:
        return [e.to_dict() for e in self.entries]