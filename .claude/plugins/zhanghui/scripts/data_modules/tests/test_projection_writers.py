#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sqlite3
from pathlib import Path

import pytest

from data_modules.tests.commit_helpers import build_commit_with_reconciliation
from data_modules.chapter_commit_service import ChapterCommitService
from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager
from data_modules.memory.store import ScratchpadManager
from data_modules.index_projection_writer import IndexProjectionWriter
from data_modules.memory_projection_writer import MemoryProjectionWriter
from data_modules.state_projection_writer import StateProjectionWriter
from data_modules.summary_projection_writer import SummaryProjectionWriter
from data_modules.vector_projection_writer import VectorProjectionWriter


def _commit_payload(*, chapter=3, status="accepted", **extraction):
    extraction_payload = {
        "accepted_events": [],
        "state_deltas": [],
        "entity_deltas": [],
        "entities_appeared": [],
        "scenes": [],
        "chapter_meta": {},
        "dominant_strand": "",
        "summary_text": "",
    }
    extraction_payload.update(extraction)
    return {
        "meta": {
            "schema_version": "story-system/v1",
            "status": status,
            "chapter": chapter,
        },
        "provenance": {"write_fact_role": "chapter_commit"},
        "review_result": {"blocking_count": 1 if status == "rejected" else 0},
        "fulfillment_result": {
            "planned_nodes": [],
            "covered_nodes": [],
            "missed_nodes": ["test rejection"] if status == "rejected" else [],
            "extra_nodes": [],
        },
        "disambiguation_result": {
            "pending": ["test rejection"] if status == "rejected" else [],
        },
        "extraction_result": extraction_payload,
    }


def _persist_payload(project_root, payload):
    commit_path = project_root / ".story-system" / "commits" / (
        f"chapter_{int(payload['meta']['chapter']):03d}.commit.json"
    )
    commit_path.parent.mkdir(parents=True, exist_ok=True)
    commit_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return commit_path


def _initialize_story_system(project_root):
    story_root = project_root / ".story-system"
    story_root.mkdir(parents=True, exist_ok=True)
    (story_root / "MASTER_SETTING.json").write_text("{}", encoding="utf-8")


def _apply_with_durable_payload(writer, project_root, payload):
    _persist_payload(project_root, payload)
    return writer.apply(payload)


@pytest.fixture(autouse=True)
def stage_test_payloads_as_durable_commits(monkeypatch, tmp_path, request):
    """Most tests here cover projection output; attack tests must retain no-commit input."""
    attack_tests = {
        "test_state_projection_rejects_fake_payload_before_state_write",
        "test_index_projection_rejects_fake_payload_before_index_write",
        "test_projection_writers_reject_mismatched_payload_before_side_effects",
        "test_summary_memory_and_vector_writers_reject_payload_without_commit",
    }
    if request.node.name in attack_tests:
        return

    for writer_class in (
        IndexProjectionWriter,
        MemoryProjectionWriter,
        StateProjectionWriter,
        SummaryProjectionWriter,
        VectorProjectionWriter,
    ):
        original_apply = writer_class.apply

        def apply_after_staging(writer, payload, original_apply=original_apply):
            path = tmp_path / ".story-system" / "commits" / (
                f"chapter_{int(payload['meta']['chapter']):03d}.commit.json"
            )
            if not path.exists():
                _persist_payload(tmp_path, payload)
            return original_apply(writer, payload)

        monkeypatch.setattr(writer_class, "apply", apply_after_staging)


def test_state_projection_rejects_fake_payload_before_state_write(tmp_path):
    _initialize_story_system(tmp_path)
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text('{"sentinel":true}', encoding="utf-8")
    before = state_path.read_bytes()
    with pytest.raises(RuntimeError, match="Durable chapter commit is missing"):
        StateProjectionWriter(tmp_path).apply(
            _commit_payload(state_deltas=[{"entity_id": "hero", "field": "realm", "new": "B"}])
        )

    assert state_path.read_bytes() == before


