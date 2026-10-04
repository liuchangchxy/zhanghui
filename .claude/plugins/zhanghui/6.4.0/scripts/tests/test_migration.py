"""Tests for migrate_story_craft.py (Task 8).

Verifies one-shot migration:
- Adds story_craft field when missing
- Creates .bak backup before modifying
- Preserves existing story_craft content
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# 让 import 能找到 migrate_story_craft.py
_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from migrate_story_craft import migrate_state_json  # noqa: E402


def test_migrate_adds_story_craft_when_missing():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
        json.dump({"project_info": {"title": "X"}, "progress": {}}, f)
        path = f.name
    backup = path + ".bak"
    try:
        result = migrate_state_json(path)
        assert result["story_craft"] is not None
        assert result["project_info"]["title"] == "X"
        assert Path(backup).exists()
    finally:
        Path(path).unlink(missing_ok=True)
        Path(backup).unlink(missing_ok=True)


def test_migrate_preserves_existing_story_craft():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
        json.dump({
            "project_info": {},
            "story_craft": {"rhythm_curve": {"chapters_since_peak": 5}}
        }, f)
        path = f.name
    backup = path + ".bak"
    try:
        result = migrate_state_json(path)
        assert result["story_craft"]["rhythm_curve"]["chapters_since_peak"] == 5
    finally:
        Path(path).unlink(missing_ok=True)
        Path(backup).unlink(missing_ok=True)