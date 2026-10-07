import json
import sqlite3

import pytest

from data_modules.canon_correction_schema import (
    artifact_sha256, base_commit_digest, effective_content_digest, request_sha256, canonical_json,
)
from data_modules.canon_correction_store import (
    CorrectionStoreError, append_correction, append_correction_request,
    build_correction_review_package, record_interactive_correction_decision,
    verify_phase9_correction_decision,
)
from data_modules.effective_history import EffectiveHistoryStore
from data_modules.project_migration import (
    create_verified_backup, dry_run_migration, migrate_project, preflight_project,
)
from data_modules.projection_generation import GenerationError, ProjectionGeneration
from data_modules.projection_rebuild import build_effective_generation
from data_modules.chapter_commit_service import ChapterCommitService, ChapterCommitError
from data_modules.owned_project_view import OwnedProjectView, OwnedRAGView, OwnedStateStore
from data_modules.config import DataModulesConfig
from data_modules.context_manager import ContextManager
from data_modules.index_manager import IndexManager


def _commit(chapter):
    return {
        "meta": {"schema_version": "story-system/v1", "chapter": chapter, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": [],
                              "chapter_meta": {"title": f"chapter {chapter}"}},
    }


def _active_root(root, chapters=2, include_state=False):
    commits = []
    for chapter in range(1, chapters + 1):
        body = _commit(chapter)
        body["extraction_result"]["summary_text"] = f"Original Canon summary chapter {chapter}"
        if include_state:
            body["extraction_result"]["entity_deltas"] = [
                {"entity_id": "hero", "canonical_name": "Hero", "is_protagonist": True}]
            body["extraction_result"]["state_deltas"] = [
                {"entity_id": "hero", "field": "realm", "new": "Initial"}]
        path = root / f".story-system/commits/chapter_{chapter:03d}.commit.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body), encoding="utf-8")
        commits.append((body, path))
    webnovel = root / ".webnovel"
    webnovel.mkdir(parents=True, exist_ok=True)
    (webnovel / "state.json").write_text(json.dumps({"story_craft": {"voice": "warm"}}), encoding="utf-8")
    db = sqlite3.connect(webnovel / "index.db")
    db.execute("CREATE TABLE chapters (chapter INTEGER)")
    db.execute("CREATE TABLE review_attempts (id INTEGER)")
    db.commit(); db.close()
    report = preflight_project(root)
    plan = dry_run_migration(root, report.report_digest)
    backup = create_verified_backup(root, plan)
    migrate_project(root, report.report_digest, plan.plan_digest, backup)
    return commits


def _stage_retract(root, chapter, base, correction_id, *, interaction_id=None, prior_verifications=(),
                   return_verification=False):
    active = EffectiveHistoryStore().read_active_snapshot(root)
    entry = active.chapters[chapter]
    digest = base_commit_digest(base)
    request = {
        "schema_version": "canon-correction-request/v1", "request_id": f"{correction_id}-request",
        "chapter": chapter, "base_commit_sha256": digest,
        "parent_revision_id": entry.effective_revision_id,
        "parent_effective_content_sha256": entry.effective_content_sha256,
        "operation": "RETRACT", "proposed_effective_status": "retracted",
        "proposed_effective_extraction_result": None,
        "proposed_effective_content_sha256": effective_content_digest("retracted", None),
        "changed_paths": [], "proposer_provenance": {"fixture": "TEST ONLY"}, "reason": "TEST ONLY",
    }
    append_correction_request(root, request, decision_verifications=prior_verifications)
    package = build_correction_review_package(
        request, parent_status=entry.status, parent_extraction=entry.extraction_result)
    authorization = record_interactive_correction_decision(
        root, request, package, choice="APPROVE", authorization_id=f"{correction_id}-auth",
        interaction_id=interaction_id or f"{correction_id}-interaction",
        interaction_surface="test fixture", confirmed_at="2026-10-07T00:00:00Z")
    decision = verify_phase9_correction_decision(request, authorization, package)
    correction = {
        "schema_version": "canon-correction/v1", "correction_id": correction_id,
        "chapter": chapter, "base_commit_sha256": digest,
        "parent_revision_id": request["parent_revision_id"],
        "parent_effective_content_sha256": request["parent_effective_content_sha256"],
        "operation": "RETRACT", "effective_extraction_result": None, "changed_paths": [],
        "request_sha256": request_sha256(request), "authorization_ref": authorization.authorization_id,
        "authorization_sha256": artifact_sha256(authorization),
        "provenance": {"fixture": "TEST ONLY"}, "actor_ref": "TEST ONLY", "reason": "TEST ONLY",
    }
    append_correction(root, correction, request=request, authorization=authorization,
                      decision_verifications=[*prior_verifications, decision])
    return (authorization, decision) if return_verification else authorization


