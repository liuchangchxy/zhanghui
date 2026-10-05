#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sqlite3
import sys
from pathlib import Path

import pytest


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_on_path()

from data_modules.tests.commit_helpers import build_commit_with_reconciliation
from data_modules.tests.commit_helpers import EMPTY_PROPOSAL
from data_modules.chapter_commit_service import ChapterCommitService  # noqa: E402
from data_modules.projection_log import commit_hash, read_projection_runs  # noqa: E402
from data_modules.gate_findings import DetectedFinding, EvidenceRef, FindingAuthority, FindingCategory
from data_modules.reconciliation import reconcile_changes
from data_modules.projections import (  # noqa: E402
    rebuild_projections,
    replay_projections,
    retry_projection,
)


def _make_rejected_commit(project_root: Path, chapter: int) -> None:
    (project_root / ".webnovel").mkdir(parents=True, exist_ok=True)
    (project_root / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    service = ChapterCommitService(project_root)
    extraction = {"state_deltas": [], "entity_deltas": [], "accepted_events": []}
    chapter_text = "test final prose\n<chapter_changes>" + json.dumps(
        EMPTY_PROPOSAL, ensure_ascii=False
    ) + "</chapter_changes>"
    finding = DetectedFinding(
        gate_id="projection-fixture.integrity",
        stable_subject_key=f"invalid-integrity-proof:{chapter}",
        category=FindingCategory.INTEGRITY,
        authority=FindingAuthority.SYSTEM_INTEGRITY,
        scope={"chapter": chapter},
        evidence=[EvidenceRef(kind="deterministic_validation", identity={"valid": False})],
        checker_id="projection-fixture", checker_version="1",
    )
    service.evaluate_attempt(
        chapter, [finding], attempt_id=f"projection-fixture-{chapter}",
        policy_version="test-v1", scope={"chapter": chapter},
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []}, extraction_result=extraction,
        chapter_text=chapter_text, proposed_changes=EMPTY_PROPOSAL,
        reconciliation_result=reconcile_changes(EMPTY_PROPOSAL, extraction, chapter_text=chapter_text),
    )


def test_rejected_projection_fixture_is_bound_to_a_service_owned_hard_veto(tmp_path):
    _make_rejected_commit(tmp_path, chapter=8)
    payload = json.loads((tmp_path / ".story-system/commits/chapter_008.commit.json").read_text(encoding="utf-8"))
    assert payload["meta"]["status"] == "rejected"
    assert payload["gate_decision_binding"]["final_action"] == "REJECT"
    assert payload["gate_decision_binding"]["policy_version"] == "test-v1"


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


def test_full_rebuild_validates_index_field_values(tmp_path, monkeypatch):
    _make_index_rich_commit(tmp_path)
    from data_modules.index_manager import IndexManager
    original = IndexManager.record_appearance

    def corrupt_mentions(self, entity_id, chapter, mentions, confidence=1.0, skip_if_exists=False):
        original(self, entity_id, chapter, mentions, confidence, skip_if_exists)
        with self._get_conn() as conn:
            conn.execute("UPDATE appearances SET mentions='[]' WHERE entity_id=? AND chapter=?", (entity_id, chapter))

    monkeypatch.setattr(IndexManager, "record_appearance", corrupt_mentions)
    report = rebuild_projections(tmp_path)

    assert report["ok"] is False
    assert report["error"]["projection"] == "index"
    assert report["error"]["chapter"] == 4
    assert "appearances index rows differ" in report["error"]["message"]


def test_rebuild_regenerates_intent_diagnostics_and_clears_stale_rows(tmp_path):
    _make_accepted_loop_commit(tmp_path, 1, "open_loop_closed")
    first = rebuild_projections(tmp_path)
    diagnostic_path = tmp_path / ".story-system" / "projections" / "intent-diagnostics.json"
    assert first["ok"] is True
    first_bytes = diagnostic_path.read_bytes()
    first_data = json.loads(first_bytes)
    assert [row["reason"] for row in first_data["diagnostics"]] == ["orphan_close"]

    second = rebuild_projections(tmp_path)
    assert second["ok"] is True
    assert diagnostic_path.read_bytes() == first_bytes

    diagnostic_path.write_text(
        json.dumps({"schema_version": "intent-diagnostics/v1", "diagnostics": [{"event_id": "stale", "reason": "stale"}]}),
        encoding="utf-8",
    )
    third = rebuild_projections(tmp_path)
    assert third["ok"] is True
    assert diagnostic_path.read_bytes() == first_bytes


