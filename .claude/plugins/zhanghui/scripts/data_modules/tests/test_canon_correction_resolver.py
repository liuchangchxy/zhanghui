import json
import hashlib

import pytest

from data_modules.canon_correction_schema import (
    artifact_sha256, base_commit_digest, effective_content_digest, request_sha256, canonical_json,
)
from data_modules.canon_correction_store import VerifiedCorrectionDecision
from data_modules.canon_correction_resolver import validate_lineage, resolve_effective_history


def commit():
    extraction = {"accepted_events": [], "state_deltas": [], "entity_deltas": []}
    return {"meta": {"schema_version": "story-system/v1", "chapter": 3, "status": "accepted"},
            "review_result": {"blocking_count": 0},
            "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
            "disambiguation_result": {"pending": []}, "extraction_result": extraction}


def edge_fixtures():
    base = commit(); digest = base_commit_digest(base); extraction = base["extraction_result"]
    req = {"schema_version": "canon-correction-request/v1", "request_id": "r1", "chapter": 3,
           "base_commit_sha256": digest, "parent_revision_id": f"base:{digest}",
           "parent_effective_content_sha256": effective_content_digest("accepted", extraction),
           "operation": "SUPERSEDE", "proposed_effective_status": "accepted",
           "proposed_effective_extraction_result": extraction,
           "proposed_effective_content_sha256": effective_content_digest("accepted", extraction),
           "changed_paths": [], "proposer_provenance": {}, "reason": "fixture"}
    req_hash = request_sha256(req)
    auth = {"schema_version": "canon-correction-authorization/v1", "authorization_id": "a1",
            "request_id": "r1", "request_sha256": req_hash, "choice": "APPROVE",
            "actor_ref": "human", "decision_provenance": {}}
    auth_hash = artifact_sha256(auth)
    correction = {"schema_version": "canon-correction/v1", "correction_id": "c1", "chapter": 3,
                  "base_commit_sha256": digest, "parent_revision_id": f"base:{digest}",
                  "parent_effective_content_sha256": effective_content_digest("accepted", extraction),
                  "operation": "SUPERSEDE", "effective_extraction_result": extraction, "changed_paths": [],
                  "request_sha256": req_hash, "authorization_ref": "a1", "authorization_sha256": auth_hash,
                  "provenance": {}, "actor_ref": "writer", "reason": "fixture"}
    verification = VerifiedCorrectionDecision("test-v1", req_hash, auth_hash, "test-only", "VERIFIED_APPROVE")
    return base, correction, req, auth, verification


def test_lineage_base_only_is_clean_without_verification():
    result = validate_lineage(commit(), [], [], [], [])
    assert result.ok is True
    assert result.ordered_corrections == ()
    assert result.effective_revision_id.startswith("base:")


def test_lineage_requires_exact_typed_human_verification():
    base, edge, req, auth, verification = edge_fixtures()
    missing = validate_lineage(base, [edge], [req], [auth], [])
    assert "HUMAN_AUTHORITY_UNVERIFIED" in {item.code for item in missing.diagnostics}
    assert missing.ok is False and missing.effective_revision_id is None
    arbitrary = validate_lineage(base, [edge], [req], [auth], [{"request_sha256": edge["request_sha256"]}])
    assert arbitrary.ok is False
    assert "HUMAN_AUTHORITY_UNVERIFIED" in {item.code for item in arbitrary.diagnostics}
    valid = validate_lineage(base, [edge], [req], [auth], [verification])
    assert valid.ok is True
    assert [item["correction_id"] for item in valid.ordered_corrections] == ["c1"]
    assert validate_lineage(base, [edge], [req], [auth], [verification, verification]).diagnostics[0].code == "HUMAN_AUTHORITY_CONFLICT"


def test_lineage_sibling_is_conflict_independent_of_input_order_and_preserves_files():
    base, edge, req, auth, verification = edge_fixtures()
    sibling = dict(edge, correction_id="c2")
    before = (json.dumps(edge, sort_keys=True), json.dumps(sibling, sort_keys=True))
    results = [validate_lineage(base, [edge, sibling], [req], [auth], [verification]),
               validate_lineage(base, [sibling, edge], [req], [auth], [verification])]
    for result in results:
        assert result.ok is False and result.effective_revision_id is None
        assert "LINEAGE_SIBLING_CONFLICT" in {item.code for item in result.diagnostics}
    assert [item.code for item in results[0].diagnostics] == [item.code for item in results[1].diagnostics]
    assert before == (json.dumps(edge, sort_keys=True), json.dumps(sibling, sort_keys=True))


