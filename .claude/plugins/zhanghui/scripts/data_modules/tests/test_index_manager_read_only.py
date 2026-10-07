from __future__ import annotations

import hashlib
import sqlite3

from data_modules.config import DataModulesConfig
from data_modules.context_manager import ContextManager
from data_modules.index_manager import ChapterMeta, IndexManager


def _schema(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        return conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()


def test_read_only_index_manager_reads_partial_schema_without_initializing(tmp_path):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    with sqlite3.connect(config.index_db) as conn:
        conn.execute("CREATE TABLE chapters (chapter INTEGER PRIMARY KEY, title TEXT)")
        conn.execute("INSERT INTO chapters VALUES (1, 'existing')")

    before_bytes = config.index_db.read_bytes()
    before_schema = _schema(config.index_db)
    manager = IndexManager(config, read_only=True)

    assert manager.get_chapter(1)["title"] == "existing"
    assert manager.get_chapter(2) is None
    assert manager.get_recent_chapters() == [{"chapter": 1, "title": "existing"}]
    assert manager.get_recent_appearances() == []
    assert manager.get_invalid_ids("entity") == set()
    assert manager.get_recent_reading_power() == []
    assert manager.get_writing_checklist_score_trend()["count"] == 0
    assert manager.get_stats()["chapters"] == 1
    assert manager.get_stats()["appearances"] == 0
    assert manager.get_stats()["total_debt"] == 0
    assert manager.log_tool_call("TEST ONLY", True) is None

    assert hashlib.sha256(config.index_db.read_bytes()).digest() == hashlib.sha256(before_bytes).digest()
    assert _schema(config.index_db) == before_schema
    assert not config.index_db.with_name(config.index_db.name + "-wal").exists()
    assert not config.index_db.with_name(config.index_db.name + "-shm").exists()


def test_read_only_index_manager_with_missing_database_does_not_create_it(tmp_path):
    config = DataModulesConfig.from_project_root(tmp_path)
    manager = IndexManager(config, read_only=True)

    assert not config.index_db.exists()
    assert manager.get_chapter(1) is None
    assert manager.get_recent_chapters() == []
    assert manager.get_recent_appearances() == []
    assert manager.get_invalid_ids("entity") == set()
    assert manager.get_stats()["chapters"] == 0
    assert not config.index_db.exists()


def test_context_init_build_and_read_helpers_leave_index_unchanged(tmp_path):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    config.state_file.write_text('{"project": {"genre": "玄幻"}}', encoding="utf-8")
    with sqlite3.connect(config.index_db) as conn:
        conn.execute("CREATE TABLE chapters (chapter INTEGER PRIMARY KEY, title TEXT)")
        conn.execute("INSERT INTO chapters VALUES (1, 'existing')")
    before = hashlib.sha256(config.index_db.read_bytes()).hexdigest()
    before_schema = _schema(config.index_db)

    manager = ContextManager(config)
    manager.build_context(2)
    manager.index_manager.get_recent_chapters()
    manager.index_manager.get_recent_reading_power()
    manager.index_manager.get_invalid_ids("entity")

    assert hashlib.sha256(config.index_db.read_bytes()).hexdigest() == before
    assert _schema(config.index_db) == before_schema
    assert not config.index_db.with_name(config.index_db.name + "-wal").exists()
    assert not config.index_db.with_name(config.index_db.name + "-shm").exists()


def test_writable_index_manager_still_initializes_and_updates(tmp_path):
    config = DataModulesConfig.from_project_root(tmp_path)
    manager = IndexManager(config)
    manager.add_chapter(ChapterMeta(
        chapter=1, title="TEST ONLY", location="", word_count=0, characters=[], summary=""))
    assert manager.get_chapter(1)["title"] == "TEST ONLY"
