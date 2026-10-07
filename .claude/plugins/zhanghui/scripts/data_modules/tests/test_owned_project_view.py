import json
import asyncio
import hashlib
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
from data_modules.state_projection_writer import StateProjectionWriter
from data_modules.context_manager import ContextManager


def _activate(root, *, summary="Canon summary"):
    commit = {
        "meta": {"schema_version": "story-system/v1", "chapter": 1, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": [],
                              "chapter_meta": {"title": "Canon title"}, "summary_text": summary},
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


def test_pinned_state_is_materialized_and_immutable_after_publication(tmp_path, monkeypatch):
    chapter = tmp_path / "正文" / "第0001章.md"
    chapter.parent.mkdir(parents=True, exist_ok=True)
    chapter.write_text("original chapter prose", encoding="utf-8")
    commit, _snapshot, pinned, _publication = _activate(tmp_path)
    state = OwnedStateStore(tmp_path)
    before = state.read_view(pinned)
    assert before["progress"]["total_words"] == len("original chapter prose")
    assert any(item.get("path") == "正文/第0001章.md" and item.get("kind") == "chapter_prose"
               for item in pinned.record_body["dependency_closure"])
    state_slice = pinned.generation_root / "state/chapter_001.json"
    state_bytes = state_slice.read_bytes()
    manifest_digest = pinned.record_body["generation_manifest_sha256"]
    from data_modules.state_projection_writer import StateProjectionWriter
    monkeypatch.setattr(StateProjectionWriter, "reduce_state",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("runtime reducer called")))
    chapter.write_text("changed after publication" * 10, encoding="utf-8")
    first = state.read_view(pinned)
    import time
    time.sleep(0.01)
    second = state.read_view(pinned)
    assert first == second == before
    assert state.write_owner_values({"story_craft": {"note": "mutable"}}) == 1
    assert state.read_view(pinned)["story_craft"]["note"] == "mutable"
    assert state_slice.read_bytes() == state_bytes
    assert hashlib.sha256(state_slice.read_bytes()).hexdigest() == hashlib.sha256(state_bytes).hexdigest()
    assert pinned.record_body["generation_manifest_sha256"] == manifest_digest


def test_generation_rag_uses_same_chinese_tokenizer_as_mutable_index(tmp_path):
    from data_modules.rag_tokenizer import tokenize_rag
    assert tokenize_rag("林青突破金丹 青城") == RAGAdapter._tokenize(None, "林青突破金丹 青城")
    assert tokenize_rag("林青") == ["林", "青"]


@pytest.mark.parametrize("query", ["林青", "金丹", "青城"])
def test_generation_rag_chinese_bm25_matches_shared_index_tokens(tmp_path, query):
    _commit, _snapshot, pinned, _publication = _activate(
        tmp_path, summary="林青在青城突破金丹")
    matches = OwnedRAGView(pinned, lambda _query: []).search(query, strategy="bm25")
    assert matches and "林青" in matches[0]["content"]


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


def test_generation_rag_has_distinct_bm25_vector_hybrid_and_graph_paths(tmp_path):
    _commit, _snapshot, pinned, _publication = _activate(tmp_path)
    projection = json.loads((pinned.generation_root / "vector/chapter_001.json").read_text(encoding="utf-8"))["projection"]
    chunk = projection["chunks"][0]
    assert chunk["terms"] and chunk["doc_length"] > 0 and chunk["embedding"]
    view = OwnedRAGView(pinned, lambda _query: [])
    bm25 = view.search("Canon summary", strategy="bm25")
    vector = view.search("unrelated", strategy="vector", query_embedding=chunk["embedding"])
    hybrid = view.search("Canon summary", strategy="hybrid", query_embedding=chunk["embedding"])
    graph = view.search("Canon summary", strategy="graph_hybrid", query_embedding=chunk["embedding"],
                        center_entities=["Canon"])
    assert bm25 and bm25[0]["source"] == "bm25"
    assert vector and vector[0]["source"] == "vector"
    assert hybrid and hybrid[0]["source"] == "hybrid"
    assert graph and graph[0]["source"] == "graph_hybrid"
    assert all(row["generation_id"] == pinned.generation_id for row in graph)