def _stage_amend_summary(root, chapter, base, correction_id, new_summary):
    from data_modules.canon_correction_resolver import _structural_changes
    active = EffectiveHistoryStore().read_active_snapshot(root)
    entry = active.chapters[chapter]
    digest = base_commit_digest(base)
    updated = {**entry.extraction_result, "summary_text": new_summary,
               "state_deltas": [{"entity_id": "hero", "field": "realm", "new": "Corrected"}]}
    request = {
        "schema_version": "canon-correction-request/v1", "request_id": f"{correction_id}-request",
        "chapter": chapter, "base_commit_sha256": digest,
        "parent_revision_id": entry.effective_revision_id,
        "parent_effective_content_sha256": entry.effective_content_sha256,
        "operation": "AMEND", "proposed_effective_status": "accepted",
        "proposed_effective_extraction_result": updated,
        "proposed_effective_content_sha256": effective_content_digest("accepted", updated),
        "changed_paths": _structural_changes(entry.extraction_result, updated),
        "proposer_provenance": {"fixture": "TEST ONLY"}, "reason": "TEST ONLY",
    }
    append_correction_request(root, request)
    package = build_correction_review_package(
        request, parent_status=entry.status, parent_extraction=entry.extraction_result)
    authorization = record_interactive_correction_decision(
        root, request, package, choice="APPROVE", authorization_id=f"{correction_id}-auth",
        interaction_id=f"{correction_id}-interaction", interaction_surface="test fixture",
        confirmed_at="2026-10-07T00:00:00Z")
    decision = verify_phase9_correction_decision(request, authorization, package)
    correction = {
        "schema_version": "canon-correction/v1", "correction_id": correction_id,
        "chapter": chapter, "base_commit_sha256": digest,
        "parent_revision_id": request["parent_revision_id"],
        "parent_effective_content_sha256": request["parent_effective_content_sha256"],
        "operation": "AMEND", "effective_extraction_result": updated,
        "changed_paths": request["changed_paths"],
        "request_sha256": request_sha256(request), "authorization_ref": authorization.authorization_id,
        "authorization_sha256": artifact_sha256(authorization),
        "provenance": {"fixture": "TEST ONLY"}, "actor_ref": "TEST ONLY", "reason": "TEST ONLY",
    }
    append_correction(root, correction, request=request, authorization=authorization,
                      decision_verifications=[decision])
    return authorization, decision


def _stage_supersede(root, chapter, base, correction_id, extraction, prior_verifications):
    active = EffectiveHistoryStore().read_active_snapshot(root)
    entry = active.chapters[chapter]
    digest = base_commit_digest(base)
    request = {
        "schema_version": "canon-correction-request/v1", "request_id": f"{correction_id}-request",
        "chapter": chapter, "base_commit_sha256": digest,
        "parent_revision_id": entry.effective_revision_id,
        "parent_effective_content_sha256": entry.effective_content_sha256,
        "operation": "SUPERSEDE", "proposed_effective_status": "accepted",
        "proposed_effective_extraction_result": extraction,
        "proposed_effective_content_sha256": effective_content_digest("accepted", extraction),
        "changed_paths": [], "proposer_provenance": {"fixture": "TEST ONLY"}, "reason": "TEST ONLY",
    }
    append_correction_request(root, request, decision_verifications=prior_verifications)
    package = build_correction_review_package(
        request, parent_status=entry.status, parent_extraction=entry.extraction_result)
    authorization = record_interactive_correction_decision(
        root, request, package, choice="APPROVE", authorization_id=f"{correction_id}-auth",
        interaction_id=f"{correction_id}-interaction", interaction_surface="test fixture",
        confirmed_at="2026-10-07T00:00:00Z")
    decision = verify_phase9_correction_decision(request, authorization, package)
    correction = {
        "schema_version": "canon-correction/v1", "correction_id": correction_id,
        "chapter": chapter, "base_commit_sha256": digest,
        "parent_revision_id": request["parent_revision_id"],
        "parent_effective_content_sha256": request["parent_effective_content_sha256"],
        "operation": "SUPERSEDE", "effective_extraction_result": extraction, "changed_paths": [],
        "request_sha256": request_sha256(request), "authorization_ref": authorization.authorization_id,
        "authorization_sha256": artifact_sha256(authorization),
        "provenance": {"fixture": "TEST ONLY"}, "actor_ref": "TEST ONLY", "reason": "TEST ONLY",
    }
    append_correction(root, correction, request=request, authorization=authorization,
                      decision_verifications=[*prior_verifications, decision])
    return authorization, decision


