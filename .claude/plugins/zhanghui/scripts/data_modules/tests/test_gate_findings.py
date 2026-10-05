from __future__ import annotations

import copy
from collections import UserDict

import pytest
from pydantic import ValidationError

from data_modules.gate_findings import (
    DetectedFinding,
    EffectiveSeverity,
    EvidenceRef,
    FindingAuthority,
    FindingCategory,
    GateDecision,
    Explicitness,
    WorkflowAction,
    fingerprint_evidence,
    fingerprint_policy_inputs,
    stable_finding_id,
)
from data_modules.gate_severity_policy import GateSeverityPolicy


SCOPE = {"project": "demo", "chapter": 3}


def make_finding(**overrides):
    values = {
        "identity_version": "v1",
        "gate_id": "test.gate",
        "stable_subject_key": "node-17",
        "category": FindingCategory.CRAFT,
        "authority": FindingAuthority.CRAFT_HEURISTIC,
        "explicitness": Explicitness.UNKNOWN,
        "scope": SCOPE,
        "evidence": [EvidenceRef(kind="span", identity={"start": 1}, observed="old")],
        "checker_id": "test-checker",
        "checker_version": "1",
        "message": "old wording",
    }
    values.update(overrides)
    return DetectedFinding(**values)


def evaluate(*findings):
    return GateSeverityPolicy().evaluate(list(findings), policy_version="gate-policy/v1", scope=SCOPE)


def test_enum_dimensions_are_separate_and_unknown_values_rejected():
    finding = make_finding(category="INTENT_FULFILLMENT", authority="PLANNER_GENERATED")
    assert finding.category == FindingCategory.INTENT_FULFILLMENT
    assert finding.authority == FindingAuthority.PLANNER_GENERATED
    with pytest.raises(ValidationError):
        make_finding(category="HARD_WORKFLOW")
    with pytest.raises(ValidationError):
        make_finding(authority="UNTRUSTED_SOURCE")


def test_evidence_is_structured_and_extra_policy_fields_are_rejected():
    ref = EvidenceRef(kind="contract_constraint", identity={"constraint_id": "c1"}, source_ref="chapter:3/node:c1")
    assert ref.identity["constraint_id"] == "c1"
    with pytest.raises(ValidationError):
        EvidenceRef(kind="", identity="c1")
    with pytest.raises(ValidationError):
        make_finding(unreviewed_policy_override=True)


def _decision(severity, **kwargs):
    base = {
        "finding_id": "gf1_" + "0" * 64,
        "effective_action": WorkflowAction.ALLOW_WITH_ADVISORY,
        "policy_version": "gate-policy/v1",
        "rule_id": "quality.score",
        "policy_reason": "score",
        "decision_scope": SCOPE,
        "evidence_fingerprint": "0" * 64,
        "input_fingerprint": "1" * 64,
        "effective_severity": severity,
    }
    base.update(kwargs)
    return GateDecision(**base)


def test_score_payload_required_only_for_score_and_scale_validated():
    with pytest.raises(ValidationError):
        _decision("SCORE")
    score = {"kind": "pacing", "value": 0.72, "scale": [0.0, 1.0]}
    assert _decision("SCORE", score=score).score.value == 0.72
    with pytest.raises(ValidationError):
        _decision("ADVISORY", score=score)
    with pytest.raises(ValidationError):
        _decision("SCORE", score={"kind": "pacing", "value": 1.1, "scale": [0, 1]})
    with pytest.raises(ValidationError):
        _decision("SCORE", score={"kind": "pacing", "value": float("nan"), "scale": [0, 1]})


def test_stable_finding_id_uses_only_logical_identity():
    first = make_finding()
    second = make_finding(
        category=FindingCategory.STYLE,
        authority=FindingAuthority.LLM_REVIEW,
        evidence=[EvidenceRef(kind="artifact", identity={"digest": "changed"}, observed="new")],
        message="rewritten message",
        suggested_severity=EffectiveSeverity.HARD_USER,
    )
    assert first.finding_id == second.finding_id
    assert first.finding_id.startswith("gf1_")
    assert stable_finding_id(identity_version="v1", gate_id="g", subject_key="s", scope=SCOPE) != stable_finding_id(
        identity_version="v1", gate_id="g", subject_key="s", scope={"project": "demo", "chapter": 4}
    )


def test_finding_identity_scope_is_deeply_immutable_after_id_creation():
    nested_mapping = UserDict({"name": "stable"})
    supplied_scope = {"project": "demo", "chapter": 3, "labels": ["one", nested_mapping]}
    finding = make_finding(scope=supplied_scope)
    original_id = finding.finding_id

    with pytest.raises(TypeError):
        finding.scope["chapter"] = 4
    with pytest.raises(TypeError):
        finding.scope["labels"][1]["name"] = "changed"
    with pytest.raises(TypeError):
        dict.__setitem__(finding.scope, "chapter", 4)
    assert isinstance(finding.scope["labels"], tuple)
    assert finding.model_dump(mode="json")["scope"] == supplied_scope

    # Freezing also detaches identity state from the caller's input object.
    supplied_scope["chapter"] = 8
    nested_mapping["name"] = "external mutation"
    assert finding.finding_id == original_id
    assert stable_finding_id(
        identity_version=finding.identity_version,
        gate_id=finding.gate_id,
        subject_key=finding.stable_subject_key,
        scope=finding.scope,
    ) == original_id


