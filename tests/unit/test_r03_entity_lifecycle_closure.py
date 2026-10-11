"""Regression test for R3 entity lifecycle closure and canonical authority."""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from changes_gate import check_r03_entities, run_changes_gate
from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager
from data_modules.index_projection_writer import IndexProjectionWriter


def test_r03_canonical_entity_from_state_json_passes(tmp_path: Path):
    """Canonical entities in state.json (e.g. 梅叔) pass R3 even if not yet in index.db."""
    db_path = tmp_path / "index.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            tier TEXT DEFAULT '装饰',
            desc TEXT,
            current_json TEXT,
            first_appearance INTEGER DEFAULT 0,
            last_appearance INTEGER DEFAULT 0,
            is_protagonist INTEGER DEFAULT 0,
            is_archived INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE aliases (
            alias TEXT,
            entity_id TEXT,
            entity_type TEXT,
            PRIMARY KEY (alias, entity_id, entity_type)
        );
    """)
    # index.db only has protagonist 林越
    conn.execute("INSERT INTO entities (id, type, canonical_name) VALUES ('林越', '角色', '林越')")
    conn.commit()
    conn.close()

    # state.json has canonical character 梅叔
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({
            "entity_state": {
                "林越": {"身份": "主角"},
                "梅叔": {"身份": "退休档案员", "状态": "保管一批未数字化旧档案"},
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    # 梅叔 in character_state_changes should PASS
    changes = {
        "character_state_changes": [
            {"character_id": "林越", "importance": "critical"},
            {"character_id": "梅叔", "importance": "important"},
        ],
    }
    failures = check_r03_entities(changes, db_path, state_path)
    assert failures == []

    # Unknown hallucinated character must strictly FAIL CLOSED
    bad_changes = {
        "character_state_changes": [
            {"character_id": "未知神秘人999", "importance": "important"},
        ]
    }
    bad_failures = check_r03_entities(bad_changes, db_path, state_path)
    assert len(bad_failures) == 1
    assert bad_failures[0].rule_id == "R3"
    assert "未知神秘人999" in bad_failures[0].message


def test_r03_grounded_hierarchical_location_passes(tmp_path: Path):
    """Hierarchical location grounded in known location passes; arbitrary unknown location fails."""
    db_path = tmp_path / "index.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            is_archived INTEGER DEFAULT 0
        );
        CREATE TABLE aliases (
            alias TEXT,
            entity_id TEXT,
            entity_type TEXT,
            PRIMARY KEY (alias, entity_id, entity_type)
        );
        CREATE TABLE scenes (
            id INTEGER PRIMARY KEY,
            chapter INTEGER,
            scene_order INTEGER,
            location TEXT
        );
        CREATE TABLE story_events (
            id INTEGER PRIMARY KEY,
            event_id TEXT,
            chapter INTEGER,
            event_type TEXT,
            subject TEXT,
            payload TEXT
        );
    """)
    conn.execute("INSERT INTO entities VALUES ('延清装订修补铺', '地点', '延清装订修补铺', 0)")
    conn.execute("INSERT INTO story_events (event_id, chapter, event_type, subject, payload) VALUES ('evt-1', 1, 'world_rule', '临汐城', '{\"scope\": \"临汐城咸水巷盲区\"}')")
    conn.execute("INSERT INTO story_events (event_id, chapter, event_type, subject, payload) VALUES ('evt-2', 1, 'artifact_obtained', '林越', '{\"source\": \"防汛库七号杂档\"}')")
    conn.commit()
    conn.close()

    # 咸水巷地下七号防汛杂档库 is grounded in 咸水巷 and 防汛库七号杂档 -> should pass
    changes = {
        "location_state_changes": [
            {"location_id": "咸水巷地下七号防汛杂档库", "new_state": "闭锁", "importance": "important"},
        ]
    }
    failures = check_r03_entities(changes, db_path)
    assert failures == []

    # Arbitrary ungrounded location must strictly FAIL CLOSED
    bad_changes = {
        "location_state_changes": [
            {"location_id": "火星秘密仓库999", "new_state": "闭锁", "importance": "important"},
        ]
    }
    bad_failures = check_r03_entities(bad_changes, db_path)
    assert len(bad_failures) == 1
    assert bad_failures[0].rule_id == "R3"
    assert "火星秘密仓库999" in bad_failures[0].message


def test_index_manager_applies_entity_name_and_normalizes_type(tmp_path: Path):
    """IndexManager.apply_entity_delta handles entity_name and maps english type to chinese."""
    config = DataModulesConfig(project_root=tmp_path)
    manager = IndexManager(config)

    # Delta with entity_name and english entity_type
    delta = {
        "entity_name": "延清装订修补铺",
        "entity_type": "location",
        "action": "create",
        "description": "位于下城区咸水巷盲区的旧纸装订作坊",
        "chapter": 1,
    }
    applied = manager.apply_entity_delta(delta)
    assert applied is True

    ent = manager.get_entity("延清装订修补铺")
    assert ent is not None
    assert ent["canonical_name"] == "延清装订修补铺"
    assert ent["type"] == "地点"


def test_index_projection_writer_syncs_state_json_canon(tmp_path: Path):
    """IndexProjectionWriter._apply_accepted_commit seeds canonical entities from state.json."""
    webnovel_dir = tmp_path / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    state_file = webnovel_dir / "state.json"
    state_file.write_text(
        json.dumps({
            "entity_state": {
                "林越": {"身份": "主角"},
                "梅叔": {"身份": "退休档案员"},
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    writer = IndexProjectionWriter(tmp_path)
    config = DataModulesConfig(project_root=tmp_path)
    manager = IndexManager(config)

    synced = writer._sync_canonical_state_entities(manager)
    assert synced == 2
    assert manager.get_entity("梅叔") is not None
    assert manager.get_entity("林越") is not None


def test_replay_chapter_2_artifact_passes_gate():
    """Exact replay of Chapter 2 writer output from run-005 passes changes_gate with updated R3."""
    writer_output_path = Path("/Users/chang/Desktop/Code/zhanghui-benchmark/runs/pilot-tide-archive-001/run-005-post-native-repair/_invocations/inv-zh-ch02-step2a_writer-a6a33249/output.txt")
    db_path = Path("/Users/chang/Desktop/Code/zhanghui-benchmark/runs/pilot-tide-archive-001/run-005-post-native-repair/zhanghui/.webnovel/index.db")
    state_path = Path("/Users/chang/Desktop/Code/zhanghui-benchmark/runs/pilot-tide-archive-001/run-005-post-native-repair/zhanghui/.webnovel/state.json")

    if not writer_output_path.is_file() or not db_path.is_file() or not state_path.is_file():
        pytest.skip("Run-005 artifacts not found on local path")

    chapter_text = writer_output_path.read_text(encoding="utf-8")
    result = run_changes_gate(
        chapter_text=chapter_text,
        db_path=db_path,
        state_path=state_path,
        chapter=2,
    )
    # Both 梅叔 and 咸水巷地下七号防汛杂档库 must now pass R3
    r3_failures = [f for f in result.failures if f.rule_id == "R3"]
    assert r3_failures == [], f"Unexpected R3 failures: {[f.message for f in r3_failures]}"
    assert result.passed is True
