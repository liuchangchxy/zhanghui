import json
import asyncio
from types import SimpleNamespace

import pytest

from data_modules.effective_history import EffectiveHistoryStore
from data_modules.owned_project_view import (
    OwnedIndexView, OwnedMemoryView, OwnedProjectView, OwnedRAGView, OwnedStateStore, OwnedViewError,
    activation_health_report,
)
from data_modules.projection_generation import GenerationError, ProjectionGeneration
from data_modules.projection_rebuild import build_effective_generation
from data_modules.projections import _active_generation_recovery
from data_modules.rag_adapter import RAGAdapter, SearchResult
from data_modules.config import DataModulesConfig
from data_modules.state_manager import StateManager
from data_modules.index_manager import IndexManager
from data_modules.event_log_store import EventLogStore
from data_modules.memory.store import ScratchpadManager
from data_modules.memory.schema import MemoryItem, ScratchpadData
from data_modules.canon_correction_schema import base_commit_digest, effective_content_digest
from data_modules.canon_correction_store import append_correction_request


def _activate(root):
    commit = {
        "meta": {"schema_version": "story-system/v1", "chapter": 1, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": [],
                              "chapter_meta": {"title": "Canon title"}, "summary_text": "Canon summary"},
    }
    path = root / ".story-system/commits/chapter_001.commit.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(commit), encoding="utf-8")
    snapshot = EffectiveHistoryStore().read_active_snapshot(root)
    built = build_effective_generation(root, snapshot)
    protocol = ProjectionGeneration(root)
    record = protocol.publish_generation(built["validated_generation"], None,
                                         snapshot.correction_lineage_digest)
    return commit, snapshot, protocol.pin_active_generation(), record


def test_late_owner_write_is_visible_without_changing_pinned_canon(tmp_path):
    _commit, snapshot, pinned, publication = _activate(tmp_path)
    state = OwnedStateStore(tmp_path)
    before_digest = pinned.manifest["effective_history_digest"]
    assert state.read_view(pinned)["_view"]["owner_overlay_revision"] == 0
    assert state.write_owner_values({"story_craft": {"plan": "new owner value"},
                                     "progress.volumes_planned": ["Volume 1"]}) == 1
    view = state.read_view(pinned)
    assert view["story_craft"]["plan"] == "new owner value"
    assert view["progress"]["volumes_planned"] == ["Volume 1"]
    assert view["_view"]["generation_id"] == pinned.generation_id
    assert view["_view"]["owner_overlay_revision"] == 1
    assert pinned.manifest["effective_history_digest"] == before_digest
    assert ProjectionGeneration(tmp_path).pin_active_generation().publication_record_id == publication.publication_record_id


def test_owner_state_collision_and_unowned_path_fail_closed(tmp_path):
    _commit, _snapshot, pinned, _publication = _activate(tmp_path)
    state = OwnedStateStore(tmp_path)
    with pytest.raises(OwnedViewError, match="CANON_STATE_IS_IMMUTABLE"):
        state.write_owner_values({"entity_state": {"hero": {"hp": 0}}})
    with pytest.raises(OwnedViewError, match="UNOWNED_STATE_OVERLAY_PATH"):
        state.write_owner_values({"progress.current_chapter": 7})
    state.overlay_path.parent.mkdir(parents=True, exist_ok=True)
    state.overlay_path.write_text(json.dumps({"schema_version": "owner-state-overlay/v1", "revision": 1,
                                               "values": {"entity_state": {"hero": {"hp": 0}}}}))
    with pytest.raises(OwnedViewError, match="OWNER_CANON_STATE_COLLISION"):
        state.read_view(pinned)


def test_owned_index_routes_canon_reads_and_blocks_canon_writes(tmp_path):
    _commit, _snapshot, pinned, _publication = _activate(tmp_path)
    index = OwnedIndexView(tmp_path, pinned)
    rows = index.read_table("chapters")
    assert rows[0]["payload"]["title"] == "Canon title"
    with pytest.raises(OwnedViewError, match="CANON_INDEX_IS_IMMUTABLE"):
        index.write_owner_sql("INSERT INTO chapters(chapter) VALUES (?)", (2,))


def test_memory_and_rag_owner_results_cannot_claim_canon(tmp_path):
    _commit, _snapshot, pinned, _publication = _activate(tmp_path)
    with pytest.raises(OwnedViewError, match="OWNER_MEMORY_CANNOT_CLAIM_CANON"):
        OwnedMemoryView(pinned, [{"id": "x", "authority_claim": "CANON_AUTHORITY"}]).rows()
    with pytest.raises(OwnedViewError, match="OWNER_RAG_CANNOT_CLAIM_CANON"):
        OwnedRAGView(pinned, lambda _query: [{"id": "x", "authority_claim": "CANON_AUTHORITY"}]).search("x")
    results = OwnedRAGView(pinned, lambda _query: [{"id": "mutable", "score": 0.5}]).search("Canon")
    assert {row["authority_claim"] for row in results} == {"CANON_AUTHORITY", "OWNER_AUTHORITY"}


