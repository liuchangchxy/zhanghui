"""R2: 枚举值合法——action/importance/status 取值在白名单内。"""
from changes_gate import check_r02_enums


def test_r02_passes_with_valid_importance():
    changes = {
        "character_state_changes": [
            {"importance": "important"}
        ]
    }
    assert check_r02_enums(changes) == []


def test_r02_fails_on_invalid_importance():
    changes = {
        "character_state_changes": [
            {"importance": "very-important"}  # 非法
        ]
    }
    failures = check_r02_enums(changes)
    assert len(failures) == 1
    assert failures[0].rule_id == "R2"
    assert "importance" in failures[0].message


def test_r02_fails_on_invalid_action():
    changes = {
        "foreshadowing_actions": [
            {"action": "delete"}  # 只能是 setup 或 payoff
        ]
    }
    failures = check_r02_enums(changes)
    assert len(failures) == 1
    assert failures[0].rule_id == "R2"
    assert "foreshadowing_actions" in failures[0].message


def test_r02_fails_on_invalid_item_status():
    changes = {
        "item_transfers": [
            {"new_status": "broken"}  # 只能 active/lost/destroyed/sealed
        ]
    }
    failures = check_r02_enums(changes)
    assert len(failures) == 1
    assert failures[0].rule_id == "R2"


def test_r02_fails_on_invalid_time_progression_importance():
    """Issue 1: time_progression.importance must validate against ENUM_TIME_IMPORTANCE."""
    changes = {
        "time_progression": {"importance": "urgent"}  # 非法
    }
    failures = check_r02_enums(changes)
    assert len(failures) == 1
    assert failures[0].rule_id == "R2"
    assert "time_progression.importance" in failures[0].message


def test_r02_fails_on_none_importance_in_new_plot_points():
    """Issue 3: importance is REQUIRED in new_plot_points (consistent with character_state_changes)."""
    changes = {
        "new_plot_points": [
            {"importance": None}  # None 应触发失败
        ]
    }
    failures = check_r02_enums(changes)
    assert len(failures) == 1
    assert failures[0].rule_id == "R2"
    assert "new_plot_points" in failures[0].message


def test_r02_includes_valid_set_in_message_for_new_plot_points():
    """Issue 2: failure message for storyline must include sorted valid set."""
    changes = {
        "new_plot_points": [
            {"storyline": "foo", "importance": "normal"}  # 非法 storyline；importance 提供有效值避免噪声
        ]
    }
    failures = check_r02_enums(changes)
    assert len(failures) == 1
    assert failures[0].rule_id == "R2"
    # sorted(ENUM_STORYLINE) == ['character_arc', 'main', 'sub']
    assert "['character_arc', 'main', 'sub']" in failures[0].message


# === Bug 1 修复回归测试：array fields 接受非 list 类型时不再崩溃 ===
import pytest


@pytest.mark.parametrize("field_name,array_value", [
    ("character_state_changes", True),
    ("character_state_changes", False),
    ("character_state_changes", {"foo": "bar"}),
    ("new_plot_points", True),
    ("foreshadowing_actions", True),
    ("location_state_changes", False),
    ("faction_state_changes", {"foo": "bar"}),
    ("item_transfers", True),
])
def test_r02_does_not_crash_on_non_list_array_field(field_name, array_value):
    """Bug 1: 非 list 类型的 array 字段不应导致 R2 崩溃。"""
    changes = {field_name: array_value}
    failures = check_r02_enums(changes)
    # 必须返回 list（不抛 TypeError）
    assert isinstance(failures, list)
    # 应该记录该字段类型错误的 R2 失败
    assert any(f.rule_id == "R2" for f in failures)


def test_r02_does_not_crash_when_array_element_is_non_dict():
    """Bug 1: array 内是非 dict 元素（如 bool/int/str）不应导致崩溃。"""
    changes = {"character_state_changes": [True, "hello", 42, None]}
    failures = check_r02_enums(changes)
    # 至少 4 条 R2 失败（每个非 dict 元素报一次）
    assert isinstance(failures, list)
    assert len(failures) >= 4


def test_r02_skips_missing_new_status():
    """Bug 8: 缺失或 null new_status 不应导致 R2 false positive。"""
    # 缺失字段
    changes = {"item_transfers": [{"item_id": "I-001"}]}
    failures = check_r02_enums(changes)
    assert failures == []
    # 显式 None
    changes = {"item_transfers": [{"item_id": "I-001", "new_status": None}]}
    failures = check_r02_enums(changes)
    assert failures == []


def test_r02_skips_missing_action():
    """Bug 9: 缺失或 null action 不应导致 R2 false positive。"""
    changes = {"foreshadowing_actions": [{"foreshadow_id": "F1-001"}]}
    failures = check_r02_enums(changes)
    assert failures == []
    changes = {"foreshadowing_actions": [{"foreshadow_id": "F1-001", "action": None}]}
    failures = check_r02_enums(changes)
    assert failures == []


def test_r02_accepts_null_time_progression():
    """time_progression 字段为 None 时不应触发 R2 失败。"""
    changes = {"time_progression": None}
    failures = check_r02_enums(changes)
    assert failures == []


def test_r02_accepts_bool_time_progression():
    """time_progression 字段为 bool 时不应触发崩溃。"""
    changes = {"time_progression": False}
    failures = check_r02_enums(changes)
    assert isinstance(failures, list)