def test_activation_publishes_only_after_complete_generation_and_keeps_owner_overlay(tmp_path, monkeypatch):
    from data_modules.canon_correction_store import activate_correction

    commits = _active_root(tmp_path, chapters=1)
    authorization = _stage_retract(tmp_path, 1, commits[0][0], "TEST-ONLY-activate")
    protocol = ProjectionGeneration(tmp_path)
    before = protocol.pin_active_generation()
    legacy_state_bytes = (tmp_path / ".webnovel/state.json").read_bytes()
    active_before = EffectiveHistoryStore().read_active_snapshot(tmp_path)
    candidate = EffectiveHistoryStore().resolve_candidate(tmp_path, "TEST-ONLY-activate")
    assert candidate.ok
    assert active_before.chapters[1].status == "accepted"

    publish = ProjectionGeneration.publish_generation
    observed = []
    def inspect_before_publish(self, *args, **kwargs):
        pinned_before = self.pin_active_generation()
        history_before = EffectiveHistoryStore().read_active_snapshot(tmp_path)
        observed.append((pinned_before.publication_record_id, history_before.chapters[1].status))
        return publish(self, *args, **kwargs)
    monkeypatch.setattr(ProjectionGeneration, "publish_generation", inspect_before_publish)

    result = activate_correction(tmp_path, "TEST-ONLY-activate", authorization)

    assert observed == [(before.publication_record_id, "accepted")]
    assert result.ok is True
    assert result.publication_record_id == "publication-00000002"
    after = protocol.pin_active_generation()
    assert after.publication_record_id == result.publication_record_id
    assert after.semantic_activation_id != before.semantic_activation_id
    active_after = EffectiveHistoryStore().read_active_snapshot(tmp_path)
    assert active_after.chapters[1].status == "retracted"
    for domain in ("events", "state", "index", "summary", "memory", "vector", "intent_diagnostics"):
        output = json.loads((after.generation_root / domain / "chapter_001.json").read_text(encoding="utf-8"))
        assert output["projection"]["tombstone"] is True
        assert output["effective_revision_id"] == active_after.chapters[1].effective_revision_id
    owner_view = OwnedProjectView.pin_active(tmp_path)
    assert owner_view.state_view()["story_craft"]["voice"] == "warm"
    context = ContextManager(DataModulesConfig.from_project_root(tmp_path)).build_context(2)
    context_pin = context["meta"]["context_snapshot"]
    assert context_pin["publication_record_id"] == result.publication_record_id
    assert context_pin["generation_id"] == result.generation_id
    assert context_pin["semantic_activation_id"] == result.semantic_activation_id
    assert (tmp_path / ".story-system/commits/chapter_001.commit.json").read_bytes() == commits[0][1].read_bytes()
    retry = activate_correction(tmp_path, "TEST-ONLY-activate", authorization)
    assert retry.activated is False
    assert retry.publication_record_id == result.publication_record_id
    assert len(protocol._records()) == 2


def test_normal_chapter_commit_publishes_complete_activation_generation(tmp_path):
    _active_root(tmp_path, chapters=1)
    protocol = ProjectionGeneration(tmp_path)
    before = protocol.pin_active_generation()
    legacy_state_bytes = (tmp_path / ".webnovel/state.json").read_bytes()
    payload = _commit(2)
    payload["extraction_result"]["summary_text"] = "chapter two Canon summary"
    committed = ChapterCommitService(tmp_path).apply_projections(payload)
    after = protocol.pin_active_generation()
    active = EffectiveHistoryStore().read_active_snapshot(tmp_path)
    assert after.publication_record_id != before.publication_record_id
    assert active.ok and set(active.chapters) == {1, 2}
    assert committed["publication_record_id"] == after.publication_record_id
    for domain in ("events", "state", "index", "summary", "memory", "vector", "intent_diagnostics"):
        assert (after.generation_root / domain / "chapter_002.json").is_file()
    assert (tmp_path / ".webnovel/state.json").read_bytes() == legacy_state_bytes