def test_rag_generation_excludes_stale_commit_rows_but_keeps_mutable_owner_rows(tmp_path):
    _activate(tmp_path)
    adapter = RAGAdapter.__new__(RAGAdapter)
    adapter.config = SimpleNamespace(project_root=tmp_path)
    adapter.bm25_search = lambda *_args, **_kwargs: [
        SearchResult("stale", 1, 0, "stale Canon", 1.0, "bm25", source_file="commit:chapter_001"),
        SearchResult("owner", 1, 0, "mutable planning note", 0.4, "bm25", source_file="owner"),
    ]
    results = asyncio.run(adapter.search("Canon", strategy="bm25", top_k=10))
    assert any(row.chunk_id == "ch0001_summary" for row in results)
    assert any(row.chunk_id == "owner" for row in results)
    assert all(row.chunk_id != "stale" for row in results)


@pytest.mark.parametrize("strategy", ["bm25", "vector", "hybrid", "graph_hybrid"])
def test_activation_rag_excludes_stale_canon_before_owner_top_k(tmp_path, monkeypatch, strategy):
    _activate(tmp_path)
    adapter = RAGAdapter(DataModulesConfig.from_project_root(tmp_path))
    async def embed(_texts):
        return [[1.0, 0.0]]
    async def rerank(_query, _documents, top_n=5):
        return []
    monkeypatch.setattr(adapter.api_client, "embed", embed)
    monkeypatch.setattr(adapter.api_client, "rerank", rerank)
    with adapter._get_conn() as conn:
        cursor = conn.cursor()
        for index in range(24):
            chunk_id = f"stale-{index:02d}"
            content = "needle " + (" filler" * 8)
            cursor.execute("INSERT INTO vectors (chunk_id, chapter, scene_index, content, embedding, chunk_type, source_file) VALUES (?, 1, 0, ?, ?, 'scene', ?)",
                           (chunk_id, content, adapter._serialize_embedding([1.0, 0.0]), f"commit:chapter_{index:03d}"))
            adapter._update_bm25_index(cursor, chunk_id, content)
        owner_content = "needle " + (" filler" * 400)
        cursor.execute("INSERT INTO vectors (chunk_id, chapter, scene_index, content, embedding, chunk_type, source_file) VALUES (?, 1, 0, ?, ?, 'scene', 'owner')",
                       ("owner-needle", owner_content, adapter._serialize_embedding([0.9, 0.435])))
        adapter._update_bm25_index(cursor, "owner-needle", owner_content)
        conn.commit()
    rows = asyncio.run(adapter.search("needle", strategy=strategy, top_k=1,
                                      center_entities=["no-owner-entity"]))
    assert rows and rows[0].chunk_id == "owner-needle"
    assert all(not str(row.source_file or "").startswith("commit:") for row in rows)


def test_generation_bm25_matches_base_only_canon_bm25(tmp_path, monkeypatch):
    from data_modules.vector_projection_writer import VectorProjectionWriter

    commit = {
        "meta": {"schema_version": "story-system/v1", "chapter": 1, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": [],
                              "chapter_meta": {"title": "Canon title"},
                              "summary_text": "Canon summary for BM25 parity 林青突破金丹 青城"},
    }
    path = tmp_path / ".story-system/commits/chapter_001.commit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(commit), encoding="utf-8")
    config = DataModulesConfig.from_project_root(tmp_path)
    adapter = RAGAdapter(config)
    monkeypatch.setattr(adapter.api_client, "embed_batch", lambda texts: _async_values([[0.25] * 16 for _ in texts]))
    chunks = VectorProjectionWriter(tmp_path)._collect_chunks(commit)
    asyncio.run(adapter.store_chunks(chunks))
    base_only = {query: adapter.bm25_search(query, log_query=False)
                 for query in ("Canon summary", "林青", "金丹", "青城")}
    snapshot = EffectiveHistoryStore().read_active_snapshot(tmp_path)
    built = build_effective_generation(tmp_path, snapshot)
    protocol = ProjectionGeneration(tmp_path)
    protocol.publish_generation(built["validated_generation"], None, snapshot.correction_lineage_digest)
    pinned = protocol.pin_active_generation()
    for query, legacy_rows in base_only.items():
        generation = OwnedRAGView(pinned, lambda _query: []).search(query, strategy="bm25")
        assert any(row.chunk_id == "ch0001_summary" for row in legacy_rows)
        assert any(row["chunk_id"] == "ch0001_summary" for row in generation)


