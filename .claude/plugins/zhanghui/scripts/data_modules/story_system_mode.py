"""Story System mode detection and the canonical projection write scope."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path


CANON_WRITE_ERROR = (
    "Story System canonical mode: chapter facts must originate from durable "
    "CHAPTER_COMMIT projections."
)
_CANONICAL_PROJECTION_ROOT: ContextVar[str | None] = ContextVar(
    "zhanghui_canonical_projection_root", default=None
)


def is_story_system_project(project_root: str | Path) -> bool:
    root = Path(project_root) / ".story-system"
    return (
        (root / "MASTER_SETTING.json").is_file()
        or (root / "chapters").is_dir()
        or (root / "volumes").is_dir()
        or any((root / "commits").glob("chapter_*.commit.json"))
    )


@contextmanager
def canonical_projection_write_scope(project_root: str | Path):
    """Mark IndexManager writes made inside the canonical projection writer."""
    root = str(Path(project_root).resolve())
    token = _CANONICAL_PROJECTION_ROOT.set(root)
    try:
        yield
    finally:
        _CANONICAL_PROJECTION_ROOT.reset(token)


def require_legacy_canon_write_allowed(project_root: str | Path) -> None:
    """Reject ordinary legacy fact writes for Story System projects."""
    if not is_story_system_project(project_root):
        return
    if _CANONICAL_PROJECTION_ROOT.get() == str(Path(project_root).resolve()):
        return
    raise RuntimeError(CANON_WRITE_ERROR)