def test_lineage_reports_authorization_conflict_without_selecting_a_winner():
    base, edge, req, auth, verification = edge_fixtures()
    rejected = {**auth, "authorization_id": "a2", "choice": "REJECT"}
    result = validate_lineage(base, [edge], [req], [auth, rejected], [verification])
    assert result.ok is False and result.effective_revision_id is None
    assert "AUTHORIZATION_CONFLICT" in {item.code for item in result.diagnostics}


def test_lineage_artifact_permutations_produce_identical_order_and_diagnostics():
    base, edge, req, auth, verification = edge_fixtures()
    clone = dict(edge, correction_id="c2", parent_revision_id=f"correction:{edge['base_commit_sha256']}:c1")
    clone_req = dict(req, request_id="r2", parent_revision_id=f"correction:{edge['base_commit_sha256']}:c1")
    clone_auth = dict(auth, authorization_id="a2", request_id="r2", request_sha256=request_sha256(clone_req))
    clone["request_sha256"] = request_sha256(clone_req)
    clone["authorization_ref"] = "a2"
    clone["authorization_sha256"] = artifact_sha256(clone_auth)
    clone_verification = VerifiedCorrectionDecision("test-v2", clone["request_sha256"],
                                                      clone["authorization_sha256"], "test-only", "VERIFIED_APPROVE")
    first = validate_lineage(base, [edge, clone], [req, clone_req], [auth, clone_auth], [verification, clone_verification])
    second = validate_lineage(base, [clone, edge], [clone_req, req], [clone_auth, auth], [clone_verification, verification])
    assert first.ok is True and second.ok is True
    assert first.ordered_corrections == second.ordered_corrections
    assert first.revision_ids == second.revision_ids
    assert first.diagnostics == second.diagnostics == ()


def test_lineage_rejects_rejected_base_missing_parent_and_cycles():
    base, edge, req, auth, verification = edge_fixtures()
    rejected = json.loads(json.dumps(base)); rejected["meta"]["status"] = "rejected"
    assert "INVALID_BASE" in {item.code for item in validate_lineage(rejected, [edge], [req], [auth], [verification]).diagnostics}
    missing_parent = f"correction:{edge['base_commit_sha256']}:absent"
    missing_req = dict(req, parent_revision_id=missing_parent)
    missing_req_digest = request_sha256(missing_req)
    missing_auth = dict(auth, request_sha256=missing_req_digest)
    missing_auth_digest = artifact_sha256(missing_auth)
    missing = dict(edge, parent_revision_id=missing_parent, request_sha256=missing_req_digest,
                   authorization_sha256=missing_auth_digest)
    result = validate_lineage(base, [missing], [missing_req], [missing_auth],
        [VerifiedCorrectionDecision("missing-parent", missing_req_digest, missing_auth_digest, "test-only", "VERIFIED_APPROVE")])
    assert "LINEAGE_DISCONNECTED" in {item.code for item in result.diagnostics}

    digest = edge["base_commit_sha256"]
    content = effective_content_digest("accepted", base["extraction_result"])
    edges, requests, authorizations, verifications = [], [], [], []
    for cid, parent_cid in (("cycle-a", "cycle-b"), ("cycle-b", "cycle-a")):
        rid, aid = f"r-{cid}", f"a-{cid}"
        candidate = {"schema_version": "canon-correction-request/v1", "request_id": rid, "chapter": 3,
                     "base_commit_sha256": digest, "parent_revision_id": f"correction:{digest}:{parent_cid}",
                     "parent_effective_content_sha256": content, "operation": "SUPERSEDE",
                     "proposed_effective_status": "accepted", "proposed_effective_extraction_result": base["extraction_result"],
                     "proposed_effective_content_sha256": content, "changed_paths": [], "proposer_provenance": {}, "reason": "cycle"}
        req_digest = request_sha256(candidate)
        authorization = {"schema_version": "canon-correction-authorization/v1", "authorization_id": aid,
                         "request_id": rid, "request_sha256": req_digest, "choice": "APPROVE",
                         "actor_ref": "human", "decision_provenance": {}}
        auth_digest = artifact_sha256(authorization)
        correction = {"schema_version": "canon-correction/v1", "correction_id": cid, "chapter": 3,
                      "base_commit_sha256": digest, "parent_revision_id": candidate["parent_revision_id"],
                      "parent_effective_content_sha256": content, "operation": "SUPERSEDE",
                      "effective_extraction_result": base["extraction_result"], "changed_paths": [],
                      "request_sha256": req_digest, "authorization_ref": aid, "authorization_sha256": auth_digest,
                      "provenance": {}, "actor_ref": "writer", "reason": "cycle"}
        edges.append(correction); requests.append(candidate); authorizations.append(authorization)
        verifications.append(VerifiedCorrectionDecision(cid, req_digest, auth_digest, "test-only", "VERIFIED_APPROVE"))
    result = validate_lineage(base, edges, requests, authorizations, verifications)
    assert result.ok is False and "LINEAGE_CYCLE" in {item.code for item in result.diagnostics}


