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
    # audit_log is list[dict] (frozen dataclass allows mutation of mutable fields' contents).
    # Each entry: {"action": "advance"|"payoff"|"mark_overdue", "chapter": int, "ts": iso_now}
    # backward-additive: not present in entries created before this column existed.
    audit_log: list[dict] = field(default_factory=list)
    # Exact optional Canon pointer. It is opaque and never changes this row's
    # planner-owned status or the lifecycle of the referenced Canon event.
    canon_event_ref: str | None = None

    _ALLOWED_TYPES = frozenset({"foreshadow", "promise", "callback"})
    _MAX_NOTES_LEN = 4096

    def __post_init__(self):
        # I3: type whitelist
        if self.type not in self._ALLOWED_TYPES:
            raise ValueError(
                f"type must be one of {sorted(self._ALLOWED_TYPES)}, got {self.type!r}"
            )
        # I4: notes max length
        if len(self.notes) > self._MAX_NOTES_LEN:
            raise ValueError(
                f"notes exceeds {self._MAX_NOTES_LEN} chars (got {len(self.notes)})"
            )
        # Boundary checks (Critical 2)
        if not self.id:
            raise ValueError("id must be non-empty")
        if self.canon_event_ref is not None and (
                not isinstance(self.canon_event_ref, str) or not self.canon_event_ref.strip()):
            raise ValueError("canon_event_ref must be a non-empty opaque ID")
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
            audit_log=list(d.get("audit_log", []) or []),
            canon_event_ref=d.get("canon_event_ref"),
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

    # --- T2 cross-volume ledger API ---

    def upsert(self, entry: ForeshadowEntry) -> None:
        """Add or replace entry by id. Updates updated_at via new entry's value."""
        for i, existing in enumerate(self.entries):
            if existing.id == entry.id:
                self.entries[i] = entry
                return
        self.entries.append(entry)

    def update_schedule(self, entry_id: str, *, expected_payoff_chapter: int,
                        expected_payoff_volume: int, canon_event_ref: str | None = None) -> None:
        """Edit planner schedule while preserving status and exact Canon reference."""
        for index, existing in enumerate(self.entries):
            if existing.id != entry_id:
                continue
            data = existing.to_dict()
            data["expected_payoff_chapter"] = expected_payoff_chapter
            data["expected_payoff_volume"] = expected_payoff_volume
            if canon_event_ref is not None:
                if not isinstance(canon_event_ref, str) or not canon_event_ref.strip():
                    raise ValueError("canon_event_ref must be a non-empty opaque ID")
                data["canon_event_ref"] = canon_event_ref
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.entries[index] = ForeshadowEntry.from_dict(data)
            return
        raise KeyError(f"foreshadow not found: {entry_id}")

    def defer(self, entry_id: str, *, expected_payoff_chapter: int,
              expected_payoff_volume: int) -> None:
        """Defer the planner deadline without changing the legacy lifecycle enum."""
        self._record_planner_action(
            entry_id, "defer", expected_payoff_chapter=expected_payoff_chapter,
            expected_payoff_volume=expected_payoff_volume,
        )

    def cancel(self, entry_id: str) -> None:
        """Cancel planner intent only; Canon-derived rows remain untouched."""
        self._record_planner_action(entry_id, "cancel")

    def is_cancelled(self, entry_id: str) -> bool:
        for entry in self.entries:
            if entry.id == entry_id:
                return bool(entry.audit_log and entry.audit_log[-1].get("action") == "cancel")
        raise KeyError(f"foreshadow not found: {entry_id}")

    def _record_planner_action(self, entry_id: str, action: str, **schedule: int) -> None:
        if action not in {"defer", "cancel"}:
            raise ValueError("unsupported planner action")
        for index, existing in enumerate(self.entries):
            if existing.id != entry_id:
                continue
            data = existing.to_dict()
            data.update(schedule)
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            data["audit_log"] = [*data.get("audit_log", []), {
                "action": action, "chapter": 0, "ts": data["updated_at"],
            }]
            self.entries[index] = ForeshadowEntry.from_dict(data)
            return
        raise KeyError(f"foreshadow not found: {entry_id}")

    def advance(self, entry_id: str, at_chapter: int) -> None:
        """Transition entry to ADVANCED status; record audit_log entry (I2)."""
        self._mutate_status(entry_id, ForeshadowStatus.ADVANCED,
                            action="advance", at_chapter=at_chapter)

    def payoff(self, entry_id: str, at_chapter: int) -> None:
        """Transition entry to PAID_OFF status; record audit_log entry (I2)."""
        self._mutate_status(entry_id, ForeshadowStatus.PAID_OFF,
                            action="payoff", at_chapter=at_chapter)

    def mark_overdue(self, entry_id: str) -> None:
        """I1: flip an entry whose payoff is overdue to OVERDUE.

        Entries already paid off are not touched (they're already resolved).
        Side-effecting writeback — callers are expected to persist the
        updated ledger via the VolumeStateManager method that wraps this.
        """
        # Read current status first; PAID_OFF entries must not flip.
        current_status = None
        for existing in self.entries:
            if existing.id == entry_id:
                current_status = existing.status
                break
        if current_status is None:
            raise KeyError(f"foreshadow not found: {entry_id}")
        if current_status == ForeshadowStatus.PAID_OFF:
            return  # already resolved — leave untouched
        # Use at_chapter=0 to mean "lifecycle marker, no specific chapter event"
        self._mutate_status(entry_id, ForeshadowStatus.OVERDUE,
                            action="mark_overdue", at_chapter=0)

    def _mutate_status(
        self,
        entry_id: str,
        new_status: ForeshadowStatus,
        *,
        action: str | None = None,
        at_chapter: int | None = None,
    ) -> None:
        """Replace entry with a new ForeshadowEntry with new status (frozen-compatible)."""
        for i, existing in enumerate(self.entries):
            if existing.id == entry_id:
                # Build replacement via from_dict (frozen-safe construction)
                d = existing.to_dict()
                d["status"] = new_status.value
                d["updated_at"] = datetime.now(timezone.utc).isoformat()
                # I2: record audit_log entry (only when action supplied; backward compat)
                if action is not None:
                    log = list(d.get("audit_log") or [])
                    log.append({
                        "action": action,
                        "chapter": int(at_chapter) if at_chapter is not None else 0,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    })
                    d["audit_log"] = log
                self.entries[i] = ForeshadowEntry.from_dict(d)
                return
        raise KeyError(f"foreshadow not found: {entry_id}")

    def list_overdue(self, current_chapter: int, current_volume: int) -> list[ForeshadowEntry]:
        """Return entries that should have been paid off but aren't."""
        result: list[ForeshadowEntry] = []
        for e in self.entries:
            if e.status == ForeshadowStatus.PAID_OFF:
                continue
            if e.audit_log and e.audit_log[-1].get("action") == "cancel":
                continue
            if e.expected_payoff_volume < current_volume:
                result.append(e)
            elif (e.expected_payoff_volume == current_volume
                  and e.expected_payoff_chapter < current_chapter):
                result.append(e)
        return result

    def list_for_volume(self, volume: int) -> list[ForeshadowEntry]:
        """Return entries planted OR scheduled to payoff in given volume."""
        return [e for e in self.entries
                if not (e.audit_log and e.audit_log[-1].get("action") == "cancel")
                if e.planted_volume == volume or e.expected_payoff_volume == volume]
