import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from data_modules.canon_correction_schema import (
    artifact_sha256, base_commit_digest, canonical_json, effective_content_digest,
    request_sha256,
)
from data_modules.canon_correction_store import (
    append_correction_request, append_correction_authorization,
    append_correction, correction_target_dir, CorrectionStoreError,
    VerifiedCorrectionDecision,
)


def commit():
    return {"meta": {"schema_version": "story-system/v1", "chapter": 3, "status": "accepted"},
            "review_result": {"blocking_count": 0},
            "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
            "disambiguation_result": {"pending": []},
            "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": []}}


def setup_base(root):
    base = commit()
    path = root / ".story-system/commits/chapter_003.commit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(base), encoding="utf-8")
    return base


def request(base):
    digest = base_commit_digest(base)
    extraction = base["extraction_result"]
    return {"schema_version": "canon-correction-request/v1", "request_id": "r1", "chapter": 3,
            "base_commit_sha256": digest, "parent_revision_id": f"base:{digest}",
            "parent_effective_content_sha256": effective_content_digest("accepted", extraction),
            "operation": "AMEND", "proposed_effective_status": "accepted",
            "proposed_effective_extraction_result": extraction,
            "proposed_effective_content_sha256": effective_content_digest("accepted", extraction),
            "changed_paths": [], "proposer_provenance": {}, "reason": "correction"}


def _path_change(before, after):
    absent = {"$canon": "absent"}
    before_value = absent if before is None else before
    after_value = absent if after is None else after
    return {"path": "/summary_text",
            "before_sha256": hashlib.sha256(canonical_json(before_value).encode()).hexdigest(),
            "after_sha256": hashlib.sha256(canonical_json(after_value).encode()).hexdigest()}


def _amend_request(base, request_id, parent_revision_id, parent_status, parent_extraction,
                   new_summary):
    digest = base_commit_digest(base)
    prior_extraction = parent_extraction or base["extraction_result"]
    before = prior_extraction.get("summary_text")
    extraction = {**prior_extraction, "summary_text": new_summary}
    return {
        "schema_version": "canon-correction-request/v1", "request_id": request_id,
        "chapter": base["meta"]["chapter"], "base_commit_sha256": digest,
        "parent_revision_id": parent_revision_id,
        "parent_effective_content_sha256": effective_content_digest(parent_status, parent_extraction),
        "operation": "AMEND", "proposed_effective_status": "accepted",
        "proposed_effective_extraction_result": extraction,
        "proposed_effective_content_sha256": effective_content_digest("accepted", extraction),
        "changed_paths": [_path_change(before, new_summary)],
        "proposer_provenance": {"fixture": "test-only"}, "reason": "amend summary"}