def test_backward_compatible_base_and_unverified_correction_have_exact_result_shape():
    base, edge, req, auth, verification = edge_fixtures()
    clean = resolve_effective_history(base, [], [], [], [])
    assert clean.ok is True and clean.chapter == 3
    assert clean.effective_status == "accepted"
    assert clean.effective_extraction_result == base["extraction_result"]
    assert clean.applied_correction_ids == ()
    invalid = resolve_effective_history(base, [edge], [req], [auth], [])
    assert invalid.ok is False
    assert "HUMAN_AUTHORITY_UNVERIFIED" in {item.code for item in invalid.diagnostics}
    assert invalid.effective_extraction_result is None and invalid.effective_revision_id is None
    assert set(invalid.__dataclass_fields__) >= {
        "ok", "chapter", "base_commit_sha256", "effective_revision_id", "effective_status",
        "effective_extraction_result", "applied_correction_ids", "effective_content_sha256", "diagnostics",
    }


def test_retract_and_supersede_resolve_in_chain_order():
    base, first, req1, auth1, verify1 = edge_fixtures()
    digest = first["base_commit_sha256"]
    retract_req = {**req1, "request_id": "r2", "operation": "RETRACT", "proposed_effective_status": "retracted",
                   "proposed_effective_extraction_result": None, "changed_paths": [],
                   "proposed_effective_content_sha256": effective_content_digest("retracted", None),
                   "parent_revision_id": f"correction:{digest}:c1",
                   "parent_effective_content_sha256": effective_content_digest("accepted", base["extraction_result"])}
    auth2 = {**auth1, "authorization_id": "a2", "request_id": "r2", "request_sha256": request_sha256(retract_req)}
    retract = {"schema_version": "canon-correction/v1", "correction_id": "c2", "chapter": 3,
               "base_commit_sha256": digest, "parent_revision_id": retract_req["parent_revision_id"],
               "parent_effective_content_sha256": retract_req["parent_effective_content_sha256"],
               "operation": "RETRACT", "effective_extraction_result": None, "changed_paths": [],
               "request_sha256": auth2["request_sha256"], "authorization_ref": "a2",
               "authorization_sha256": artifact_sha256(auth2), "provenance": {}, "actor_ref": "test", "reason": "withdraw"}
    verify2 = VerifiedCorrectionDecision("test-2", auth2["request_sha256"], artifact_sha256(auth2), "test-only", "VERIFIED_APPROVE")
    result = resolve_effective_history(base, [first, retract], [req1, retract_req], [auth1, auth2], [verify1, verify2])
    assert result.ok is True
    assert result.effective_status == "retracted" and result.effective_extraction_result is None
    assert result.applied_correction_ids == ("c1", "c2")