def test_index_projection_rejects_fake_payload_before_index_write(tmp_path):
    _initialize_story_system(tmp_path)
    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    index = IndexManager(config)
    with pytest.raises(RuntimeError, match="Durable chapter commit is missing"):
        IndexProjectionWriter(tmp_path).apply(
            _commit_payload(entity_deltas=[{
                "entity_id": "hero", "canonical_name": "主角", "type": "角色",
                "current": {"realm": "B"}, "chapter": 3,
            }])
        )

    assert index.get_entity("hero") is None
    assert index.get_chapter(3) is None


def test_projection_rejects_corrupt_durable_commit_before_state_write(tmp_path):
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text('{"sentinel":true}', encoding="utf-8")
    before = state_path.read_bytes()
    commit_path = tmp_path / ".story-system" / "commits" / "chapter_003.commit.json"
    commit_path.parent.mkdir(parents=True)
    commit_path.write_text("{truncated", encoding="utf-8")

    with pytest.raises(RuntimeError, match="cannot be read"):
        StateProjectionWriter(tmp_path).apply(_commit_payload())

    assert state_path.read_bytes() == before


def test_projection_writers_reject_mismatched_payload_before_side_effects(tmp_path, monkeypatch):
    _initialize_story_system(tmp_path)
    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    index = IndexManager(config)
    state_path = config.state_file
    state_path.write_text('{"sentinel":true}', encoding="utf-8")
    before_state = state_path.read_bytes()
    durable = _commit_payload(
        summary_text="canonical summary",
        entity_deltas=[{"entity_id": "hero", "canonical_name": "主角", "type": "角色", "current": {"realm": "A"}}],
        accepted_events=[{"event_id": "evt-a", "event_type": "open_loop_created", "subject": "A", "payload": {"content": "A"}}],
    )
    _persist_payload(tmp_path, durable)
    mismatched = json.loads(json.dumps(durable))
    mismatched["extraction_result"]["state_deltas"] = [
        {"entity_id": "hero", "field": "realm", "new": "B"}
    ]

    class ForbiddenMemoryWrite:
        @staticmethod
        def apply_commit_projection(*args, **kwargs):
            raise AssertionError("memory side effect happened before provenance validation")

    vector_calls = []
    monkeypatch.setattr("data_modules.memory_projection_writer.MemoryWriter", ForbiddenMemoryWrite)
    monkeypatch.setattr(VectorProjectionWriter, "_store_chunks", lambda self, chunks: vector_calls.append(chunks))

    for writer in (
        StateProjectionWriter(tmp_path),
        IndexProjectionWriter(tmp_path),
        SummaryProjectionWriter(tmp_path),
        MemoryProjectionWriter(tmp_path),
        VectorProjectionWriter(tmp_path),
    ):
        with pytest.raises(RuntimeError, match="does not match durable chapter commit"):
            writer.apply(mismatched)

    assert state_path.read_bytes() == before_state
    assert index.get_entity("hero") is None
    assert not (tmp_path / ".webnovel" / "summaries" / "ch0003.md").exists()
    assert vector_calls == []


