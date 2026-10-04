"""Small project-mode check based on initialized Story System contracts."""
from pathlib import Path


def is_story_system_project(project_root: str | Path) -> bool:
    root = Path(project_root) / ".story-system"
    return (
        (root / "MASTER_SETTING.json").is_file()
        or (root / "chapters").is_dir()
        or (root / "volumes").is_dir()
        or any((root / "commits").glob("chapter_*.commit.json"))
    )
