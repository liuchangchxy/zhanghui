"""Bug A/B 回归测试：_check_db_validity 的三态语义。

对抗式审查（第一性原理）A2.3 / A7.1 / A2.2：
    任何让 db 不可用的输入（/dev/null、纯文本、空文件、缺表、破损链接、目录）
    过去都会让 R3-R8 **静默跳过**，门禁输出 passed=true, failures=[]。
    这既是透明性（A6）违反，也是安全漏洞（A7）：攻击者可构造特殊文件让门禁永远通过。

三态约定：
    (True,  None) → db 可用，**或** db 文件不存在（未初始化项目，调用方决定）
    (False, None) → 未提供 db 路径（调用方决定）
    (False, msg)  → db 存在但无效 → 调用方**必须**报错，不得静默跳过
"""
import sqlite3
from pathlib import Path

import pytest

from changes_gate import (
    EXPECTED_TABLES,
    SQLITE_HEADER,
    _check_db_validity,
)


def _make_db(path: Path, tables: list[str]) -> Path:
    """建一个含指定表的 sqlite 文件。"""
    conn = sqlite3.connect(path)
    for name in tables:
        conn.execute(f"CREATE TABLE {name} (id TEXT PRIMARY KEY, payload TEXT)")
    conn.commit()
    conn.close()
    return path


# === 状态 1：文件不存在 → 合法（未初始化项目），由调用方决定 ===
def test_check_db_validity_returns_invalid_for_nonexistent_file(tmp_path: Path):
    """db 文件不存在是合法状态（项目未初始化）→ 返回 ok 且无错误信息。"""
    is_valid, err = _check_db_validity(tmp_path / "never_created.db")
    assert is_valid is True
    assert err is None


def test_check_db_validity_returns_no_error_for_empty_path():
    """未提供 --db → (False, None)，由调用方决定，不报错。"""
    is_valid, err = _check_db_validity("")
    assert is_valid is False
    assert err is None


# === 状态 2：存在但无效 → 必须报错 ===
def test_check_db_validity_returns_invalid_for_directory(tmp_path: Path):
    """A5.5: --db 指向目录曾经导致 silent pass。"""
    d = tmp_path / "a_dir"
    d.mkdir()
    is_valid, err = _check_db_validity(d)
    assert is_valid is False
    assert err and "不是常规文件" in err


def test_check_db_validity_returns_invalid_for_empty_file(tmp_path: Path):
    """空文件（含 `sqlite3.connect(); close()` 产生的 0 字节 db）。"""
    p = tmp_path / "empty.db"
    p.write_bytes(b"")
    is_valid, err = _check_db_validity(p)
    assert is_valid is False
    assert err and "为空" in err


def test_check_db_validity_returns_invalid_for_zero_byte_sqlite_connect(tmp_path: Path):
    """`sqlite3.connect(p); close()` 不写任何东西 → 0 字节文件，同样必须报错。"""
    p = tmp_path / "touched.db"
    conn = sqlite3.connect(p)
    conn.close()
    assert p.stat().st_size == 0
    is_valid, err = _check_db_validity(p)
    assert is_valid is False
    assert err is not None


def test_check_db_validity_returns_invalid_for_non_sqlite_file(tmp_path: Path):
    """A2.2 / A7.2: /etc/passwd 类纯文本文件曾经导致 sqlite3.DatabaseError traceback。"""
    p = tmp_path / "passwd_like.db"
    p.write_text("root:x:0:0:root:/root:/bin/bash\n", encoding="utf-8")
    is_valid, err = _check_db_validity(p)
    assert is_valid is False
    assert err and "不是 SQLite 格式" in err


def test_check_db_validity_returns_invalid_for_real_etc_passwd():
    """直接打真实的 /etc/passwd（审查报告里的原始攻击输入）。"""
    if not Path("/etc/passwd").is_file():
        pytest.skip("no /etc/passwd on this platform")
    is_valid, err = _check_db_validity("/etc/passwd")
    assert is_valid is False
    assert err is not None


def test_check_db_validity_returns_invalid_for_corrupt_sqlite_file(tmp_path: Path):
    """有正确 header 但内容损坏 → 读 schema 时抛 DatabaseError，必须被捕获并报错。"""
    p = tmp_path / "corrupt.db"
    p.write_bytes(SQLITE_HEADER + b"\xde\xad\xbe\xef" * 512)
    is_valid, err = _check_db_validity(p)
    assert is_valid is False
    assert err is not None


