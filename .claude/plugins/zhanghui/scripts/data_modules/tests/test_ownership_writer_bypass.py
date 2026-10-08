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


def _activate_owned_project(root):
    from data_modules.effective_history import EffectiveHistoryStore
    from data_modules.owned_project_view import OwnedProjectView
    from data_modules.projection_generation import ProjectionGeneration
    from data_modules.projection_rebuild import build_effective_generation

    commit = {
        "meta": {"schema_version": "story-system/v1", "chapter": 1, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": [],
                              "chapter_meta": {"title": "Canon title"}, "summary_text": "summary"},
    }
    commit_path = root / ".story-system/commits/chapter_001.commit.json"
    commit_path.parent.mkdir(parents=True, exist_ok=True)
    commit_path.write_text(json.dumps(commit), encoding="utf-8")
    snapshot = EffectiveHistoryStore().read_active_snapshot(root)
    built = build_effective_generation(root, snapshot)
    protocol = ProjectionGeneration(root)
    protocol.publish_generation(built["validated_generation"], None, snapshot.correction_lineage_digest)
    return OwnedProjectView.pin_active(root)


@pytest.mark.parametrize(
    ("option", "expected"),
    [
        (("--volume-planned", "1", "--chapters-range", "1-10"), "progress.volumes_planned"),
        (("--add-review", "1-2", "review/report.md"), "review_checkpoints"),
    ],
)
def test_enrolled_update_state_cli_writes_owner_overlay_without_legacy_mutation(
    tmp_path, monkeypatch, capsys, option, expected
):
    from data_modules.owned_project_view import OwnedProjectView, OwnedStateStore
    import update_state as update_state_module

    (tmp_path / ".webnovel").mkdir()
    state_path = tmp_path / ".webnovel/state.json"
    state_path.write_text(json.dumps({"legacy_sentinel": "unchanged"}), encoding="utf-8")
    legacy_bytes = state_path.read_bytes()
    _activate_owned_project(tmp_path)
    monkeypatch.setattr(sys, "argv", ["update_state.py", "--project-root", str(tmp_path), *option])

    update_state_module.main()
    output = capsys.readouterr().out

    store = OwnedStateStore(tmp_path)
    assert state_path.read_bytes() == legacy_bytes
    assert "已保存 owner overlay" in output
    assert "备份: None" not in output
    assert store._overlay()["revision"] == 1
    view = OwnedProjectView.pin_active(tmp_path)
    assert view is not None
    state = view.state_view()
    if expected == "progress.volumes_planned":
        assert state["progress"]["volumes_planned"][0]["volume"] == 1
    else:
        assert state["review_checkpoints"][-1]["report"] == "review/report.md"


def test_enrolled_migrate_story_craft_routes_to_owner_without_legacy_write(tmp_path):
    from data_modules.owned_project_view import OwnedProjectView, OwnedStateStore
    from migrate_story_craft import migrate_state_json

    (tmp_path / ".webnovel").mkdir()
    state_path = tmp_path / ".webnovel/state.json"
    original = json.dumps({"legacy_sentinel": "retain", "unknown_field": {"x": 1}})
    state_path.write_text(original, encoding="utf-8")
    _activate_owned_project(tmp_path)

    result = migrate_state_json(str(state_path))

    assert state_path.read_text(encoding="utf-8") == original
    store = OwnedStateStore(tmp_path)
    overlay = store._overlay()
    assert overlay["revision"] == 1
    assert "unknown_field" not in overlay["values"]
    assert "story_craft" in overlay["values"]
    view = OwnedProjectView.pin_active(tmp_path)
    assert view is not None
    assert view.state_view()["story_craft"] == result["story_craft"]


def test_enrolled_update_state_cli_stale_owner_revision_fails_closed(tmp_path, monkeypatch):
    from data_modules.owned_project_view import OwnedProjectView, OwnedStateStore
    import update_state as update_state_module

    (tmp_path / ".webnovel").mkdir()
    state_path = tmp_path / ".webnovel/state.json"
    legacy_bytes = b'{"legacy_sentinel":"unchanged"}\n'
    state_path.write_bytes(legacy_bytes)
    _activate_owned_project(tmp_path)
    original_update = update_state_module.StateUpdater.mark_volume_planned

    def race_owner_revision(updater, volume, chapters_range):
        original_update(updater, volume, chapters_range)
        OwnedStateStore(tmp_path).write_owner_values(
            {"review_checkpoints": [{"report": "external"}]}, expected_revision=0
        )

    monkeypatch.setattr(update_state_module.StateUpdater, "mark_volume_planned", race_owner_revision)
    monkeypatch.setattr(sys, "argv", [
        "update_state.py", "--project-root", str(tmp_path), "--volume-planned", "1",
        "--chapters-range", "1-10",
    ])

    with pytest.raises(SystemExit) as stopped:
        update_state_module.main()

    assert stopped.value.code == 1
    assert state_path.read_bytes() == legacy_bytes
    view = OwnedProjectView.pin_active(tmp_path)
    assert view is not None
    assert view.state_view()["review_checkpoints"] == [{"report": "external"}]
    assert "volumes_planned" not in view.state_view().get("progress", {})


def test_plan_story_craft_initializer_is_not_legacy_only():
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[2]
    plan_skill = (scripts.parent / "skills/webnovel-plan/SKILL.md").read_text(encoding="utf-8")
    helper = (scripts / "migrate_story_craft.py").read_text(encoding="utf-8")
    assert "migrate_story_craft.py" in plan_skill
    assert "OwnedProjectView.pin_active" in helper
    assert "write_owner_values" in helper


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