def test_summary_memory_and_vector_writers_reject_payload_without_commit(tmp_path, monkeypatch):
    _initialize_story_system(tmp_path)
    payload = _commit_payload(
        summary_text="not durable",
        accepted_events=[{"event_type": "open_loop_created", "subject": "fake", "payload": {"content": "fake"}}],
    )
    memory_calls = []
    vector_calls = []

    class MemorySideEffect:
        def __init__(self, config):
            pass

        def apply_commit_projection(self, commit_payload):
            memory_calls.append(commit_payload)
            return {"items_added": 1}

    monkeypatch.setattr("data_modules.memory_projection_writer.MemoryWriter", MemorySideEffect)
    monkeypatch.setattr(VectorProjectionWriter, "_store_chunks", lambda self, chunks: vector_calls.append(chunks))

    for writer in (
        SummaryProjectionWriter(tmp_path),
        MemoryProjectionWriter(tmp_path),
        VectorProjectionWriter(tmp_path),
    ):
        with pytest.raises(RuntimeError, match="Durable chapter commit is missing"):
            writer.apply(payload)

    assert not (tmp_path / ".webnovel" / "summaries" / "ch0003.md").exists()
    assert memory_calls == []
    assert vector_calls == []

    from data_modules.memory.writer import MemoryWriter
    from data_modules.summary_projection_writer import append_summary_projection

    with pytest.raises(RuntimeError, match="Durable chapter commit is missing"):
        MemoryWriter(DataModulesConfig.from_project_root(tmp_path)).apply_commit_projection(payload)
    with pytest.raises(RuntimeError, match="Durable chapter commit is missing"):
        append_summary_projection(tmp_path, payload)


def test_projection_writers_accept_matching_durable_payload_and_ignore_projection_status(tmp_path):
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{}", encoding="utf-8")
    payload = _commit_payload(
        state_deltas=[{"entity_id": "hero", "field": "realm", "new": "B"}],
        entity_deltas=[{"entity_id": "hero", "canonical_name": "主角", "type": "角色", "current": {"realm": "B"}}],
        summary_text="matching durable summary",
    )
    payload_with_legacy_status = json.loads(json.dumps(payload))
    payload_with_legacy_status["projection_status"] = {"state": "failed:old"}
    commit_path = _persist_payload(tmp_path, payload_with_legacy_status)
    before_commit = commit_path.read_bytes()

    result = StateProjectionWriter(tmp_path).apply(payload)
    summary = SummaryProjectionWriter(tmp_path).apply(payload)
    index_result = IndexProjectionWriter(tmp_path).apply(payload)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert result["applied"] is True
    assert state["entity_state"]["hero"]["realm"] == "B"
    assert summary["applied"] is True
    assert index_result["applied"] is True
    assert IndexManager(DataModulesConfig.from_project_root(tmp_path)).get_entity("hero")["current_json"]["realm"] == "B"
    assert commit_path.read_bytes() == before_commit
