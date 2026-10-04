"""Story System mode must reserve chapter facts for durable commit projections."""

import json
import sqlite3
from pathlib import Path

import pytest

from data_modules.config import DataModulesConfig
from data_modules.index_manager import ChapterMeta, IndexManager, RelationshipMeta, StateChangeMeta
from data_modules.sql_state_manager import EntityData, SQLStateManager
from data_modules.state_manager import EntityState, StateManager
from data_modules.story_system_mode import (
    canonical_projection_write_scope,
    require_legacy_canon_write_allowed,
)


STORY_ROOT = ".story-system"
CANON_ERROR = "chapter facts must originate from durable CHAPTER_COMMIT projections"


def _project(tmp_path, *, story_system: bool):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    config.state_file.write_text(
        json.dumps({"progress": {"current_chapter": 0, "total_words": 0}}),
        encoding="utf-8",
    )
    sql = SQLStateManager(config)
    sql.upsert_entity(EntityData(
        id="hero", type="角色", name="主角", current={"realm": "A"},
    ))
    if story_system:
        story_root = tmp_path / STORY_ROOT
        story_root.mkdir()
        (story_root / "MASTER_SETTING.json").write_text("{}", encoding="utf-8")
    return config


def _state_change_count(config):
    with sqlite3.connect(config.index_db) as conn:
        return conn.execute("SELECT COUNT(*) FROM state_changes").fetchone()[0]


def test_story_system_record_state_change_fails_before_any_state_or_sqlite_write(tmp_path):
    config = _project(tmp_path, story_system=True)
    before_state = config.state_file.read_bytes()
    manager = StateManager(config)

    with pytest.raises(RuntimeError, match=CANON_ERROR):
        manager.record_state_change("hero", "realm", "A", "B", "breakthrough", 5)

    assert config.state_file.read_bytes() == before_state
    assert manager._sql_state_manager.get_entity("hero")["current_json"]["realm"] == "A"
    assert _state_change_count(config) == 0
    assert manager._pending_state_changes == []
    assert manager._pending_entity_patches == {}


def test_story_system_entity_mutation_is_rejected_before_save(tmp_path):
    config = _project(tmp_path, story_system=True)
    before_state = config.state_file.read_bytes()
    manager = StateManager(config)

    with pytest.raises(RuntimeError, match=CANON_ERROR):
        manager.update_entity("hero", {"current": {"realm": "B"}})

    with pytest.raises(RuntimeError, match=CANON_ERROR):
        manager.add_entity(EntityState(id="new", name="新角色", type="角色"))

    assert config.state_file.read_bytes() == before_state
    assert manager._sql_state_manager.get_entity("hero")["current_json"]["realm"] == "A"
    assert manager._sql_state_manager.get_entity("new") is None


def test_story_system_relationship_and_appearance_mutations_fail_fast(tmp_path):
    config = _project(tmp_path, story_system=True)
    before_state = config.state_file.read_bytes()
    manager = StateManager(config)

    with pytest.raises(RuntimeError, match=CANON_ERROR):
        manager.add_relationship("hero", "mentor", "师徒", "拜师", 5)
    with pytest.raises(RuntimeError, match=CANON_ERROR):
        manager.update_entity_appearance("hero", 5, "角色")

    assert config.state_file.read_bytes() == before_state
    assert manager._pending_structured_relationships == []
    assert manager._pending_entity_patches == {}
    assert manager._sql_state_manager.get_entity_relationships("hero") == []


def test_story_system_save_state_backstop_rejects_pending_canon_before_both_stores(tmp_path):
    config = _project(tmp_path, story_system=True)
    before_state = config.state_file.read_bytes()
    manager = StateManager(config)
    # Simulate an unguarded/older caller bypassing the public mutation API.
    manager._pending_state_changes.append({
        "entity_id": "hero", "field": "realm", "old_value": "A",
        "new_value": "B", "reason": "breakthrough", "chapter": 5,
    })

    with pytest.raises(RuntimeError, match=CANON_ERROR):
        manager.save_state()

    assert config.state_file.read_bytes() == before_state
    assert manager._sql_state_manager.get_entity("hero")["current_json"]["realm"] == "A"
    assert _state_change_count(config) == 0


def test_story_system_keeps_review_workflow_status_writable(tmp_path):
    config = _project(tmp_path, story_system=True)
    manager = StateManager(config)

    manager.set_chapter_status(5, "chapter_drafted")
    manager.set_chapter_status(5, "chapter_reviewed")

    with pytest.raises(RuntimeError, match=CANON_ERROR):
        manager.update_progress(5, words=1000)
    with pytest.raises(RuntimeError, match=CANON_ERROR):
        manager.set_chapter_status(5, "chapter_committed")

    state = json.loads(config.state_file.read_text(encoding="utf-8"))
    assert state["progress"]["chapter_status"]["5"] == "chapter_reviewed"


def test_story_system_legacy_sql_and_index_fact_apis_reject_direct_writes(tmp_path):
    config = _project(tmp_path, story_system=True)
    sql = SQLStateManager(config)
    index = IndexManager(config)

    with pytest.raises(RuntimeError, match=CANON_ERROR):
        sql.update_entity_current("hero", {"realm": "B"})
    with pytest.raises(RuntimeError, match=CANON_ERROR):
        sql.record_state_change("hero", "realm", "A", "B", "breakthrough", 5)
    with pytest.raises(RuntimeError, match=CANON_ERROR):
        index.record_state_change(StateChangeMeta(
            entity_id="hero", field="realm", old_value="A", new_value="B",
            reason="breakthrough", chapter=5,
        ))

    assert sql.get_entity("hero")["current_json"]["realm"] == "A"
    assert _state_change_count(config) == 0