def test_check_db_validity_returns_invalid_for_missing_tables(tmp_path: Path):
    """有 sqlite schema 但不是 webnovel-writer 的账本。"""
    p = _make_db(tmp_path / "wrong_schema.db", ["some_other_table"])
    is_valid, err = _check_db_validity(p)
    assert is_valid is False
    assert err and "缺少表" in err
    # 报错必须点名具体缺了哪些表（A6 透明性）
    for missing in EXPECTED_TABLES:
        assert missing in err


def test_check_db_validity_returns_invalid_when_only_entities_table(tmp_path: Path):
    """只有 entities 没有 aliases → 仍然不是完整账本。"""
    p = _make_db(tmp_path / "partial.db", ["entities"])
    is_valid, err = _check_db_validity(p)
    assert is_valid is False
    assert err and "aliases" in err


def test_check_db_validity_returns_invalid_for_broken_symlink(tmp_path: Path):
    """A7.1: 破损符号链接曾经被当成"文件不存在"而静默跳过。"""
    link = tmp_path / "broken.db"
    link.symlink_to(tmp_path / "does_not_exist_target.db")
    assert not link.exists() and link.is_symlink()
    is_valid, err = _check_db_validity(link)
    assert is_valid is False
    assert err and "符号链接" in err


def test_check_db_validity_returns_invalid_for_dev_null():
    """A7.1: /dev/null 是字符设备，不是常规文件。"""
    if not Path("/dev/null").exists():
        pytest.skip("no /dev/null on this platform")
    is_valid, err = _check_db_validity("/dev/null")
    assert is_valid is False
    assert err is not None


# === 状态 3：有效（含全新空账本）===
def test_check_db_validity_returns_valid_for_good_db(test_db: Path):
    """完整 fixture 账本 → 有效。"""
    is_valid, err = _check_db_validity(test_db)
    assert is_valid is True
    assert err is None


def test_check_db_validity_returns_valid_for_empty_but_well_formed_db(tmp_path: Path):
    """表齐全但一行数据都没有（全新项目）→ 合法，必须继续校验而不是跳过。"""
    p = _make_db(tmp_path / "fresh.db", sorted(EXPECTED_TABLES))
    is_valid, err = _check_db_validity(p)
    assert is_valid is True
    assert err is None


def test_check_db_validity_accepts_real_index_db_schema(tmp_path: Path):
    """真实 webnovel-writer index.db 没有 foreshadowing / timeline 表，必须仍判为有效。

    见 plugins/webnovel-writer/scripts/data_modules/index_manager.py —— 伏笔存在
    state.json 而非 sqlite。若把这两张表列入 EXPECTED_TABLES，所有真实项目都会被
    R0 拒绝。
    """
    p = _make_db(
        tmp_path / "index.db",
        ["chapters", "scenes", "entities", "aliases", "relationships", "state_changes"],
    )
    is_valid, err = _check_db_validity(p)
    assert is_valid is True, err


def test_expected_tables_excludes_tables_absent_from_real_schema():
    """守卫测试：EXPECTED_TABLES 不得包含真实 index.db 里不存在的表。"""
    assert "foreshadowing" not in EXPECTED_TABLES
    assert "timeline" not in EXPECTED_TABLES
    assert {"entities", "aliases"} <= set(EXPECTED_TABLES)


# === Bug B：DatabaseError（OperationalError 的父类）必须被捕获 ===
def test_loaders_do_not_raise_on_non_sqlite_file(tmp_path: Path):
    """所有 _load_* 在非 sqlite 文件上都不能抛异常。"""
    from changes_gate import (
        _load_entity_lookup,
        _load_foreshadowing_state,
        _load_item_state,
        _load_timeline,
    )
    p = tmp_path / "not_a_db.db"
    p.write_text("root:x:0:0::/root:/bin/sh\n" * 50, encoding="utf-8")

    assert _load_entity_lookup(p) == (set(), set(), False)
    assert _load_foreshadowing_state(p) == ({}, False)
    assert _load_item_state(p) == {}
    assert _load_timeline(p) == {}


def test_loaders_do_not_raise_on_corrupt_sqlite(tmp_path: Path):
    """损坏 sqlite（正确 header + 垃圾内容）同样不能抛异常。"""
    from changes_gate import (
        _load_entity_lookup,
        _load_foreshadowing_state,
        _load_item_state,
        _load_timeline,
    )
    p = tmp_path / "corrupt.db"
    p.write_bytes(SQLITE_HEADER + b"\x00\xff" * 1024)

    assert _load_entity_lookup(p) == (set(), set(), False)
    assert _load_foreshadowing_state(p) == ({}, False)
    assert _load_item_state(p) == {}
    assert _load_timeline(p) == {}
