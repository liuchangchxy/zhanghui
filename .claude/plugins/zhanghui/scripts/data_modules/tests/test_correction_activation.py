import json
import sqlite3

import pytest

from data_modules.canon_correction_schema import (
    artifact_sha256, base_commit_digest, effective_content_digest, request_sha256,
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
from data_modules.owned_project_view import OwnedProjectView
from data_modules.config import DataModulesConfig
from data_modules.context_manager import ContextManager


def _commit(chapter):
    return {
        "meta": {"schema_version": "story-system/v1", "chapter": chapter, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": [],
                              "chapter_meta": {"title": f"chapter {chapter}"}},
    }


def _active_root(root, chapters=2):
    commits = []
    for chapter in range(1, chapters + 1):
        body = _commit(chapter)
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


def _stage_retract(root, chapter, base, correction_id, *, interaction_id=None):
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
    append_correction_request(root, request)
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
                      decision_verifications=[decision])
    return authorization


def test_activation_publishes_only_after_complete_generation_and_keeps_owner_overlay(tmp_path, monkeypatch):
    from data_modules.canon_correction_store import activate_correction

    commits = _active_root(tmp_path, chapters=1)
    authorization = _stage_retract(tmp_path, 1, commits[0][0], "TEST-ONLY-activate")
    protocol = ProjectionGeneration(tmp_path)
    before = protocol.pin_active_generation()
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
