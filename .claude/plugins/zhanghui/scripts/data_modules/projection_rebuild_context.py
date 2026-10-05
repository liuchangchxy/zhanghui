"""Coordinator-scoped permission for ordered projection recovery."""
from __future__ import annotations

from contextvars import ContextVar
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


_active_root: ContextVar[str | None] = ContextVar("projection_rebuild_root", default=None)


@contextmanager
def _controlled_rebuild(project_root: str | Path) -> Iterator[None]:
    token = _active_root.set(str(Path(project_root).expanduser().resolve()))
    try:
        yield
    finally:
        _active_root.reset(token)


def is_controlled_rebuild(project_root: str | Path) -> bool:
    return _active_root.get() == str(Path(project_root).expanduser().resolve())
