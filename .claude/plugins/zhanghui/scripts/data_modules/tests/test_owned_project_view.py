import json

import pytest

from data_modules.effective_history import EffectiveHistoryStore
from data_modules.owned_project_view import (
    OwnedIndexView, OwnedMemoryView, OwnedRAGView, OwnedStateStore, OwnedViewError,
)
from data_modules.projection_generation import ProjectionGeneration
from data_modules.projection_rebuild import build_effective_generation


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
    results = OwnedRAGView(pinned, lambda _query: [{"id": "mutable", "score": 0.5}]).search("x")
    assert {row["authority_claim"] for row in results} == {"CANON_AUTHORITY", "OWNER_AUTHORITY"}