def test_durable_migration_full_smoke_preserves_owner_chapter_correction_and_checklist(tmp_path, monkeypatch):
    import sys
    from data_modules.canon_correction_store import activate_correction

    base = _commit(1)
    base["extraction_result"]["accepted_events"] = [{
        "event_id": "accepted-relationship", "chapter": 1,
        "event_type": "relationship_changed", "subject": "Hero",
        "payload": {"from_entity": "Hero", "to_entity": "Mentor",
                    "relationship_type": "ally", "description": "Canon relationship"},
    }]
    commit_path = tmp_path / ".story-system/commits/chapter_001.commit.json"
    commit_path.parent.mkdir(parents=True)
    commit_path.write_text(json.dumps(base), encoding="utf-8")
    state = {"project_info": {"title": "TEST ONLY", "genre": "玄幻",
                              "core_selling_points": ["planned premise"]},
             "volumes": [{"title": "TEST ONLY volume", "outline": "planned"}],
             "relationships": {"legacy-only": [{"description": "must not become Canon"}]}}
    state_path = tmp_path / ".webnovel/state.json"
    state_path.parent.mkdir(parents=True)
    original_state = json.dumps(state, ensure_ascii=False).encode("utf-8")
    state_path.write_bytes(original_state)
    with sqlite3.connect(tmp_path / ".webnovel/index.db") as conn:
        conn.execute("CREATE TABLE chapters (chapter INTEGER)")
        conn.execute("CREATE TABLE review_attempts (id INTEGER)")

    report = preflight_project(tmp_path)
    assert report.ok is True
    plan = dry_run_migration(tmp_path, report.report_digest)
    assert {"project_info", "volumes"}.issubset(next(
        row["fields"] for row in plan.mutable_overlays if row["path"] == ".webnovel/state-overlay.json"))
    backup = create_verified_backup(tmp_path, plan)
    migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)
    active = OwnedProjectView.pin_active(tmp_path)
    state_view = OwnedStateStore(tmp_path).read_view(active.pinned)
    assert state_view["project_info"] == state["project_info"]
    assert state_view["volumes"] == state["volumes"]
    relations = active.index.read_table("relationships")
    assert [row["payload"]["description"] for row in relations] == ["Canon relationship"]

    second = _commit(2)
    second["extraction_result"]["summary_text"] = "chapter two accepted"
    ChapterCommitService(tmp_path).apply_projections(second)
    authorization, _ = _stage_amend_summary(
        tmp_path, 1, base, "TEST-ONLY-full-smoke", "corrected accepted Canon summary")
    activation = activate_correction(tmp_path, "TEST-ONLY-full-smoke", authorization)
    assert activation.ok is True
    assert (state_path.read_bytes() == original_state)

    # A new manager instance represents the restarted runtime reading the activated generation.
    restarted = ContextManager(DataModulesConfig.from_project_root(tmp_path))
    context = restarted.build_context(3)
    assert context["meta"]["context_snapshot"]["publication_record_id"] == activation.publication_record_id
    persisted_owner_state = OwnedProjectView.pin_active(tmp_path).state_view()
    assert persisted_owner_state["project_info"] == state["project_info"]
    assert persisted_owner_state["volumes"] == state["volumes"]

    monkeypatch.setattr(sys, "argv", ["context_manager", "--project-root", str(tmp_path),
                                      "--chapter", "3", "--persist-checklist-score"])
    from data_modules.context_manager import main
    main()
    assert IndexManager(DataModulesConfig.from_project_root(tmp_path), read_only=True).get_writing_checklist_score(3) is not None
    assert ContextManager(DataModulesConfig.from_project_root(tmp_path)).build_context(4)
    assert IndexManager(DataModulesConfig.from_project_root(tmp_path), read_only=True).get_writing_checklist_score_trend()["count"] == 1


def test_new_chapter_rejects_snapshot_staled_by_same_semantic_publication(tmp_path, monkeypatch):
    _active_root(tmp_path, chapters=1)
    protocol = ProjectionGeneration(tmp_path)
    original_read = EffectiveHistoryStore.read_active_snapshot
    observed = {"published": False, "calls": 0}

    def race_after_snapshot(store, root, **kwargs):
        snapshot = original_read(store, root, **kwargs)
        observed["calls"] += 1
        if observed["calls"] == 2 and not observed["published"]:
            observed["published"] = True
            built = build_effective_generation(root, snapshot,
                                               previous_generation_id=protocol.pin_active_generation().generation_id)
            head = protocol.latest_publication()
            protocol.publish_generation(built["validated_generation"], head.record_sha256,
                                        snapshot.correction_lineage_digest)
        return snapshot

    monkeypatch.setattr(EffectiveHistoryStore, "read_active_snapshot", race_after_snapshot)
    with pytest.raises(GenerationError, match="PUBLICATION_HEAD_CHANGED"):
        ChapterCommitService(tmp_path).apply_projections(_commit(2))
    monkeypatch.setattr(EffectiveHistoryStore, "read_active_snapshot", original_read)
    active = original_read(EffectiveHistoryStore(), tmp_path)
    assert set(active.chapters) == {1}
    assert active.activation_record_id == protocol.latest_publication().publication_record_id
    result = ChapterCommitService(tmp_path).apply_projections(_commit(2), on_conflict="skip")
    retry = original_read(EffectiveHistoryStore(), tmp_path)
    assert result["publication_record_id"] == protocol.latest_publication().publication_record_id
    assert set(retry.chapters) == {1, 2}


