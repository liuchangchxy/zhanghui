#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
from pathlib import Path

import pytest

from data_modules.tests.commit_helpers import build_commit_with_reconciliation
from data_modules.chapter_commit_service import ChapterCommitService
from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager
from data_modules.gate_findings import (
    DetectedFinding, EvidenceRef, FindingAuthority, FindingCategory,
    GateDecisionSet, WorkflowAction,
)
from data_modules.gate_decision_store import GateDecisionStore


def _gate_finding(category, authority, *, key, evidence):
    return DetectedFinding(
        gate_id="step2.test", stable_subject_key=key, category=category,
        authority=authority, scope={"chapter": 3}, evidence=evidence,
        checker_id="step2-test", checker_version="1",
    )


def _attempt_kwargs():
    from data_modules.tests.commit_helpers import EMPTY_PROPOSAL
    extraction = {"state_deltas": [], "entity_deltas": [], "accepted_events": []}
    return {
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []}, "extraction_result": extraction,
        "chapter_text": "final prose\n<chapter_changes>" + json.dumps(EMPTY_PROPOSAL) + "</chapter_changes>",
        "proposed_changes": EMPTY_PROPOSAL,
    }


def _evaluate(service, findings, attempt_id, **overrides):
    kwargs = _attempt_kwargs()
    kwargs.update(overrides)
    return service.evaluate_attempt(
        3, findings, attempt_id=attempt_id, policy_version="gate-policy/v1",
        scope={"chapter": 3}, **kwargs,
    )


def test_planner_missed_node_does_not_veto_commit(tmp_path):
    service = ChapterCommitService(tmp_path)
    payload = build_commit_with_reconciliation(service,
        chapter=3,
        review_result={"blocking_count": 0},
        fulfillment_result={
            "planned_nodes": ["发现陷阱"],
            "covered_nodes": [],
            "missed_nodes": ["发现陷阱"],
            "extra_nodes": [],
        },
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )
    assert payload["meta"]["status"] == "accepted"


