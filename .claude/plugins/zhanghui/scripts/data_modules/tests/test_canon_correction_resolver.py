import json

import pytest

from data_modules.canon_correction_schema import (
    artifact_sha256, base_commit_digest, effective_content_digest, request_sha256,
)
from data_modules.canon_correction_store import VerifiedCorrectionDecision
from data_modules.canon_correction_resolver import validate_lineage


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