def test_new_chapter_retry_preserves_concurrent_correction_activation(tmp_path, monkeypatch):
    commits = _active_root(tmp_path, chapters=1, include_state=True)
    auth, _decision = _stage_amend_summary(tmp_path, 1, commits[0][0],
                                           "TEST-ONLY-chapter-correction-race", "Correction S2")
    protocol = ProjectionGeneration(tmp_path)
    original = EffectiveHistoryStore.read_active_snapshot
    race = {"calls": 0, "activated": False}

    def concurrent_activation(store, root, **kwargs):
        snapshot = original(store, root, **kwargs)
        race["calls"] += 1
        if race["calls"] == 2 and not race["activated"]:
            race["activated"] = True
            from data_modules.canon_correction_schema import artifact_sha256
            from data_modules.effective_history import ActiveEffectiveHistorySnapshot, _snapshot_digests
            candidate = store.resolve_candidate(tmp_path, "TEST-ONLY-chapter-correction-race")
            corrected_chapters = {1: candidate.chapters[1]}
            base_digest, lineage_digest, history_digest = _snapshot_digests(corrected_chapters)
            artifact_dependencies = [item for item in candidate.dependencies
                                     if item.get("kind") in {"correction", "request", "authorization"}]
            exact_lineage_digest = artifact_sha256({
                "effective_lineage_digest": lineage_digest,
                "artifacts": artifact_dependencies,
            })
            corrected = ActiveEffectiveHistorySnapshot(
                True, candidate.chapters, snapshot.activation_record_id,
                base_digest, exact_lineage_digest, history_digest,
                snapshot.generation_id, (),
                candidate.dependencies, candidate.lineage_namespace_checks,
                snapshot.publication_record_sha256, snapshot.semantic_activation_id,
            )
            corrected = ActiveEffectiveHistorySnapshot(
                corrected.ok, corrected_chapters, corrected.activation_record_id,
                corrected.base_set_digest, corrected.correction_lineage_digest,
                corrected.effective_history_digest, corrected.generation_id,
                corrected.diagnostics, corrected.dependencies,
                corrected.lineage_namespace_checks, corrected.publication_record_sha256,
                corrected.semantic_activation_id,
            )
            built = build_effective_generation(
                tmp_path, corrected, previous_generation_id=snapshot.generation_id)
            head = protocol.latest_publication()
            protocol.publish_generation(built["validated_generation"], head.record_sha256,
                                        corrected.correction_lineage_digest)
        return snapshot

    monkeypatch.setattr(EffectiveHistoryStore, "read_active_snapshot", concurrent_activation)
    with pytest.raises(GenerationError, match="PUBLICATION_HEAD_CHANGED"):
        ChapterCommitService(tmp_path).apply_projections(_commit(2))
    monkeypatch.setattr(EffectiveHistoryStore, "read_active_snapshot", original)
    active = original(EffectiveHistoryStore(), tmp_path)
    assert active.chapters[1].extraction_result["summary_text"] == "Correction S2"
    assert set(active.chapters) == {1}

    ChapterCommitService(tmp_path).apply_projections(_commit(2), on_conflict="skip")
    retried = original(EffectiveHistoryStore(), tmp_path)
    assert set(retried.chapters) == {1, 2}
    assert retried.chapters[1].extraction_result["summary_text"] == "Correction S2"
    assert protocol.pin_active_generation().publication_record_id == retried.activation_record_id


def test_pending_recovery_rejects_snapshot_staled_by_semantic_activation(tmp_path, monkeypatch):
    from data_modules.canon_correction_store import activate_correction
    from data_modules.projections import retry_projection

    commits = _active_root(tmp_path, chapters=1, include_state=True)
    auth, _decision = _stage_amend_summary(tmp_path, 1, commits[0][0],
                                           "TEST-ONLY-recovery-race", "Correction S2")
    original = EffectiveHistoryStore.read_active_snapshot
    raced = {"done": False}

    def race_after_snapshot(store, root, **kwargs):
        snapshot = original(store, root, **kwargs)
        if not raced["done"]:
            raced["done"] = True
            monkeypatch.setattr(EffectiveHistoryStore, "read_active_snapshot", original)
            activate_correction(tmp_path, "TEST-ONLY-recovery-race", auth)
            monkeypatch.setattr(EffectiveHistoryStore, "read_active_snapshot", race_after_snapshot)
        return snapshot

    monkeypatch.setattr(EffectiveHistoryStore, "read_active_snapshot", race_after_snapshot)
    result = retry_projection(tmp_path, chapter=1)
    assert result["ok"] is False
    monkeypatch.setattr(EffectiveHistoryStore, "read_active_snapshot", original)
    active = original(EffectiveHistoryStore(), tmp_path)
    assert active.chapters[1].extraction_result["summary_text"] == "Correction S2"
    recovered = retry_projection(tmp_path, chapter=1)
    assert recovered["ok"] is True
    assert original(EffectiveHistoryStore(), tmp_path).chapters[1].extraction_result["summary_text"] == "Correction S2"