def test_commit_service_accepts_when_all_checks_pass(tmp_path):
    service = ChapterCommitService(tmp_path)
    payload = build_commit_with_reconciliation(service,
        chapter=3,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": ["发现陷阱"], "covered_nodes": ["发现陷阱"], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )
    assert payload["meta"]["status"] == "accepted"
    assert payload["contract_refs"]["master"] == "MASTER_SETTING.json"
    assert payload["contract_refs"]["volume"] == "volume_001.json"
    assert payload["contract_refs"]["chapter"] == "chapter_003.json"
    assert payload["outline_snapshot"]["covered_nodes"] == ["发现陷阱"]
    assert payload["extraction_result"]["accepted_events"] == []
    assert "accepted_events" not in payload
    assert "state_deltas" not in payload
    assert "entity_deltas" not in payload


def test_commit_service_rejects_missing_original_reconciliation_inputs_even_with_no_artifact(tmp_path):
    service = ChapterCommitService(tmp_path)
    with pytest.raises(Exception, match="final chapter_text and proposed_changes are required"):
        service.build_commit(
            chapter=3,
            review_result={"blocking_count": 0},
            fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
            disambiguation_result={"pending": []},
            extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
            reconciliation_result={"schema_version": "story-reconciliation/v1", "status": "passed",
                                   "observed_sha256": "forged", "accepted_payload": {"state_deltas": []}},
        )


def test_commit_service_rejects_conflicted_reconciliation(tmp_path):
    service = ChapterCommitService(tmp_path)
    extraction = {"state_deltas": [], "entity_deltas": [], "accepted_events": []}
    with pytest.raises(Exception, match="audit artifact is stale"):
        service.build_commit(
            chapter=3,
            review_result={"blocking_count": 0},
            fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
            disambiguation_result={"pending": []},
            extraction_result=extraction,
            proposed_changes={
                "character_state_changes": [], "new_plot_points": [],
                "foreshadowing_actions": [], "location_state_changes": [],
                "faction_state_changes": [], "time_progression": None,
                "item_transfers": [], "unresolved_questions": [],
            },
            chapter_text="final prose\n<chapter_changes>" + json.dumps({
                "character_state_changes": [], "new_plot_points": [],
                "foreshadowing_actions": [], "location_state_changes": [],
                "faction_state_changes": [], "time_progression": None,
                "item_transfers": [], "unresolved_questions": [],
            }) + "</chapter_changes>",
            reconciliation_result={"schema_version": "story-reconciliation/v1", "status": "conflict", "conflicts": [], "observed_sha256": "x", "accepted_payload": {}},
        )


def test_service_recomputes_and_rejects_forged_passed_artifact(tmp_path):
    service = ChapterCommitService(tmp_path)
    with pytest.raises(Exception, match="audit artifact is stale"):
        service.build_commit(
            chapter=3,
            review_result={"blocking_count": 0},
            fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
            disambiguation_result={"pending": []},
            extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
            proposed_changes={
                "character_state_changes": [], "new_plot_points": [],
                "foreshadowing_actions": [], "location_state_changes": [],
                "faction_state_changes": [], "time_progression": None,
                "item_transfers": [], "unresolved_questions": [],
            },
            chapter_text="forged prose\n<chapter_changes>" + json.dumps({
                "character_state_changes": [], "new_plot_points": [],
                "foreshadowing_actions": [], "location_state_changes": [],
                "faction_state_changes": [], "time_progression": None,
                "item_transfers": [], "unresolved_questions": [],
            }) + "</chapter_changes>",
            reconciliation_result={"schema_version": "story-reconciliation/v1", "status": "passed",
                                   "observed_sha256": "forged", "accepted_payload": {"state_deltas": []}},
        )


def test_require_human_persists_pending_attempt_without_consuming_commit_slot(tmp_path, monkeypatch):
    service = ChapterCommitService(tmp_path)
    monkeypatch.setattr(service, "apply_projection_writers", lambda payload: payload)
    finding = _gate_finding(
        FindingCategory.DISAMBIGUATION, FindingAuthority.SYSTEM_INTEGRITY, key="identity-choice",
        evidence=[EvidenceRef(kind="identity_choice", identity={"required": True})],
    )
    outcome = _evaluate(service, [finding], "attempt-human")
    commit = tmp_path / ".story-system/commits/chapter_003.commit.json"
    record = GateDecisionStore(tmp_path).read_record(3, "attempt-human")
    assert outcome.action == WorkflowAction.REQUIRE_HUMAN
    assert outcome.chapter_outcome is None
    assert outcome.attempt_status == "pending_human"
    assert record["workflow_status"] == "pending_human"
    assert not commit.exists()
    GateDecisionStore(tmp_path).append_human_response(
        3, "attempt-human", "response-human-1", finding_id=finding.finding_id,
        choice="resolve-as-accepted", actor_ref="user:reviewer",
    )

    resolved = _gate_finding(
        FindingCategory.CRAFT, FindingAuthority.CRAFT_HEURISTIC, key="resolved-advisory",
        evidence=[EvidenceRef(kind="resolution_recorded", identity={"response_id": "r1"})],
    )
    accepted = _evaluate(service, [resolved], "attempt-after-human")
    assert accepted.action == WorkflowAction.ALLOW_WITH_ADVISORY
    assert accepted.chapter_outcome.chapter_outcome == "accepted"
    assert commit.exists()


def test_reject_keeps_immutable_rejected_commit_and_binding_only(tmp_path, monkeypatch):
    service = ChapterCommitService(tmp_path)
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    finding = _gate_finding(
        FindingCategory.INTEGRITY, FindingAuthority.SYSTEM_INTEGRITY, key="bad-integrity",
        evidence=[EvidenceRef(kind="deterministic_validation", identity={"valid": False})],
    )
    outcome = _evaluate(service, [finding], "attempt-reject")
    commit_path = tmp_path / ".story-system/commits/chapter_003.commit.json"
    payload = json.loads(commit_path.read_text(encoding="utf-8"))
    assert outcome.action == WorkflowAction.REJECT
    assert outcome.chapter_outcome.chapter_outcome == "rejected"
    assert payload["meta"]["status"] == "rejected"
    assert payload["extraction_result"]["accepted_events"] == []
    assert payload["extraction_result"]["state_deltas"] == []
    state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["progress"]["chapter_status"]["3"] == "chapter_rejected"
    assert set(payload["gate_decision_binding"]) == {
        "gate_decision_ref", "input_fingerprint", "policy_version", "final_action"
    }
    assert "decisions" not in payload
    from data_modules.durable_projection import DurableCommitError, read_validated_chapter_commit
    assert read_validated_chapter_commit(commit_path)["gate_decision_binding"]["final_action"] == "REJECT"
    payload["gate_decision_binding"]["final_action"] = "ALLOW_WITH_ADVISORY"
    commit_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DurableCommitError, match="does not match status"):
        read_validated_chapter_commit(commit_path)


def test_service_recomputes_policy_and_records_cached_count_mismatch(tmp_path, monkeypatch):
    service = ChapterCommitService(tmp_path)
    monkeypatch.setattr(service, "apply_projection_writers", lambda payload: payload)
    finding = _gate_finding(
        FindingCategory.CRAFT, FindingAuthority.CRAFT_HEURISTIC, key="soft-quality",
        evidence=[EvidenceRef(kind="review", identity={"value": "advisory"})],
    )
    # An external count cannot turn an advisory into a hard veto.
    result = _evaluate(service, [finding], "attempt-count", effective_hard_count=88)
    assert result.action == WorkflowAction.ALLOW_WITH_ADVISORY
    assert result.inconsistency_diagnostic == {"effective_hard_count_mismatch": {"supplied": 88, "recomputed": 0}}
    stored = GateDecisionStore(tmp_path).read_record(3, "attempt-count")
    assert stored["inconsistency_diagnostic"] == result.inconsistency_diagnostic