def test_unstable_subject_cannot_produce_identity_or_veto():
    with pytest.raises(ValueError):
        stable_finding_id(identity_version="v1", gate_id="g", subject_key="", scope=SCOPE)
    finding = make_finding(stable_subject_key=None)
    assert finding.finding_id is None
    decision = evaluate(finding).decisions[0]
    assert decision.effective_severity == EffectiveSeverity.ADVISORY
    assert decision.effective_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_evidence_and_input_fingerprints_change_independently_of_identity():
    before = make_finding()
    after = make_finding(evidence=[EvidenceRef(kind="span", identity={"start": 22}, observed="rewritten")])
    assert before.finding_id == after.finding_id
    assert fingerprint_evidence(before.evidence) != fingerprint_evidence(after.evidence)
    assert fingerprint_policy_inputs([before], "gate-policy/v1", SCOPE) != fingerprint_policy_inputs([after], "gate-policy/v1", SCOPE)
    assert fingerprint_policy_inputs([before], "gate-policy/v1", SCOPE) == fingerprint_policy_inputs([copy.deepcopy(before)], "gate-policy/v1", SCOPE)


def test_fingerprints_ignore_finding_order_but_bind_policy_version():
    a, b = make_finding(stable_subject_key="a"), make_finding(stable_subject_key="b")
    assert fingerprint_policy_inputs([a, b], "v1", SCOPE) == fingerprint_policy_inputs([b, a], "v1", SCOPE)
    assert fingerprint_policy_inputs([a], "v1", SCOPE) != fingerprint_policy_inputs([a], "v2", SCOPE)


def test_policy_empty_and_action_precedence():
    assert evaluate().aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY
    low = make_finding(stable_subject_key="low")
    human = make_finding(stable_subject_key="human", category="DISAMBIGUATION", authority="SYSTEM_INTEGRITY")
    recover = make_finding(stable_subject_key="recover", category="PROJECTION_HEALTH", authority="SYSTEM_INTEGRITY", evidence=[EvidenceRef(kind="recovery_required", identity={"projection": "state"})])
    hard = make_finding(stable_subject_key="hard", category="INTEGRITY", authority="SYSTEM_INTEGRITY", evidence=[EvidenceRef(kind="deterministic_validation", identity={"valid": False, "validator_id": "schema.v1"})])
    assert evaluate(low, human, recover).aggregate_action == WorkflowAction.REQUIRE_HUMAN
    assert evaluate(low, recover).aggregate_action == WorkflowAction.RECOVER
    assert evaluate(human, hard).aggregate_action == WorkflowAction.REJECT


def test_llm_canon_candidate_never_self_asserts_hard_canon():
    finding = make_finding(category="CANON_CONTRADICTION", authority="LLM_REVIEW", suggested_severity="HARD_CANON", evidence=[EvidenceRef(kind="canon_contradiction", identity={"accepted_canon": True, "canon_event_id": "e1", "validator_id": "v1", "deterministic": True, "contradiction": True})])
    decision = evaluate(finding).decisions[0]
    assert decision.effective_severity == EffectiveSeverity.HUMAN_DECISION
    assert decision.effective_severity != EffectiveSeverity.HARD_CANON


def test_hard_canon_requires_accepted_linkage_and_deterministic_contradiction():
    evidence = EvidenceRef(kind="canon_contradiction", identity={"accepted_canon": True, "canon_event_id": "e1", "validator_id": "canon-check/v2", "deterministic": True, "contradiction": True})
    finding = make_finding(category="CANON_CONTRADICTION", authority="ACCEPTED_CANON", evidence=[evidence])
    assert evaluate(finding).decisions[0].effective_severity == EffectiveSeverity.HARD_CANON
    unproven = make_finding(category="CANON_CONTRADICTION", authority="ACCEPTED_CANON", evidence=[EvidenceRef(kind="canon_contradiction", identity={"accepted_canon": False})])
    assert evaluate(unproven).decisions[0].effective_severity != EffectiveSeverity.HARD_CANON


