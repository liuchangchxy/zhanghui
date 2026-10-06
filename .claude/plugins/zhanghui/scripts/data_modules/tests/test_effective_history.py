import json
from dataclasses import replace
import hashlib

import pytest

from data_modules.canon_correction_schema import (
    artifact_sha256, base_commit_digest, canonical_json, effective_content_digest, request_sha256,
)
from data_modules.canon_correction_store import (
    append_correction, append_correction_request, build_correction_review_package,
    record_interactive_correction_decision, verify_phase9_correction_decision,
)
from data_modules.durable_projection import DurableCommitError
from data_modules.event_projection_router import EventProjectionRouter
from data_modules.projection_generation import ProjectionGeneration
from data_modules.effective_history import (
    EffectiveHistoryStore, EffectiveProjectionInput,
    validate_effective_projection_input,
)
from data_modules.event_log_store import EventLogStore
from data_modules.index_projection_writer import IndexProjectionWriter
from data_modules.memory_projection_writer import MemoryProjectionWriter
from data_modules.state_projection_writer import StateProjectionWriter
from data_modules.summary_projection_writer import SummaryProjectionWriter
from data_modules.vector_projection_writer import VectorProjectionWriter
from data_modules.projection_rebuild import build_effective_generation


def _commit(chapter=3):
    return {
        "meta": {"schema_version": "story-system/v1", "chapter": chapter, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": []},
    }


def _install_base(root, chapter=3):
    base = _commit(chapter)
    path = root / f".story-system/commits/chapter_{chapter:03d}.commit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(base), encoding="utf-8")
    return base


def _stage_amend_summary(root, base):
    digest = base_commit_digest(base)
    before = base["extraction_result"].get("summary_text")
    before_value = {"$canon": "absent"} if before is None else before
    extraction = {**base["extraction_result"], "summary_text": "corrected summary"}
    req = {
        "schema_version": "canon-correction-request/v1", "request_id": "TEST-ONLY-amend-request",
        "chapter": 3, "base_commit_sha256": digest, "parent_revision_id": f"base:{digest}",
        "parent_effective_content_sha256": effective_content_digest("accepted", base["extraction_result"]),
        "operation": "AMEND", "proposed_effective_status": "accepted",
        "proposed_effective_extraction_result": extraction,
        "proposed_effective_content_sha256": effective_content_digest("accepted", extraction),
        "changed_paths": [{
            "path": "/summary_text",
            "before_sha256": hashlib.sha256(canonical_json(before_value).encode()).hexdigest(),
            "after_sha256": hashlib.sha256(canonical_json("corrected summary").encode()).hexdigest(),
        }],
        "proposer_provenance": {"fixture": "TEST ONLY"}, "reason": "TEST ONLY",
    }
    append_correction_request(root, req)
    package = build_correction_review_package(req, parent_status="accepted",
                                               parent_extraction=base["extraction_result"])
    auth = record_interactive_correction_decision(
        root, req, package, choice="APPROVE", authorization_id="TEST-ONLY-amend-auth",
        interaction_id="TEST-ONLY-amend-interaction", interaction_surface="test fixture",
        confirmed_at="2026-10-06T00:00:00Z",
    )
    verified = verify_phase9_correction_decision(req, auth, package)
    correction = {
        "schema_version": "canon-correction/v1", "correction_id": "TEST-ONLY-amend",
        "chapter": 3, "base_commit_sha256": digest, "parent_revision_id": req["parent_revision_id"],
        "parent_effective_content_sha256": req["parent_effective_content_sha256"],
        "operation": "AMEND", "effective_extraction_result": extraction,
        "changed_paths": req["changed_paths"], "request_sha256": request_sha256(req),
        "authorization_ref": auth.authorization_id, "authorization_sha256": artifact_sha256(auth),
        "provenance": {"fixture": "TEST ONLY"}, "actor_ref": "TEST ONLY", "reason": "TEST ONLY",
    }
    append_correction(root, correction, request=req, authorization=auth,
                      decision_verifications=[verified])


def _stage_retract(root, base, suffix="retract", prior_verifications=()):
    digest = base_commit_digest(base)
    req = {
        "schema_version": "canon-correction-request/v1", "request_id": f"TEST-ONLY-{suffix}-request",
        "chapter": 3, "base_commit_sha256": digest, "parent_revision_id": f"base:{digest}",
        "parent_effective_content_sha256": effective_content_digest("accepted", base["extraction_result"]),
        "operation": "RETRACT", "proposed_effective_status": "retracted",
        "proposed_effective_extraction_result": None,
        "proposed_effective_content_sha256": effective_content_digest("retracted", None),
        "changed_paths": [], "proposer_provenance": {"fixture": "TEST ONLY"}, "reason": "TEST ONLY",
    }
    append_correction_request(root, req, decision_verifications=prior_verifications)
    package = build_correction_review_package(
        req, parent_status="accepted", parent_extraction=base["extraction_result"],
    )
    auth = record_interactive_correction_decision(
        root, req, package, choice="APPROVE", authorization_id=f"TEST-ONLY-{suffix}-auth",
        interaction_id=f"TEST-ONLY-{suffix}-interaction", interaction_surface="test fixture",
        confirmed_at="2026-10-06T00:00:00Z",
    )
    verified = verify_phase9_correction_decision(req, auth, package)
    correction = {
        "schema_version": "canon-correction/v1", "correction_id": f"TEST-ONLY-{suffix}",
        "chapter": 3, "base_commit_sha256": digest, "parent_revision_id": req["parent_revision_id"],
        "parent_effective_content_sha256": req["parent_effective_content_sha256"],
        "operation": "RETRACT", "effective_extraction_result": None, "changed_paths": [],
        "request_sha256": request_sha256(req), "authorization_ref": auth.authorization_id,
        "authorization_sha256": artifact_sha256(auth), "provenance": {"fixture": "TEST ONLY"},
        "actor_ref": "TEST ONLY", "reason": "TEST ONLY",
    }
    append_correction(root, correction, request=req, authorization=auth,
                      decision_verifications=[verified])
    return req, auth, package, verified


def test_staged_candidate_does_not_change_active_base_history(tmp_path):
    base = _install_base(tmp_path)
    store = EffectiveHistoryStore()
    before = store.read_active_snapshot(tmp_path)
    digest = base_commit_digest(base)
    req = {
        "schema_version": "canon-correction-request/v1", "request_id": "TEST-ONLY-pending",
        "chapter": 3, "base_commit_sha256": digest, "parent_revision_id": f"base:{digest}",
        "parent_effective_content_sha256": effective_content_digest("accepted", base["extraction_result"]),
        "operation": "RETRACT", "proposed_effective_status": "retracted",
        "proposed_effective_extraction_result": None,
        "proposed_effective_content_sha256": effective_content_digest("retracted", None),
        "changed_paths": [], "proposer_provenance": {"fixture": "TEST ONLY"}, "reason": "TEST ONLY",
    }
    append_correction_request(tmp_path, req)
    candidate = store.resolve_candidate(tmp_path, "missing-target")
    after = store.read_active_snapshot(tmp_path)
    assert not candidate.ok
    assert before.effective_history_digest == after.effective_history_digest
    assert before.chapters[3].status == "accepted"


def test_approved_staged_correction_is_candidate_until_publication(tmp_path):
    base = _install_base(tmp_path)
    store = EffectiveHistoryStore()
    active_before = store.read_active_snapshot(tmp_path)
    _stage_retract(tmp_path, base)
    candidate = store.resolve_candidate(tmp_path, "TEST-ONLY-retract")
    active_after = store.read_active_snapshot(tmp_path)
    assert candidate.ok
    assert candidate.chapters[3].status == "retracted"
    assert active_after.chapters[3].status == "accepted"
    assert active_after.effective_history_digest == active_before.effective_history_digest


def test_effective_projection_input_revalidates_disk_base_and_rejects_arbitrary_dict(tmp_path):
    base = _install_base(tmp_path)
    store = EffectiveHistoryStore()
    snapshot = store.read_active_snapshot(tmp_path)
    value = store.projection_input(snapshot, 3)
    assert validate_effective_projection_input(tmp_path, value) is value
    with pytest.raises(TypeError):
        validate_effective_projection_input(tmp_path, {"base_commit": base})
    path = tmp_path / ".story-system/commits/chapter_003.commit.json"
    changed = _commit()
    changed["extraction_result"]["summary_text"] = "tampered"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(DurableCommitError, match="BASE_COMMIT_MISMATCH"):
        validate_effective_projection_input(tmp_path, value)


def test_sibling_candidate_conflict_does_not_change_base_active_snapshot(tmp_path):
    base = _install_base(tmp_path)
    store = EffectiveHistoryStore()
    active_before = store.read_active_snapshot(tmp_path)
    _stage_retract(tmp_path, base, "first")
    correction_dir = next((tmp_path / ".story-system/corrections").glob("chapter_*/*/corrections"))
    original = json.loads((correction_dir / "TEST-ONLY-first.correction.json").read_text(encoding="utf-8"))
    sibling = {**original, "correction_id": "TEST-ONLY-sibling"}
    (correction_dir / "TEST-ONLY-sibling.correction.json").write_text(
        json.dumps(sibling), encoding="utf-8",
    )
    candidate = store.resolve_candidate(tmp_path, "TEST-ONLY-first")
    active_after = store.read_active_snapshot(tmp_path)
    assert not candidate.ok
    assert any("SIBLING" in item for item in candidate.diagnostics)
    assert active_after.effective_history_digest == active_before.effective_history_digest
    assert active_after.chapters[3].status == "accepted"


def test_publication_pins_exact_active_dependencies_and_corruption_fails_closed(tmp_path):
    _install_base(tmp_path)
    store = EffectiveHistoryStore()
    snapshot = store.read_active_snapshot(tmp_path)
    protocol = ProjectionGeneration(tmp_path)
    handle = protocol.begin(snapshot)
    expected = {"domains": {}}
    for domain in EventProjectionRouter.PROJECTION_MANIFEST:
        relative = f"{domain}/slice.json"
        data = json.dumps({"domain": domain}).encode()
        digest = handle.write_domain_file(domain, relative, data)
        expected["domains"][domain] = {relative: digest}
    validated = protocol.validate_generation(handle, expected)
    record = protocol.publish_generation(validated, None, snapshot.correction_lineage_digest)
    active = store.read_active_snapshot(tmp_path)
    assert active.ok
    assert active.activation_record_id == record.publication_record_id
    assert active.generation_id == validated.generation_id
    assert active.effective_history_digest == snapshot.effective_history_digest

    commit_path = tmp_path / ".story-system/commits/chapter_003.commit.json"
    commit_path.write_text("{}", encoding="utf-8")
    broken = store.read_active_snapshot(tmp_path)
    assert not broken.ok
    assert any("ACTIVE_DEPENDENCY_CORRUPT" in item for item in broken.diagnostics)


def test_all_projection_writers_require_typed_inputs_and_bind_one_generation(tmp_path):
    base = _install_base(tmp_path)
    store = EffectiveHistoryStore()
    snapshot = store.read_active_snapshot(tmp_path)
    effective_input = store.projection_input(snapshot, 3)
    writers = [
        EventLogStore(tmp_path), StateProjectionWriter(tmp_path), IndexProjectionWriter(tmp_path),
        SummaryProjectionWriter(tmp_path), MemoryProjectionWriter(tmp_path), VectorProjectionWriter(tmp_path),
    ]
    for writer in writers:
        with pytest.raises(TypeError):
            writer.apply_effective({"meta": {"chapter": 3}}, object())
    built = build_effective_generation(tmp_path, snapshot)
    assert len(built["results"]) == 7
    assert all(result["generation_id"] == built["generation_id"] for result in built["results"].values())
    assert json.loads((tmp_path / ".story-system/commits/chapter_003.commit.json").read_text()) == base
    generation = built["validated_generation"]
    assert len(generation.manifest["domains"]) == 7


def test_retract_generation_writes_explicit_tombstones_and_preserves_base(tmp_path):
    base = _install_base(tmp_path)
    _stage_retract(tmp_path, base)
    candidate = EffectiveHistoryStore().resolve_candidate(tmp_path, "TEST-ONLY-retract")
    assert candidate.ok
    built = build_effective_generation(tmp_path, candidate)
    assert len(built["results"]) == 7
    for domain in ("events", "state", "index", "summary", "memory", "vector", "intent_diagnostics"):
        path = built["validated_generation"].generation_root / domain / "chapter_003.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["effective_status"] == "retracted"
        assert data["projection"]["tombstone"] is True
    assert json.loads((tmp_path / ".story-system/commits/chapter_003.commit.json").read_text()) == base


def test_amend_generation_projects_corrected_content_without_mutating_base(tmp_path):
    base = _install_base(tmp_path)
    _stage_amend_summary(tmp_path, base)
    candidate = EffectiveHistoryStore().resolve_candidate(tmp_path, "TEST-ONLY-amend")
    assert candidate.ok
    built = build_effective_generation(tmp_path, candidate)
    for domain in ("events", "state", "index", "summary", "memory", "vector", "intent_diagnostics"):
        path = built["validated_generation"].generation_root / domain / "chapter_003.json"
        output = json.loads(path.read_text(encoding="utf-8"))
        assert output["effective_status"] == "accepted"
        assert output["projection"]["tombstone"] is False
        if domain == "summary":
            assert output["projection"]["summary_text"] == "corrected summary"
    assert json.loads((tmp_path / ".story-system/commits/chapter_003.commit.json").read_text()) == base


def test_projection_rejects_mutated_base_and_generation_digest_mismatch(tmp_path):
    import copy

    base = _install_base(tmp_path)
    store = EffectiveHistoryStore()
    snapshot = store.read_active_snapshot(tmp_path)
    writer = StateProjectionWriter(tmp_path)
    effective_input = store.projection_input(snapshot, 3)
    original = copy.deepcopy(effective_input.base_commit)
    effective_input.base_commit["meta"]["status"] = "rejected"
    handle = ProjectionGeneration(tmp_path).begin(snapshot)
    with pytest.raises(DurableCommitError, match="BASE_COMMIT_MISMATCH"):
        writer.apply_effective(effective_input, handle)
    effective_input.base_commit.clear()
    effective_input.base_commit.update(original)

    mismatched_snapshot = replace(snapshot, effective_history_digest="f" * 64)
    mismatched_handle = ProjectionGeneration(tmp_path).begin(mismatched_snapshot)
    with pytest.raises(DurableCommitError, match="EFFECTIVE_GENERATION_BINDING_MISMATCH"):
        writer.apply_effective(store.projection_input(snapshot, 3), mismatched_handle)
    assert json.loads((tmp_path / ".story-system/commits/chapter_003.commit.json").read_text()) == base