def test_stale_cached_decision_and_false_external_count_cannot_suppress_reject(tmp_path, monkeypatch):
    service = ChapterCommitService(tmp_path)
    monkeypatch.setattr(service, "apply_projection_writers", lambda payload: payload)
    finding = _gate_finding(
        FindingCategory.INTEGRITY, FindingAuthority.SYSTEM_INTEGRITY, key="hard-integrity",
        evidence=[EvidenceRef(kind="deterministic_validation", identity={"valid": False})],
    )
    stale = GateDecisionSet(decisions=[], aggregate_action=WorkflowAction.ALLOW_WITH_ADVISORY)
    result = _evaluate(
        service, [finding], "attempt-stale-cache", cached_decision_set=stale,
        effective_hard_count=0,
    )
    assert result.action == WorkflowAction.REJECT
    assert result.inconsistency_diagnostic == {
        "cached_decision_mismatch": True,
        "effective_hard_count_mismatch": {"supplied": 0, "recomputed": 1},
    }
    assert result.chapter_outcome.chapter_outcome == "rejected"


def test_recover_success_creates_two_attempts_and_only_then_commits(tmp_path, monkeypatch):
    service = ChapterCommitService(tmp_path)
    monkeypatch.setattr(service, "apply_projection_writers", lambda payload: payload)
    report = {
        "schema_version": "webnovel-projections/v1", "action": "rebuild", "ok": True,
        "error": None, "results": [{"chapter": 1, "ok": True}], "chapters": [1],
    }
    import data_modules.projection_rebuild as rebuild_module
    calls = []
    def rebuild(_root):
        calls.append(True)
        assert not (tmp_path / ".story-system/commits/chapter_003.commit.json").exists()
        return report
    monkeypatch.setattr(rebuild_module, "rebuild_projections", rebuild)
    finding = _gate_finding(
        FindingCategory.PROJECTION_HEALTH, FindingAuthority.SYSTEM_INTEGRITY, key="state-projection",
        evidence=[EvidenceRef(kind="recovery_required", identity={"projection": "state"})],
    )
    refreshed = _gate_finding(
        FindingCategory.CRAFT, FindingAuthority.CRAFT_HEURISTIC, key="fresh-review-after-rebuild",
        evidence=[EvidenceRef(kind="refreshed_review", identity={"version": 2})],
    )
    result = _evaluate(service, [finding], "attempt-recover", refresh_findings=lambda _report: [refreshed])
    attempts = sorted((tmp_path / ".story-system/reviews/gate-decisions/chapter_003").glob("*.json"))
    assert calls == [True]
    assert len(attempts) == 2
    assert GateDecisionStore(tmp_path).read_record(3, "attempt-recover")["workflow_status"] == "recovery_pending"
    assert result.attempt_id == "attempt-recover.recovery-1"
    assert result.action == WorkflowAction.ALLOW_WITH_ADVISORY
    assert result.chapter_outcome.chapter_outcome == "accepted"
    assert (tmp_path / ".story-system/commits/chapter_003.commit.json").is_file()
    events = list((tmp_path / ".story-system/reviews/gate-decisions/chapter_003/workflow-events").glob("*.json"))
    assert {json.loads(path.read_text())["event_type"] for path in events} == {"recovery_pending", "recovery_succeeded"}


def test_recovery_success_requires_fresh_policy_result_before_terminal_commit(tmp_path, monkeypatch):
    service = ChapterCommitService(tmp_path)
    monkeypatch.setattr(service, "apply_projection_writers", lambda payload: payload)
    report = {
        "schema_version": "webnovel-projections/v1", "action": "rebuild", "ok": True,
        "error": None, "results": [{"chapter": 1, "ok": True}], "chapters": [1],
    }
    import data_modules.projection_rebuild as rebuild_module
    monkeypatch.setattr(rebuild_module, "rebuild_projections", lambda _root: report)
    recover = _gate_finding(
        FindingCategory.PROJECTION_HEALTH, FindingAuthority.SYSTEM_INTEGRITY, key="recover-before-hard",
        evidence=[EvidenceRef(kind="recovery_required", identity={"projection": "state"})],
    )
    fresh_hard = _gate_finding(
        FindingCategory.INTEGRITY, FindingAuthority.SYSTEM_INTEGRITY, key="fresh-hard-after-rebuild",
        evidence=[EvidenceRef(kind="deterministic_validation", identity={"valid": False})],
    )
    result = _evaluate(service, [recover], "attempt-recover-hard", refresh_findings=lambda _report: [fresh_hard])
    assert result.attempt_id == "attempt-recover-hard.recovery-1"
    assert result.action == WorkflowAction.REJECT
    assert result.chapter_outcome.chapter_outcome == "rejected"
    assert GateDecisionStore(tmp_path).read_record(3, result.attempt_id)["workflow_status"] == "rejected"


