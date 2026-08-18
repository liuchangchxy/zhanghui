"""Volume state management for multi-volume init.

Owns per-volume status state machine (confirmed / draft / deferred)
plus planning_horizon metadata. See
docs/superpowers/specs/2026-08-18-multi-volume-init-design.md
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
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
