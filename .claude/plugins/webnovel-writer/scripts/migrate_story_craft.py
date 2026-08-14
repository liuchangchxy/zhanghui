"""One-shot migration to add story_craft field to existing state.json.

Safe to run multiple times. Creates .bak before modifying.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from story_craft import EMPTY_STORY_CRAFT
from security_utils import atomic_write_json


def migrate_state_json(path: str) -> dict:
    """Add story_craft field if missing. Backup to .bak. Return new state."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"state.json not found: {path}")

    # Parse FIRST (before any destructive backup/write)
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"state.json is not valid JSON: {e}") from e

    if not isinstance(state, dict):
        raise ValueError(
            f"state.json top level must be a dict, got {type(state).__name__}"
        )

    # Only NOW write backup (from successfully-parsed state)
    backup = p.with_suffix(p.suffix + ".bak")
    backup.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Modify and write atomically
    if "story_craft" not in state or not isinstance(state.get("story_craft"), dict):
        state["story_craft"] = json.loads(json.dumps(EMPTY_STORY_CRAFT))

    atomic_write_json(str(p), state, use_lock=True, backup=False)
    return state


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: migrate_story_craft.py <path/to/state.json>")
        sys.exit(1)
    migrate_state_json(sys.argv[1])
    print(f"Migrated {sys.argv[1]}")