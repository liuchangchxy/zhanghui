"""R7: 物品状态机——item status 转移合法。"""
from pathlib import Path

from changes_gate import check_r07_item_state


def test_r07_passes_with_normal_status(test_db: Path):
    changes = {"item_transfers": [{"new_status": "active"}]}
    assert check_r07_item_state(changes, test_db) == []


def test_r07_passes_when_no_previous_state(test_db: Path):
    """物品首次出现，没有 prev state 时不报错。"""
    changes = {"item_transfers": [{"item_id": "I-NEW", "new_status": "active"}]}
    assert check_r07_item_state(changes, test_db) == []


def test_r07_fails_on_destroyed_to_active(test_db: Path):
    """已 destroyed 的物品不能变回 active（除非经过 sealed 中转）。"""
    import sqlite3
    conn = sqlite3.connect(test_db)
    # 给 I-001 设一个前状态——直接更新 entities.current_json，与实现读取的字段对齐
    conn.execute(
        "UPDATE entities SET current_json = ? WHERE id = 'I-001'",
        ('{"status": "destroyed"}',),
    )
    conn.commit()
    conn.close()

    changes = {"item_transfers": [{"item_id": "I-001", "new_status": "active"}]}
    failures = check_r07_item_state(changes, test_db)
    assert len(failures) == 1
    assert failures[0].rule_id == "R7"
