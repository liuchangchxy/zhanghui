from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from data_modules.gate_decision_store import GateDecisionStore, GateDecisionStoreError
from data_modules.gate_findings import (
    DetectedFinding, EffectiveSeverity, EvidenceRef, FindingAuthority,
    FindingCategory, GateDecisionSet, WorkflowAction,
)
from data_modules.gate_severity_policy import GateSeverityPolicy


def make_finding(*, category=FindingCategory.CRAFT, evidence=None):
    return DetectedFinding(
        gate_id="store.test", stable_subject_key="subject-1", category=category,
        authority=FindingAuthority.CRAFT_HEURISTIC, scope={"chapter": 2},
        evidence=evidence or [EvidenceRef(kind="span", identity={"start": 1})],
        checker_id="test", checker_version="1",
    )


def test_attempt_round_trip_and_unique_append_only(tmp_path):
    decision_set = GateSeverityPolicy().evaluate([make_finding()], policy_version="policy/v1", scope={"chapter": 2})
    store = GateDecisionStore(tmp_path)
    path = store.append_attempt(2, "attempt-a", decision_set)
    assert path == (tmp_path / ".story-system/reviews/gate-decisions/chapter_002/attempt-a.json").resolve()
    assert store.read_attempt(2, "attempt-a") == decision_set
    before = path.read_bytes()
    with pytest.raises(GateDecisionStoreError, match="immutable"):
        store.append_attempt(2, "attempt-a", decision_set)
    assert path.read_bytes() == before


def test_malformed_score_attempt_fails_validation(tmp_path):
    path = tmp_path / ".story-system/reviews/gate-decisions/chapter_002/bad.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "schema_version": "gate-decision-attempt/v1", "chapter": 2,
        "attempt_id": "bad", "workflow_status": "accepted",
        "decision_set": {"aggregate_action": "ALLOW_WITH_ADVISORY", "decisions": [{
            "finding_id": "gf1_" + "0" * 64, "effective_severity": "SCORE",
            "effective_action": "ALLOW_WITH_ADVISORY", "policy_version": "p1",
            "rule_id": "score", "policy_reason": "score", "decision_scope": {"chapter": 2},
            "evidence_fingerprint": "0" * 64, "input_fingerprint": "1" * 64,
            "score": {"kind": "pacing", "value": 3, "scale": [0, 1]},
        }]},
    }), encoding="utf-8")
    with pytest.raises(GateDecisionStoreError, match="within declared scale"):
        GateDecisionStore(tmp_path).read_attempt(2, "bad")


def test_workflow_events_and_human_responses_are_append_only(tmp_path):
    finding = make_finding(category=FindingCategory.DISAMBIGUATION, evidence=[EvidenceRef(kind="choice", identity={"required": True})])
    decision_set = GateSeverityPolicy().evaluate([finding], policy_version="policy/v1", scope={"chapter": 2})
    assert decision_set.aggregate_action == WorkflowAction.REQUIRE_HUMAN
    store = GateDecisionStore(tmp_path)
    store.append_attempt(2, "pending-a", decision_set, workflow_status="pending_human")
    response = store.append_human_response(
        2, "pending-a", "response-a", finding_id=finding.finding_id,
        choice="accept-ambiguity", actor_ref="user:1",
    )
    assert response.is_file()
    with pytest.raises(GateDecisionStoreError, match="already exists"):
        store.append_human_response(
            2, "pending-a", "response-a", finding_id=finding.finding_id,
            choice="accept-ambiguity", actor_ref="user:1",
        )
    event = store.append_workflow_event(
        2, "pending-a.recovery", attempt_id="pending-a", event_type="recovery_pending", status="started"
    )
    with pytest.raises(GateDecisionStoreError, match="already exists"):
        store.append_workflow_event(
            2, "pending-a.recovery", attempt_id="pending-a", event_type="recovery_pending", status="started"
        )
    assert event.is_file()