def _async_values(value):
    async def result():
        return value
    return result()


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
    assert any(row.chunk_id == "ch0001_summary" for row in results)
    assert any(row.chunk_id == "legacy" for row in results)


def test_state_manager_reads_pinned_view_and_writes_workflow_overlay(tmp_path):
    _activate(tmp_path)
    state_path = tmp_path / ".webnovel/state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_bytes = b'{"legacy_snapshot":true}\n'
    state_path.write_bytes(legacy_bytes)
    manager = StateManager(DataModulesConfig.from_project_root(tmp_path), enable_sqlite_sync=False)
    assert manager.get_chapter_status(1) == "chapter_committed"
    manager.set_chapter_status(2, "chapter_drafted")
    assert state_path.read_bytes() == legacy_bytes
    view = OwnedStateStore(tmp_path).read_view(OwnedProjectView.pin_active(tmp_path).pinned)
    assert view["progress"]["chapter_status"]["2"] == "chapter_drafted"


def test_owner_overlay_expected_revision_conflict_fails_closed(tmp_path):
    _activate(tmp_path)
    store = OwnedStateStore(tmp_path)
    store.write_owner_values({"story_craft": {"first": True}}, expected_revision=0)
    with pytest.raises(OwnedViewError, match="OWNER_STATE_REVISION_CONFLICT"):
        store.write_owner_values({"story_craft": {"second": True}}, expected_revision=0)


def test_state_manager_save_state_routes_owner_mutations_to_overlay(tmp_path):
    _activate(tmp_path)
    state_path = tmp_path / ".webnovel/state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_bytes = b'{"story_craft":{"rhythm_curve":{"old":true}}}\n'
    state_path.write_bytes(legacy_bytes)
    manager = StateManager(DataModulesConfig.from_project_root(tmp_path), enable_sqlite_sync=False)
    manager._state.setdefault("story_craft", {})["rhythm_curve"] = {"chapters_since_peak": 3}
    manager._state["project_info"] = {"title": "planned title", "promise_ledger": [
        {"id": "P1", "status": "deferred", "expected_payoff_chapter": 20}
    ]}
    manager._state["volumes"] = [{"index": 1, "status": "confirmed"}]
    manager._state.setdefault("chapter_meta", {})["2"] = {"hook_type": "悬念式"}
    manager._pending_chapter_meta["2"] = {"hook_type": "悬念式"}
    manager.save_state()
    assert state_path.read_bytes() == legacy_bytes
    fresh = OwnedProjectView.pin_active(tmp_path)
    assert fresh.state_view()["story_craft"]["rhythm_curve"] == {"chapters_since_peak": 3}
    assert fresh.state_view()["project_info"]["title"] == "planned title"
    assert fresh.state_view()["project_info"]["promise_ledger"][0]["status"] == "deferred"
    assert fresh.state_view()["volumes"] == [{"index": 1, "status": "confirmed"}]
    assert fresh.state_view()["chapter_meta"]["2"]["hook_type"] == "悬念式"
    manager2 = StateManager(DataModulesConfig.from_project_root(tmp_path), enable_sqlite_sync=False)
    assert manager2._state.get("story_craft", {}).get("rhythm_curve") == {"chapters_since_peak": 3}


