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