def test_activation_publication_supports_sparse_and_rejected_commits(tmp_path):
    _active_root(tmp_path, chapters=1)
    service = ChapterCommitService(tmp_path)
    sparse = service.apply_projections(_commit(3))
    assert sparse["publication_record_id"] == "publication-00000002"
    assert set(EffectiveHistoryStore().read_active_snapshot(tmp_path).chapters) == {1, 3}

    rejected = _commit(4)
    rejected["meta"]["status"] = "rejected"
    rejected["extraction_result"]["accepted_events"] = []
    result = service.apply_projections(rejected)
    assert result["publication_record_id"] == "publication-00000003"
    active = EffectiveHistoryStore().read_active_snapshot(tmp_path)
    assert active.ok and active.chapters[4].status == "rejected"
    view = OwnedStateStore(tmp_path).read_view(ProjectionGeneration(tmp_path).pin_active_generation())
    assert view["progress"]["chapter_status"]["4"] == "chapter_rejected"


def test_failed_normal_publication_blocks_next_commit_and_retry_recovers_pending(tmp_path, monkeypatch):
    _active_root(tmp_path, chapters=1)
    protocol = ProjectionGeneration(tmp_path)
    before = protocol.pin_active_generation()
    publish = ProjectionGeneration.publish_generation
    monkeypatch.setattr(ProjectionGeneration, "publish_generation",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("TEST ONLY publish failure")))
    with pytest.raises(ChapterCommitError, match="pending recovery"):
        ChapterCommitService(tmp_path).apply_projections(_commit(2))
    pending_path = tmp_path / ".story-system/workflow/activation-publication-pending.json"
    assert json.loads(pending_path.read_text())["chapter"] == 2
    assert protocol.pin_active_generation().publication_record_id == before.publication_record_id
    assert (tmp_path / ".story-system/commits/chapter_002.commit.json").is_file()
    with pytest.raises(ChapterCommitError, match="recovery required"):
        ChapterCommitService(tmp_path).apply_projections(_commit(3))
    monkeypatch.setattr(ProjectionGeneration, "publish_generation", publish)
    from data_modules.projections import retry_projection
    recovered = retry_projection(tmp_path, chapter=2)
    assert recovered["ok"] is True
    assert not pending_path.exists()
    assert set(EffectiveHistoryStore().read_active_snapshot(tmp_path).chapters) == {1, 2}


def test_amend_replaces_generation_rag_chunks_and_retract_removes_them(tmp_path):
    from data_modules.canon_correction_store import activate_correction

    commits = _active_root(tmp_path, chapters=1, include_state=True)
    protocol = ProjectionGeneration(tmp_path)
    initial = protocol.pin_active_generation()
    initial_view = OwnedRAGView(initial, lambda _query: [])
    assert any("Original Canon summary" in row["content"]
               for row in initial_view.search("Original", strategy="bm25"))

    amend_auth, amend_verification = _stage_amend_summary(
        tmp_path, 1, commits[0][0], "TEST-ONLY-amend-rag", "Revised Canon summary")
    amended = activate_correction(tmp_path, "TEST-ONLY-amend-rag", amend_auth)
    amended_pin = protocol.pin_active_generation()
    amended_rows = OwnedRAGView(amended_pin, lambda _query: []).search("Revised", strategy="bm25")
    assert amended.activated is True
    assert any("Revised Canon summary" in row["content"] for row in amended_rows)
    assert all("Original Canon summary" not in row["content"] for row in amended_rows)
    assert OwnedStateStore(tmp_path).read_view(amended_pin)["protagonist_state"]["realm"] == "Corrected"

    retract_auth, retract_verification = _stage_retract(
        tmp_path, 1, commits[0][0], "TEST-ONLY-retract-rag",
        prior_verifications=(amend_verification,), return_verification=True)
    retracted = activate_correction(tmp_path, "TEST-ONLY-retract-rag", retract_auth)
    retracted_pin = protocol.pin_active_generation()
    assert retracted.activated is True
    assert OwnedRAGView(retracted_pin, lambda _query: []).search("Revised", strategy="bm25") == []
    state_after_retract = OwnedStateStore(tmp_path).read_view(retracted_pin)
    assert "hero" not in state_after_retract["entity_state"]

    amended_extraction = {**commits[0][0]["extraction_result"], "summary_text": "Revised Canon summary",
                          "state_deltas": [{"entity_id": "hero", "field": "realm", "new": "Corrected"}]}
    supersede_auth, _supersede_verification = _stage_supersede(
        tmp_path, 1, commits[0][0], "TEST-ONLY-supersede-rag", amended_extraction,
        (amend_verification, retract_verification))
    superseded = activate_correction(tmp_path, "TEST-ONLY-supersede-rag", supersede_auth)
    superseded_pin = protocol.pin_active_generation()
    assert superseded.activated is True
    assert "Revised Canon summary" in OwnedRAGView(
        superseded_pin, lambda _query: []).search("Revised", strategy="bm25")[0]["content"]
    assert OwnedStateStore(tmp_path).read_view(superseded_pin)["protagonist_state"]["realm"] == "Corrected"


