#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sqlite3
import sys
from pathlib import Path


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_on_path()

from data_modules.tests.commit_helpers import build_commit_with_reconciliation
from data_modules.chapter_commit_service import ChapterCommitService  # noqa: E402
from data_modules.projection_log import commit_hash, read_projection_runs  # noqa: E402
from data_modules.projections import (  # noqa: E402
    rebuild_projections,
    replay_projections,
    retry_projection,
)


def _make_rejected_commit(project_root: Path, chapter: int) -> None:
    (project_root / ".webnovel").mkdir(parents=True, exist_ok=True)
    (project_root / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    service = ChapterCommitService(project_root)
    payload = build_commit_with_reconciliation(service,
        chapter=chapter,
        review_result={"blocking_count": 1},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )
    service.persist_commit(payload)


def _make_accepted_commit_with_event(project_root: Path, chapter: int) -> None:
    (project_root / ".webnovel").mkdir(parents=True, exist_ok=True)
    (project_root / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    service = ChapterCommitService(project_root)
    payload = build_commit_with_reconciliation(service,
        chapter=chapter,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={
            "state_deltas": [],
            "entity_deltas": [],
            "accepted_events": [
                {
                    "event_id": "evt-open-loop",
                    "event_type": "open_loop_created",
                    "chapter": chapter,
                    "subject": "韩立",
                    "payload": {"description": "神秘玉佩为何发热"},
                }
            ],
        },
    )
    service.persist_commit(payload)


def _make_accepted_loop_commit(project_root: Path, chapter: int, event_type: str) -> None:
    service = ChapterCommitService(project_root)
    payload = build_commit_with_reconciliation(service,
        chapter=chapter,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={
            "state_deltas": [], "entity_deltas": [],
            "accepted_events": [{
                "event_id": f"evt-loop-{chapter}", "event_type": event_type,
                "chapter": chapter, "subject": "谜团",
                "payload": {"description": "同一条谜团"},
            }],
        },
    )
    service.persist_commit(payload)


def _make_index_rich_commit(project_root: Path, chapter: int = 4) -> None:
    service = ChapterCommitService(project_root)
    payload = build_commit_with_reconciliation(service,
        chapter=chapter,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={
            "accepted_events": [],
            "state_deltas": [{"entity_id": "hero", "field": "realm", "old": "练气", "new": "筑基"}],
            "entity_deltas": [{
                "entity_id": "hero", "canonical_name": "主角", "type": "角色",
                "tier": "主角", "is_protagonist": True, "current": {"realm": "筑基"},
            }],
            "entities_appeared": [{"id": "hero", "mentions": ["陆鸣"]}],
            "scenes": [{"scene_index": 1, "start_line": 1, "end_line": 8, "summary": "石门开启", "characters": ["hero"]}],
        },
    )
    service.persist_commit(payload)


def test_retry_projection_replays_existing_commit(tmp_path):
    _make_rejected_commit(tmp_path, chapter=3)

    report = retry_projection(tmp_path, chapter=3)

    assert report["ok"] is True
    assert report["projection_status"]["state"] == "done"
    state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["progress"]["chapter_status"]["3"] == "chapter_rejected"
    assert read_projection_runs(tmp_path, chapter=3)


def test_retry_projection_rebuilds_event_read_models_from_commit(tmp_path):
    _make_accepted_commit_with_event(tmp_path, chapter=3)
    event_path = tmp_path / ".story-system" / "events" / "chapter_003.events.json"
    assert not event_path.exists()

    report = retry_projection(tmp_path, chapter=3)

    assert report["ok"] is True
    assert report["projection_status"]["memory"] in {"done", "skipped"}
    assert event_path.is_file()
    events = json.loads(event_path.read_text(encoding="utf-8"))
    assert [event["event_id"] for event in events] == ["evt-open-loop"]
    with sqlite3.connect(tmp_path / ".webnovel" / "index.db") as conn:
        rows = conn.execute(
            "SELECT event_id, chapter FROM story_events WHERE chapter = 3"
        ).fetchall()
    assert rows == [("evt-open-loop", 3)]
    assert read_projection_runs(tmp_path, chapter=3)


def test_retry_projection_replay_keeps_event_read_models_aligned_and_unique(tmp_path):
    _make_accepted_commit_with_event(tmp_path, chapter=3)

    first = retry_projection(tmp_path, chapter=3)
    second = retry_projection(tmp_path, chapter=3)

    assert first["ok"] is True
    assert second["ok"] is True
    with sqlite3.connect(tmp_path / ".webnovel" / "index.db") as conn:
        rows = conn.execute(
            "SELECT event_id, chapter FROM story_events WHERE chapter = 3"
        ).fetchall()
    assert rows == [("evt-open-loop", 3)]


def test_retry_legacy_commit_with_projection_status_preserves_its_bytes(tmp_path):
    _make_rejected_commit(tmp_path, chapter=3)
    commit_path = tmp_path / ".story-system" / "commits" / "chapter_003.commit.json"
    legacy = json.loads(commit_path.read_text(encoding="utf-8"))
    legacy["projection_status"] = {"state": "pending", "index": "pending"}
    commit_path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    before = commit_path.read_bytes()

    report = retry_projection(tmp_path, chapter=3)

    assert report["ok"] is True
    assert commit_path.read_bytes() == before


def test_retry_repairs_divergent_event_file_and_sqlite_from_commit(tmp_path):
    _make_accepted_commit_with_event(tmp_path, chapter=3)
    event_path = tmp_path / ".story-system" / "events" / "chapter_003.events.json"
    event_path.parent.mkdir(parents=True, exist_ok=True)
    event_path.write_text(json.dumps([{"event_id": "wrong", "chapter": 3}]), encoding="utf-8")
    with sqlite3.connect(tmp_path / ".webnovel" / "index.db") as conn:
        conn.execute("CREATE TABLE story_events(event_id TEXT, chapter INTEGER, event_type TEXT, subject TEXT, payload_json TEXT)")
        conn.execute("INSERT INTO story_events VALUES ('wrong', 3, 'x', 'x', '{}')")

    report = retry_projection(tmp_path, chapter=3)

    assert report["ok"] is True
    assert json.loads(event_path.read_text(encoding="utf-8"))[0]["event_id"] == "evt-open-loop"
    with sqlite3.connect(tmp_path / ".webnovel" / "index.db") as conn:
        assert conn.execute("SELECT event_id FROM story_events WHERE chapter=3").fetchall() == [("evt-open-loop",)]


def test_retry_after_event_mirror_failure_repairs_and_preserves_commit(tmp_path, monkeypatch):
    _make_accepted_commit_with_event(tmp_path, chapter=3)
    commit_path = tmp_path / ".story-system" / "commits" / "chapter_003.commit.json"
    before = json.loads(commit_path.read_text(encoding="utf-8"))
    original = __import__("data_modules.event_log_store", fromlist=["EventLogStore"]).EventLogStore._write_sqlite_mirror
    failures = {"remaining": 1}

    def fail_once(self, chapter, events):
        if failures["remaining"]:
            failures["remaining"] -= 1
            raise OSError("sqlite unavailable")
        return original(self, chapter, events)

    monkeypatch.setattr(
        "data_modules.event_log_store.EventLogStore._write_sqlite_mirror", fail_once
    )
    first = retry_projection(tmp_path, chapter=3)
    assert first["ok"] is False
    assert json.loads((tmp_path / ".story-system" / "events" / "chapter_003.events.json").read_text())[0]["event_id"] == "evt-open-loop"

    second = retry_projection(tmp_path, chapter=3)
    after = json.loads(commit_path.read_text(encoding="utf-8"))
    assert second["ok"] is True
    assert commit_hash(before) == commit_hash(after)


def test_retry_projection_reports_missing_commit(tmp_path):
    report = retry_projection(tmp_path, chapter=99)

    assert report["ok"] is False
    assert report["error"] == "missing_commit"


def test_replay_projections_runs_range(tmp_path):
    _make_rejected_commit(tmp_path, chapter=1)
    _make_rejected_commit(tmp_path, chapter=2)

    report = replay_projections(tmp_path, start_chapter=1, end_chapter=2)

    assert report["ok"] is True
    assert [item["chapter"] for item in report["results"]] == [1, 2]


def test_full_rebuild_discovers_sparse_commit_sequence_and_preserves_canon(tmp_path):
    _make_rejected_commit(tmp_path, chapter=1)
    _make_rejected_commit(tmp_path, chapter=3)
    commit_paths = sorted((tmp_path / ".story-system" / "commits").glob("*.json"))
    before = {path: path.read_bytes() for path in commit_paths}
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.write_text(json.dumps({"intent": {"next": "keep"}, "unknown": 7}))

    report = rebuild_projections(tmp_path)

    assert report["ok"] is True
    assert report["chapters"] == [1, 3]
    assert {path: path.read_bytes() for path in commit_paths} == before
    state = json.loads(state_path.read_text())
    assert state["intent"] == {"next": "keep"}
    assert state["unknown"] == 7
    assert state["progress"]["chapter_status"] == {
        "1": "chapter_rejected", "3": "chapter_rejected"
    }


def test_full_rebuild_validates_every_commit_before_reset(tmp_path):
    _make_rejected_commit(tmp_path, chapter=1)
    broken_path = tmp_path / ".story-system" / "commits" / "chapter_003.commit.json"
    broken_path.write_text('{"meta": {"chapter": 3, "status": "accepted"}}')
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text('{"keep": true}')

    report = rebuild_projections(tmp_path)

    assert report["ok"] is False
    assert report["error"]["chapter"] == 3
    assert state_path.read_text() == '{"keep": true}'


def test_full_rebuild_is_repeatable_and_preserves_operational_index_data(tmp_path):
    _make_accepted_commit_with_event(tmp_path, chapter=2)
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.write_text(json.dumps({
        "progress": {"current_chapter": 88, "chapter_status": {"88": "manual"}, "planning": "keep"},
        "protagonist_state": {"name": "主角", "location": "手工意图"},
        "intent": {"next": "keep"},
    }), encoding="utf-8")
    from data_modules.config import DataModulesConfig
    from data_modules.index_manager import IndexManager
    from data_modules.memory.schema import MemoryItem
    from data_modules.memory.store import ScratchpadManager
    from data_modules.memory.writer import MemoryWriter
    IndexManager(DataModulesConfig.from_project_root(tmp_path))
    memory_store = ScratchpadManager(DataModulesConfig.from_project_root(tmp_path))
    memory_store.upsert_item(MemoryItem(
        id="manual-keep", layer="semantic", category="story_fact", subject="planning",
        field="intent", value="keep", evidence=["manual:planning"],
    ))
    mixed_id = MemoryWriter(DataModulesConfig.from_project_root(tmp_path))._item_id(
        "open_loop", "神秘玉佩为何发热", "status", 2
    )
    memory_store.upsert_item(MemoryItem(
        id=mixed_id, layer="semantic", category="open_loop", subject="神秘玉佩为何发热",
        field="status", value="active", source_chapter=2,
        evidence=["memory_facts:open_loop:2", "manual:review-note"],
    ))
    with sqlite3.connect(tmp_path / ".webnovel" / "index.db") as conn:
        conn.execute("INSERT INTO review_metrics(start_chapter,end_chapter,notes) VALUES (1,2,'keep')")
        conn.execute("INSERT INTO rag_query_log(query,query_type) VALUES ('keep','manual')")

    first = rebuild_projections(tmp_path)
    second = rebuild_projections(tmp_path)

    assert first["ok"] is True
    assert second["ok"] is True
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["intent"] == {"next": "keep"}
    assert state["progress"]["planning"] == "keep"
    assert state["progress"]["current_chapter"] == 2
    assert state["progress"]["chapter_status"] == {"2": "chapter_committed"}
    memory_items = ScratchpadManager(DataModulesConfig.from_project_root(tmp_path)).dump()["story_facts"]
    assert [item["id"] for item in memory_items].count("manual-keep") == 1
    open_loop_items = [item for item in ScratchpadManager(DataModulesConfig.from_project_root(tmp_path)).dump()["open_loops"] if item["source_chapter"] == 2]
    assert len(open_loop_items) == 1
    assert "manual:review-note" in open_loop_items[0]["evidence"]
    event_path = tmp_path / ".story-system" / "events" / "chapter_002.events.json"
    assert [event["event_id"] for event in json.loads(event_path.read_text())] == ["evt-open-loop"]
    with sqlite3.connect(tmp_path / ".webnovel" / "index.db") as conn:
        assert conn.execute("SELECT event_id FROM story_events WHERE chapter=2").fetchall() == [("evt-open-loop",)]
        assert conn.execute("SELECT notes FROM review_metrics").fetchall() == [("keep",)]
        assert conn.execute("SELECT query FROM rag_query_log").fetchall() == [("keep",)]


def test_full_rebuild_reports_projection_and_chapter_on_failure(tmp_path, monkeypatch):
    _make_accepted_commit_with_event(tmp_path, chapter=1)

    def fail_state(self, payload):
        raise RuntimeError("state unavailable")

    monkeypatch.setattr("data_modules.state_projection_writer.StateProjectionWriter.apply", fail_state)
    report = rebuild_projections(tmp_path)

    assert report["ok"] is False
    assert report["error"] == {"projection": "state", "chapter": 1, "message": "failed:state unavailable"}


def test_full_rebuild_refuses_empty_or_noncanonical_commit_sets_before_reset(tmp_path):
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text('{"keep": true}')

    empty = rebuild_projections(tmp_path)
    assert empty["ok"] is False
    assert state_path.read_text() == '{"keep": true}'

    _make_rejected_commit(tmp_path, chapter=1)
    canonical = tmp_path / ".story-system" / "commits" / "chapter_001.commit.json"
    alternate = tmp_path / ".story-system" / "commits" / "chapter_1.commit.json"
    alternate.write_bytes(canonical.read_bytes())
    malformed = rebuild_projections(tmp_path)

    assert malformed["ok"] is False
    assert malformed["error"]["chapter"] == 1


def test_full_rebuild_preserves_incremental_foreshadowing_semantics(tmp_path):
    _make_accepted_loop_commit(tmp_path, 1, "open_loop_created")
    _make_accepted_loop_commit(tmp_path, 2, "open_loop_closed")
    _make_accepted_loop_commit(tmp_path, 3, "open_loop_created")
    for chapter in (1, 2, 3):
        assert retry_projection(tmp_path, chapter=chapter)["ok"] is True
    state_path = tmp_path / ".webnovel" / "state.json"
    before = json.loads(state_path.read_text(encoding="utf-8"))["plot_threads"]["foreshadowing"]

    report = rebuild_projections(tmp_path)

    after = json.loads(state_path.read_text(encoding="utf-8"))["plot_threads"]["foreshadowing"]
    assert report["ok"] is True
    assert after == before


def test_full_rebuild_validates_scenes_appearances_and_state_change_index(tmp_path, monkeypatch):
    _make_index_rich_commit(tmp_path)

    def omit_scenes(self, manager, payload):
        return 0

    monkeypatch.setattr("data_modules.index_projection_writer.IndexProjectionWriter._apply_scenes", omit_scenes)
    report = rebuild_projections(tmp_path)

    assert report["ok"] is False
    assert report["error"]["projection"] == "index"
    assert report["error"]["chapter"] == 4
    assert "scenes index rows differ" in report["error"]["message"]