def _append_test_correction(root, base, *, request_id, correction_id, authorization_id,
                            parent_revision_id, parent_status, parent_extraction,
                            operation="AMEND", new_summary=None, prior_verifications=()):
    digest = base_commit_digest(base)
    if operation == "AMEND":
        req = _amend_request(base, request_id, parent_revision_id, parent_status,
                             parent_extraction, new_summary)
    elif operation == "RETRACT":
        req = {"schema_version": "canon-correction-request/v1", "request_id": request_id,
               "chapter": base["meta"]["chapter"], "base_commit_sha256": digest,
               "parent_revision_id": parent_revision_id,
               "parent_effective_content_sha256": effective_content_digest(parent_status, parent_extraction),
               "operation": "RETRACT", "proposed_effective_status": "retracted",
               "proposed_effective_extraction_result": None,
               "proposed_effective_content_sha256": effective_content_digest("retracted", None),
               "changed_paths": [], "proposer_provenance": {"fixture": "test-only"},
               "reason": "retract"}
    else:
        req = {"schema_version": "canon-correction-request/v1", "request_id": request_id,
               "chapter": base["meta"]["chapter"], "base_commit_sha256": digest,
               "parent_revision_id": parent_revision_id,
               "parent_effective_content_sha256": effective_content_digest(parent_status, parent_extraction),
               "operation": "SUPERSEDE", "proposed_effective_status": "accepted",
               "proposed_effective_extraction_result": parent_extraction or base["extraction_result"],
               "proposed_effective_content_sha256": effective_content_digest(
                   "accepted", parent_extraction or base["extraction_result"]),
               "changed_paths": [], "proposer_provenance": {"fixture": "test-only"},
               "reason": "supersede"}
    append_correction_request(root, req, decision_verifications=prior_verifications)
    auth = {"schema_version": "canon-correction-authorization/v1",
            "authorization_id": authorization_id, "request_id": request_id,
            "request_sha256": request_sha256(req), "choice": "APPROVE",
            "actor_ref": "test-fixture", "decision_provenance": {"test_only": True}}
    append_correction_authorization(root, auth)
    auth_digest = artifact_sha256(auth)
    verification = VerifiedCorrectionDecision(
        f"verify-{request_id}", request_sha256(req), auth_digest,
        "test-fixture-only", "VERIFIED_APPROVE")
    result_extraction = req["proposed_effective_extraction_result"]
    correction = {"schema_version": "canon-correction/v1", "correction_id": correction_id,
                  "chapter": req["chapter"], "base_commit_sha256": digest,
                  "parent_revision_id": req["parent_revision_id"],
                  "parent_effective_content_sha256": req["parent_effective_content_sha256"],
                  "operation": operation,
                  "effective_extraction_result": result_extraction if operation != "RETRACT" else None,
                  "changed_paths": req["changed_paths"], "request_sha256": request_sha256(req),
                  "authorization_ref": authorization_id, "authorization_sha256": auth_digest,
                  "provenance": {"test_only": True}, "actor_ref": "test-fixture",
                  "reason": req["reason"]}
    decisions = (*prior_verifications, verification)
    saved = append_correction(root, correction, request=req, authorization=auth,
                              decision_verifications=decisions)
    return req, auth, verification, saved


def _prepare_candidate(root, base, req, *, correction_id, authorization_id,
                       prior_verifications=()):
    append_correction_request(root, req, decision_verifications=prior_verifications)
    auth = {"schema_version": "canon-correction-authorization/v1",
            "authorization_id": authorization_id, "request_id": req["request_id"],
            "request_sha256": request_sha256(req), "choice": "APPROVE",
            "actor_ref": "test-fixture", "decision_provenance": {"test_only": True}}
    append_correction_authorization(root, auth)
    auth_digest = artifact_sha256(auth)
    verification = VerifiedCorrectionDecision(
        f"verify-{req['request_id']}", request_sha256(req), auth_digest,
        "test-fixture-only", "VERIFIED_APPROVE")
    corr = {"schema_version": "canon-correction/v1", "correction_id": correction_id,
            "chapter": req["chapter"], "base_commit_sha256": req["base_commit_sha256"],
            "parent_revision_id": req["parent_revision_id"],
            "parent_effective_content_sha256": req["parent_effective_content_sha256"],
            "operation": req["operation"],
            "effective_extraction_result": req["proposed_effective_extraction_result"],
            "changed_paths": req["changed_paths"], "request_sha256": request_sha256(req),
            "authorization_ref": authorization_id, "authorization_sha256": auth_digest,
            "provenance": {"test_only": True}, "actor_ref": "test-fixture", "reason": req["reason"]}
    return corr, auth, verification, (*prior_verifications, verification)


def test_request_is_immutable_retryable_and_conflicts_on_id_reuse(tmp_path):
    base = setup_base(tmp_path)
    commit_path = tmp_path / ".story-system/commits/chapter_003.commit.json"
    base_bytes = commit_path.read_bytes()
    req = request(base)
    saved = append_correction_request(tmp_path, req)
    assert saved == append_correction_request(tmp_path, req)
    path = correction_target_dir(tmp_path, 3, req["base_commit_sha256"]) / "requests/r1.request.json"
    original = path.read_bytes()
    with pytest.raises(CorrectionStoreError, match="ID_CONFLICT"):
        append_correction_request(tmp_path, {**req, "reason": "different"})
    assert path.read_bytes() == original
    assert commit_path.read_bytes() == base_bytes