def test_rebuild_writes_empty_intent_diagnostics_projection(tmp_path):
    _make_accepted_empty_commit(tmp_path, 1)
    report = rebuild_projections(tmp_path)
    diagnostic_path = tmp_path / ".story-system" / "projections" / "intent-diagnostics.json"
    assert report["ok"] is True
    assert json.loads(diagnostic_path.read_text(encoding="utf-8")) == {
        "schema_version": "intent-diagnostics/v1",
        "diagnostics": [],
    }


def _make_accepted_empty_commit(project_root: Path, chapter: int) -> None:
    service = ChapterCommitService(project_root)
    payload = build_commit_with_reconciliation(
        service,
        chapter=chapter,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )
    service.persist_commit(payload)


def test_rebuild_upgrades_unique_legacy_state_loop_row_to_event_identity(tmp_path):
    _make_accepted_loop_commit(tmp_path, 1, "open_loop_created")
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"plot_threads": {"foreshadowing": [{
        "content": "同一条谜团", "status": "active", "planted_chapter": 1,
    }]}}), encoding="utf-8")

    report = rebuild_projections(tmp_path)

    rows = json.loads(state_path.read_text(encoding="utf-8"))["plot_threads"]["foreshadowing"]
    assert report["ok"] is True
    assert len(rows) == 1
    assert rows[0]["loop_id"] == "evt-loop-1"
    assert rows[0]["status"] == "active"


def test_rebuild_upgrades_legacy_state_description_alias_for_structured_loop_content(tmp_path):
    _make_accepted_intent_commit(tmp_path, 1, [{
        "event_id": "typed-loop", "event_type": "open_loop_created", "chapter": 1,
        "subject": "线索", "payload": {
            "content": "身份悬疑：保人身份不明",
            "loop_type": "身份悬疑", "description": "保人身份不明",
        },
    }])
    _make_accepted_intent_commit(tmp_path, 2, [{
        "event_id": "typed-close", "event_type": "open_loop_closed", "chapter": 2,
        "subject": "线索", "payload": {"loop_id": "typed-loop", "content": "真相揭晓"},
    }])
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"plot_threads": {"foreshadowing": [{
        "content": "保人身份不明", "status": "active", "planted_chapter": 1,
    }]}}), encoding="utf-8")

    report = rebuild_projections(tmp_path)

    rows = json.loads(state_path.read_text(encoding="utf-8"))["plot_threads"]["foreshadowing"]
    assert report["ok"] is True
    assert len(rows) == 1
    assert rows[0]["loop_id"] == "typed-loop"
    assert rows[0]["content"] == "身份悬疑：保人身份不明"
    assert rows[0]["status"] == "resolved"
    assert rows[0]["resolution_event_id"] == "typed-close"


def test_rebuild_upgrades_legacy_state_question_alias_for_structured_loop_content(tmp_path):
    _make_accepted_intent_commit(tmp_path, 1, [{
        "event_id": "question-loop", "event_type": "open_loop_created", "chapter": 1,
        "subject": "线索", "payload": {
            "content": "身份悬疑：保人身份不明",
            "loop_type": "身份悬疑", "description": "保人身份不明",
            "unanswered_question": "谁是保人？",
        },
    }])
    _make_accepted_intent_commit(tmp_path, 2, [{
        "event_id": "question-close", "event_type": "open_loop_closed", "chapter": 2,
        "subject": "线索", "payload": {"loop_id": "question-loop", "content": "真相揭晓"},
    }])
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"plot_threads": {"foreshadowing": [{
        "content": "谁是保人？", "status": "active", "planted_chapter": 1,
    }]}}), encoding="utf-8")

    report = rebuild_projections(tmp_path)

    rows = json.loads(state_path.read_text(encoding="utf-8"))["plot_threads"]["foreshadowing"]
    assert report["ok"] is True
    assert len(rows) == 1
    assert rows[0]["loop_id"] == "question-loop"
    assert rows[0]["content"] == "身份悬疑：保人身份不明"
    assert rows[0]["status"] == "resolved"


