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