"""Schema 迁移框架（MED-55）的 pytest 覆盖。

覆盖目标：
- detect_and_migrate：v5.0 / v5.4 / CURRENT / unknown 四种路径
- migrate_v5_to_v6：foreshadowing dict → list 转换、state_changes 补全
- migrate_v54_to_v6：state_changes 补全
- 端到端：StateUpdater.load() 自动调用迁移
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# 让 import 能找到 update_state.py
_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import update_state as update_state  # noqa: E402
from update_state import (  # noqa: E402
    CURRENT_SCHEMA,
    MigrationError,
    detect_and_migrate,
    migrate_v5_to_v6,
    migrate_v54_to_v6,
)


# ---------------------------------------------------------------------------
# detect_and_migrate
# ---------------------------------------------------------------------------

def test_detect_already_current_returns_unchanged():
    """当前 schema → 直接返回，不修改。"""
    state = {"schema_version": CURRENT_SCHEMA, "foo": "bar"}
    out = detect_and_migrate(state)
    assert out is state or out == state
    assert out["schema_version"] == CURRENT_SCHEMA
    assert out["foo"] == "bar"


def test_detect_missing_version_defaults_to_v5_and_migrates():
    """缺 schema_version 字段 → 按 v5.0 兼容处理，自动迁移。"""
    state = {"foo": "bar"}
    out = detect_and_migrate(state)
    assert out["schema_version"] == CURRENT_SCHEMA


def test_detect_v5_triggers_migration():
    """v5.0 → 触发 migrate_v5_to_v6。"""
    state = {
        "schema_version": "v5.0",
        "plot_threads": {
            "foreshadowing": {
                "三年之约": {"status": "未回收", "planted_chapter": 1},
            }
        },
    }
    out = detect_and_migrate(state)
    assert out["schema_version"] == CURRENT_SCHEMA
    # dict → list 转换生效
    assert isinstance(out["plot_threads"]["foreshadowing"], list)
    assert len(out["plot_threads"]["foreshadowing"]) == 1
    assert out["plot_threads"]["foreshadowing"][0]["content"] == "三年之约"
    # state_changes 补全
    assert out["state_changes"] == []


def test_detect_v54_triggers_migration():
    """v5.4 → 触发 migrate_v54_to_v6。"""
    state = {
        "schema_version": "v5.4",
        "plot_threads": {"foreshadowing": []},
    }
    out = detect_and_migrate(state)
    assert out["schema_version"] == CURRENT_SCHEMA
    assert out["state_changes"] == []


def test_detect_unknown_version_raises():
    """未注册版本 → MigrationError（fail-fast）。"""
    state = {"schema_version": "v99.0", "foo": "bar"}
    with pytest.raises(MigrationError) as excinfo:
        detect_and_migrate(state)
    assert "v99.0" in str(excinfo.value)


def test_detect_non_dict_state_raises():
    """state 顶层非 dict → MigrationError。"""
    with pytest.raises(MigrationError):
        detect_and_migrate([])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# migrate_v5_to_v6
# ---------------------------------------------------------------------------

def test_v5_to_v6_foreshadowing_dict_to_list():
    """v5: dict[name→{...}] → v6: list[{content, ...}, ...]。"""
    state = {
        "schema_version": "v5.0",
        "plot_threads": {
            "foreshadowing": {
                "三年之约": {"status": "未回收", "planted_chapter": 1, "target_chapter": 50},
                "古镜": {"status": "未回收", "planted_chapter": 2, "target_chapter": 30},
            }
        },
    }
    out = migrate_v5_to_v6(dict(state))
    fsh = out["plot_threads"]["foreshadowing"]
    assert isinstance(fsh, list)
    assert len(fsh) == 2
    contents = {item["content"] for item in fsh}
    assert contents == {"三年之约", "古镜"}
    # 字段保留
    for item in fsh:
        assert "status" in item
        assert "planted_chapter" in item
        assert "target_chapter" in item


def test_v5_to_v6_idempotent_on_list():
    """v5 但 foreshadowing 已是 list（异常情况）→ 保留不动。"""
    state = {
        "schema_version": "v5.0",
        "plot_threads": {
            "foreshadowing": [{"content": "X", "status": "未回收"}],
        },
    }
    out = migrate_v5_to_v6(dict(state))
    assert isinstance(out["plot_threads"]["foreshadowing"], list)
    assert len(out["plot_threads"]["foreshadowing"]) == 1


def test_v5_to_v6_adds_state_changes_field():
    """v5 → v6：补全 state_changes 字段（v5.0 没有）。"""
    state = {"schema_version": "v5.0"}
    out = migrate_v5_to_v6(dict(state))
    assert "state_changes" in out
    assert out["state_changes"] == []


def test_v5_to_v6_preserves_existing_state_changes():
    """v6 已有 state_changes → 保留不动（不被空 list 覆盖）。"""
    state = {
        "schema_version": "v5.0",
        "state_changes": [{"op": "noop"}],
    }
    out = migrate_v5_to_v6(dict(state))
    assert out["state_changes"] == [{"op": "noop"}]


# ---------------------------------------------------------------------------
# migrate_v54_to_v6
# ---------------------------------------------------------------------------

def test_v54_to_v6_adds_state_changes_field():
    """v5.4 → v6：补全 state_changes 字段。"""
    state = {
        "schema_version": "v5.4",
        "plot_threads": {"foreshadowing": []},
    }
    out = migrate_v54_to_v6(dict(state))
    assert out["state_changes"] == []
    assert out["schema_version"] == CURRENT_SCHEMA


def test_v54_to_v6_preserves_existing_state_changes():
    """v5.4 已有 state_changes → 保留。"""
    state = {
        "schema_version": "v5.4",
        "state_changes": [{"op": "noop"}],
    }
    out = migrate_v54_to_v6(dict(state))
    assert out["state_changes"] == [{"op": "noop"}]


# ---------------------------------------------------------------------------
# StateUpdater.load() 端到端
# ---------------------------------------------------------------------------

def _write_state(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _minimal_state_v6() -> Dict[str, Any]:
    """能通过 _validate_schema 的最小 v6 state。"""
    return {
        "schema_version": CURRENT_SCHEMA,
        "project_info": {"title": "测试"},
        "progress": {"current_chapter": 1, "total_words": 0},
        "protagonist_state": {
            "power": {"realm": "筑基", "layer": 1, "bottleneck": None},
            "location": {"current": "X", "last_chapter": 1},
        },
        "relationships": {},
        "world_settings": {},
        "plot_threads": {"foreshadowing": []},
        "review_checkpoints": [],
    }


def test_load_triggers_migration_for_v5_state(tmp_path: Path):
    """StateUpdater.load()：v5.0 state.json 自动迁移到 v6.2.1。"""
    state_path = tmp_path / "state.json"
    v5_state = {
        "schema_version": "v5.0",
        "project_info": {"title": "测试"},
        "progress": {"current_chapter": 1, "total_words": 0},
        "protagonist_state": {
            "power": {"realm": "筑基", "layer": 1, "bottleneck": None},
            "location": {"current": "X", "last_chapter": 1},
        },
        "relationships": {},
        "world_settings": {},
        "plot_threads": {
            "foreshadowing": {
                "三年之约": {"status": "未回收", "planted_chapter": 1, "target_chapter": 50},
            }
        },
        "review_checkpoints": [],
    }
    _write_state(state_path, v5_state)

    updater = update_state.StateUpdater(str(state_path))
    assert updater.load() is True
    # 验证迁移生效
    assert updater.state["schema_version"] == CURRENT_SCHEMA
    assert isinstance(updater.state["plot_threads"]["foreshadowing"], list)
    assert updater.state["plot_threads"]["foreshadowing"][0]["content"] == "三年之约"


def test_load_triggers_migration_for_missing_version(tmp_path: Path):
    """StateUpdater.load()：缺 schema_version 字段自动按 v5.0 兼容。"""
    state_path = tmp_path / "state.json"
    legacy_state = {
        "project_info": {"title": "测试"},
        "progress": {"current_chapter": 1, "total_words": 0},
        "protagonist_state": {
            "power": {"realm": "筑基", "layer": 1, "bottleneck": None},
            "location": {"current": "X", "last_chapter": 1},
        },
        "relationships": {},
        "world_settings": {},
        "plot_threads": {
            "foreshadowing": {
                "古镜": {"status": "未回收", "planted_chapter": 1, "target_chapter": 30},
            }
        },
        "review_checkpoints": [],
    }
    _write_state(state_path, legacy_state)

    updater = update_state.StateUpdater(str(state_path))
    assert updater.load() is True
    assert updater.state["schema_version"] == CURRENT_SCHEMA
    assert isinstance(updater.state["plot_threads"]["foreshadowing"], list)


def test_load_no_migration_for_current_state(tmp_path: Path):
    """StateUpdater.load()：当前 schema state.json 加载成功，无需迁移。"""
    state_path = tmp_path / "state.json"
    _write_state(state_path, _minimal_state_v6())

    updater = update_state.StateUpdater(str(state_path))
    assert updater.load() is True
    assert updater.state["schema_version"] == CURRENT_SCHEMA