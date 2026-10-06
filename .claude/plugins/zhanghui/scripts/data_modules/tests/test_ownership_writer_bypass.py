"""Real Story System API checks for unowned direct Canon writes."""

import json
import sys

import pytest

from data_modules.config import DataModulesConfig
from data_modules.event_log_store import EventLogStore
from data_modules.index_manager import IndexManager
from data_modules.sql_state_manager import SQLStateManager
from data_modules.state_manager import StateManager


def _story_system_project(root):
    config = DataModulesConfig.from_project_root(root)
    config.ensure_dirs()
    story = config.story_system_dir
    story.mkdir(parents=True, exist_ok=True)
    (story / "MASTER_SETTING.json").write_text(json.dumps({
        "meta": {"schema_version": "story-system/v1", "contract_type": "MASTER_SETTING"},
        "route": {"primary_genre": "玄幻"},
    }), encoding="utf-8")
    config.state_file.write_text(json.dumps({"protagonist_state": {"name": "sentinel"}}), encoding="utf-8")
    return config


def _snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def test_actual_public_fact_writer_apis_reject_without_commit_before_persisting(tmp_path):
    config = _story_system_project(tmp_path)
    state = StateManager(config)
    sql = SQLStateManager(config)
    index = IndexManager(config)
    events = EventLogStore(config.project_root)
    before = _snapshot(tmp_path)

    with pytest.raises(RuntimeError, match="durable CHAPTER_COMMIT projections"):
        state.process_chapter_result(1, {"entities_new": [{"id": "bypass"}]})
    with pytest.raises(RuntimeError, match="durable CHAPTER_COMMIT projections"):
        sql.process_chapter_entities(1, [], [{"suggested_id": "bypass"}], [], [])
    with pytest.raises(RuntimeError, match="durable CHAPTER_COMMIT projections"):
        index.process_chapter_data(1, "title", "location", 10, [], [])
    with pytest.raises(RuntimeError, match="Durable chapter commit is missing"):
        events.write_events(1, [{"event_id": "bypass", "chapter": 1, "event_type": "open_loop_created",
                                 "subject": "x", "payload": {}}])

    assert _snapshot(tmp_path) == before
    assert not list((config.story_system_dir / "commits").glob("chapter_*.commit.json"))


def test_update_state_cli_rejects_canon_options_before_state_write(tmp_path, monkeypatch):
    config = _story_system_project(tmp_path)
    before = _snapshot(tmp_path)
    monkeypatch.setattr(sys, "argv", ["update_state.py", "--project-root", str(tmp_path),
                                       "--protagonist-power", "境界", "2", "瓶颈"])
    from update_state import main

    with pytest.raises(SystemExit) as stopped:
        main()

    assert stopped.value.code == 2
    assert _snapshot(tmp_path) == before


def test_update_state_cli_keeps_intent_volume_planning_available_in_story_system(tmp_path, monkeypatch):
    config = _story_system_project(tmp_path)
    config.state_file.write_text(json.dumps({
        "schema_version": "v6.2.1", "project_info": {}, "progress": {},
        "protagonist_state": {"power": {}, "location": ""}, "relationships": {},
        "world_settings": {}, "plot_threads": {}, "review_checkpoints": [],
    }), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["update_state.py", "--project-root", str(tmp_path),
                                       "--volume-planned", "1", "--chapters-range", "1-10"])
    from update_state import main

    main()

    saved = json.loads(config.state_file.read_text(encoding="utf-8"))
    assert saved["progress"]["volumes_planned"][0]["volume"] == 1