def test_activation_composes_prior_active_corrections_in_other_chapters(tmp_path):
    from data_modules.canon_correction_store import activate_correction

    commits = _active_root(tmp_path, chapters=2)
    first_auth = _stage_retract(tmp_path, 1, commits[0][0], "TEST-ONLY-first-chapter")
    first = activate_correction(tmp_path, "TEST-ONLY-first-chapter", first_auth)
    second_auth = _stage_retract(tmp_path, 2, commits[1][0], "TEST-ONLY-second-chapter")
    second = activate_correction(tmp_path, "TEST-ONLY-second-chapter", second_auth)
    active = EffectiveHistoryStore().read_active_snapshot(tmp_path)
    assert active.chapters[1].status == "retracted"
    assert active.chapters[2].status == "retracted"
    assert second.publication_record_id != first.publication_record_id


def test_activation_rejects_wrong_or_rejected_authorization_without_publication(tmp_path):
    from data_modules.canon_correction_store import activate_correction

    commits = _active_root(tmp_path, chapters=1)
    authorization = _stage_retract(tmp_path, 1, commits[0][0], "TEST-ONLY-wrong-auth")
    head = ProjectionGeneration(tmp_path).latest_publication()
    with pytest.raises(CorrectionStoreError, match="AUTHORIZATION_ARTIFACT_MISMATCH"):
        activate_correction(tmp_path, "TEST-ONLY-wrong-auth", {**authorization.model_dump(mode="json"), "choice": "REJECT"})
    assert ProjectionGeneration(tmp_path).latest_publication().record_sha256 == head.record_sha256
    assert EffectiveHistoryStore().read_active_snapshot(tmp_path).chapters[1].status == "accepted"


def test_failed_generation_writer_keeps_active_publication_and_candidate_staged(tmp_path, monkeypatch):
    from data_modules import projection_rebuild
    from data_modules.canon_correction_store import activate_correction

    commits = _active_root(tmp_path, chapters=1)
    authorization = _stage_retract(tmp_path, 1, commits[0][0], "TEST-ONLY-writer-failure")
    protocol = ProjectionGeneration(tmp_path)
    before = protocol.latest_publication()
    def fail_build(*_args, **_kwargs):
        raise RuntimeError("synthetic generation writer failure")
    monkeypatch.setattr(projection_rebuild, "build_effective_generation", fail_build)
    with pytest.raises(CorrectionStoreError, match="GENERATION_BUILD_FAILED"):
        activate_correction(tmp_path, "TEST-ONLY-writer-failure", authorization)
    assert protocol.latest_publication().record_sha256 == before.record_sha256
    assert EffectiveHistoryStore().read_active_snapshot(tmp_path).chapters[1].status == "accepted"
    assert EffectiveHistoryStore().resolve_candidate(tmp_path, "TEST-ONLY-writer-failure").ok


def test_candidate_namespace_change_during_build_prevents_publication(tmp_path, monkeypatch):
    from data_modules.canon_correction_store import activate_correction

    commits = _active_root(tmp_path, chapters=1)
    authorization = _stage_retract(tmp_path, 1, commits[0][0], "TEST-ONLY-racing-candidate")
    protocol = ProjectionGeneration(tmp_path)
    before = protocol.latest_publication()
    publish = ProjectionGeneration.publish_generation
    def append_candidate_then_publish(self, *args, **kwargs):
        correction_dir = next((tmp_path / ".story-system/corrections").glob("chapter_*/*/corrections"))
        (correction_dir / "late-candidate.json").write_text('{"late":true}', encoding="utf-8")
        return publish(self, *args, **kwargs)
    monkeypatch.setattr(ProjectionGeneration, "publish_generation", append_candidate_then_publish)
    with pytest.raises(CorrectionStoreError, match="ACTIVATION_PUBLICATION_FAILED"):
        activate_correction(tmp_path, "TEST-ONLY-racing-candidate", authorization)
    monkeypatch.setattr(ProjectionGeneration, "publish_generation", publish)
    assert protocol.latest_publication().record_sha256 == before.record_sha256
    assert EffectiveHistoryStore().read_active_snapshot(tmp_path).chapters[1].status == "accepted"


