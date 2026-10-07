import pytest

import json

from data_modules.canon_correction_schema import (
    artifact_sha256, base_commit_digest, effective_content_digest,
)
from data_modules.canon_correction_store import (
    CorrectionStoreError,
    append_correction_request,
    build_correction_review_package,
    record_interactive_correction_decision,
    verify_phase9_correction_decision,
)
from data_modules.canon_correction_workflow import prepare_review, record_decision


def _request():
    base = "a" * 64
    extraction = {"accepted_events": [], "state_deltas": [], "entity_deltas": []}
    content = effective_content_digest("accepted", extraction)
    return {
        "schema_version": "canon-correction-request/v1",
        "request_id": "TEST-ONLY-request-1",
        "chapter": 3,
        "base_commit_sha256": base,
        "parent_revision_id": f"base:{base}",
        "parent_effective_content_sha256": content,
        "operation": "RETRACT",
        "proposed_effective_status": "retracted",
        "proposed_effective_extraction_result": None,
        "proposed_effective_content_sha256": effective_content_digest("retracted", None),
        "changed_paths": [],
        "proposer_provenance": {"fixture": "TEST ONLY"},
        "reason": "TEST ONLY",
    }


def _authorization(request, package, choice="APPROVE"):
    return {
        "schema_version": "canon-correction-authorization/v1",
        "authorization_id": "TEST-ONLY-auth-1",
        "request_id": request["request_id"],
        "request_sha256": artifact_sha256(request),
        "choice": choice,
        "actor_ref": "local-user-workflow",
        "decision_provenance": {
            "phase9_confirmation": {
                "kind": "interactive-workflow-confirmation/v1",
                "challenge_sha256": package["challenge_sha256"],
                "interaction_id": "TEST-ONLY-interaction-1",
                "interaction_surface": "test host-adapter contract",
                "confirmed_at": "2026-10-06T00:00:00Z",
            }
        },
    }


def test_review_package_binds_exact_request_parent_and_semantics():
    req = _request()
    package = build_correction_review_package(
        req, parent_status="accepted", parent_extraction={"accepted_events": [], "state_deltas": [], "entity_deltas": []},
    )
    assert package["request_id"] == req["request_id"]
    assert package["request_sha256"] == artifact_sha256(req)
    assert package["base_commit_sha256"] == req["base_commit_sha256"]
    assert package["parent_revision_id"] == req["parent_revision_id"]
    assert package["before"]["status"] == "accepted"
    assert package["after"]["status"] == "retracted"
    assert package["challenge_sha256"] == artifact_sha256(
        {k: v for k, v in package.items() if k != "challenge_sha256"}
    )


def test_verified_decision_rejects_changed_reviewed_payload():
    req = _request()
    package = build_correction_review_package(
        req, parent_status="accepted", parent_extraction={"accepted_events": [], "state_deltas": [], "entity_deltas": []},
    )
    authorization = _authorization(req, package)
    verified = verify_phase9_correction_decision(req, authorization, package)
    assert verified.decision_status == "VERIFIED_APPROVE"
    tampered = {**package, "reason": "changed after confirmation"}
    with pytest.raises(CorrectionStoreError, match="CHALLENGE_MISMATCH"):
        verify_phase9_correction_decision(req, authorization, tampered)


@pytest.mark.parametrize("choice, expected", [("APPROVE", "VERIFIED_APPROVE"), ("REJECT", "VERIFIED_REJECT")])
def test_phase9_decision_records_terminal_choice(choice, expected):
    req = _request()
    package = build_correction_review_package(
        req, parent_status="accepted", parent_extraction={"accepted_events": [], "state_deltas": [], "entity_deltas": []},
    )
    assert verify_phase9_correction_decision(
        req, _authorization(req, package, choice), package,
    ).decision_status == expected


def test_legacy_authorization_has_no_phase9_decision_verification():
    req = _request()
    package = build_correction_review_package(
        req, parent_status="accepted", parent_extraction={"accepted_events": [], "state_deltas": [], "entity_deltas": []},
    )
    authorization = _authorization(req, package)
    authorization["decision_provenance"] = {"legacy": True}
    with pytest.raises(CorrectionStoreError, match="PHASE9_CONFIRMATION_REQUIRED"):
        verify_phase9_correction_decision(req, authorization, package)