def test_authorization_is_one_request_one_decision_and_never_writes_correction(tmp_path):
    base = setup_base(tmp_path)
    req = request(base)
    append_correction_request(tmp_path, req)
    auth = {"schema_version": "canon-correction-authorization/v1", "authorization_id": "a1",
            "request_id": "r1", "request_sha256": request_sha256(req), "choice": "APPROVE",
            "actor_ref": "human", "decision_provenance": {"source": "arbitrary"}}
    append_correction_authorization(tmp_path, auth)
    assert append_correction_authorization(tmp_path, auth)
    with pytest.raises(CorrectionStoreError, match="AUTHORIZATION_CONFLICT"):
        append_correction_authorization(tmp_path, {**auth, "authorization_id": "a2", "choice": "REJECT"})
    target = correction_target_dir(tmp_path, 3, req["base_commit_sha256"])
    assert list((target / "corrections").glob("*.correction.json")) == []


def test_rejects_cross_request_binding_and_path_unsafe_ids(tmp_path):
    base = setup_base(tmp_path)
    req = request(base)
    append_correction_request(tmp_path, req)
    auth = {"schema_version": "canon-correction-authorization/v1", "authorization_id": "a1",
            "request_id": "r1", "request_sha256": "0" * 64, "choice": "APPROVE",
            "actor_ref": "human", "decision_provenance": {}}
    with pytest.raises(CorrectionStoreError):
        append_correction_authorization(tmp_path, auth)
    with pytest.raises(CorrectionStoreError):
        append_correction_request(tmp_path, {**req, "request_id": "../outside"})


def test_concurrent_distinct_authorizations_store_one_decision(tmp_path):
    base = setup_base(tmp_path)
    req = request(base)
    append_correction_request(tmp_path, req)
    def auth(auth_id, choice):
        return {"schema_version": "canon-correction-authorization/v1", "authorization_id": auth_id,
                "request_id": "r1", "request_sha256": request_sha256(req), "choice": choice,
                "actor_ref": "human", "decision_provenance": {"fixture": "assertion-only"}}
    values = [auth("approve", "APPROVE"), auth("reject", "REJECT")]
    def append(value):
        try:
            append_correction_authorization(tmp_path, value)
            return "stored"
        except CorrectionStoreError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(append, values))
    assert sum(item == "stored" for item in outcomes) == 1
    assert sum("AUTHORIZATION_CONFLICT" in item for item in outcomes) == 1


