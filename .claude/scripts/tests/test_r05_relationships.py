"""R5: 信任度变化——单章 ±delta 不超过 30。"""
from pathlib import Path

from changes_gate import check_r05_relationships


def test_r05_passes_with_small_delta(test_db: Path):
    changes = {
        "character_state_changes": [
            {"relationship_changes": {"C-002": {"trust_delta": 10}}}
        ]
    }
    assert check_r05_relationships(changes, test_db) == []


def test_r05_fails_with_huge_delta(test_db: Path):
    changes = {
        "character_state_changes": [
            {"relationship_changes": {"C-002": {"trust_delta": 50}}}  # 超 30
        ]
    }
    failures = check_r05_relationships(changes, test_db)
    assert len(failures) == 1
    assert failures[0].rule_id == "R5"
    assert "trust_delta=50" in failures[0].message


def test_r05_fails_with_negative_delta_exceeded(test_db: Path):
    changes = {
        "character_state_changes": [
            {"relationship_changes": {"C-002": {"trust_delta": -45}}}
        ]
    }
    failures = check_r05_relationships(changes, test_db)
    assert len(failures) == 1