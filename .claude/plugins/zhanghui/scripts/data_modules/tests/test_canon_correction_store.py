import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from data_modules.canon_correction_schema import base_commit_digest, effective_content_digest, request_sha256
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
                              decision_verifications=[bundle[3]])
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