def test_state_projection_writer_handles_rejected_commit(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    writer = StateProjectionWriter(tmp_path)
    result = writer.apply(_commit_payload(status="rejected"))
    assert result["applied"] is True
    state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["progress"]["chapter_status"]["3"] == "chapter_rejected"


def test_state_projection_writer_applies_accepted_commit(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    writer = StateProjectionWriter(tmp_path)
    result = writer.apply(
        _commit_payload(state_deltas=[{"entity_id": "x", "field": "realm", "new": "斗者"}])
    )
    assert result["applied"] is True
    payload = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert payload["entity_state"]["x"]["realm"] == "斗者"
    assert payload["progress"]["chapter_status"]["3"] == "chapter_committed"
    assert payload["progress"]["current_chapter"] == 3
    assert payload["progress"]["last_updated"]


def test_state_projection_writer_rejects_out_of_order_retry(tmp_path):
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"progress": {"current_chapter": 12}}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Out-of-order state projection refused"):
        StateProjectionWriter(tmp_path).apply(_commit_payload(chapter=11))

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["progress"]["current_chapter"] == 12


def test_legacy_chapter_index_writer_rejects_story_system_project(tmp_path):
    from data_modules.config import DataModulesConfig

    story_root = tmp_path / ".story-system"
    story_root.mkdir()
    (story_root / "MASTER_SETTING.json").write_text("{}", encoding="utf-8")
    manager = IndexManager(DataModulesConfig.from_project_root(tmp_path))

    with pytest.raises(RuntimeError, match="chapter facts must originate from durable CHAPTER_COMMIT projections"):
        manager.process_chapter_data(1, "标题", "地点", 100, [], [])


def test_accepted_chapter_commits_advance_progress_and_word_count(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps(
            {"progress": {"current_chapter": 0, "total_words": 0, "last_updated": "2026-01-01 00:00:00"}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    chapters_dir = tmp_path / "正文"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (chapters_dir / "第0001章.md").write_text("第一章正文内容", encoding="utf-8")
    (chapters_dir / "第0002章.md").write_text("第二章正文内容更多", encoding="utf-8")

    service = ChapterCommitService(tmp_path)
    for chapter in (1, 2):
        payload = build_commit_with_reconciliation(service,
            chapter=chapter,
            review_result={"blocking_count": 0},
            fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
            disambiguation_result={"pending": []},
            extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
        )
        service.apply_projections(payload)

    state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["progress"]["chapter_status"]["1"] == "chapter_committed"
    assert state["progress"]["chapter_status"]["2"] == "chapter_committed"
    assert state["progress"]["current_chapter"] == 2
    assert state["progress"]["total_words"] > 0
    assert state["progress"]["last_updated"] != "2026-01-01 00:00:00"


def test_reapplying_accepted_chapter_commit_does_not_double_count_words(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps(
            {"progress": {"current_chapter": 0, "total_words": 0}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    chapters_dir = tmp_path / "正文"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (chapters_dir / "第0001章.md").write_text("第一章正文内容", encoding="utf-8")

    payload = _commit_payload(chapter=1)
    writer = StateProjectionWriter(tmp_path)
    writer.apply(payload)
    first_state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))

    writer.apply(payload)
    second_state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))

    assert second_state["progress"]["current_chapter"] == 1
    assert second_state["progress"]["total_words"] == first_state["progress"]["total_words"]
    assert second_state["progress"]["last_updated"] == first_state["progress"]["last_updated"]


def test_state_projection_writer_derives_delta_from_power_breakthrough_event(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    writer = StateProjectionWriter(tmp_path)
    result = writer.apply(
        _commit_payload(
            accepted_events=[
                {
                    "event_id": "evt-001",
                    "chapter": 3,
                    "event_type": "power_breakthrough",
                    "subject": "xiaoyan",
                    "payload": {"from": "斗者", "to": "斗师"},
                }
            ],
        )
    )

    payload = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert result["applied"] is True
    assert payload["entity_state"]["xiaoyan"]["realm"] == "斗师"


def test_state_projection_writer_updates_strand_tracker(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    writer = StateProjectionWriter(tmp_path)

    writer.apply(
        _commit_payload(chapter=3, dominant_strand="quest")
    )
    writer.apply(
        _commit_payload(chapter=4, dominant_strand="quest")
    )

    payload = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    tracker = payload["strand_tracker"]
    assert tracker["current_dominant"] == "quest"
    assert tracker["last_quest_chapter"] == 4
    assert tracker["chapters_since_switch"] == 2
    assert len(tracker["history"]) == 2


def test_state_projection_writer_rejects_changed_payload_for_same_chapter(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    writer = StateProjectionWriter(tmp_path)

    original = _commit_payload(chapter=3, dominant_strand="quest")
    _apply_with_durable_payload(writer, tmp_path, original)
    commit_path = tmp_path / ".story-system" / "commits" / "chapter_003.commit.json"
    before_commit = commit_path.read_bytes()

    with pytest.raises(RuntimeError, match="does not match durable chapter commit"):
        writer.apply(_commit_payload(chapter=3, dominant_strand="fire"))

    payload = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    tracker = payload["strand_tracker"]
    assert tracker["current_dominant"] == "quest"
    assert tracker["last_quest_chapter"] == 3
    assert tracker["last_fire_chapter"] == 0
    assert tracker["history"] == [{"chapter": 3, "dominant": "quest"}]
    assert commit_path.read_bytes() == before_commit


def test_accepted_commit_updates_state_json_end_to_end(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")

    service = ChapterCommitService(tmp_path)
    commit_payload = build_commit_with_reconciliation(service,
        chapter=3,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": ["发现陷阱"], "covered_nodes": ["发现陷阱"], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [{"entity_id": "x", "field": "realm", "new": "斗者"}], "entity_deltas": [], "accepted_events": []},
    )

    StateProjectionWriter(tmp_path).apply(commit_payload)
    payload = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert payload["entity_state"]["x"]["realm"] == "斗者"


def test_index_projection_writer_applies_entity_delta(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = IndexProjectionWriter(tmp_path)

    result = writer.apply(
        _commit_payload(
            entity_deltas=[
                {
                    "entity_id": "xiaoyan",
                    "canonical_name": "萧炎",
                    "type": "角色",
                    "current": {"realm": "斗者"},
                    "chapter": 3,
                }
            ],
        )
    )

    entity = IndexManager(cfg).get_entity("xiaoyan")
    assert result["applied"] is True
    assert entity["canonical_name"] == "萧炎"
    assert entity["current_json"]["realm"] == "斗者"


def test_index_projection_writer_registers_stable_protagonist_aliases(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = IndexProjectionWriter(tmp_path)

    result = writer.apply(
        _commit_payload(
            chapter=1,
            entity_deltas=[
                {
                    "entity_id": "lu_ming",
                    "canonical_name": "陆鸣",
                    "type": "角色",
                    "tier": "核心",
                    "chapter": 1,
                    "is_protagonist": True,
                }
            ],
        )
    )

    manager = IndexManager(cfg)
    assert result["applied"] is True
    assert manager.get_entity("lu_ming")["canonical_name"] == "陆鸣"
    assert manager.get_entity("陆鸣")["id"] == "lu_ming"
    assert manager.get_entity("protagonist")["id"] == "lu_ming"
    assert manager.get_entity("luming")["id"] == "lu_ming"


def test_entity_delta_without_protagonist_flag_preserves_existing_protagonist(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    manager = IndexManager(cfg)
    manager.apply_entity_delta(
        {
            "entity_id": "lu_ming",
            "canonical_name": "陆鸣",
            "type": "角色",
            "tier": "核心",
            "chapter": 1,
            "is_protagonist": True,
        }
    )

    manager.apply_entity_delta(
        {
            "entity_id": "lu_ming",
            "canonical_name": "陆鸣",
            "type": "角色",
            "tier": "核心",
            "chapter": 2,
            "field": "realm",
            "new": "炼气二层",
        }
    )

    assert manager.get_protagonist()["id"] == "lu_ming"
    assert manager.get_entity("protagonist")["id"] == "lu_ming"
    assert manager.get_entity("lu_ming")["is_protagonist"] == 1


def test_index_projection_writer_derives_relationship_from_event(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = IndexProjectionWriter(tmp_path)

    result = writer.apply(
        _commit_payload(
            accepted_events=[
                {
                    "event_id": "evt-001",
                    "chapter": 3,
                    "event_type": "relationship_changed",
                    "subject": "xiaoyan",
                    "payload": {
                        "to_entity": "yaolao",
                        "relationship_type": "师徒",
                        "description": "关系正式确立",
                    },
                }
            ],
        )
    )

    rels = IndexManager(cfg).get_relationship_between("xiaoyan", "yaolao")
    assert result["applied"] is True
    assert rels[0]["type"] == "师徒"


def test_index_projection_writer_derives_artifact_entity_from_event(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = IndexProjectionWriter(tmp_path)

    result = writer.apply(
        _commit_payload(
            accepted_events=[
                {
                    "event_id": "evt-002",
                    "chapter": 3,
                    "event_type": "artifact_obtained",
                    "subject": "黑戒",
                    "payload": {
                        "artifact_id": "black_ring",
                        "name": "黑戒",
                        "owner": "xiaoyan",
                    },
                }
            ],
        )
    )

    entity = IndexManager(cfg).get_entity("black_ring")
    assert result["applied"] is True
    assert entity["canonical_name"] == "黑戒"
    assert entity["current_json"]["holder"] == "xiaoyan"


def test_accepted_commit_writes_chapter_index_tables(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    chapters_dir = tmp_path / "正文"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (chapters_dir / "第0003章.md").write_text("第三章正文内容", encoding="utf-8")

    service = ChapterCommitService(tmp_path)
    payload = build_commit_with_reconciliation(service,
        chapter=3,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={
            "summary_text": "本章摘要",
            "state_deltas": [{"entity_id": "xiaoyan", "field": "realm", "old": "斗者", "new": "斗师"}],
            "entity_deltas": [],
            "entities_appeared": [{"id": "xiaoyan", "mentions": ["萧炎"], "confidence": 0.95}],
            "scenes": [
                {
                    "index": 1,
                    "start_line": 1,
                    "end_line": 12,
                    "location": "山门",
                    "summary": "萧炎完成突破",
                    "characters": ["xiaoyan"],
                }
            ],
            "accepted_events": [],
        },
    )

    result = service.apply_projections(payload)
    manager = IndexManager(cfg)

    assert result["projection_status"]["index"] == "done"
    assert manager.get_chapter(3)["summary"] == "本章摘要"
    assert manager.get_chapter_appearances(3)[0]["entity_id"] == "xiaoyan"
    assert manager.get_scenes(3)[0]["location"] == "山门"
    changes = manager.get_chapter_state_changes(3)
    assert len(changes) == 1
    assert changes[0]["entity_id"] == "xiaoyan"
    assert changes[0]["field"] == "realm"


def test_index_projection_writer_is_idempotent_for_replay(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    chapters_dir = tmp_path / "正文"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (chapters_dir / "第0003章.md").write_text("第三章正文内容", encoding="utf-8")

    service = ChapterCommitService(tmp_path)
    payload = build_commit_with_reconciliation(service,
        chapter=3,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={
            "summary_text": "本章摘要",
            "state_deltas": [{"entity_id": "xiaoyan", "field": "realm", "old": "斗者", "new": "斗师"}],
            "entity_deltas": [
                {
                    "entity_id": "xiaoyan",
                    "canonical_name": "萧炎",
                    "entity_type": "角色",
                    "tier": "核心",
                }
            ],
            "entities_appeared": [{"id": "xiaoyan", "mentions": ["萧炎"], "confidence": 0.95}],
            "scenes": [
                {
                    "index": 1,
                    "start_line": 1,
                    "end_line": 12,
                    "location": "山门",
                    "summary": "萧炎完成突破",
                    "characters": ["xiaoyan"],
                }
            ],
            "accepted_events": [],
        },
    )

    writer = IndexProjectionWriter(tmp_path)
    writer.apply(payload)
    writer.apply(payload)

    manager = IndexManager(cfg)
    assert manager.get_chapter(3)["summary"] == "本章摘要"
    assert len(manager.get_chapter_appearances(3)) == 1
    assert len(manager.get_scenes(3)) == 1
    assert len(manager.get_chapter_state_changes(3)) == 1
    assert manager.get_entity("xiaoyan")["canonical_name"] == "萧炎"


def test_index_projection_writer_records_state_change_from_event(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = IndexProjectionWriter(tmp_path)

    result = writer.apply(
        _commit_payload(
            accepted_events=[
                {
                    "event_id": "evt-001",
                    "chapter": 3,
                    "event_type": "character_state_changed",
                    "subject": "xiaoyan",
                    "payload": {"field": "mood", "old": "躁动", "new": "冷静"},
                }
            ],
        )
    )

    changes = IndexManager(cfg).get_chapter_state_changes(3)
    assert result["state_changes"] == 1
    assert len(changes) == 1
    assert changes[0]["entity_id"] == "xiaoyan"
    assert changes[0]["field"] == "mood"


def test_summary_projection_writer_writes_summary_markdown(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = SummaryProjectionWriter(tmp_path)

    result = writer.apply(
        _commit_payload(summary_text="本章主角发现陷阱并决定隐忍。")
    )

    summary_path = tmp_path / ".webnovel" / "summaries" / "ch0003.md"
    assert result["applied"] is True
    assert summary_path.is_file()
    assert "剧情摘要" in summary_path.read_text(encoding="utf-8")


def test_summary_projection_writer_replay_overwrites_not_appends(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = SummaryProjectionWriter(tmp_path)
    payload = _commit_payload(summary_text="本章主角发现陷阱并决定隐忍。")

    writer.apply(payload)
    writer.apply(payload)

    summary_path = tmp_path / ".webnovel" / "summaries" / "ch0003.md"
    text = summary_path.read_text(encoding="utf-8")
    assert text.count("本章主角发现陷阱并决定隐忍。") == 1


def test_memory_projection_writer_maps_commit_into_scratchpad(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = MemoryProjectionWriter(tmp_path)

    result = writer.apply(
        _commit_payload(
            state_deltas=[
                {"entity_id": "xiaoyan", "field": "realm", "old": "斗者", "new": "斗师"}
            ],
        )
    )

    store = ScratchpadManager(cfg)
    chars = store.query(category="character_state", status="active")
    assert result["applied"] is True
    assert any(x.subject == "xiaoyan" and x.field == "realm" for x in chars)


def test_memory_projection_writer_is_idempotent_for_replay(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = MemoryProjectionWriter(tmp_path)
    payload = _commit_payload(
        state_deltas=[
            {"entity_id": "xiaoyan", "field": "realm", "old": "斗者", "new": "斗师"}
        ],
    )

    writer.apply(payload)
    writer.apply(payload)

    store = ScratchpadManager(cfg)
    chars = [
        item
        for item in store.query(category="character_state", subject="xiaoyan", status=None)
        if item.field == "realm" and item.source_chapter == 3
    ]
    assert len(chars) == 1


def test_vector_projection_writer_is_idempotent_for_replay(tmp_path, monkeypatch):
    import data_modules.rag_adapter as rag_module

    class StubClient:
        async def embed_batch(self, texts, skip_failures=True):
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(rag_module, "get_client", lambda config: StubClient())
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = VectorProjectionWriter(tmp_path)
    payload = _commit_payload(
        summary_text="本章主角发现陷阱并决定隐忍。",
        entity_deltas=[
            {
                "entity_id": "xiaoyan",
                "canonical_name": "萧炎",
                "type": "角色",
                "chapter": 3,
            }
        ],
        accepted_events=[
            {
                "event_id": "evt-power-3",
                "chapter": 3,
                "event_type": "power_breakthrough",
                "subject": "xiaoyan",
                "payload": {"to": "斗师"},
            }
        ],
        scenes=[
            {
                "index": 1,
                "location": "山门",
                "summary": "萧炎完成突破",
            }
        ],
    )

    writer.apply(payload)
    writer.apply(payload)

    with sqlite3.connect(cfg.vector_db) as conn:
        vector_count = conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
        bm25_chunk_count = conn.execute("SELECT COUNT(DISTINCT chunk_id) FROM bm25_index").fetchone()[0]
        doc_count = conn.execute("SELECT COUNT(*) FROM doc_stats").fetchone()[0]

    assert vector_count == 4
    assert bm25_chunk_count == 4
    assert doc_count == 4


def test_memory_projection_writer_maps_open_loop_event_into_scratchpad(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    writer = MemoryProjectionWriter(tmp_path)

    result = writer.apply(
        _commit_payload(
            accepted_events=[
                {
                    "event_id": "evt-001",
                    "chapter": 3,
                    "event_type": "open_loop_created",
                    "subject": "三年之约",
                    "payload": {"content": "三年之约"},
                }
            ],
        )
    )

    store = ScratchpadManager(cfg)
    loops = store.query(category="open_loop", status="active")
    assert result["applied"] is True
    assert any("三年之约" in x.subject for x in loops)


def _loop_event(event_type, content, chapter=None, event_id=None, **payload_extra):
    payload = {"content": content}
    payload.update(payload_extra)
    event = {"event_type": event_type, "subject": "narrator", "payload": payload}
    if event_id:
        event["event_id"] = event_id
    if chapter is not None:
        event["chapter"] = chapter
    return event


def _read_state(tmp_path):
    return json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))


def test_state_writer_aggregates_foreshadowing_from_open_loop_events(tmp_path):
    """issue #130：open_loop 事件必须聚合进 plot_threads.foreshadowing。"""
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    writer = StateProjectionWriter(tmp_path)

    writer.apply(
        _commit_payload(
            chapter=5,
            accepted_events=[
                _loop_event("open_loop_created", "三年之约提及", event_id="loop-create", target_chapter=30, tier="major")
            ],
        )
    )
    rows = _read_state(tmp_path)["plot_threads"]["foreshadowing"]
    assert len(rows) == 1
    row = rows[0]
    assert row["content"] == "三年之约提及"
    assert row["status"] == "active"
    assert row["planted_chapter"] == 5
    assert row["target_chapter"] == 30
    assert row["tier"] == "major"

    writer.apply(
        _commit_payload(
            chapter=28,
            accepted_events=[_loop_event("open_loop_closed", "三年之约提及", event_id="loop-close", loop_id="loop-create")],
        )
    )
    rows = _read_state(tmp_path)["plot_threads"]["foreshadowing"]
    assert len(rows) == 1
    assert rows[0]["status"] == "resolved"
    assert rows[0]["resolved_chapter"] == 28
    assert rows[0]["planted_chapter"] == 5


def test_state_writer_foreshadowing_replay_is_idempotent(tmp_path):
    """projections replay 重放同章不得产生重复伏笔条目。"""
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    writer = StateProjectionWriter(tmp_path)
    payload = _commit_payload(
        chapter=7,
        accepted_events=[_loop_event("open_loop_created", "黑色棺材的来历", event_id="loop-replay")],
    )
    writer.apply(payload)
    writer.apply(payload)
    rows = _read_state(tmp_path)["plot_threads"]["foreshadowing"]
    assert len(rows) == 1
    assert rows[0]["planted_chapter"] == 7


def test_state_writer_foreshadowing_orphan_close_does_not_fabricate_loop(tmp_path):
    """Orphan close must be diagnosed elsewhere and must not fabricate a resolved State row."""
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    writer = StateProjectionWriter(tmp_path)
    writer.apply(
        _commit_payload(
            chapter=9,
            accepted_events=[_loop_event("open_loop_closed", "从未登记过的旧约", event_id="loop-orphan")],
        )
    )
    rows = _read_state(tmp_path)["plot_threads"]["foreshadowing"]
    assert rows == []


def test_state_writer_keeps_identical_content_loops_distinct_and_closes_by_id(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    writer = StateProjectionWriter(tmp_path)
    writer.apply(_commit_payload(chapter=1, accepted_events=[_loop_event("open_loop_created", "同一句", event_id="loop-a")]))
    writer.apply(_commit_payload(chapter=2, accepted_events=[_loop_event("open_loop_created", "同一句", event_id="loop-b")]))
    writer.apply(_commit_payload(chapter=3, accepted_events=[_loop_event("open_loop_closed", "改写后的表述", event_id="close-b", loop_id="loop-b")]))
    rows = _read_state(tmp_path)["plot_threads"]["foreshadowing"]
    assert [(row["loop_id"], row["status"]) for row in rows] == [("loop-a", "active"), ("loop-b", "resolved")]
    assert rows[1]["resolution_event_id"] == "close-b"


def test_router_routes_open_loop_events_to_state(tmp_path):
    """issue #130：open_loop 事件必须进 state 投影，否则伏笔无人聚合。"""
    from data_modules.event_projection_router import EventProjectionRouter

    router = EventProjectionRouter()
    assert "state" in router.route({"event_type": "open_loop_created"})
    assert "state" in router.route({"event_type": "open_loop_closed"})