def test_story_system_archive_lifecycle_management_remains_writable(tmp_path):
    config = _project(tmp_path, story_system=True)
    index = IndexManager(config)

    assert index.set_entity_archive_status("hero", True)
    assert index.get_entity("hero")["current_json"]["status"] == "archived"
    assert index.set_entity_archive_status("hero", False)
    assert index.get_entity("hero")["current_json"]["status"] == "active"


def test_story_system_sql_and_index_fact_apis_reject_entity_alias_relation_and_appearance(tmp_path):
    config = _project(tmp_path, story_system=True)
    sql = SQLStateManager(config)
    index = IndexManager(config)

    sql_operations = [
        lambda: sql.upsert_entity(EntityData(id="new", type="角色", name="新角色")),
        lambda: sql.register_alias("hero-alias", "hero", "角色"),
        lambda: sql.upsert_relationship("hero", "mentor", "师徒", "拜师", 5),
    ]
    for operation in sql_operations:
        with pytest.raises(RuntimeError, match=CANON_ERROR):
            operation()

    with pytest.raises(RuntimeError, match=CANON_ERROR):
        index.update_entity_current("hero", {"realm": "B"})
    with pytest.raises(RuntimeError, match=CANON_ERROR):
        index.register_alias("hero-alias", "hero", "角色")
    with pytest.raises(RuntimeError, match=CANON_ERROR):
        index.upsert_relationship(RelationshipMeta(
            from_entity="hero", to_entity="mentor", type="师徒", description="拜师", chapter=5,
        ))
    with pytest.raises(RuntimeError, match=CANON_ERROR):
        index.record_appearance("hero", 5, ["主角"])
    with pytest.raises(RuntimeError, match=CANON_ERROR):
        index.apply_entity_delta({"entity_id": "hero", "current": {"realm": "B"}, "chapter": 5})
    with pytest.raises(RuntimeError, match=CANON_ERROR):
        index.add_chapter(ChapterMeta(
            chapter=5, title="第五章", location="", word_count=100,
            characters=[], summary="",
        ))

    assert sql.get_entity("new") is None
    assert sql.get_entity("hero")["current_json"]["realm"] == "A"
    assert _state_change_count(config) == 0


def test_story_system_save_state_backstop_rejects_sqlite_batch_before_sync(tmp_path):
    config = _project(tmp_path, story_system=True)
    before_state = config.state_file.read_bytes()
    manager = StateManager(config)
    manager._pending_sqlite_data["chapter"] = 5
    manager._pending_sqlite_data["relationships_new"].append({
        "from": "hero", "to": "mentor", "type": "师徒",
    })

    with pytest.raises(RuntimeError, match=CANON_ERROR):
        manager.save_state()

    assert config.state_file.read_bytes() == before_state
    assert manager._sql_state_manager.get_entity_relationships("hero") == []


def test_story_system_sqlite_sync_helpers_reject_pending_canon(tmp_path):
    config = _project(tmp_path, story_system=True)
    manager = StateManager(config)
    manager._pending_state_changes.append({
        "entity_id": "hero", "field": "realm", "old_value": "A",
        "new_value": "B", "reason": "breakthrough", "chapter": 5,
    })

    with pytest.raises(RuntimeError, match=CANON_ERROR):
        manager._sync_to_sqlite()
    with pytest.raises(RuntimeError, match=CANON_ERROR):
        manager._sync_pending_patches_to_sqlite()

    assert _state_change_count(config) == 0
    assert manager._sql_state_manager.get_entity("hero")["current_json"]["realm"] == "A"


def test_legacy_state_manager_fact_writes_keep_existing_behavior(tmp_path):
    config = _project(tmp_path, story_system=False)
    manager = StateManager(config)

    manager.record_state_change("hero", "realm", "A", "B", "breakthrough", 5)
    result = manager.save_state()

    assert result["saved"] is True
    assert manager._sql_state_manager.get_entity("hero")["current_json"]["realm"] == "B"
    assert _state_change_count(config) == 1


def test_projection_scope_is_root_bound_and_resets_after_nested_and_exceptional_use(tmp_path):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    for root in (project_a, project_b):
        (root / STORY_ROOT).mkdir(parents=True)
        (root / STORY_ROOT / "MASTER_SETTING.json").write_text("{}", encoding="utf-8")

    with canonical_projection_write_scope(project_a):
        require_legacy_canon_write_allowed(project_a)
        with pytest.raises(RuntimeError, match=CANON_ERROR):
            require_legacy_canon_write_allowed(project_b)
        with canonical_projection_write_scope(project_b):
            require_legacy_canon_write_allowed(project_b)
        require_legacy_canon_write_allowed(project_a)
        with pytest.raises(LookupError):
            with canonical_projection_write_scope(project_b):
                raise LookupError("reset context")
        require_legacy_canon_write_allowed(project_a)

    for root in (project_a, project_b):
        with pytest.raises(RuntimeError, match=CANON_ERROR):
            require_legacy_canon_write_allowed(root)


def test_projection_scope_production_usage_stays_in_index_projection_writer():
    scripts_root = Path(__file__).resolve().parents[2]
    production_uses = []
    for source in scripts_root.rglob("*.py"):
        if "tests" in source.parts or source.name == "story_system_mode.py":
            continue
        if "canonical_projection_write_scope" in source.read_text(encoding="utf-8"):
            production_uses.append(source.name)

    assert production_uses == ["index_projection_writer.py"]