def test_append_authorized_correction_requires_typed_verification(tmp_path):
    base = setup_base(tmp_path)
    req = request(base)
    req["operation"] = "SUPERSEDE"
    append_correction_request(tmp_path, req)
    auth = {"schema_version": "canon-correction-authorization/v1", "authorization_id": "a1",
            "request_id": "r1", "request_sha256": request_sha256(req), "choice": "APPROVE",
            "actor_ref": "human", "decision_provenance": {}}
    append_correction_authorization(tmp_path, auth)
    auth_digest = __import__("data_modules.canon_correction_schema", fromlist=["authorization_sha256"]).authorization_sha256(auth)
    correction = {"schema_version": "canon-correction/v1", "correction_id": "c1", "chapter": 3,
                  "base_commit_sha256": req["base_commit_sha256"], "parent_revision_id": req["parent_revision_id"],
                  "parent_effective_content_sha256": req["parent_effective_content_sha256"],
                  "operation": "SUPERSEDE", "effective_extraction_result": req["proposed_effective_extraction_result"],
                  "changed_paths": [], "request_sha256": request_sha256(req), "authorization_ref": "a1",
                  "authorization_sha256": auth_digest, "provenance": {}, "actor_ref": "writer", "reason": "fix"}
    target = correction_target_dir(tmp_path, 3, req["base_commit_sha256"])
    final_path = target / "corrections/c1.correction.json"
    with pytest.raises(CorrectionStoreError, match="HUMAN_AUTHORITY_UNVERIFIED"):
        append_correction(tmp_path, correction, request=req, authorization=auth, decision_verifications=[])
    assert not final_path.exists()
    with pytest.raises(CorrectionStoreError):
        append_correction(tmp_path, correction, request=req, authorization=auth,
                          decision_verifications=[{"request_sha256": request_sha256(req)}])
    assert not final_path.exists()
    verification = VerifiedCorrectionDecision("fixture-v1", request_sha256(req), auth_digest,
                                               "test-fixture", "VERIFIED_APPROVE")
    mismatched = VerifiedCorrectionDecision("fixture-wrong", "f" * 64, auth_digest,
                                             "test-fixture", "VERIFIED_APPROVE")
    with pytest.raises(CorrectionStoreError, match="HUMAN_AUTHORITY_UNVERIFIED"):
        append_correction(tmp_path, correction, request=req, authorization=auth,
                          decision_verifications=[mismatched])
    duplicate = VerifiedCorrectionDecision("fixture-duplicate", request_sha256(req), auth_digest,
                                            "test-fixture", "VERIFIED_APPROVE")
    with pytest.raises(CorrectionStoreError, match="HUMAN_AUTHORITY_CONFLICT"):
        append_correction(tmp_path, correction, request=req, authorization=auth,
                          decision_verifications=[verification, duplicate])
    assert not final_path.exists()
    tampered = dict(correction, effective_extraction_result={**correction["effective_extraction_result"], "summary_text": "changed after approval"})
    with pytest.raises(CorrectionStoreError, match="REQUEST_AUTHORIZATION_MISMATCH"):
        append_correction(tmp_path, tampered, request=req, authorization=auth,
                          decision_verifications=[verification])
    assert not final_path.exists()
    assert append_correction(tmp_path, correction, request=req, authorization=auth,
                             decision_verifications=[verification])
    assert append_correction(tmp_path, correction, request=req, authorization=auth,
                             decision_verifications=[verification])
    original = final_path.read_bytes()
    with pytest.raises(CorrectionStoreError, match="ID_CONFLICT"):
        append_correction(tmp_path, {**correction, "reason": "different"}, request=req,
                          authorization=auth, decision_verifications=[verification])
    assert final_path.read_bytes() == original


def test_proposal_and_runtime_producers_do_not_import_final_correction_writer():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    guarded = [
        root / "override_ledger_service.py", root / "chapter_commit_service.py",
        root / "projection_rebuild.py", root / "story_runtime_sources.py",
        root / "reconciliation.py", root / "gate_findings.py",
    ]
    for path in guarded:
        source = path.read_text(encoding="utf-8")
        assert "canon_correction_store" not in source
        assert "append_correction(" not in source


def test_concurrent_final_appends_have_one_success_and_one_stale_parent(tmp_path):
    base = setup_base(tmp_path)
    base_bytes = (tmp_path / ".story-system/commits/chapter_003.commit.json").read_bytes()
    bundles = []
    from data_modules.canon_correction_schema import authorization_sha256
    for index in (1, 2):
        req = request(base)
        req["request_id"] = f"race-r{index}"
        req["operation"] = "SUPERSEDE"
        append_correction_request(tmp_path, req)
        auth = {"schema_version": "canon-correction-authorization/v1", "authorization_id": f"race-a{index}",
                "request_id": req["request_id"], "request_sha256": request_sha256(req), "choice": "APPROVE",
                "actor_ref": "human", "decision_provenance": {}}
        append_correction_authorization(tmp_path, auth)
        verification = VerifiedCorrectionDecision(f"race-v{index}", request_sha256(req),
            authorization_sha256(auth), "test-only", "VERIFIED_APPROVE")
        corr = {"schema_version": "canon-correction/v1", "correction_id": f"race-c{index}", "chapter": 3,
                "base_commit_sha256": req["base_commit_sha256"], "parent_revision_id": req["parent_revision_id"],
                "parent_effective_content_sha256": req["parent_effective_content_sha256"],
                "operation": "SUPERSEDE", "effective_extraction_result": req["proposed_effective_extraction_result"],
                "changed_paths": [], "request_sha256": request_sha256(req), "authorization_ref": auth["authorization_id"],
                "authorization_sha256": authorization_sha256(auth), "provenance": {}, "actor_ref": "writer", "reason": "race"}
        bundles.append((corr, req, auth, verification))
    def append(bundle):
        try:
            append_correction(tmp_path, bundle[0], request=bundle[1], authorization=bundle[2],
                              decision_verifications=[item[3] for item in bundles])
            return "ok"
        except CorrectionStoreError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(append, bundles))
    assert outcomes.count("ok") == 1
    assert sum("STALE_PARENT" in item for item in outcomes) == 1
    target = correction_target_dir(tmp_path, 3, bundles[0][1]["base_commit_sha256"])
    assert len(list((target / "corrections").glob("*.correction.json"))) == 1
    assert (tmp_path / ".story-system/commits/chapter_003.commit.json").read_bytes() == base_bytes