def test_activation_crash_after_record_creation_is_reported_as_published(tmp_path, monkeypatch):
    from data_modules.canon_correction_store import activate_correction

    commits = _active_root(tmp_path, chapters=1)
    authorization = _stage_retract(tmp_path, 1, commits[0][0], "TEST-ONLY-after-publish-crash")
    publish = ProjectionGeneration.publish_generation
    def publish_then_crash(self, *args, **kwargs):
        publish(self, *args, **kwargs)
        raise RuntimeError("synthetic crash after publication record")
    monkeypatch.setattr(ProjectionGeneration, "publish_generation", publish_then_crash)
    result = activate_correction(tmp_path, "TEST-ONLY-after-publish-crash", authorization)
    assert result.activated is True
    assert result.publication_record_id == "publication-00000002"
    assert EffectiveHistoryStore().read_active_snapshot(tmp_path).chapters[1].status == "retracted"


def test_activation_fails_closed_on_active_dependency_corruption(tmp_path):
    from data_modules.canon_correction_store import activate_correction

    commits = _active_root(tmp_path, chapters=1)
    authorization = _stage_retract(tmp_path, 1, commits[0][0], "TEST-ONLY-active-corruption")
    protocol = ProjectionGeneration(tmp_path)
    before = protocol.latest_publication()
    commits[0][1].write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(CorrectionStoreError, match="ACTIVE_PUBLICATION_INVALID"):
        activate_correction(tmp_path, "TEST-ONLY-active-corruption", authorization)
    assert protocol.latest_publication().record_sha256 == before.record_sha256


def test_candidate_conflict_blocks_only_activation_and_keeps_active_healthy(tmp_path):
    from data_modules.canon_correction_store import activate_correction
    from data_modules.owned_project_view import activation_health_report

    commits = _active_root(tmp_path, chapters=1)
    authorization = _stage_retract(tmp_path, 1, commits[0][0], "TEST-ONLY-candidate-conflict")
    correction_dir = next((tmp_path / ".story-system/corrections").glob("chapter_*/*/corrections"))
    original = json.loads((correction_dir / "TEST-ONLY-candidate-conflict.correction.json").read_text())
    (correction_dir / "TEST-ONLY-sibling.correction.json").write_text(
        json.dumps({**original, "correction_id": "TEST-ONLY-sibling"}), encoding="utf-8")
    before = ProjectionGeneration(tmp_path).latest_publication()
    with pytest.raises(CorrectionStoreError, match="CANDIDATE_BLOCKED"):
        activate_correction(tmp_path, "TEST-ONLY-candidate-conflict", authorization)
    assert ProjectionGeneration(tmp_path).latest_publication().record_sha256 == before.record_sha256
    assert activation_health_report(tmp_path)["active_status"] == "valid"


def test_competing_publication_of_same_candidate_is_detected_as_success(tmp_path, monkeypatch):
    from data_modules.canon_correction_store import activate_correction

    commits = _active_root(tmp_path, chapters=1)
    authorization = _stage_retract(tmp_path, 1, commits[0][0], "TEST-ONLY-publication-race")
    publish = ProjectionGeneration.publish_generation
    calls = {"count": 0}
    def competing_publish(self, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            publish(self, *args, **kwargs)
        return publish(self, *args, **kwargs)
    monkeypatch.setattr(ProjectionGeneration, "publish_generation", competing_publish)
    result = activate_correction(tmp_path, "TEST-ONLY-publication-race", authorization)
    assert result.activated is True
    assert len(ProjectionGeneration(tmp_path)._records()) == 2
    assert EffectiveHistoryStore().read_active_snapshot(tmp_path).chapters[1].status == "retracted"


def test_confirmation_workflow_cli_activates_using_exact_persisted_authorization(tmp_path, capsys):
    from data_modules.canon_correction_workflow import main

    commits = _active_root(tmp_path, chapters=1)
    authorization = _stage_retract(tmp_path, 1, commits[0][0], "TEST-ONLY-cli-activation")
    auth_file = tmp_path / "authorization.json"
    auth_file.write_text(json.dumps(authorization.model_dump(mode="json")), encoding="utf-8")
    code = main(["--project-root", str(tmp_path), "activate", "--correction-id",
                 "TEST-ONLY-cli-activation", "--authorization-file", str(auth_file)])
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["ok"] is True
    assert result["activated"] is True
    assert EffectiveHistoryStore().read_active_snapshot(tmp_path).chapters[1].status == "retracted"