def test_missing_recovery_finding_refresher_reevaluates_as_pending_human(tmp_path, monkeypatch):
    service = ChapterCommitService(tmp_path)
    report = {
        "schema_version": "webnovel-projections/v1", "action": "rebuild", "ok": True,
        "error": None, "results": [{"chapter": 1, "ok": True}], "chapters": [1],
    }
    import data_modules.projection_rebuild as rebuild_module
    monkeypatch.setattr(rebuild_module, "rebuild_projections", lambda _root: report)
    recover = _gate_finding(
        FindingCategory.PROJECTION_HEALTH, FindingAuthority.SYSTEM_INTEGRITY, key="recover-no-refresher",
        evidence=[EvidenceRef(kind="recovery_required", identity={"projection": "state"})],
    )

    result = _evaluate(service, [recover], "attempt-recover-no-refresher")

    assert result.attempt_id == "attempt-recover-no-refresher.recovery-1"
    assert result.action == WorkflowAction.REQUIRE_HUMAN
    assert result.attempt_status == "pending_human"
    assert result.chapter_outcome is None
    assert not (tmp_path / ".story-system/commits/chapter_003.commit.json").exists()
    store = GateDecisionStore(tmp_path)
    assert store.read_record(3, "attempt-recover-no-refresher")["workflow_status"] == "recovery_pending"
    assert store.read_record(3, result.attempt_id)["workflow_status"] == "pending_human"
    events = list((tmp_path / ".story-system/reviews/gate-decisions/chapter_003/workflow-events").glob("*.json"))
    assert {json.loads(path.read_text())["event_type"] for path in events} == {
        "recovery_pending", "recovery_succeeded"
    }


def test_human_response_is_appended_then_policy_is_reevaluated_as_new_attempt(tmp_path, monkeypatch):
    service = ChapterCommitService(tmp_path)
    pending = _gate_finding(
        FindingCategory.DISAMBIGUATION, FindingAuthority.SYSTEM_INTEGRITY,
        key="entity:pending-human", evidence=[EvidenceRef(kind="unresolved_identity", identity={"entity_id": "entity-1"})],
    )
    first = service.evaluate_attempt(
        3, [pending], attempt_id="attempt-pending", policy_version="v1", scope={"chapter": 3},
        **_attempt_kwargs(),
    )
    assert first.attempt_status == "pending_human"
    second = service.evaluate_after_human_response(
        3, [], prior_attempt_id="attempt-pending", response_id="attempt-after-human",
        finding_id=pending.finding_id, choice="resolved-to-entity-1", actor_ref="user:test",
        policy_version="v1", scope={"chapter": 3}, **_attempt_kwargs(),
    )
    assert second.action == WorkflowAction.ALLOW_WITH_ADVISORY
    record = GateDecisionStore(tmp_path).read_record(3, "attempt-after-human")
    assert record["workflow_status"] == "accepted"
    response_path = next((tmp_path / ".story-system/reviews/gate-decisions/chapter_003/attempt-pending.responses").glob("*.json"))
    assert json.loads(response_path.read_text())["choice"] == "resolved-to-entity-1"


@pytest.mark.parametrize(
    ("report", "expected_action", "expected_status"),
    [
        ({"schema_version": "webnovel-projections/v1", "action": "rebuild", "ok": False,
          "error": {"projection": "index", "chapter": 1, "message": "failed"}, "results": []},
         WorkflowAction.REJECT, "rejected"),
        ({"schema_version": "webnovel-projections/v1", "action": "rebuild", "ok": False,
          "error": {"projection": "coordinator", "chapter": None, "message": "unclear"}, "results": []},
         WorkflowAction.REQUIRE_HUMAN, "pending_human"),
    ],
)
def test_recover_failure_is_structured_and_reevaluated(tmp_path, monkeypatch, report, expected_action, expected_status):
    service = ChapterCommitService(tmp_path)
    monkeypatch.setattr(service, "apply_projection_writers", lambda payload: payload)
    import data_modules.projection_rebuild as rebuild_module
    monkeypatch.setattr(rebuild_module, "rebuild_projections", lambda _root: report)
    finding = _gate_finding(
        FindingCategory.PROJECTION_HEALTH, FindingAuthority.SYSTEM_INTEGRITY, key="failed-projection",
        evidence=[EvidenceRef(kind="recovery_required", identity={"projection": "index"})],
    )
    result = _evaluate(service, [finding], "attempt-failed-recover", refresh_findings=lambda _report: [])
    assert result.attempt_id == "attempt-failed-recover.recovery-1"
    assert result.action == expected_action
    assert result.attempt_status == expected_status
    if expected_action == WorkflowAction.REJECT:
        payload = json.loads((tmp_path / ".story-system/commits/chapter_003.commit.json").read_text())
        assert payload["meta"]["status"] == "rejected"
    else:
        assert result.chapter_outcome is None
        assert not (tmp_path / ".story-system/commits/chapter_003.commit.json").exists()


