"""Core abstractions for consistency patches.

Source: 原創（設計參考 oh-story-claudecode 的 Patch 概念）
Path in references: N/A
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CheckContext:
    project_root: Path
    chapter_num: int
    state: dict
    chapter_outline: dict | None
    previous_chapters: list[dict]
    chapter_text: str | None
    external_inputs: dict[str, object] = field(default_factory=dict)


@dataclass
class ApplyContext:
    project_root: Path
    chapter_num: int
    state: dict


@dataclass
class PatchFinding:
    """Typed observation emitted by a consistency checker.

    This is producer evidence only; severity and workflow action belong to
    GateSeverityPolicy. ``subject_id`` is optional and must refer to a real,
    stable logical subject when supplied.
    """

    patch: str
    chapter: int
    issue_code: str
    message: str
    fix_hint: str = ""
    subject_id: str | None = None
    evidence: dict[str, object] = field(default_factory=dict)
    checker_id: str | None = None
    checker_version: str = "1"
    input_ref: dict[str, object] = field(default_factory=dict)


class Patch(ABC):
    name: str = ""
    description: str = ""
    checker_version: str = "1"
    depends_on: tuple[str, ...] = ()

    @abstractmethod
    def check(self, ctx: CheckContext) -> list[PatchFinding]: ...

    @abstractmethod
    def apply(self, ctx: ApplyContext) -> None: ...