def test_public_store_apis_persist_two_amends_and_retry_old_request_after_tip_advances(tmp_path):
    from data_modules.canon_correction_resolver import resolve_effective_history

    base = setup_base(tmp_path)
    digest = base_commit_digest(base)
    first_req, _, first_verification, _ = _append_test_correction(
        tmp_path, base, request_id="chain-r1", correction_id="chain-c1", authorization_id="chain-a1",
        parent_revision_id=f"base:{digest}", parent_status="accepted",
        parent_extraction=base["extraction_result"], new_summary="first")
    first_revision = f"correction:{digest}:chain-c1"
    first_extraction = first_req["proposed_effective_extraction_result"]
    second_req, _, second_verification, _ = _append_test_correction(
        tmp_path, base, request_id="chain-r2", correction_id="chain-c2", authorization_id="chain-a2",
        parent_revision_id=first_revision, parent_status="accepted", parent_extraction=first_extraction,
        new_summary="second", prior_verifications=(first_verification,))
    assert second_req["parent_revision_id"] == first_revision
    assert second_req["parent_effective_content_sha256"] == effective_content_digest("accepted", first_extraction)

    # Exact request retry stays idempotent even though the active tip has moved.
    assert append_correction_request(tmp_path, first_req) == append_correction_request(tmp_path, first_req)
    with pytest.raises(CorrectionStoreError, match="ID_CONFLICT"):
        append_correction_request(tmp_path, {**first_req, "reason": "different body"})

    target = correction_target_dir(tmp_path, 3, digest)
    corrections = [json.loads(p.read_text()) for p in sorted((target / "corrections").glob("*.correction.json"))]
    requests = [json.loads(p.read_text()) for p in sorted((target / "requests").glob("*.request.json"))]
    authorizations = [json.loads(p.read_text()) for p in sorted((target / "authorizations").glob("*.authorization.json"))]
    resolved = resolve_effective_history(base, corrections, requests, authorizations,
                                         [first_verification, second_verification])
    assert resolved.ok is True
    assert resolved.applied_correction_ids == ("chain-c1", "chain-c2")
    assert resolved.effective_extraction_result["summary_text"] == "second"


