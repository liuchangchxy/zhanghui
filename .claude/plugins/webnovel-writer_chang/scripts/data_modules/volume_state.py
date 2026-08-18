"""Volume state management for multi-volume init.

Owns per-volume status state machine (confirmed / draft / deferred)
plus planning_horizon metadata. See
docs/superpowers/specs/2026-08-18-multi-volume-init-design.md
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum


class VolumeStatus(str, Enum):
    CONFIRMED = "confirmed"
    DRAFT = "draft"
    DEFERRED = "deferred"


class VolumeSource(str, Enum):
    HUMAN = "human"
    AI = "ai"


class LaterVolumesStatus(str, Enum):
    DEFERRED = "deferred"
    UNKNOWN = "unknown"
    PLANNED = "planned"


@dataclass(kw_only=True)
class _VolumeFields:
    title: str = ""
    chapter_range: list[int] = field(default_factory=lambda: [0, 0])
    core_conflict: str = ""
    climax: str = ""
    key_cool_points: list[str] = field(default_factory=list)
    characters_to_appear: list[str] = field(default_factory=list)
    foreshadowing: list[str] = field(default_factory=list)


@dataclass
class VolumeRecord(_VolumeFields):
    index: int
    status: VolumeStatus = VolumeStatus.DRAFT
    source: VolumeSource = VolumeSource.HUMAN
    updated_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["source"] = self.source.value
        return d


@dataclass
class CandidateVolume(_VolumeFields):
    """In-memory draft from AI drafter. Never persisted."""
    index: int
    status: VolumeStatus = VolumeStatus.DRAFT  # always draft per spec §5.2
    source: VolumeSource = VolumeSource.AI


@dataclass
class PlanningHorizon:
    expected_total_volumes: int | None = None
    confirmed_through_volume: int = 0
    later_volumes_status: LaterVolumesStatus = LaterVolumesStatus.DEFERRED


class VolumeStateManager:
    """Owns volumes[] + planning_horizon in state.json.

    Invariants enforced:
      - volumes[i].index is contiguous (no holes)
      - confirmed fields are not overwritten by AI drafts
      - drafts never persist to state.json (live in self._drafts only)
      - confirmed_through_volume = max(index of confirmed volumes)
    """

    def __init__(self, state: dict):
        self.state = state
        self.state.setdefault("volumes", [])
        self.state.setdefault("project_info", {})
        self._drafts: dict[int, CandidateVolume] = {}

    # ----- read -----

    def list_volumes(self) -> list[VolumeRecord]:
        return [self._from_dict(d) for d in self.state["volumes"]]

    def get_volume(self, index: int) -> VolumeRecord | None:
        for d in self.state["volumes"]:
            if d["index"] == index:
                return self._from_dict(d)
        return None

    def get_planning_horizon(self) -> PlanningHorizon:
        pi = self.state["project_info"]
        lvs_raw = pi.get("later_volumes_status", "deferred")
        if isinstance(lvs_raw, LaterVolumesStatus):
            lvs = lvs_raw
        else:
            try:
                lvs = LaterVolumesStatus(lvs_raw)
            except ValueError:
                lvs = LaterVolumesStatus.DEFERRED
        # Recompute from volumes[] rather than trusting the cached field
        confirmed = [d["index"] for d in self.state.get("volumes", []) if d.get("status") == "confirmed"]
        confirmed_through = max(confirmed) if confirmed else 0
        return PlanningHorizon(
            expected_total_volumes=pi.get("expected_total_volumes"),
            confirmed_through_volume=confirmed_through,
            later_volumes_status=lvs,
        )

    def has_pending_draft(self, index: int) -> bool:
        return index in self._drafts

    # ----- write: human input -----

    def append_or_update(self, rec: VolumeRecord) -> None:
        if rec.status == VolumeStatus.DRAFT:
            raise ValueError(
                "Cannot append_or_update with status=DRAFT — use append_draft() for "
                "in-memory candidates and confirm_volume() to persist."
            )
        # Defensive: refuse AI source for any user-controlled state (confirmed/deferred)
        existing_idx = self._find_dict_index(rec.index)
        if existing_idx is not None:
            existing = self.state["volumes"][existing_idx]
            if (
                existing.get("status") == "confirmed"
                and rec.source == VolumeSource.AI
            ):
                raise ValueError(
                    f"AI cannot overwrite confirmed volume {rec.index} "
                    f"via append_or_update; use confirm_volume() which has the check."
                )
        self._check_continuity(rec.index)
        d = rec.to_dict()
        d["updated_at"] = _now_iso()
        if existing_idx is not None:
            self.state["volumes"][existing_idx] = d
        else:
            self.state["volumes"].append(d)
        self._sort_by_index()
        self._update_horizon()

    # ----- write: AI draft -----

    def append_draft(self, candidate: CandidateVolume) -> None:
        self._drafts[candidate.index] = candidate

    def confirm_volume(self, index: int) -> None:
        """Promote in-memory draft (or existing record) to confirmed.

        - If a draft exists for this index AND no existing record is confirmed: promote.
        - If a draft exists AND a record is already confirmed: refuse (no overwrite).
        - If no draft but record exists (deferred): flip status to confirmed.
        - If no draft and no record: raise.
        """
        if index in self._drafts:
            cand = self._drafts.pop(index)
            existing_idx = self._find_dict_index(index)
            if existing_idx is not None:
                existing_status = self.state["volumes"][existing_idx].get("status")
                if existing_status in ("confirmed", "deferred"):
                    # AI must NOT overwrite any user-controlled state
                    return
            rec = VolumeRecord(
                index=cand.index,
                title=cand.title,
                chapter_range=list(cand.chapter_range),
                core_conflict=cand.core_conflict,
                climax=cand.climax,
                key_cool_points=list(cand.key_cool_points),
                characters_to_appear=list(cand.characters_to_appear),
                foreshadowing=list(cand.foreshadowing),
                status=VolumeStatus.CONFIRMED,
                source=VolumeSource.AI,
            )
            self.append_or_update(rec)
            return

        existing_idx = self._find_dict_index(index)
        if existing_idx is None:
            raise ValueError(f"No record or draft for volume {index}")
        self._set_status(index, VolumeStatus.CONFIRMED, {VolumeStatus.DEFERRED})

    def set_deferred(self, index: int) -> None:
        # _set_status will raise if the record is missing
        self._set_status(index, VolumeStatus.DEFERRED, {VolumeStatus.CONFIRMED})

    def revise_volume(self, index: int, fields: dict) -> None:
        """Update specific fields of an existing record. Refuses AI overwrite of confirmed/deferred."""
        existing_idx = self._find_dict_index(index)
        if existing_idx is None:
            raise ValueError(f"No record for volume {index}")
        existing = self.state["volumes"][existing_idx]
        # Defensive: refuse AI source for any user-controlled state
        if fields.get("source") == VolumeSource.AI and existing.get("status") in ("confirmed", "deferred"):
            raise ValueError(f"Cannot revise confirmed/deferred volume {index} with AI source")
        for k, v in fields.items():
            existing[k] = v
        existing["updated_at"] = _now_iso()
        # No horizon recompute since fields shouldn't include status

    # ----- internal -----

    def _find_dict_index(self, index: int) -> int | None:
        for i, d in enumerate(self.state["volumes"]):
            if d["index"] == index:
                return i
        return None

    def _check_continuity(self, new_index: int) -> None:
        existing_indexes = sorted(d["index"] for d in self.state["volumes"])
        if not existing_indexes:
            if new_index != 1:
                raise ValueError(
                    f"index continuity violated: first volume must be 1, got {new_index}"
                )
            return
        expected = set(range(1, existing_indexes[-1] + 1))
        actual = set(existing_indexes)
        if actual != expected:
            missing = sorted(expected - actual)
            raise ValueError(
                f"index continuity violated: missing indexes {missing} "
                f"before inserting {new_index}"
            )
        if new_index > existing_indexes[-1] + 1:
            raise ValueError(
                f"index continuity violated: expected next index "
                f"{existing_indexes[-1] + 1}, got {new_index}"
            )

    def _set_status(
        self,
        index: int,
        new_status: VolumeStatus,
        allowed_from: set[VolumeStatus],
    ) -> None:
        """Transition a persisted record's status if currently in allowed_from; no-op otherwise."""
        existing_idx = self._find_dict_index(index)
        if existing_idx is None:
            raise ValueError(f"No record for volume {index}")
        cur = VolumeStatus(self.state["volumes"][existing_idx]["status"])
        if cur not in allowed_from:
            return
        self.state["volumes"][existing_idx]["status"] = new_status.value
        self.state["volumes"][existing_idx]["updated_at"] = _now_iso()
        self._update_horizon()

    def _sort_by_index(self) -> None:
        self.state["volumes"].sort(key=lambda d: d["index"])

    def _update_horizon(self) -> None:
        confirmed = [d["index"] for d in self.state["volumes"] if d["status"] == "confirmed"]
        self.state["project_info"]["confirmed_through_volume"] = max(confirmed) if confirmed else 0
        if "later_volumes_status" not in self.state["project_info"]:
            self.state["project_info"]["later_volumes_status"] = LaterVolumesStatus.DEFERRED.value

    def _from_dict(self, d: dict) -> VolumeRecord:
        return VolumeRecord(
            index=d["index"],
            title=d.get("title", ""),
            chapter_range=d.get("chapter_range", [0, 0]),
            core_conflict=d.get("core_conflict", ""),
            climax=d.get("climax", ""),
            key_cool_points=d.get("key_cool_points", []),
            characters_to_appear=d.get("characters_to_appear", []),
            foreshadowing=d.get("foreshadowing", []),
            status=VolumeStatus(d.get("status", "draft")),
            source=VolumeSource(d.get("source", "human")),
            updated_at=d.get("updated_at", ""),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