def test_service_detects_stale_prose_and_proposal_against_audit(tmp_path):
    from data_modules.reconciliation import reconcile_changes

    service = ChapterCommitService(tmp_path)
    proposal = {
        "character_state_changes": [], "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [], "time_progression": None,
        "item_transfers": [], "unresolved_questions": [],
    }
    extraction = {"state_deltas": [], "entity_deltas": [], "accepted_events": []}
    chapter_text = "final prose\n<chapter_changes>" + json.dumps(proposal) + "</chapter_changes>"
    audit = reconcile_changes(proposal, extraction, chapter_text=chapter_text)
    changed_proposal = {**proposal, "new_plot_points": [{"plot": "changed"}]}
    changed_proposal_text = "正文\n<chapter_changes>" + json.dumps(changed_proposal) + "</chapter_changes>"
    for changed_text, supplied_proposal in (
        (chapter_text + " polished", proposal),
        (changed_proposal_text, changed_proposal),
    ):
        with pytest.raises(Exception):
            service.build_commit(
                chapter=3, review_result={"blocking_count": 0},
                fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
                disambiguation_result={"pending": []}, extraction_result=extraction,
                chapter_text=changed_text, proposed_changes=supplied_proposal, reconciliation_result=audit,
            )


def test_service_detects_stale_extraction_against_audit(tmp_path):
    from data_modules.reconciliation import reconcile_changes

    service = ChapterCommitService(tmp_path)
    proposal = {
        "character_state_changes": [], "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [], "time_progression": None,
        "item_transfers": [], "unresolved_questions": [],
    }
    text = "final prose\n<chapter_changes>" + json.dumps(proposal) + "</chapter_changes>"
    extraction = {"state_deltas": [], "entity_deltas": [], "accepted_events": []}
    audit = reconcile_changes(proposal, extraction, chapter_text=text)
    with pytest.raises(Exception, match="audit artifact is stale"):
        service.build_commit(
            chapter=3, review_result={"blocking_count": 0},
            fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
            disambiguation_result={"pending": []},
            extraction_result={"state_deltas": [{"entity_id": "x", "field": "realm", "new": "筑基"}], "entity_deltas": [], "accepted_events": []},
            chapter_text=text, proposed_changes=proposal, reconciliation_result=audit,
        )


