"""Core abstractions for consistency patches.

Source: 原創（設計參考 oh-story-claudecode 的 Patch 概念）
Path in references: N/A
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CheckContext:
    project_root: Path
    chapter_num: int
    state: dict
    chapter_outline: dict | None
    previous_chapters: list[dict]
    chapter_text: str | None


@dataclass
class ApplyContext:
    project_root: Path
    chapter_num: int
    state: dict


@dataclass
class Blocker:
    patch: str
    chapter: int
    message: str
    fix_hint: str
    # Optional machine-authored Phase 6A identity/evidence. Legacy fields stay
    # intact and remain the only fields used by existing CLI renderers.
    issue_code: str | None = None
    subject_id: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


class Patch(ABC):
    name: str = ""
    description: str = ""
    depends_on: tuple[str, ...] = ()

    @abstractmethod
    def check(self, ctx: CheckContext) -> list[Blocker]: ...

    @abstractmethod
    def apply(self, ctx: ApplyContext) -> None: ...