def test_hard_user_requires_all_explicit_contract_bindings():
    proof = EvidenceRef(kind="contract_constraint", identity={"constraint_id": "uc-3", "source_ref": "chapter:3/node:uc-3"}, source_ref="chapter:3/node:uc-3")
    valid = make_finding(category="USER_CONSTRAINT", authority="USER_EXPLICIT", explicitness="EXPLICIT", constraint_id="uc-3", source_ref="chapter:3/node:uc-3", evidence=[proof])
    assert evaluate(valid).decisions[0].effective_severity == EffectiveSeverity.HARD_USER
    identity_ref_only = EvidenceRef(kind="contract_constraint", identity={"constraint_id": "uc-3", "source_ref": "chapter:3/node:uc-3"})
    valid_with_typed_identity_ref = make_finding(category="USER_CONSTRAINT", authority="USER_EXPLICIT", explicitness="EXPLICIT", constraint_id="uc-3", source_ref="chapter:3/node:uc-3", evidence=[identity_ref_only])
    assert evaluate(valid_with_typed_identity_ref).decisions[0].effective_severity == EffectiveSeverity.HARD_USER
    mismatched_source_ref = EvidenceRef(kind="contract_constraint", identity={"constraint_id": "uc-3", "source_ref": "chapter:3/node:other"}, source_ref="chapter:3/node:other")
    mismatched = make_finding(category="USER_CONSTRAINT", authority="USER_EXPLICIT", explicitness="EXPLICIT", constraint_id="uc-3", source_ref="chapter:3/node:uc-3", evidence=[mismatched_source_ref])
    assert evaluate(mismatched).decisions[0].effective_severity != EffectiveSeverity.HARD_USER
    absent_evidence_source_ref = EvidenceRef(kind="contract_constraint", identity={"constraint_id": "uc-3"})
    absent_ref = make_finding(category="USER_CONSTRAINT", authority="USER_EXPLICIT", explicitness="EXPLICIT", constraint_id="uc-3", source_ref="chapter:3/node:uc-3", evidence=[absent_evidence_source_ref])
    assert evaluate(absent_ref).decisions[0].effective_severity != EffectiveSeverity.HARD_USER
    for change in ({"explicitness": "IMPLICIT"}, {"constraint_id": None, "evidence": [EvidenceRef(kind="contract_constraint", identity={})]}, {"source_ref": None, "evidence": [EvidenceRef(kind="contract_constraint", identity={"constraint_id": "uc-3"})]}, {"authority": "PLANNER_GENERATED"}):
        values = {"category": "USER_CONSTRAINT", "authority": "USER_EXPLICIT", "explicitness": "EXPLICIT", "constraint_id": "uc-3", "source_ref": "chapter:3/node:uc-3", "evidence": [proof]}
        values.update(change)
        assert evaluate(make_finding(**values)).decisions[0].effective_severity != EffectiveSeverity.HARD_USER


def test_author_plan_and_planner_misses_are_only_advisory_or_score():
    for authority in ("AUTHOR_PLAN", "PLANNER_GENERATED"):
        finding = make_finding(category="INTENT_FULFILLMENT", authority=authority, suggested_severity="HARD_USER")
        decision = evaluate(finding).decisions[0]
        assert decision.effective_severity == EffectiveSeverity.ADVISORY
        assert decision.effective_action == WorkflowAction.ALLOW_WITH_ADVISORY
        scored = make_finding(category="INTENT_FULFILLMENT", authority=authority, score={"kind": "satisfaction", "value": 0.15, "scale": [0.0, 1.0]})
        assert evaluate(scored).decisions[0].effective_severity == EffectiveSeverity.SCORE


@pytest.mark.parametrize("category", ["CRAFT", "STYLE"])
def test_craft_and_style_heuristics_never_hard_veto(category):
    finding = make_finding(category=category, authority="CRAFT_HEURISTIC", suggested_severity="HARD_USER")
    assert evaluate(finding).decisions[0].effective_severity == EffectiveSeverity.ADVISORY


@pytest.mark.parametrize("value", [0.0, 0.42, 1.0])
def test_score_is_advisory_at_all_threshold_values_and_not_hard_counted(value):
    finding = make_finding(category="CRAFT", authority="CRAFT_HEURISTIC", score={"kind": "pacing", "value": value, "scale": [0.0, 1.0]}, evidence=[EvidenceRef(kind="threshold", identity={"warn_below": 0.5})])
    result = evaluate(finding)
    assert result.decisions[0].effective_severity == EffectiveSeverity.SCORE
    assert result.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY
    assert result.hard_count == 0


def test_recoverable_and_workflow_findings_have_explicit_transitions():
    recover = make_finding(category="PROJECTION_HEALTH", authority="SYSTEM_INTEGRITY", evidence=[EvidenceRef(kind="recovery_required", identity={"projection": "index"})])
    assert evaluate(recover).decisions[0].effective_severity == EffectiveSeverity.RECOVERABLE
    choice = make_finding(category="WORKFLOW", authority="LEGACY_UNKNOWN", evidence=[EvidenceRef(kind="accountable_choice_required", identity={"choice": "referent"})])
    assert evaluate(choice).decisions[0].effective_severity == EffectiveSeverity.HUMAN_DECISION


def test_decisions_are_deterministic_and_include_distinct_fingerprints():
    finding = make_finding()
    first, second = evaluate(finding), evaluate(finding)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.decisions[0].evidence_fingerprint == fingerprint_evidence(finding.evidence)
    assert first.decisions[0].input_fingerprint == fingerprint_policy_inputs([finding], "gate-policy/v1", SCOPE)