def test_commit_service_includes_volume_ref_and_write_fact_provenance(tmp_path):
    service = ChapterCommitService(tmp_path)
    payload = build_commit_with_reconciliation(service,
        chapter=3,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": ["发现陷阱"], "covered_nodes": ["发现陷阱"], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )

    assert payload["contract_refs"]["volume"] == "volume_001.json"
    assert payload["provenance"]["write_fact_role"] == "chapter_commit"
    assert payload["provenance"]["projection_role"] == "derived_read_models"


def test_commit_service_rejects_malformed_gate_artifacts(tmp_path):
    service = ChapterCommitService(tmp_path)
    valid_fulfillment = {
        "planned_nodes": [],
        "covered_nodes": [],
        "missed_nodes": [],
        "extra_nodes": [],
    }
    valid_disambiguation = {"pending": []}
    valid_extraction = {"state_deltas": [], "entity_deltas": [], "accepted_events": []}

    with pytest.raises(ValueError, match="blocking_count"):
        build_commit_with_reconciliation(service,
            chapter=3,
            review_result={},
            fulfillment_result=valid_fulfillment,
            disambiguation_result=valid_disambiguation,
            extraction_result=valid_extraction,
        )

    with pytest.raises(ValueError, match="fulfillment_result"):
        build_commit_with_reconciliation(service,
            chapter=3,
            review_result={"blocking_count": 0},
            fulfillment_result={"fulfillment": {"missed_nodes": ["遗漏节点"]}},
            disambiguation_result=valid_disambiguation,
            extraction_result=valid_extraction,
        )

    with pytest.raises(ValueError, match="disambiguation_result"):
        build_commit_with_reconciliation(service,
            chapter=3,
            review_result={"blocking_count": 0},
            fulfillment_result=valid_fulfillment,
            disambiguation_result={"disambiguation": {"pending": ["宗主"]}},
            extraction_result=valid_extraction,
        )


def test_commit_service_rejects_nested_extraction_result_shape(tmp_path):
    service = ChapterCommitService(tmp_path)

    with pytest.raises(ValueError, match="top-level"):
        build_commit_with_reconciliation(service,
            chapter=76,
            review_result={"blocking_count": 0},
            fulfillment_result={
                "planned_nodes": [],
                "covered_nodes": [],
                "missed_nodes": [],
                "extra_nodes": [],
            },
            disambiguation_result={"pending": []},
            extraction_result={
                "chapter": 76,
                "extraction": {
                    "scenes": [{"summary": "场景切分"}],
                    "unresolved_threads": ["未解线索"],
                },
            },
        )


def test_commit_service_rejects_extraction_wrapper_even_with_empty_core_fields(tmp_path):
    service = ChapterCommitService(tmp_path)

    with pytest.raises(ValueError, match="nested under extraction"):
        build_commit_with_reconciliation(service,
            chapter=76,
            review_result={"blocking_count": 0},
            fulfillment_result={
                "planned_nodes": [],
                "covered_nodes": [],
                "missed_nodes": [],
                "extra_nodes": [],
            },
            disambiguation_result={"pending": []},
            extraction_result={
                "accepted_events": [],
                "state_deltas": [],
                "entity_deltas": [],
                "extraction": {
                    "scenes": [{"summary": "真实场景却被包错层"}],
                    "summary_text": "真实摘要却被包错层",
                },
            },
        )


def test_commit_service_rejects_extraction_result_missing_core_fields(tmp_path):
    service = ChapterCommitService(tmp_path)

    with pytest.raises(ValueError, match="accepted_events"):
        build_commit_with_reconciliation(service,
            chapter=3,
            review_result={"blocking_count": 0},
            fulfillment_result={
                "planned_nodes": [],
                "covered_nodes": [],
                "missed_nodes": [],
                "extra_nodes": [],
            },
            disambiguation_result={"pending": []},
            extraction_result={"summary_text": "摘要"},
        )


def test_commit_service_rejects_non_object_extraction_items(tmp_path):
    service = ChapterCommitService(tmp_path)

    with pytest.raises(ValueError, match=r"state_deltas\[0\]"):
        build_commit_with_reconciliation(service,
            chapter=3,
            review_result={"blocking_count": 0},
            fulfillment_result={
                "planned_nodes": [],
                "covered_nodes": [],
                "missed_nodes": [],
                "extra_nodes": [],
            },
            disambiguation_result={"pending": []},
            extraction_result={
                "accepted_events": [],
                "state_deltas": ["realm changed"],
                "entity_deltas": [],
            },
        )


def test_commit_service_rejects_non_object_accepted_event_items(tmp_path):
    service = ChapterCommitService(tmp_path)

    with pytest.raises(ValueError, match=r"accepted_events\[0\]"):
        build_commit_with_reconciliation(service,
            chapter=3,
            review_result={"blocking_count": 0},
            fulfillment_result={
                "planned_nodes": [],
                "covered_nodes": [],
                "missed_nodes": [],
                "extra_nodes": [],
            },
            disambiguation_result={"pending": []},
            extraction_result={
                "accepted_events": ["not-a-json-object"],
                "state_deltas": [],
                "entity_deltas": [],
            },
        )


def test_commit_service_normalizes_accepted_events_before_projection(tmp_path):
    service = ChapterCommitService(tmp_path)

    payload = build_commit_with_reconciliation(service,
        chapter=76,
        review_result={"blocking_count": 0},
        fulfillment_result={
            "planned_nodes": [],
            "covered_nodes": [],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        disambiguation_result={"pending": []},
        extraction_result={
            "state_deltas": [],
            "entity_deltas": [],
            "accepted_events": [
                {
                    "type": "mystery_introduction",
                    "characters": ["xiaoyan"],
                    "payload": {"content": "萧炎发现石门背后的新疑点"},
                }
            ],
        },
    )

    event = payload["extraction_result"]["accepted_events"][0]
    assert event["event_id"].startswith("evt-ch076-001-")
    assert event["chapter"] == 76
    assert event["event_type"] == "open_loop_created"
    assert event["subject"] == "xiaoyan"
    assert "accepted_events" not in payload


def test_apply_projections_normalizes_events_before_router_inspection(
    tmp_path, monkeypatch
):
    captured = {}

    class SpyRouter:
        def required_writers(self, payload):
            captured["events"] = list(payload.get("extraction_result", {}).get("accepted_events") or [])
            return []

    monkeypatch.setattr(
        "data_modules.chapter_commit_service.EventProjectionRouter",
        lambda: SpyRouter(),
    )

    service = ChapterCommitService(tmp_path)
    payload = {
        "meta": {"schema_version": "story-system/v1", "status": "accepted", "chapter": 76},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {
            "accepted_events": [
                {
                    "type": "scene_open",
                    "characters": ["xiaoyan"],
                    "payload": {"content": "萧炎推开石门，新的悬念出现"},
                }
            ],
            "state_deltas": [],
            "entity_deltas": [],
            "summary_text": "",
        },
        "projection_status": {
            "state": "pending",
            "index": "pending",
            "summary": "pending",
            "memory": "pending",
            "vector": "pending",
        },
    }

    service.apply_projections(payload)

    event = captured["events"][0]
    assert event["event_id"].startswith("evt-ch076-001-")
    assert event["chapter"] == 76
    assert event["event_type"] == "open_loop_created"
    assert event["subject"] == "xiaoyan"
    assert payload["extraction_result"]["accepted_events"] == captured["events"]


def test_apply_projections_updates_state_for_rejected_commit(tmp_path):
    import json

    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")

    service = ChapterCommitService(tmp_path)
    hard = _gate_finding(
        FindingCategory.INTEGRITY, FindingAuthority.SYSTEM_INTEGRITY,
        key="reject-projection", evidence=[EvidenceRef(kind="deterministic_validation", identity={"valid": False})],
    )
    kwargs = _attempt_kwargs()
    attempt = service.evaluate_attempt(
        7, [hard], attempt_id="reject-projection-attempt", policy_version="gate-policy/v1",
        scope={"chapter": 7}, **kwargs,
    )
    projected = attempt.chapter_outcome.commit_payload

    state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert projected["projection_status"]["state"] == "done"
    assert state["progress"]["chapter_status"]["7"] == "chapter_rejected"


def test_chapter_commit_cli_ignores_consistency_fields_and_preserves_changes_advisories(tmp_path, monkeypatch):
    import subprocess

    review_path = tmp_path / "review.json"
    fulfillment_path = tmp_path / "fulfillment.json"
    disambiguation_path = tmp_path / "disambiguation.json"
    extraction_path = tmp_path / "extraction.json"
    review_path.write_text(json.dumps({
        "blocking_count": 0,
        "consistency_findings": [
            {"patch": "foreshadow_dag", "issue_code": "overdue", "subject_id": "fs-1"},
            {"patch": "pacing_tracker", "issue_code": "consecutive_fast", "subject_id": "chapter:3"},
            {"patch": "reader_contract", "issue_code": "broken_promise", "subject_id": "promise-1"},
        ],
    }), encoding="utf-8")
    fulfillment_path.write_text(
        '{"planned_nodes": ["发现陷阱"], "covered_nodes": ["发现陷阱"], "missed_nodes": [], "extra_nodes": []}',
        encoding="utf-8",
    )
    disambiguation_path.write_text('{"pending": []}', encoding="utf-8")
    extraction_path.write_text('{"state_deltas": [], "entity_deltas": [], "accepted_events": []}', encoding="utf-8")
    chapter_path = tmp_path / "chapter.md"
    chapter_text = '''<chapter_changes>{"character_state_changes": [], "new_plot_points": [], "foreshadowing_actions": [], "location_state_changes": [], "faction_state_changes": [], "time_progression": null, "item_transfers": [], "unresolved_questions": []}</chapter_changes>'''
    chapter_path.write_text(chapter_text, encoding="utf-8")
    from data_modules.reconciliation import reconcile_changes
    proposed = {
        "character_state_changes": [], "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [], "time_progression": None,
        "item_transfers": [], "unresolved_questions": [],
    }
    reconciliation_path = tmp_path / "reconciliation.json"
    reconciliation_path.write_text(json.dumps(reconcile_changes(proposed, json.loads(extraction_path.read_text()), chapter_text=chapter_text)), encoding="utf-8")

    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from chapter_commit import main
    monkeypatch.setattr(
        "chapter_commit.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0,
            stdout=json.dumps({"passed": False, "failures": [
                {"rule_id": "R0", "severity": "advisory", "location": "db"},
                {"rule_id": "R8", "severity": "advisory", "location": "time_progression.elapsed_time"},
            ]}),
            stderr="",
        ),
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "chapter_commit",
            "--project-root",
            str(tmp_path),
            "--chapter",
            "3",
            "--review-result",
            str(review_path),
            "--fulfillment-result",
            str(fulfillment_path),
            "--disambiguation-result",
            str(disambiguation_path),
            "--extraction-result",
            str(extraction_path),
            "--reconciliation-result",
            str(reconciliation_path),
            "--chapter-file",
            str(chapter_path),
        ],
    )
    main()

    commit_path = tmp_path / ".story-system" / "commits" / "chapter_003.commit.json"
    assert commit_path.is_file()
    payload = json.loads(commit_path.read_text(encoding="utf-8"))
    assert payload["gate_decision_binding"]["final_action"] == "ALLOW_WITH_ADVISORY"
    decision_ref = payload["gate_decision_binding"]["gate_decision_ref"]
    decision_record = json.loads((tmp_path / decision_ref).read_text(encoding="utf-8"))
    decisions = decision_record["decision_set"]["decisions"]
    assert len(decisions) == 2
    assert all(row["effective_severity"] == "ADVISORY" for row in decisions)