def test_enrolled_chapter_meta_owner_fields_can_be_edited_without_touching_legacy_state(tmp_path):
    _activate(tmp_path)
    state_path = tmp_path / ".webnovel/state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_bytes = b'{"chapter_meta":{"2":{"title":"legacy title"}}}\n'
    state_path.write_bytes(legacy_bytes)
    manager = StateManager(DataModulesConfig.from_project_root(tmp_path), enable_sqlite_sync=False)

    manager._state.setdefault("chapter_meta", {}).setdefault("2", {}).update({
        "hook_type": "悬念式", "must_cover": ["A"],
    })
    manager._pending_chapter_meta["2"] = {"hook_type": "悬念式", "must_cover": ["A"]}
    manager.save_state()

    manager._state["chapter_meta"]["2"].update({"hook_type": "揭示式", "must_cover": ["B"]})
    manager._pending_chapter_meta["2"] = {"hook_type": "揭示式", "must_cover": ["B"]}
    manager.save_state()

    fresh_view = OwnedProjectView.pin_active(tmp_path)
    assert fresh_view.state_view()["chapter_meta"]["2"] == {"hook_type": "揭示式", "must_cover": ["B"]}
    assert state_path.read_bytes() == legacy_bytes
    restarted = StateManager(DataModulesConfig.from_project_root(tmp_path), enable_sqlite_sync=False)
    assert restarted._state["chapter_meta"]["2"]["hook_type"] == "揭示式"
    assert restarted._state["chapter_meta"]["2"]["must_cover"] == ["B"]


def test_enrolled_unknown_chapter_meta_field_fails_closed(tmp_path):
    _activate(tmp_path)
    manager = StateManager(DataModulesConfig.from_project_root(tmp_path), enable_sqlite_sync=False)
    manager._state.setdefault("chapter_meta", {}).setdefault("2", {})["future_claim"] = "unknown"
    manager._pending_chapter_meta["2"] = {"future_claim": "unknown"}
    with pytest.raises(RuntimeError, match="UNMAPPED_CHAPTER_META:2.future_claim"):
        manager.save_state()


def test_state_manager_rejects_publication_change_since_load(tmp_path):
    _commit, snapshot, _pinned, _record = _activate(tmp_path)
    manager = StateManager(DataModulesConfig.from_project_root(tmp_path), enable_sqlite_sync=False)
    manager._state.setdefault("progress", {}).setdefault("chapter_status", {})["2"] = "chapter_drafted"
    manager._pending_chapter_status["2"] = "chapter_drafted"
    protocol = ProjectionGeneration(tmp_path)
    built = build_effective_generation(tmp_path, snapshot)
    active = protocol.pin_active_generation()
    protocol.publish_generation(built["validated_generation"], active.publication_record_sha256,
                                snapshot.correction_lineage_digest)
    with pytest.raises(RuntimeError, match="ACTIVE_PUBLICATION_CHANGED_DURING_OPERATION"):
        manager.save_state()


def test_story_craft_cli_routes_enrolled_mutation_to_overlay(tmp_path):
    from data_modules.webnovel import cmd_story_craft

    _activate(tmp_path)
    state_path = tmp_path / ".webnovel/state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_bytes = b'{"story_craft":{"foreshadow_chain":[]}}\n'
    state_path.write_bytes(legacy_bytes)
    args = SimpleNamespace(project_root=str(tmp_path), story_craft_action="init-volume-beat",
                           volume=1, total_chapters=20)
    assert cmd_story_craft(args) == 0
    assert state_path.read_bytes() == legacy_bytes
    args.story_craft_action = "set-chapter-meta"
    args.chapter = 2
    args.hook_type = "悬念式"
    args.beat_position = args.scene_goal = args.scene_conflict = None
    args.scene_setback = args.scene_resolution = None
    args.sequel_reaction = args.sequel_dilemma = args.sequel_decision = None
    assert cmd_story_craft(args) == 0
    view_state = OwnedProjectView.pin_active(tmp_path).state_view()
    assert "story_craft" in view_state
    assert view_state["chapter_meta"]["2"]["hook_type"] == "悬念式"
    args.hook_type = "反转式"
    assert cmd_story_craft(args) == 0
    assert OwnedProjectView.pin_active(tmp_path).state_view()["chapter_meta"]["2"]["hook_type"] == "反转式"
    assert state_path.read_bytes() == legacy_bytes