def test_amend_requires_exact_exhaustive_changed_path_digests_and_preserves_schema_field():
    base = commit(); digest = base_commit_digest(base)
    updated = dict(base["extraction_result"], summary_text="corrected")
    path_record = {"path": "/summary_text",
                   "before_sha256": hashlib.sha256(canonical_json({"$canon": "absent"}).encode()).hexdigest(),
                   "after_sha256": hashlib.sha256(canonical_json("corrected").encode()).hexdigest()}
    req = {"schema_version": "canon-correction-request/v1", "request_id": "amend-req", "chapter": 3,
           "base_commit_sha256": digest, "parent_revision_id": f"base:{digest}",
           "parent_effective_content_sha256": effective_content_digest("accepted", base["extraction_result"]),
           "operation": "AMEND", "proposed_effective_status": "accepted",
           "proposed_effective_extraction_result": updated,
           "proposed_effective_content_sha256": effective_content_digest("accepted", updated),
           "changed_paths": [path_record], "proposer_provenance": {}, "reason": "amend"}
    req_hash = request_sha256(req)
    auth = {"schema_version": "canon-correction-authorization/v1", "authorization_id": "amend-auth",
            "request_id": req["request_id"], "request_sha256": req_hash, "choice": "APPROVE",
            "actor_ref": "human", "decision_provenance": {}}
    auth_hash = artifact_sha256(auth)
    edge = {"schema_version": "canon-correction/v1", "correction_id": "amend", "chapter": 3,
            "base_commit_sha256": digest, "parent_revision_id": req["parent_revision_id"],
            "parent_effective_content_sha256": req["parent_effective_content_sha256"],
            "operation": "AMEND", "effective_extraction_result": updated, "changed_paths": [path_record],
            "request_sha256": req_hash, "authorization_ref": auth["authorization_id"],
            "authorization_sha256": auth_hash, "provenance": {}, "actor_ref": "writer", "reason": "amend"}
    verification = VerifiedCorrectionDecision("amend-test", req_hash, auth_hash, "test-only", "VERIFIED_APPROVE")
    result = resolve_effective_history(base, [edge], [req], [auth], [verification])
    assert result.ok is True
    assert result.effective_extraction_result == updated
    wrong_path = {**path_record, "after_sha256": "0" * 64}
    bad_req = dict(req, changed_paths=[wrong_path])
    bad_req_hash = request_sha256(bad_req)
    bad_auth = dict(auth, request_sha256=bad_req_hash)
    bad_auth_hash = artifact_sha256(bad_auth)
    wrong = dict(edge, changed_paths=[wrong_path], request_sha256=bad_req_hash,
                 authorization_sha256=bad_auth_hash)
    invalid = resolve_effective_history(base, [wrong], [bad_req], [bad_auth],
        [VerifiedCorrectionDecision("bad-amend", bad_req_hash, bad_auth_hash, "test-only", "VERIFIED_APPROVE")])
    assert invalid.ok is False and invalid.effective_extraction_result is None
    assert "AMEND_CHANGED_PATHS_MISMATCH" in {item.code for item in invalid.diagnostics}


@pytest.mark.parametrize("artifact_kind", ["request", "authorization", "correction"])
def test_same_id_different_bodies_are_permutation_independent_and_select_no_winner(artifact_kind):
    base, edge, req, auth, verification = edge_fixtures()
    if artifact_kind == "request":
        conflicting = dict(req, reason="different request body")
        values = ([req, conflicting], [conflicting, req])
        results = [validate_lineage(base, [edge], requests, [auth], [verification])
                   for requests in values]
        expected_code = "REQUEST_ID_CONFLICT"
    elif artifact_kind == "authorization":
        conflicting = dict(auth, choice="REJECT")
        values = ([auth, conflicting], [conflicting, auth])
        results = [validate_lineage(base, [edge], [req], authorizations, [verification])
                   for authorizations in values]
        expected_code = "AUTHORIZATION_ID_CONFLICT"
    else:
        conflicting = dict(edge, reason="different correction body")
        values = ([edge, conflicting], [conflicting, edge])
        results = [validate_lineage(base, corrections, [req], [auth], [verification])
                   for corrections in values]
        expected_code = "CORRECTION_ID_CONFLICT"
    assert results[0] == results[1]
    assert results[0].ok is False and results[0].effective_revision_id is None
    assert [item.code for item in results[0].diagnostics] == [expected_code]


def test_resolver_rejects_unreferenced_cross_chapter_request_and_orphan_authorization():
    base, edge, req, auth, verification = edge_fixtures()
    foreign_request = dict(req, request_id="other-chapter", chapter=4)
    result = validate_lineage(base, [edge], [req, foreign_request], [auth], [verification])
    assert result.ok is False and "CROSS_BASE_REFERENCE" in {d.code for d in result.diagnostics}

    orphan = dict(auth, authorization_id="orphan-auth", request_id="not-present",
                  request_sha256="f" * 64)
    result = validate_lineage(base, [], [req], [orphan], [])
    assert result.ok is False and "AUTHORIZATION_REQUEST_NOT_FOUND" in {d.code for d in result.diagnostics}


def test_resolver_rejects_unreferenced_artifact_with_foreign_revision_namespace():
    base, _edge, req, _auth, _verification = edge_fixtures()
    foreign_parent = dict(req, request_id="foreign-parent",
                          parent_revision_id=f"correction:{'b' * 64}:other-correction")
    result = validate_lineage(base, [], [foreign_parent], [], [])
    assert result.ok is False
    assert "INVALID_NAMESPACE_BINDING" in {item.code for item in result.diagnostics}
