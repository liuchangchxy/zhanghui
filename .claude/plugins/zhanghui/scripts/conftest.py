from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import uuid
from pathlib import Path

import pytest


_ORIGINAL_SQLITE_CONNECT = sqlite3.connect
_ORIGINAL_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _tmp_root() -> Path:
    """Use system tempdir, not plugin scan root. Prevents Claude Code slash command breakage."""
    root = Path(tempfile.gettempdir()) / "webnovel-writer-chang-pytest"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_mkdtemp(suffix: str | None = None, prefix: str | None = None, dir: str | os.PathLike[str] | None = None) -> str:
    """Avoid WindowsApps Python creating inaccessible 0o700 temp dirs."""
    suffix = "" if suffix is None else suffix
    prefix = "tmp" if prefix is None else prefix
    root = Path(dir) if dir is not None else _tmp_root()
    root.mkdir(parents=True, exist_ok=True)

    for _ in range(100):
        path = root / f"{prefix}{uuid.uuid4().hex}{suffix}"
        try:
            path.mkdir()
        except FileExistsError:
            continue
        return str(path.resolve())

    raise FileExistsError(f"Unable to create unique temporary directory under {root}")


def _install_safe_tempfile() -> None:
    root = _tmp_root()
    for name in ("TMP", "TEMP", "TMPDIR"):
        os.environ[name] = str(root)
    os.environ["WEBNOVEL_TEST_RELAX_ATOMIC_REPLACE"] = "1"
    tempfile.tempdir = str(root)
    tempfile.mkdtemp = _safe_mkdtemp
    tempfile.TemporaryDirectory = _SafeTemporaryDirectory


class _SafeTemporaryDirectory(_ORIGINAL_TEMPORARY_DIRECTORY):
    def __init__(self, suffix=None, prefix=None, dir=None, ignore_cleanup_errors=True, *, delete=True):
        super().__init__(
            suffix=suffix,
            prefix=prefix,
            dir=dir,
            ignore_cleanup_errors=ignore_cleanup_errors,
            delete=delete,
        )


def _safe_sqlite_connect(*args, **kwargs):
    conn = _ORIGINAL_SQLITE_CONNECT(*args, **kwargs)
    try:
        conn.execute("PRAGMA journal_mode=MEMORY")
    except sqlite3.DatabaseError:
        pass
    return conn


def _install_safe_sqlite() -> None:
    sqlite3.connect = _safe_sqlite_connect


def pytest_configure(config: pytest.Config) -> None:
    _install_safe_tempfile()
    _install_safe_sqlite()


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in request.node.name)
    path = _tmp_root() / f"{safe_name}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        if os.environ.get("WEBNOVEL_KEEP_TEST_TMP") != "1":
            shutil.rmtree(path, ignore_errors=True)


_install_safe_tempfile()
_install_safe_sqlite()

# === merged from dev/.claude/scripts/tests/conftest.py ===

@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Create an in-memory SQLite db with the schema webnovel-writer uses."""
    db_path = tmp_path / "test_project.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            type TEXT,
            canonical_name TEXT,
            is_protagonist INTEGER DEFAULT 0,
            is_archived INTEGER DEFAULT 0,
            current_json TEXT
        );
        CREATE TABLE aliases (
            alias TEXT,
            entity_id TEXT,
            entity_type TEXT,
            PRIMARY KEY (alias, entity_id, entity_type)
        );
        CREATE TABLE foreshadowing (
            id TEXT PRIMARY KEY,
            description TEXT,
            status TEXT,
            setup_chapter INTEGER,
            payoff_chapter INTEGER
        );
        CREATE TABLE relationships (
            from_entity TEXT,
            to_entity TEXT,
            type TEXT,
            trust_value REAL,
            PRIMARY KEY (from_entity, to_entity, type)
        );
        CREATE TABLE timeline (
            chapter INTEGER PRIMARY KEY,
            time_anchor TEXT,
            elapsed_from_prev TEXT
        );

        INSERT INTO entities VALUES
            ('C-001', 'character', '陈默', 1, 0, NULL),
            ('C-002', 'character', '王玄之', 0, 0, NULL),
            ('L-001', 'location', '论剑台', 0, 0, NULL),
            ('F-001', 'faction', '青云宗', 0, 0, NULL),
            ('I-001', 'item', '照夜古镜', 0, 0, NULL);

        INSERT INTO aliases VALUES
            ('陈默', 'C-001', 'character'),
            ('玄之', 'C-002', 'character');

        INSERT INTO foreshadowing VALUES
            ('F1-001', '古镜窥见三日', 'setup', 1, NULL),
            ('F1-002', '王玄之身世', 'setup', 2, NULL);

        INSERT INTO relationships VALUES
            ('C-001', 'C-002', 'friend', 50.0);

        INSERT INTO timeline VALUES
            (1, '黄昏', '初始'),
            (2, '夏末', '三日');
    """)
    conn.commit()
    conn.close()
    return db_path



@pytest.fixture
def sample_chapter() -> Path:
    """Return path to a sample chapter file with valid CHANGES block."""
    return Path(__file__).parent / "fixtures" / "sample_chapter.md"



@pytest.fixture
def valid_changes_xml() -> str:
    """Return a valid CHANGES XML block matching the 8-field snake_case schema."""
    return """<chapter_changes>
{
  "character_state_changes": [
    {
      "character_id": "C-001",
      "new_state": "困惑与好奇",
      "key_event": "在祖父遗物中发现古镜",
      "importance": "important"
    }
  ],
  "new_plot_points": [
    {
      "keywords": ["古镜", "窥见"],
      "context": "陈默发现照夜古镜能显示三日后的景象",
      "involved_characters": ["C-001"],
      "importance": "important",
      "storyline": "main"
    }
  ],
  "foreshadowing_actions": [
    {"foreshadow_id": "F1-001", "action": "setup"}
  ],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": {
    "time_period": "夏末黄昏",
    "elapsed_time": "当日半天",
    "importance": "normal"
  },
  "item_transfers": [
    {
      "item_name": "照夜古镜",
      "from_holder": "祖父遗物箱",
      "to_holder": "C-001",
      "new_status": "active",
      "importance": "critical"
    }
  ],
  "unresolved_questions": []
}
</chapter_changes>"""
