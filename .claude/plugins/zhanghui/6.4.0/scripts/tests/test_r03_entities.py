"""R3: 实体引用合法——character_id/location_id/faction_id 必须在账本。"""
import sqlite3
from pathlib import Path

import pytest

from changes_gate import check_r03_entities, Failure


def test_r03_passes_with_known_character(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "C-001"}],
        "new_plot_points": [{"involved_characters": ["C-002"]}],
    }
    failures = check_r03_entities(changes, test_db)
    assert failures == []


def test_r03_fails_on_unknown_character(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "C-999"}],  # 不存在
    }
    failures = check_r03_entities(changes, test_db)
    assert len(failures) == 1
    assert failures[0].rule_id == "R3"
    assert "C-999" in failures[0].message


def test_r03_passes_with_known_alias(test_db: Path):
    """允许用别名而非 ID。"""
    changes = {
        "character_state_changes": [{"character_id": "陈默"}],  # alias
    }
    failures = check_r03_entities(changes, test_db)
    assert failures == []


def test_r03_fails_on_unknown_alias(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "张三"}],  # 不在 alias
    }
    failures = check_r03_entities(changes, test_db)
    assert len(failures) == 1


# === Bug 3 修复回归测试：db 文件存在但表缺失时不应崩溃 ===
def test_r03_does_not_crash_when_entities_table_missing(tmp_path: Path):
    """Bug 3: db 文件存在但无 entities 表，不应导致 R3 崩溃。"""
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(db_path)
    conn.close()  # 空 db，无 entities / aliases 表
    changes = {"character_state_changes": [{"character_id": "C-001"}]}
    failures = check_r03_entities(changes, db_path)
    # 应该返回空 list（不抛 sqlite3.OperationalError），因为 db 不可用就跳过
    assert failures == []


def test_r03_does_not_crash_when_only_entities_table_exists(tmp_path: Path):
    """Bug 3: db 只有 entities 表但没有 aliases 表，不应崩溃。"""
    db_path = tmp_path / "partial.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            is_archived INTEGER DEFAULT 0
        )
    """)
    conn.execute("INSERT INTO entities VALUES ('C-001', 0)")
    conn.commit()
    conn.close()
    changes = {"character_state_changes": [{"character_id": "C-001"}]}
    failures = check_r03_entities(changes, db_path)
    # aliases 不存在 → tables_ok=False → 跳过
    assert failures == []


def test_r03_does_not_crash_when_db_is_directory(tmp_path: Path):
    """Bug 12: --db 指向目录不应导致 R3 崩溃。"""
    dir_path = tmp_path / "is_dir"
    dir_path.mkdir()
    changes = {"character_state_changes": [{"character_id": "C-001"}]}
    failures = check_r03_entities(changes, dir_path)
    assert failures == []


# === Bug 7 修复回归测试：空项目应继续校验（不再静默跳过）===
def test_r03_does_not_skip_when_project_is_empty(tmp_path: Path):
    """Bug 7: 表存在但无任何行（新项目）应继续校验，不应整个跳过。"""
    db_path = tmp_path / "empty_project.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            is_archived INTEGER DEFAULT 0
        );
        CREATE TABLE aliases (
            alias TEXT,
            entity_id TEXT,
            entity_type TEXT,
            PRIMARY KEY (alias, entity_id, entity_type)
        );
    """)
    conn.commit()
    conn.close()
    # 表存在但 entities/aliases 都没有行 — 旧实现会跳过整个 R3
    changes = {
        "character_state_changes": [{"character_id": "C-999"}],  # 不在账本，应报 R3
    }
    failures = check_r03_entities(changes, db_path)
    # 现在必须实际校验，发现未知 ID 报错
    assert len(failures) == 1
    assert failures[0].rule_id == "R3"
    assert "C-999" in failures[0].message


# === Bug 10 修复回归测试：R3 也检查 item_transfers 中的 ID ===
def test_r03_fails_on_unknown_item_id(test_db: Path):
    """Bug 10: item_transfers[].item_id 必须在账本。"""
    changes = {
        "item_transfers": [{"item_id": "I-999", "new_status": "active"}]
    }
    failures = check_r03_entities(changes, test_db)
    assert len(failures) == 1
    assert failures[0].rule_id == "R3"
    assert "I-999" in failures[0].message