def test_no_answer_does_not_append_authorization(tmp_path):
    req = _request()
    package = build_correction_review_package(
        req, parent_status="accepted", parent_extraction={"accepted_events": [], "state_deltas": [], "entity_deltas": []},
    )
    with pytest.raises(CorrectionStoreError, match="DECISION_REQUIRED"):
        record_interactive_correction_decision(
            tmp_path, req, package, choice=None, authorization_id="TEST-ONLY-auth-1",
            interaction_id="TEST-ONLY-interaction-1", interaction_surface="test",
            confirmed_at="2026-10-06T00:00:00Z",
        )
    assert not (tmp_path / ".story-system/corrections").exists()


@pytest.mark.parametrize("choice", ["APPROVE", "REJECT"])
def test_host_adapter_contract_passes_canonical_package_and_explicit_choice(tmp_path, choice):
    base, req = _persistable_request(3)
    commit_path = tmp_path / ".story-system/commits/chapter_003.commit.json"
    commit_path.parent.mkdir(parents=True, exist_ok=True)
    commit_path.write_text(json.dumps(base), encoding="utf-8")
    append_correction_request(tmp_path, req)
    package = prepare_review(tmp_path, req["request_id"], {
        "status": "accepted", "extraction_result": base["extraction_result"],
    })

    authorization = record_decision(tmp_path, req["request_id"], package, choice)

    assert authorization.choice == choice
    assert authorization.request_id == req["request_id"]
    assert authorization.request_sha256 == artifact_sha256(req)
    assert authorization.decision_provenance["phase9_confirmation"]["challenge_sha256"] == package["challenge_sha256"]
    assert verify_phase9_correction_decision(req, authorization, package).decision_status == f"VERIFIED_{choice}"


def _persistable_request(chapter):
    base = {
        "meta": {"schema_version": "story-system/v1", "chapter": chapter, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": []},
    }
    extraction = base["extraction_result"]
    digest = base_commit_digest(base)
    return base, {
        "schema_version": "canon-correction-request/v1", "request_id": f"TEST-ONLY-r{chapter}",
        "chapter": chapter, "base_commit_sha256": digest,
        "parent_revision_id": f"base:{digest}",
        "parent_effective_content_sha256": effective_content_digest("accepted", extraction),
        "operation": "RETRACT", "proposed_effective_status": "retracted",
        "proposed_effective_extraction_result": None,
        "proposed_effective_content_sha256": effective_content_digest("retracted", None),
        "changed_paths": [], "proposer_provenance": {"fixture": "TEST ONLY"}, "reason": "TEST ONLY",
    }


def test_interaction_id_replay_across_requests_is_rejected(tmp_path):
    for chapter in (3, 4):
        base, req = _persistable_request(chapter)
        commit_path = tmp_path / f".story-system/commits/chapter_{chapter:03d}.commit.json"
        commit_path.parent.mkdir(parents=True, exist_ok=True)
        commit_path.write_text(json.dumps(base), encoding="utf-8")
        append_correction_request(tmp_path, req)
        parent = base["extraction_result"]
        package = build_correction_review_package(req, parent_status="accepted", parent_extraction=parent)
        if chapter == 3:
            record_interactive_correction_decision(
                tmp_path, req, package, choice="REJECT", authorization_id="TEST-ONLY-a3",
                interaction_id="TEST-ONLY-same", interaction_surface="test", confirmed_at="2026-10-06T00:00:00Z",
            )
        else:
            with pytest.raises(CorrectionStoreError, match="INTERACTION_REPLAY"):
                record_interactive_correction_decision(
                    tmp_path, req, package, choice="APPROVE", authorization_id="TEST-ONLY-a4",
                    interaction_id="TEST-ONLY-same", interaction_surface="test", confirmed_at="2026-10-06T00:01:00Z",
                )