def test_rebuild_keeps_unprovable_legacy_state_row_non_authoritative(tmp_path):
    _make_accepted_loop_commit(tmp_path, 1, "open_loop_created")
    _make_accepted_loop_commit(tmp_path, 2, "open_loop_created")
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"plot_threads": {"foreshadowing": [{
        "content": "同一条谜团", "status": "active", "planted_chapter": 99,
    }]}}), encoding="utf-8")

    report = rebuild_projections(tmp_path)

    rows = json.loads(state_path.read_text(encoding="utf-8"))["plot_threads"]["foreshadowing"]
    legacy = [row for row in rows if "loop_id" not in row]
    assert report["ok"] is True
    assert len(legacy) == 1
    assert legacy[0]["status"] == "legacy_unlinked"


def test_rebuild_shadows_mixed_evidence_legacy_memory_row_when_canon_resolves_loop(tmp_path):
    from data_modules.config import DataModulesConfig
    from data_modules.memory.schema import MemoryItem
    from data_modules.memory.store import ScratchpadManager

    _make_accepted_loop_commit(tmp_path, 1, "open_loop_created")
    _make_accepted_loop_commit(tmp_path, 2, "open_loop_closed")
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    store = ScratchpadManager(cfg)
    legacy_id = "old-content-derived-loop"
    store.upsert_item(MemoryItem(
        id=legacy_id, layer="semantic", category="open_loop", subject="同一条谜团",
        field="status", value="同一条谜团", status="active", source_chapter=1,
        payload={"planted_chapter": 1, "status": "active"},
        evidence=["memory_facts:open_loop:1", "manual:preserve"],
    ))

    report = rebuild_projections(tmp_path)

    rows = store.query(category="open_loop", status=None)
    active = store.query(category="open_loop", status="active")
    assert report["ok"] is True
    upgraded = [row for row in rows if row.payload.get("loop_id") == "evt-loop-1"]
    assert len(upgraded) == 1
    assert "manual:preserve" in upgraded[0].evidence
    assert upgraded[0].status == "outdated"
    assert all(row.id != legacy_id for row in active)
    assert len([row for row in rows if row.subject == "同一条谜团"]) == 1