def test_public_store_apis_allow_retract_then_supersede_and_reject_stale_request(tmp_path):
    from data_modules.canon_correction_resolver import resolve_effective_history

    base = setup_base(tmp_path)
    digest = base_commit_digest(base)
    retract_req, _, retract_verification, _ = _append_test_correction(
        tmp_path, base, request_id="recover-r1", correction_id="recover-c1", authorization_id="recover-a1",
        parent_revision_id=f"base:{digest}", parent_status="accepted",
        parent_extraction=base["extraction_result"], operation="RETRACT")
    retract_revision = f"correction:{digest}:recover-c1"
    retract_req_digest = effective_content_digest("retracted", None)
    stale = request(base)
    stale["request_id"] = "stale-after-retract"
    with pytest.raises(CorrectionStoreError, match="STALE_PARENT"):
        append_correction_request(tmp_path, stale, decision_verifications=(retract_verification,))
    stale_path = correction_target_dir(tmp_path, 3, digest) / "requests/stale-after-retract.request.json"
    assert not stale_path.exists()

    _, _, supersede_verification, _ = _append_test_correction(
        tmp_path, base, request_id="recover-r2", correction_id="recover-c2", authorization_id="recover-a2",
        parent_revision_id=retract_revision, parent_status="retracted", parent_extraction=None,
        operation="SUPERSEDE", prior_verifications=(retract_verification,))
    target = correction_target_dir(tmp_path, 3, digest)
    corrections = [json.loads(p.read_text()) for p in sorted((target / "corrections").glob("*.correction.json"))]
    requests = [json.loads(p.read_text()) for p in sorted((target / "requests").glob("*.request.json"))]
    authorizations = [json.loads(p.read_text()) for p in sorted((target / "authorizations").glob("*.authorization.json"))]
    resolved = resolve_effective_history(base, corrections, requests, authorizations,
                                         [retract_verification, supersede_verification])
    assert resolved.ok is True
    assert resolved.applied_correction_ids == ("recover-c1", "recover-c2")
    assert resolved.effective_status == "accepted"
    assert resolved.effective_content_sha256 != retract_req_digest
    assert resolved.effective_extraction_result == base["extraction_result"]


@pytest.mark.parametrize("bad_kind", ["unchanged", "bad_changed_path_digest", "replaces_all_fields"])
def test_final_append_rejects_invalid_amend_semantics_before_correction_write(tmp_path, bad_kind):
    base = setup_base(tmp_path)
    digest = base_commit_digest(base)
    if bad_kind == "unchanged":
        req = request(base)
        req["request_id"] = "bad-unchanged"
    elif bad_kind == "bad_changed_path_digest":
        req = _amend_request(base, "bad-digest", f"base:{digest}", "accepted",
                             base["extraction_result"], "changed")
        req["changed_paths"][0]["after_sha256"] = "0" * 64
    else:
        from data_modules.canon_correction_resolver import _structural_changes

        original = base["extraction_result"]
        replacement = {
            "accepted_events": [{"changed": "x"}], "state_deltas": [{"changed": "x"}],
            "entity_deltas": [{"changed": "x"}], "entities_appeared": [{"changed": "x"}],
            "scenes": [{"changed": "x"}], "chapter_meta": {"changed": "x"},
            "dominant_strand": "changed", "summary_text": "changed",
        }
        changed_paths = _structural_changes(original, replacement)
        req = _amend_request(base, "bad-all-fields", f"base:{digest}", "accepted",
                             original, "changed")
        req["proposed_effective_extraction_result"] = replacement
        req["proposed_effective_content_sha256"] = effective_content_digest("accepted", replacement)
        req["changed_paths"] = changed_paths

    correction, auth, verification, decisions = _prepare_candidate(
        tmp_path, base, req, correction_id=f"corr-{bad_kind}", authorization_id=f"auth-{bad_kind}")
    final_path = correction_target_dir(tmp_path, 3, digest) / f"corrections/{correction['correction_id']}.correction.json"
    expected = "AMEND_REPLACES_ALL_CANONICAL_FIELDS" if bad_kind == "replaces_all_fields" else "AMEND_CHANGED_PATHS_MISMATCH"
    with pytest.raises(CorrectionStoreError, match=expected):
        append_correction(tmp_path, correction, request=req, authorization=auth,
                          decision_verifications=decisions)
    assert not final_path.exists()


