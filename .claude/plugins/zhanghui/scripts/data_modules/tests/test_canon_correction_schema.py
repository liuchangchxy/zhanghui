import hashlib
import json

import pytest

from data_modules.canon_correction_schema import (
    CanonCorrectionRequest,
    CanonCorrectionAuthorization,
    CanonCorrection,
    artifact_sha256,
    base_commit_digest,
    canonical_json,
    effective_content_digest,
)


EXTRACTION = {"accepted_events": [], "state_deltas": [], "entity_deltas": []}


def request(operation="AMEND", **overrides):
    body = {
        "schema_version": "canon-correction-request/v1", "request_id": "req-1",
        "chapter": 3, "base_commit_sha256": "a" * 64,
        "parent_revision_id": "base:" + "a" * 64,
        "parent_effective_content_sha256": "b" * 64, "operation": operation,
        "proposed_effective_status": "accepted",
        "proposed_effective_extraction_result": EXTRACTION,
        "proposed_effective_content_sha256": "c" * 64,
        "changed_paths": [], "proposer_provenance": {"source": "test"}, "reason": "fix"}
    body.update(overrides)
    return body


def accepted_commit():
    return {"meta": {"schema_version": "story-system/v1", "chapter": 3, "status": "accepted"},
            "review_result": {"blocking_count": 0},
            "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
            "disambiguation_result": {"pending": []}, "extraction_result": EXTRACTION}


def test_request_schema_requires_version_fields_and_path_safe_id():
    assert CanonCorrectionRequest.model_validate(request()).request_id == "req-1"
    with pytest.raises(ValueError):
        CanonCorrectionRequest.model_validate(request(schema_version="canon-correction-request/v2"))
    with pytest.raises(ValueError):
        CanonCorrectionRequest.model_validate(request(request_id="../escape"))
    with pytest.raises(ValueError):
        CanonCorrectionRequest.model_validate({"schema_version": "canon-correction-request/v1"})


def test_operation_specific_shapes_and_authorization_references_are_strict():
    with pytest.raises(ValueError):
        CanonCorrectionRequest.model_validate(request("RETRACT"))
    retract = request("RETRACT", proposed_effective_status="retracted",
                      proposed_effective_extraction_result=None, changed_paths=[])
    assert CanonCorrectionRequest.model_validate(retract)
    auth = {"schema_version": "canon-correction-authorization/v1", "authorization_id": "auth-1",
            "request_id": "req-1", "request_sha256": "d" * 64, "choice": "APPROVE",
            "actor_ref": "human", "decision_provenance": {"source": "test"}}
    assert CanonCorrectionAuthorization.model_validate(auth)
    with pytest.raises(ValueError):
        CanonCorrectionAuthorization.model_validate({**auth, "choice": "MAYBE"})
    correction = {"schema_version": "canon-correction/v1", "correction_id": "cor-1", "chapter": 3,
                  "base_commit_sha256": "a" * 64, "parent_revision_id": "base:" + "a" * 64,
                  "parent_effective_content_sha256": "b" * 64, "operation": "AMEND",
                  "effective_extraction_result": EXTRACTION, "changed_paths": [],
                  "request_sha256": "d" * 64, "authorization_ref": "auth-1",
                  "authorization_sha256": "e" * 64, "provenance": {}, "actor_ref": "author", "reason": "fix"}
    assert CanonCorrection.model_validate(correction)
    with pytest.raises(ValueError):
        CanonCorrection.model_validate({**correction, "authorization_ref": "../auth"})


def test_canonical_artifact_digests_and_effective_digest_are_stable():
    left = {"schema_version": "canon-correction-authorization/v1", "authorization_id": "auth-1", "choice": "APPROVE"}
    right = json.loads('{ "choice":"APPROVE", "authorization_id":"auth-1", "schema_version":"canon-correction-authorization/v1" }')
    assert canonical_json(left) == canonical_json(right)
    assert artifact_sha256(left) == hashlib.sha256(canonical_json(left).encode()).hexdigest()
    assert effective_content_digest("accepted", EXTRACTION) != effective_content_digest("retracted", None)
    with pytest.raises((ValueError, TypeError)):
        canonical_json({"bad": float("nan")})


def test_base_identity_uses_validated_commit_and_excludes_projection_status():
    commit = accepted_commit()
    with_projection = dict(commit, projection_status={"last_run": "x"})
    assert base_commit_digest(commit) == base_commit_digest(with_projection)
    changed = json.loads(json.dumps(commit))
    changed["extraction_result"]["summary_text"] = "new"
    assert base_commit_digest(commit) != base_commit_digest(changed)
    changed["meta"]["status"] = "rejected"
    with pytest.raises(ValueError):
        base_commit_digest(changed)