def test_rebuild_resolves_description_alias_before_context_exposes_legacy_loop(tmp_path):
    from data_modules.config import DataModulesConfig
    from data_modules.memory_contract_adapter import MemoryContractAdapter
    from data_modules.memory.schema import MemoryItem
    from data_modules.memory.store import ScratchpadManager

    _make_accepted_intent_commit(tmp_path, 1, [{
        "event_id": "mystery-loop", "event_type": "open_loop_created", "chapter": 1,
        "subject": "线索", "payload": {"loop_type": "mystery", "description": "玉佩为何发热"},
    }])
    _make_accepted_intent_commit(tmp_path, 2, [{
        "event_id": "mystery-close", "event_type": "open_loop_closed", "chapter": 2,
        "subject": "谜底揭晓", "payload": {"loop_id": "mystery-loop", "description": "真相已经揭晓"},
    }])
    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    store = ScratchpadManager(config)
    store.upsert_item(MemoryItem(
        id="legacy-mystery-loop", layer="semantic", category="open_loop",
        subject="玉佩为何发热", field="status", value="玉佩为何发热", status="active",
        source_chapter=1, evidence=["memory_facts:open_loop:1", "manual:author-note"],
    ))

    report = rebuild_projections(tmp_path)
    first_rows = store.query(category="open_loop", status=None)
    second_report = rebuild_projections(tmp_path)

    rows = store.query(category="open_loop", status=None)
    assert report["ok"] is True and second_report["ok"] is True
    canonical = next(row for row in rows if row.payload.get("loop_id") == "mystery-loop")
    state_rows = json.loads(
        (tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8")
    )["plot_threads"]["foreshadowing"]
    assert next(row for row in state_rows if row.get("loop_id") == "mystery-loop")["status"] == "resolved"
    assert canonical.status == "outdated"
    assert canonical.payload["lifecycle_status"] == "resolved"
    assert canonical.payload["resolution_event_id"] == "mystery-close"
    assert "manual:author-note" in canonical.evidence
    assert store.query(category="open_loop", status="active") == []
    assert MemoryContractAdapter(config).get_open_loops(status="active") == []
    context = MemoryContractAdapter(config).load_context(chapter=3)
    assert context.sections.get("urgent_loops", []) == []
    assert len([row for row in rows if row.payload.get("loop_id") == "mystery-loop"]) == 1
    assert len(rows) == len(first_rows)
    first_canonical = next(row for row in first_rows if row.payload.get("loop_id") == "mystery-loop")
    assert first_canonical.id == canonical.id
    assert "manual:author-note" in first_canonical.evidence


@pytest.mark.parametrize(
    ("field", "legacy_text"),
    [
        ("content", "玉佩为何发热"),
        ("description", "玉佩为何发热"),
        ("unanswered_question", "玉佩为何发热？"),
        ("normalized", "mystery：玉佩为何发热"),
    ],
)
def test_rebuild_migrates_only_exact_historical_memory_aliases(tmp_path, field, legacy_text):
    from data_modules.config import DataModulesConfig
    from data_modules.memory.schema import MemoryItem
    from data_modules.memory.store import ScratchpadManager

    payload = {"loop_type": "mystery", "description": "玉佩为何发热"}
    if field == "content":
        payload["content"] = legacy_text
    elif field == "unanswered_question":
        payload[field] = legacy_text
    _make_accepted_intent_commit(tmp_path, 1, [{
        "event_id": "alias-loop", "event_type": "open_loop_created", "chapter": 1,
        "subject": "线索", "payload": payload,
    }])
    _make_accepted_intent_commit(tmp_path, 2, [{
        "event_id": "alias-close", "event_type": "open_loop_closed", "chapter": 2,
        "subject": "谜底揭晓", "payload": {"loop_id": "alias-loop", "content": "真相揭晓"},
    }])
    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    store = ScratchpadManager(config)
    store.upsert_item(MemoryItem(
        id="old-alias", layer="semantic", category="open_loop", subject=legacy_text,
        field="status", value=legacy_text, status="active", source_chapter=1,
        evidence=["memory_facts:open_loop:1", "manual:keep"],
    ))

    report = rebuild_projections(tmp_path)

    rows = store.query(category="open_loop", status=None)
    assert report["ok"] is True
    assert len(rows) == 1
    assert rows[0].payload["loop_id"] == "alias-loop"
    assert rows[0].status == "outdated"
    assert "manual:keep" in rows[0].evidence


def test_rebuild_does_not_bind_ambiguous_or_wrong_chapter_legacy_memory_alias(tmp_path):
    from data_modules.config import DataModulesConfig
    from data_modules.memory.schema import MemoryItem
    from data_modules.memory.store import ScratchpadManager

    _make_accepted_intent_commit(tmp_path, 1, [
        {
            "event_id": "loop-a", "event_type": "open_loop_created", "chapter": 1,
            "subject": "A", "payload": {"description": "玉佩发热"},
        },
        {
            "event_id": "loop-b", "event_type": "open_loop_created", "chapter": 1,
            "subject": "B", "payload": {"description": "玉佩发热"},
        },
    ])
    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    store = ScratchpadManager(config)
    store.upsert_item(MemoryItem(
        id="ambiguous", layer="semantic", category="open_loop", subject="玉佩发热",
        field="status", value="玉佩发热", status="active", source_chapter=1,
        evidence=["manual:ambiguous"],
    ))
    store.upsert_item(MemoryItem(
        id="wrong-chapter", layer="semantic", category="open_loop", subject="玉佩发热",
        field="status", value="玉佩发热", status="active", source_chapter=9,
        evidence=["manual:wrong-chapter"],
    ))

    report = rebuild_projections(tmp_path)

    rows = store.query(category="open_loop", status=None)
    assert report["ok"] is True
    legacy = [row for row in rows if row.id in {"ambiguous", "wrong-chapter"}]
    assert {row.id for row in legacy} == {"ambiguous", "wrong-chapter"}
    assert all(row.payload.get("loop_id") is None for row in legacy)
    assert all(row.status == "outdated" for row in legacy)
    assert {e for row in legacy for e in row.evidence} == {"manual:ambiguous", "manual:wrong-chapter"}


def test_rebuild_keeps_payoff_only_diagnostic_without_creating_active_promise(tmp_path):
    _make_accepted_promise_commit(tmp_path, 1, "promise_paid_off", "paid-only", "救下盟友", {})
    report = rebuild_projections(tmp_path)
    diagnostics = json.loads((tmp_path / ".story-system" / "projections" / "intent-diagnostics.json").read_text(encoding="utf-8"))
    from data_modules.config import DataModulesConfig
    from data_modules.memory.store import ScratchpadManager
    active = ScratchpadManager(DataModulesConfig.from_project_root(tmp_path)).query(category="reader_promise", status="active")
    assert report["ok"] is True
    assert [row["reason"] for row in diagnostics["diagnostics"]] == ["unlinked_payoff"]
    assert active == []


def _make_accepted_promise_commit(project_root: Path, chapter: int, event_type: str, event_id: str, content: str, extra: dict) -> None:
    service = ChapterCommitService(project_root)
    payload = build_commit_with_reconciliation(
        service,
        chapter=chapter,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={
            "state_deltas": [], "entity_deltas": [],
            "accepted_events": [{
                "event_id": event_id, "event_type": event_type, "chapter": chapter,
                "subject": content, "payload": {"content": content, **extra},
            }],
        },
    )
    service.persist_commit(payload)


def _make_accepted_intent_commit(project_root: Path, chapter: int, events: list[dict]) -> None:
    service = ChapterCommitService(project_root)
    payload = build_commit_with_reconciliation(
        service,
        chapter=chapter,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": events},
    )
    service.persist_commit(payload)


def test_rebuild_reconciles_duplicate_loops_promises_and_legacy_rows_without_duplicate_active_context(tmp_path):
    from data_modules.config import DataModulesConfig
    from data_modules.memory_contract_adapter import MemoryContractAdapter
    from data_modules.memory.schema import MemoryItem
    from data_modules.memory.store import ScratchpadManager

    _make_accepted_intent_commit(tmp_path, 1, [
        {"event_id": "loop-a", "event_type": "open_loop_created", "chapter": 1, "subject": "谜团", "payload": {"content": "相同谜团"}},
        {"event_id": "amb-a", "event_type": "open_loop_created", "chapter": 1, "subject": "谜团", "payload": {"content": "歧义谜团"}},
        {"event_id": "promise-a", "event_type": "promise_created", "chapter": 1, "subject": "守护村庄", "payload": {"content": "守护村庄", "promise_id": "planned-promise-a"}},
    ])
    _make_accepted_intent_commit(tmp_path, 2, [
        {"event_id": "loop-b", "event_type": "open_loop_created", "chapter": 2, "subject": "谜团", "payload": {"content": "相同谜团"}},
        {"event_id": "amb-b", "event_type": "open_loop_created", "chapter": 2, "subject": "谜团", "payload": {"content": "歧义谜团"}},
        {"event_id": "close-b", "event_type": "open_loop_closed", "chapter": 2, "subject": "谜团已解", "payload": {"content": "谜团已解", "loop_id": "loop-b"}},
        {"event_id": "paid-a", "event_type": "promise_paid_off", "chapter": 2, "subject": "守护村庄", "payload": {"content": "约定已兑现", "source_event_id": "promise-a"}},
    ])
    _make_accepted_intent_commit(tmp_path, 3, [
        {"event_id": "close-amb", "event_type": "open_loop_closed", "chapter": 3, "subject": "歧义谜团", "payload": {"content": "歧义谜团"}},
        {"event_id": "paid-only", "event_type": "promise_paid_off", "chapter": 3, "subject": "无来源约定", "payload": {"content": "无来源约定", "promise_id": "missing-promise"}},
    ])

    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "project_info": {"promise_ledger": [{"id": "planned-promise-a", "status": "pending"}]},
        "plot_threads": {"foreshadowing": [{"content": "相同谜团", "status": "active", "planted_chapter": 1}]},
    }), encoding="utf-8")
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    store = ScratchpadManager(cfg)
    store.upsert_item(MemoryItem(
        id="old-loop-a", layer="semantic", category="open_loop", subject="相同谜团",
        field="status", value="相同谜团", status="active", source_chapter=1,
        payload={"planted_chapter": 1, "status": "active"},
        evidence=["memory_facts:open_loop:1", "manual:keep"],
    ))
    store.upsert_item(MemoryItem(
        id="old-promise-a", layer="semantic", category="reader_promise", subject="守护村庄",
        field="promise", value="守护村庄", status="active", source_chapter=1,
        evidence=["memory_facts:reader_promise:1", "manual:keep-promise"],
    ))

    commits_dir = tmp_path / ".story-system" / "commits"
    canon_before = {path.name: path.read_bytes() for path in sorted(commits_dir.glob("chapter_*.json"))}
    # A stale diagnostics row must be replaced as part of the same owned projection lifecycle.
    diagnostics_path = tmp_path / ".story-system" / "projections" / "intent-diagnostics.json"
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_path.write_text(json.dumps({"schema_version": "intent-diagnostics/v1", "diagnostics": [{"event_id": "stale"}]}), encoding="utf-8")

    first = rebuild_projections(tmp_path)
    first_state = json.loads(state_path.read_text(encoding="utf-8"))
    first_rows = store.query(category="open_loop", status=None)
    first_promises = store.query(category="reader_promise", status=None)
    first_diagnostics = diagnostics_path.read_bytes()
    second = rebuild_projections(tmp_path)

    state_rows = first_state["plot_threads"]["foreshadowing"]
    state_by_id = {row.get("loop_id"): row for row in state_rows if row.get("loop_id")}
    assert first["ok"] is True and second["ok"] is True
    assert state_by_id["loop-a"]["status"] == "active"
    assert state_by_id["loop-b"]["status"] == "resolved"
    assert state_by_id["loop-b"]["resolution_event_id"] == "close-b"
    assert state_by_id["amb-a"]["status"] == state_by_id["amb-b"]["status"] == "active"
    active_loop_ids = {row.payload.get("loop_id") for row in store.query(category="open_loop", status="active")}
    assert active_loop_ids == {"loop-a", "amb-a", "amb-b"}
    context_loops = MemoryContractAdapter(cfg).get_open_loops(status="active")
    assert len(context_loops) == 3
    assert sum(loop.content == "相同谜团" for loop in context_loops) == 1
    same_content_rows = [row for row in first_rows if row.subject == "相同谜团"]
    assert {row.payload.get("loop_id") for row in same_content_rows} == {"loop-a", "loop-b"}
    assert len([row for row in same_content_rows if row.status == "active"]) == 1
    assert "manual:keep" in next(row for row in first_rows if row.payload.get("loop_id") == "loop-a").evidence
    assert len(first_promises) == 1
    assert first_promises[0].payload["promise_event_id"] == "promise-a"
    assert first_promises[0].status == "outdated"
    assert first_promises[0].payload["resolution_event_id"] == "paid-a"
    assert store.query(category="reader_promise", status="active") == []
    assert json.loads(state_path.read_text(encoding="utf-8"))["project_info"]["promise_ledger"] == [{"id": "planned-promise-a", "status": "pending"}]
    diagnostics = json.loads(first_diagnostics)
    assert {row["reason"] for row in diagnostics["diagnostics"]} == {"ambiguous_legacy_close", "unlinked_payoff"}
    assert diagnostics_path.read_bytes() == first_diagnostics
    assert {path.name: path.read_bytes() for path in sorted(commits_dir.glob("chapter_*.json"))} == canon_before


