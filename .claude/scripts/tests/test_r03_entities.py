"""R3: 实体引用合法——character_id/location_id/faction_id 必须在账本。"""
import sqlite3
from pathlib import Path

import pytest

from changes_gate import check_r03_entities, Failure


def test_r03_passes_with_known_character(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "C-001"}],
        "new_plot_points": [{"involved_characters": ["C-002"]}],
    }
    failures = check_r03_entities(changes, test_db)
    assert failures == []


def test_r03_fails_on_unknown_character(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "C-999"}],  # 不存在
    }
    failures = check_r03_entities(changes, test_db)
    assert len(failures) == 1
    assert failures[0].rule_id == "R3"
    assert "C-999" in failures[0].message


def test_r03_passes_with_known_alias(test_db: Path):
    """允许用别名而非 ID。"""
    changes = {
        "character_state_changes": [{"character_id": "陈默"}],  # alias
    }
    failures = check_r03_entities(changes, test_db)
    assert failures == []


def test_r03_fails_on_unknown_alias(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "张三"}],  # 不在 alias
    }
    failures = check_r03_entities(changes, test_db)
    assert len(failures) == 1