def test_apply_projections_writes_events_and_amend_proposals(tmp_path):
    service = ChapterCommitService(tmp_path)
    payload = build_commit_with_reconciliation(service,
        chapter=3,
        review_result={"blocking_count": 0},
        fulfillment_result={
            "planned_nodes": ["发现陷阱"],
            "covered_nodes": ["发现陷阱"],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        disambiguation_result={"pending": []},
        extraction_result={
            "state_deltas": [],
            "entity_deltas": [],
            "summary_text": "",
            "accepted_events": [
                {
                    "event_id": "evt-001",
                    "chapter": 3,
                    "event_type": "world_rule_broken",
                    "subject": "金手指",
                    "payload": {
                        "field": "world_rule",
                        "base_value": "每日一次",
                        "proposed_value": "短时失控突破",
                    },
                }
            ],
        },
    )

    service.apply_projections(payload)

    assert (tmp_path / ".story-system" / "events" / "chapter_003.events.json").is_file()
    manager = IndexManager(DataModulesConfig.from_project_root(tmp_path))
    with manager._get_conn() as conn:
        row = conn.execute(
            """
            SELECT record_type, field, override_value, status
            FROM override_contracts
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    assert row["record_type"] == "amend_proposal"
    assert row["field"] == "world_rule"
    assert row["override_value"] == "短时失控突破"
    assert row["status"] == "pending"


def test_commit_is_durable_before_any_projection_side_effect(tmp_path, monkeypatch):
    service = ChapterCommitService(tmp_path)
    payload = build_commit_with_reconciliation(service,
        chapter=11,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )
    original = service.persist_commit
    order = []

    def record_persist(*args, **kwargs):
        result = original(*args, **kwargs)
        order.append(("commit", result.is_file()))
        return result

    class SpyWriter:
        def apply(self, commit_payload):
            commit_path = tmp_path / ".story-system" / "commits" / "chapter_011.commit.json"
            order.append(("projection", commit_path.is_file()))
            return {"applied": True, "writer": "state"}

    monkeypatch.setattr(service, "persist_commit", record_persist)
    monkeypatch.setattr(service, "_projection_writers", lambda: {"state": SpyWriter()})

    projected = service.apply_projections(payload)

    assert order == [("commit", True), ("projection", True)]
    saved = __import__("json").loads(
        (tmp_path / ".story-system" / "commits" / "chapter_011.commit.json").read_text(encoding="utf-8")
    )
    assert "projection_status" not in saved
    assert projected["projection_status"]["state"] == "done"


def test_failed_commit_persistence_runs_no_projection(tmp_path, monkeypatch):
    service = ChapterCommitService(tmp_path)
    payload = build_commit_with_reconciliation(service,
        chapter=12,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )

    def fail_persist(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(service, "persist_commit", fail_persist)

    with pytest.raises(OSError, match="disk full"):
        service.apply_projections(payload)

    assert not (tmp_path / ".story-system" / "events" / "chapter_012.events.json").exists()
    assert not (tmp_path / ".webnovel" / "index.db").exists()
    assert not (tmp_path / ".webnovel" / "projection_log.jsonl").exists()


def test_projection_failure_does_not_mutate_durable_commit(tmp_path, monkeypatch):
    import json
    from data_modules.projection_log import commit_hash

    service = ChapterCommitService(tmp_path)
    payload = build_commit_with_reconciliation(service,
        chapter=13,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )

    class FailingWriter:
        def apply(self, _payload):
            raise RuntimeError("projection unavailable")

    original_factory = service._projection_writers
    monkeypatch.setattr(service, "_projection_writers", lambda: {"state": FailingWriter()})
    projected = service.apply_projections(payload)
    commit_path = tmp_path / ".story-system" / "commits" / "chapter_013.commit.json"

    assert projected["meta"]["status"] == "accepted"
    assert projected["projection_status"]["state"].startswith("failed:")
    saved = json.loads(commit_path.read_text(encoding="utf-8"))
    assert saved["meta"]["status"] == "accepted"
    assert "projection_status" not in saved
    original_hash = commit_hash(saved)

    monkeypatch.setattr(service, "_projection_writers", original_factory)
    retried = service.apply_projection_writers(saved)
    durable_after_retry = json.loads(commit_path.read_text(encoding="utf-8"))
    assert retried["projection_status"]["state"] == "done"
    assert commit_hash(durable_after_retry) == original_hash