def test_rebuild_upgrades_legacy_reader_promise_memory_without_duplicate_active_rows(tmp_path):
    from data_modules.config import DataModulesConfig
    from data_modules.memory.schema import MemoryItem
    from data_modules.memory.store import ScratchpadManager

    _make_accepted_promise_commit(tmp_path, 1, "promise_created", "promise-a", "守护村庄", {"type": "protection"})
    _make_accepted_promise_commit(tmp_path, 2, "promise_paid_off", "paid-a", "守护村庄", {"source_event_id": "promise-a"})
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    store = ScratchpadManager(cfg)
    store.upsert_item(MemoryItem(
        id="old-reader-promise", layer="semantic", category="reader_promise",
        subject="守护村庄", field="promise", value="守护村庄", status="active",
        source_chapter=1, evidence=["memory_facts:reader_promise:1", "manual:review"],
    ))

    report = rebuild_projections(tmp_path)

    rows = store.query(category="reader_promise", status=None)
    assert report["ok"] is True
    assert len(rows) == 1
    assert rows[0].payload["promise_event_id"] == "promise-a"
    assert rows[0].payload["resolution_event_id"] == "paid-a"
    assert "manual:review" in rows[0].evidence
    assert rows[0].status == "outdated"
    assert store.query(category="reader_promise", status="active") == []
