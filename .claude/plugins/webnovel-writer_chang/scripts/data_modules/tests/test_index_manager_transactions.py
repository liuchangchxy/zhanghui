"""
M-H18 / M-E2：index.db 显式事务 + WAL 模式。

覆盖：
- WAL 与 busy_timeout 生效
- 正常路径自动提交（调用方不写 conn.commit() 也不丢数据）
- 异常路径自动回滚（多语句更新不会只落一半）
- 调用方自行 commit 仍兼容（不会 "no transaction is active"）
- row_factory 仍为 sqlite3.Row（回归保护：改造时容易漏掉）
"""
from __future__ import annotations

import sqlite3

import pytest

from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager


@pytest.fixture
def manager(tmp_path):
    return IndexManager(DataModulesConfig.from_project_root(tmp_path))


def test_journal_mode_is_wal(manager):
    """WAL：读不阻塞写、写不阻塞读（M-E2）。"""
    with manager._get_conn() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_busy_timeout_configured(manager):
    with manager._get_conn() as conn:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000


def test_row_factory_still_row(manager):
    """回归保护：显式事务改造不得丢掉 row_factory，否则所有 row['col'] 取值全崩。"""
    with manager._get_conn() as conn:
        row = conn.execute("SELECT 1 AS answer").fetchone()
        assert isinstance(row, sqlite3.Row)
        assert row["answer"] == 1


def test_writes_commit_without_explicit_commit(manager):
    """调用方不写 conn.commit() 也必须落盘 —— 修复前会被静默丢弃。"""
    with manager._get_conn() as conn:
        conn.execute(
            "INSERT INTO chapters (chapter, title, word_count) VALUES (?,?,?)",
            (1, "第一章", 2000),
        )

    with manager._get_conn() as conn:
        row = conn.execute("SELECT title FROM chapters WHERE chapter=1").fetchone()
    assert row is not None and row["title"] == "第一章"


def test_explicit_commit_by_caller_still_works(manager):
    """既有调用方自带 conn.commit()：退出时不得再 COMMIT 一次导致报错。"""
    with manager._get_conn() as conn:
        conn.execute(
            "INSERT INTO chapters (chapter, title, word_count) VALUES (?,?,?)",
            (7, "第七章", 2100),
        )
        conn.commit()

    with manager._get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM chapters WHERE chapter=7").fetchone()["c"] == 1


def test_exception_rolls_back_partial_multi_statement_update(manager):
    """中途抛异常 → 整批回滚，不留半套数据。"""
    with manager._get_conn() as conn:
        conn.execute(
            "INSERT INTO chapters (chapter, title, word_count) VALUES (?,?,?)",
            (2, "基线", 1000),
        )

    with pytest.raises(RuntimeError):
        with manager._get_conn() as conn:
            conn.execute("UPDATE chapters SET title='改后' WHERE chapter=2")
            conn.execute(
                "INSERT INTO chapters (chapter, title, word_count) VALUES (?,?,?)",
                (3, "第三章", 1500),
            )
            raise RuntimeError("模拟中途失败")

    with manager._get_conn() as conn:
        title = conn.execute("SELECT title FROM chapters WHERE chapter=2").fetchone()["title"]
        ch3 = conn.execute("SELECT COUNT(*) c FROM chapters WHERE chapter=3").fetchone()["c"]

    assert title == "基线", "第一条语句未回滚"
    assert ch3 == 0, "第二条语句未回滚"


def test_integrity_error_rolls_back_and_propagates(manager):
    """主键冲突等 sqlite 异常同样回滚并如实抛出。"""
    with manager._get_conn() as conn:
        conn.execute(
            "INSERT INTO chapters (chapter, title, word_count) VALUES (?,?,?)",
            (5, "原始", 1200),
        )

    with pytest.raises(sqlite3.IntegrityError):
        with manager._get_conn() as conn:
            conn.execute("UPDATE chapters SET title='脏写' WHERE chapter=5")
            conn.execute(
                "INSERT INTO chapters (chapter, title, word_count) VALUES (?,?,?)",
                (5, "重复主键", 1),
            )

    with manager._get_conn() as conn:
        assert conn.execute(
            "SELECT title FROM chapters WHERE chapter=5"
        ).fetchone()["title"] == "原始"