def test_r03_passes_with_known_item_id(test_db: Path):
    changes = {
        "item_transfers": [{"item_id": "I-001", "new_status": "active"}]
    }
    failures = check_r03_entities(changes, test_db)
    assert failures == []


def test_r03_does_not_crash_on_bool_array(test_db: Path):
    """Bug 1 (R3 侧): 字段为 bool 时不应让 R3 崩溃。"""
    changes = {"item_transfers": True}
    failures = check_r03_entities(changes, test_db)
    assert isinstance(failures, list)


# === Bug A 回归（第一性原理 A2.3 / A7.1）：db 不可用时 R3 不再静默跳过 ===
# 单元层 R3 仍返回空（避免破坏现有测试），但 main() 必须发出 R0 loud fail。
# 下面 3 个测试通过 CLI 子进程验证 main() 的行为。
import json
import subprocess
import sys
import tempfile
import uuid


def _run_gate(cli_chapter: str, db_path: Path) -> dict:
    chapter_file = Path(tempfile.gettempdir()) / f"_r3bug_{uuid.uuid4().hex[:8]}.md"
    try:
        chapter_file.write_text(cli_chapter, encoding="utf-8")
        cmd = [sys.executable, str(Path(__file__).resolve().parent.parent / "changes_gate.py"),
               "--chapter-file", str(chapter_file),
               "--db", str(db_path), "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode in (0, 1), f"rc={result.returncode}; stderr={result.stderr!r}"
        if not result.stdout.strip():
            return {}
        return json.loads(result.stdout)
    finally:
        chapter_file.unlink(missing_ok=True)


_BUG_A_CHAPTER = """# 第5章

<chapter_changes>
{"character_state_changes":[{"character_id":"NONEXISTENT","importance":"important"}],"new_plot_points":[],"foreshadowing_actions":[],"location_state_changes":[],"faction_state_changes":[],"time_progression":null,"item_transfers":[],"unresolved_questions":[]}
</chapter_changes>
"""


def test_r03_fails_when_db_is_dev_null():
    """A2.3 / A7.1: --db=/dev/null 过去 R3 静默通过 → 现在必须 R0 loud fail。"""
    if not Path("/dev/null").exists():
        import pytest
        pytest.skip("no /dev/null on this platform")
    data = _run_gate(_BUG_A_CHAPTER, Path("/dev/null"))
    assert data.get("passed") is False
    assert any("R0" in f["rule_id"] for f in data.get("failures", []))
    # 且 R3 **不应该**继续说"未在账本" —— 因为 db 根本无效
    assert not any("R3" in f["rule_id"] for f in data.get("failures", [])), data


def test_r03_fails_when_db_is_etc_passwd():
    """A2.2 / A7.2: --db=/etc/passwd 过去 DatabaseError traceback → 现在 R0 loud fail。"""
    if not Path("/etc/passwd").is_file():
        import pytest
        pytest.skip("no /etc/passwd on this platform")
    data = _run_gate(_BUG_A_CHAPTER, Path("/etc/passwd"))
    assert data.get("passed") is False
    assert any("R0" in f["rule_id"] for f in data.get("failures", []))
    assert not any("R3" in f["rule_id"] for f in data.get("failures", [])), data


def test_r03_fails_when_db_has_no_entities_table(tmp_path: Path):
    """A2.3 矩阵: db 缺 entities 表 → R0 loud fail（不再 R3 静默通过）。"""
    import sqlite3
    db = tmp_path / "no_entities.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE some_other_table (id TEXT)")
    conn.commit(); conn.close()
    data = _run_gate(_BUG_A_CHAPTER, db)
    assert data.get("passed") is False
    assert any("R0" in f["rule_id"] for f in data.get("failures", []))
    assert not any("R3" in f["rule_id"] for f in data.get("failures", [])), data


def test_r03_fails_when_db_is_empty_file(tmp_path: Path):
    """A2.3 矩阵: 0 字节 db → R0 loud fail。"""
    db = tmp_path / "zero.db"
    db.write_bytes(b"")
    data = _run_gate(_BUG_A_CHAPTER, db)
    assert data.get("passed") is False
    assert any("R0" in f["rule_id"] for f in data.get("failures", []))
