"""R4: 伏笔推进——foreshadow_id 必须存在于账本。"""
import sqlite3
from pathlib import Path

import pytest

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


# === Bug 3 修复回归测试：db 缺 foreshadowing 表 ===
def test_r04_does_not_crash_when_foreshadowing_table_missing(tmp_path: Path):
    """Bug 3: db 文件存在但无 foreshadowing 表，不应导致 R4 崩溃。"""
    db_path = tmp_path / "no_fs.db"
    conn = sqlite3.connect(db_path)
    conn.close()
    changes = {"foreshadowing_actions": [{"foreshadow_id": "F1-001", "action": "setup"}]}
    failures = check_r04_foreshadowing(changes, db_path)
    assert failures == []  # db 不可用，跳过


def test_r04_does_not_crash_when_db_is_directory(tmp_path: Path):
    """Bug 12: --db 指向目录不应导致 R4 崩溃。"""
    dir_path = tmp_path / "is_dir"
    dir_path.mkdir()
    changes = {"foreshadowing_actions": [{"foreshadow_id": "F1-001", "action": "setup"}]}
    failures = check_r04_foreshadowing(changes, dir_path)
    assert failures == []


# === Bug 7 修复回归测试：空项目应继续校验（不再静默跳过）===
def test_r04_does_not_skip_when_foreshadowing_table_is_empty(tmp_path: Path):
    """Bug 7: 表存在但无任何行（新项目）应继续校验，不应整个跳过。"""
    db_path = tmp_path / "empty_fs.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE foreshadowing (
            id TEXT PRIMARY KEY,
            description TEXT,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()
    # 表存在但无任何行
    changes = {"foreshadowing_actions": [{"foreshadow_id": "F9-999", "action": "setup"}]}
    failures = check_r04_foreshadowing(changes, db_path)
    # 现在必须实际校验，发现未知 ID 报错
    assert len(failures) == 1
    assert failures[0].rule_id == "R4"
    assert "F9-999" in failures[0].message


def test_r04_does_not_crash_on_non_list_foreshadowing_actions(test_db: Path):
    """Bug 1: foreshadowing_actions 字段为非 list 类型不应导致 R4 崩溃。"""
    for bad in (True, {"foo": "bar"}, None):
        changes = {"foreshadowing_actions": bad}
        failures = check_r04_foreshadowing(changes, test_db)
        assert isinstance(failures, list)