def test_story_craft_overlay_failure_raises_without_touching_legacy_file(tmp_path, monkeypatch):
    from data_modules.webnovel import cmd_story_craft

    _activate(tmp_path)
    state_path = tmp_path / ".webnovel/state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    original = b'{"story_craft":{}}\n'
    state_path.write_bytes(original)
    def fail_write(self, values, **kwargs):
        raise OwnedViewError("OVERLAY_WRITE_FAILED")
    monkeypatch.setattr(OwnedStateStore, "write_owner_values", fail_write)
    args = SimpleNamespace(project_root=str(tmp_path), story_craft_action="init-volume-beat",
                           volume=1, total_chapters=20)
    with pytest.raises(OwnedViewError, match="OVERLAY_WRITE_FAILED"):
        cmd_story_craft(args)
    assert state_path.read_bytes() == original


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


def test_generation_state_matches_legacy_reducer_and_context_semantics(tmp_path):
    for chapter in range(1, 4):
        events = []
        if chapter == 1:
            events.append({"event_id": "loop-create", "chapter": chapter,
                           "event_type": "open_loop_created", "subject": "hero",
                           "payload": {"description": "旧约"}})
        if chapter == 3:
            events.append({"event_id": "loop-close", "chapter": chapter,
                           "event_type": "open_loop_closed", "subject": "hero",
                           "payload": {"loop_id": "loop-create", "description": "旧约"}})
        commit = {
            "meta": {"schema_version": "story-system/v1", "chapter": chapter, "status": "accepted"},
            "review_result": {"blocking_count": 0},
            "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
            "disambiguation_result": {"pending": []},
            "extraction_result": {
                "accepted_events": events,
                "entity_deltas": ([{"entity_id": "hero", "canonical_name": "林青", "is_protagonist": True}]
                                   if chapter == 1 else []),
                "state_deltas": [{"entity_id": "hero", "field": "location.city", "new": ["青城", "北港", "天都"][chapter - 1]},
                                 {"entity_id": "hero", "field": "realm", "new": ["炼气", "筑基", "金丹"][chapter - 1]}],
                "chapter_meta": {"title": f"第{chapter}章", "dominant_strand": ["quest", "fire", "constellation"][chapter - 1]},
                "summary_text": f"第{chapter}章 林青 {chapter}",
            },
        }
        path = tmp_path / f".story-system/commits/chapter_{chapter:03d}.commit.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(commit, ensure_ascii=False), encoding="utf-8")
        StateProjectionWriter(tmp_path).apply(commit)

    legacy = json.loads((tmp_path / ".webnovel/state.json").read_text(encoding="utf-8"))
    snapshot = EffectiveHistoryStore().read_active_snapshot(tmp_path)
    built = build_effective_generation(tmp_path, snapshot)
    protocol = ProjectionGeneration(tmp_path)
    protocol.publish_generation(built["validated_generation"], None, snapshot.correction_lineage_digest)
    pinned = protocol.pin_active_generation()
    actual = OwnedStateStore(tmp_path).read_view(pinned)
    for key in ("entity_state", "protagonist_state", "strand_tracker", "plot_threads"):
        assert actual.get(key) == legacy.get(key)
    assert {k: v for k, v in actual["progress"].items() if k != "last_updated"} == {
        k: v for k, v in legacy["progress"].items() if k != "last_updated"}
    assert "last_updated" not in actual["progress"]
    context = ContextManager(DataModulesConfig.from_project_root(tmp_path)).build_context(4)
    assert context["core"]["protagonist_snapshot"]["name"] == "林青"
    assert context["scene"]["location_context"]["city"] == "天都"
    assert actual["plot_threads"]["foreshadowing"][0]["status"] == "resolved"
