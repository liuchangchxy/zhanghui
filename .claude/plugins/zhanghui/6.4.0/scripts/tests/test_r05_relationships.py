"""R5: 信任度变化——单章 ±delta 不超过 30。"""
from pathlib import Path

import pytest

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


# === Bug 2 修复回归测试：trust_delta 类型守卫 ===
@pytest.mark.parametrize("bad_delta", [
    "30",
    "$30",
    "30.0",
    [10, 20],
    {"value": 30},
])
def test_r05_does_not_crash_on_non_numeric_delta(test_db: Path, bad_delta):
    """Bug 2: trust_delta 类型错误不应让 R5 崩溃，而应记录 R5 failure。"""
    changes = {
        "character_state_changes": [
            {"relationship_changes": {"C-002": {"trust_delta": bad_delta}}}
        ]
    }
    failures = check_r05_relationships(changes, test_db)
    assert isinstance(failures, list)
    # 必须记录 R5 失败
    assert any(f.rule_id == "R5" for f in failures)
    # 失败消息包含类型信息
    assert any(type(bad_delta).__name__ in f.message or "数字" in f.message for f in failures)


def test_r05_rejects_boolean_delta(test_db: Path):
    """Bug 2/Major 7: trust_delta 为 True/False 时不应静默通过（abs(True)=1）。"""
    for bad in (True, False):
        changes = {
            "character_state_changes": [
                {"relationship_changes": {"C-002": {"trust_delta": bad}}}
            ]
        }
        failures = check_r05_relationships(changes, test_db)
        assert any(f.rule_id == "R5" for f in failures), f"bool {bad} 应被 R5 拦截"


def test_r05_passes_with_float(test_db: Path):
    changes = {
        "character_state_changes": [
            {"relationship_changes": {"C-002": {"trust_delta": 15.5}}}
        ]
    }
    assert check_r05_relationships(changes, test_db) == []


def test_r05_does_not_crash_when_character_state_changes_is_bool(test_db: Path):
    """Bug 1 (R5 侧): character_state_changes 字段为 bool 时不应让 R5 崩溃。"""
    changes = {"character_state_changes": True}
    failures = check_r05_relationships(changes, test_db)
    assert isinstance(failures, list)


def test_r05_handles_null_trust_delta(test_db: Path):
    changes = {
        "character_state_changes": [
            {"relationship_changes": {"C-002": {"trust_delta": None}}}
        ]
    }
    assert check_r05_relationships(changes, test_db) == []
