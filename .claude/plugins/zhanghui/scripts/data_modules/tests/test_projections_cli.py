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

from data_modules.chapter_commit_service import ChapterCommitService  # noqa: E402
from data_modules.projection_log import commit_hash, read_projection_runs  # noqa: E402
from data_modules.projections import replay_projections, retry_projection  # noqa: E402


def _make_rejected_commit(project_root: Path, chapter: int) -> None:
    (project_root / ".webnovel").mkdir(parents=True, exist_ok=True)
    (project_root / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    service = ChapterCommitService(project_root)
    payload = service.build_commit(
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
    payload = service.build_commit(
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
