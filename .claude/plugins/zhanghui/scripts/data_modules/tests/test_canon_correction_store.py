import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from data_modules.canon_correction_schema import base_commit_digest, effective_content_digest, request_sha256
from data_modules.canon_correction_store import (
    append_correction_request, append_correction_authorization,
    correction_target_dir, CorrectionStoreError,
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
