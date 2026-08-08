"""R4: 伏笔推进——foreshadow_id 必须存在于账本。"""
from pathlib import Path

from changes_gate import check_r04_foreshadowing


def test_r04_passes_with_known_foreshadow(test_db: Path):
    changes = {"foreshadowing_actions": [{"foreshadow_id": "F1-001", "action": "setup"}]}
    assert check_r04_foreshadowing(changes, test_db) == []


def test_r04_fails_on_unknown_foreshadow(test_db: Path):
    changes = {"foreshadowing_actions": [{"foreshadow_id": "F9-999", "action": "setup"}]}
    failures = check_r04_foreshadowing(changes, test_db)
    assert len(failures) == 1
    assert failures[0].rule_id == "R4"


def test_r04_fails_on_payoff_before_setup(test_db: Path):
    """R4 高级约束：如果 foreshadowing 在账本中状态不是 setup，标记 payoff 应报错。"""
    # 先把 F1-002 标记为 payoff（已回收）
    import sqlite3
    conn = sqlite3.connect(test_db)
    conn.execute("UPDATE foreshadowing SET status='paid' WHERE id='F1-002'")
    conn.commit()
    conn.close()

    changes = {"foreshadowing_actions": [{"foreshadow_id": "F1-002", "action": "payoff"}]}
    failures = check_r04_foreshadowing(changes, test_db)
    assert len(failures) >= 1  # 不允许重复 payoff