def test_final_append_rejects_illegal_transition_before_correction_write(tmp_path):
    base = setup_base(tmp_path)
    digest = base_commit_digest(base)
    _, _, retract_verification, _ = _append_test_correction(
        tmp_path, base, request_id="transition-r1", correction_id="transition-c1",
        authorization_id="transition-a1", parent_revision_id=f"base:{digest}",
        parent_status="accepted", parent_extraction=base["extraction_result"], operation="RETRACT")
    parent = f"correction:{digest}:transition-c1"
    req = _amend_request(base, "transition-r2", parent, "retracted", None, "illegal")
    correction, auth, _, decisions = _prepare_candidate(
        tmp_path, base, req, correction_id="transition-c2", authorization_id="transition-a2",
        prior_verifications=(retract_verification,))
    final_path = correction_target_dir(tmp_path, 3, digest) / "corrections/transition-c2.correction.json"
    with pytest.raises(CorrectionStoreError, match="INVALID_OPERATION_TRANSITION"):
        append_correction(tmp_path, correction, request=req, authorization=auth,
                          decision_verifications=decisions)
    assert not final_path.exists()


def test_valid_amend_is_semantically_validated_before_write_and_resolves_same_tip(tmp_path):
    from data_modules.canon_correction_resolver import resolve_effective_history

    base = setup_base(tmp_path)
    digest = base_commit_digest(base)
    req = _amend_request(base, "valid-amend-r1", f"base:{digest}", "accepted",
                         base["extraction_result"], "accepted edit")
    correction, auth, verification, decisions = _prepare_candidate(
        tmp_path, base, req, correction_id="valid-amend-c1", authorization_id="valid-amend-a1")
    saved = append_correction(tmp_path, correction, request=req, authorization=auth,
                              decision_verifications=decisions)
    target = correction_target_dir(tmp_path, 3, digest)
    corrections = [json.loads(p.read_text()) for p in (target / "corrections").glob("*.correction.json")]
    requests = [json.loads(p.read_text()) for p in (target / "requests").glob("*.request.json")]
    authorizations = [json.loads(p.read_text()) for p in (target / "authorizations").glob("*.authorization.json")]
    resolved = resolve_effective_history(base, corrections, requests, authorizations, [verification])
    assert resolved.ok is True
    assert resolved.effective_revision_id == f"correction:{digest}:{saved.correction_id}"
    assert resolved.applied_correction_ids == (saved.correction_id,)
    assert resolved.effective_extraction_result == req["proposed_effective_extraction_result"]


def test_final_append_refuses_preexisting_authorization_conflict_without_correction_write(tmp_path):
    base = setup_base(tmp_path)
    req = request(base); req["operation"] = "SUPERSEDE"
    append_correction_request(tmp_path, req)
    from data_modules.canon_correction_schema import authorization_sha256
    auth = {"schema_version": "canon-correction-authorization/v1", "authorization_id": "conflict-a1",
            "request_id": req["request_id"], "request_sha256": request_sha256(req), "choice": "APPROVE",
            "actor_ref": "human", "decision_provenance": {}}
    append_correction_authorization(tmp_path, auth)
    req_dir = correction_target_dir(tmp_path, 3, req["base_commit_sha256"])
    second = {**auth, "authorization_id": "conflict-a2", "choice": "REJECT"}
    path = req_dir / "authorizations/conflict-a2.authorization.json"
    path.write_text(json.dumps(second), encoding="utf-8")
    correction = {"schema_version": "canon-correction/v1", "correction_id": "conflict-c", "chapter": 3,
                  "base_commit_sha256": req["base_commit_sha256"], "parent_revision_id": req["parent_revision_id"],
                  "parent_effective_content_sha256": req["parent_effective_content_sha256"],
                  "operation": "SUPERSEDE", "effective_extraction_result": req["proposed_effective_extraction_result"],
                  "changed_paths": [], "request_sha256": request_sha256(req), "authorization_ref": auth["authorization_id"],
                  "authorization_sha256": authorization_sha256(auth), "provenance": {}, "actor_ref": "writer", "reason": "conflict"}
    verification = VerifiedCorrectionDecision("conflict-test", request_sha256(req), authorization_sha256(auth),
                                               "test-only", "VERIFIED_APPROVE")
    with pytest.raises(CorrectionStoreError, match="AUTHORIZATION_CONFLICT"):
        append_correction(tmp_path, correction, request=req, authorization=auth,
                          decision_verifications=[verification])
    assert list((req_dir / "corrections").glob("*.correction.json")) == []