def test_candidate_request_append_does_not_change_operation_pin(tmp_path):
    commit, _snapshot, pinned, _publication = _activate(tmp_path)
    original = OwnedProjectView.pin_active(tmp_path)
    request = {
        "schema_version": "canon-correction-request/v1", "request_id": "TEST-ONLY-pending",
        "chapter": 1, "base_commit_sha256": base_commit_digest(commit),
        "parent_revision_id": f"base:{base_commit_digest(commit)}",
        "parent_effective_content_sha256": effective_content_digest("accepted", commit["extraction_result"]), "operation": "RETRACT",
        "proposed_effective_status": "retracted", "proposed_effective_extraction_result": None,
        "proposed_effective_content_sha256": effective_content_digest("retracted", None), "changed_paths": [],
        "proposer_provenance": {"fixture": "TEST ONLY"}, "reason": "TEST ONLY",
    }
    append_correction_request(tmp_path, request)
    assert original.canon_chapter(1)["generation_id"] == pinned.generation_id
    assert OwnedProjectView.pin_active(tmp_path).pinned.publication_record_id == pinned.publication_record_id


def test_active_evidence_corruption_blocks_runtime_view_without_fallback(tmp_path):
    _commit, _snapshot, pinned, _publication = _activate(tmp_path)
    commit_path = tmp_path / ".story-system/commits/chapter_001.commit.json"
    commit_path.write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(GenerationError, match="ACTIVE_DEPENDENCY_CORRUPT"):
        OwnedProjectView.pin_active(tmp_path)
    assert pinned.generation_root.is_dir()


def test_activation_recovery_replaces_only_generation_for_same_semantics(tmp_path):
    _commit, _snapshot, pinned, _publication = _activate(tmp_path)
    report = _active_generation_recovery(tmp_path, chapter=1)
    assert report["ok"] is True
    assert report["semantic_activation_id"] == pinned.semantic_activation_id
    assert report["generation_id"] != pinned.generation_id
    assert report["candidate_status"] == "not_considered"


def test_activation_health_reports_active_and_candidate_separately(tmp_path):
    _activate(tmp_path)
    report = activation_health_report(tmp_path)
    assert report["active_status"] == "valid"
    assert report["candidate_status"] == "pending_or_blocked"
    assert report["semantic_activation_id"].startswith("semantic-")
    assert report["generation_id"].startswith("generation-")


def test_rag_runtime_reads_pinned_canon_and_labels_legacy_owner_results(tmp_path):
    _activate(tmp_path)
    adapter = RAGAdapter.__new__(RAGAdapter)
    adapter.config = SimpleNamespace(project_root=tmp_path)
    adapter.bm25_search = lambda *_args, **_kwargs: [SearchResult(
        chunk_id="legacy", chapter=1, scene_index=0, content="mutable result", score=0.4,
        source="bm25", chunk_type="planning", source_file="owner",
    )]
    results = asyncio.run(adapter.search("Canon", top_k=5))
    assert any(row.chunk_id == "canon-chapter-1" for row in results)
    assert any(row.chunk_id == "legacy" for row in results)


def test_state_manager_reads_pinned_view_and_writes_workflow_overlay(tmp_path):
    _activate(tmp_path)
    state_path = tmp_path / ".webnovel/state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_bytes = b'{"legacy_snapshot":true}\n'
    state_path.write_bytes(legacy_bytes)
    manager = StateManager(DataModulesConfig.from_project_root(tmp_path), enable_sqlite_sync=False)
    assert manager.get_chapter_status(1) == "accepted"
    manager.set_chapter_status(2, "chapter_drafted")
    assert state_path.read_bytes() == legacy_bytes
    view = OwnedStateStore(tmp_path).read_view(OwnedProjectView.pin_active(tmp_path).pinned)
    assert view["progress"]["chapter_status"]["2"] == "chapter_drafted"


def test_state_manager_direct_canon_edit_is_rejected_after_enrollment(tmp_path):
    _activate(tmp_path)
    manager = StateManager(DataModulesConfig.from_project_root(tmp_path), enable_sqlite_sync=False)
    manager._state["protagonist_state"]["location"] = "forged"
    with pytest.raises(RuntimeError, match="Story System canonical mode"):
        manager._save_state()


def test_existing_index_and_event_readers_use_the_pinned_generation(tmp_path):
    _activate(tmp_path)
    config = DataModulesConfig.from_project_root(tmp_path)
    index = IndexManager(config)
    assert index.get_chapter(1)["title"] == "Canon title"
    assert EventLogStore(tmp_path).read_events(1) == []


def test_scratchpad_keeps_owner_writes_and_rejects_new_canon_owned_rows(tmp_path):
    _activate(tmp_path)
    store = ScratchpadManager(DataModulesConfig.from_project_root(tmp_path))
    data = ScratchpadData.empty()
    data.story_facts.append(MemoryItem(
        id="owner-row", layer="semantic", category="story_fact", subject="note",
        field="context", value="owner", evidence=["owner:fixture"],
    ))
    store.save(data)
    assert store.load().story_facts[0].value == "owner"
    data.story_facts.append(MemoryItem(
        id="canon-row", layer="semantic", category="story_fact", subject="fact",
        field="state", value="forged", evidence=["state_change:chapter:1"],
    ))
    with pytest.raises(RuntimeError, match="Canon memory rows are immutable"):
        store.save(data)
