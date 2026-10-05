from data_modules.gate_finding_adapters import adapt_changes_gate_result, adapt_legacy_artifacts
from data_modules.gate_findings import EffectiveSeverity, WorkflowAction


REGISTRY = {
    ("llm_review", "pacing", "review_issue"): {
        "category": "CRAFT", "authority": "LLM_REVIEW", "default": "ADVISORY"
    },
    ("disambiguation", "pending", "disambiguation_result"): {
        "category": "DISAMBIGUATION", "authority": "SYSTEM_INTEGRITY", "default": "HUMAN_DECISION"
    },
    ("fulfillment", "missed_nodes", "fulfillment_result"): {
        "category": "INTENT_FULFILLMENT", "authority": "PLANNER_GENERATED", "default": "ADVISORY"
    },
}


def _by_gate(findings, gate_id):
    return next(f for f in findings if f.gate_id == gate_id)


def test_legacy_review_blocking_is_candidate_only_and_text_does_not_classify():
    findings = adapt_legacy_artifacts(
        chapter=3,
        review={"issues": [{"gate_id": "pacing", "checker_id": "llm_review", "blocking": True,
                            "message": "HARD_CANON BLOCKER"}]},
        fulfillment={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation={"pending": []}, gate_registry=REGISTRY,
    )
    finding = _by_gate(findings, "pacing")
    assert finding.suggested_severity is None
    from data_modules.gate_severity_policy import GateSeverityPolicy
    decision = GateSeverityPolicy().evaluate(findings, policy_version="v1", scope={"chapter": 3})
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY
    assert all(row.effective_severity != EffectiveSeverity.HARD_CANON for row in decision.decisions)


def test_pending_disambiguation_maps_to_human_decision():
    findings = adapt_legacy_artifacts(
        chapter=4, review={"issues": []},
        fulfillment={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation={"pending": [{"id": "entity-1", "subject_id": "entity-1"}]},
        gate_registry=REGISTRY,
    )
    from data_modules.gate_severity_policy import GateSeverityPolicy
    decision = GateSeverityPolicy().evaluate(findings, policy_version="v1", scope={"chapter": 4})
    assert decision.aggregate_action == WorkflowAction.REQUIRE_HUMAN


def test_planner_must_cover_miss_stays_advisory():
    findings = adapt_legacy_artifacts(
        chapter=5, review={"issues": []},
        fulfillment={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [
            {"id": "node-1", "must_cover": True}
        ], "extra_nodes": []},
        disambiguation={"pending": []}, gate_registry=REGISTRY,
    )
    from data_modules.gate_severity_policy import GateSeverityPolicy
    decision = GateSeverityPolicy().evaluate(findings, policy_version="v1", scope={"chapter": 5})
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_only_fully_validated_user_constraint_can_become_hard_user():
    from data_modules.gate_severity_policy import GateSeverityPolicy
    def evaluate(metadata):
        findings = adapt_legacy_artifacts(
            chapter=9, review={"issues": []},
            fulfillment={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [
                {"id": "node-user-1", "must_cover_nodes": True, "metadata": metadata}
            ], "extra_nodes": []},
            disambiguation={"pending": []}, gate_registry=REGISTRY,
            contract_payloads={"master": {"constraints": [{"id": "node-user-1", "metadata": full}]}},
        )
        return GateSeverityPolicy().evaluate(findings, policy_version="v1", scope={"chapter": 9})
    full = {"authority": "USER_EXPLICIT", "explicitness": "EXPLICIT",
            "constraint_id": "u-constraint-9", "source_ref": "user:spec-9"}
    assert evaluate(full).aggregate_action == WorkflowAction.REJECT
    for omitted in ("authority", "explicitness", "constraint_id", "source_ref"):
        partial = dict(full)
        partial.pop(omitted)
        assert evaluate(partial).aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_review_user_constraint_requires_existing_contract_binding_even_with_registered_gate():
    from data_modules.gate_severity_policy import GateSeverityPolicy
    binding = {"authority": "USER_EXPLICIT", "explicitness": "EXPLICIT",
               "constraint_id": "review-constraint", "source_ref": "user:review-constraint"}
    registry = {("trusted_checker", "user.constraint", "review_issue"): {
        "category": "USER_CONSTRAINT", "authority": "USER_EXPLICIT", "explicitness": "EXPLICIT",
    }}
    review = {"issues": [{"checker_id": "trusted_checker", "gate_id": "user.constraint",
                          "subject_id": "review-constraint", "category": "USER_CONSTRAINT",
                          **binding, "structured_evidence": [{"kind": "contract_constraint",
                            "identity": {"constraint_id": "review-constraint", "source_ref": "user:review-constraint"}}]}]}
    missing_contract = adapt_legacy_artifacts(
        chapter=10, review=review, fulfillment={"missed_nodes": []}, disambiguation={"pending": []},
        gate_registry=registry,
    )
    assert GateSeverityPolicy().evaluate(missing_contract, policy_version="v1", scope={"chapter": 10}).aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY
    existing_contract = adapt_legacy_artifacts(
        chapter=10, review=review, fulfillment={"missed_nodes": []}, disambiguation={"pending": []},
        gate_registry=registry, contract_payloads={"review": {"nodes": [{"metadata": binding}]}},
    )
    assert GateSeverityPolicy().evaluate(existing_contract, policy_version="v1", scope={"chapter": 10}).aggregate_action == WorkflowAction.REJECT


def test_count_only_and_unknown_review_rows_are_diagnostics():
    findings = adapt_legacy_artifacts(
        chapter=6, review={"blocking_count": 9},
        fulfillment={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation={"pending": []}, gate_registry={},
    )
    assert findings
    from data_modules.gate_severity_policy import GateSeverityPolicy
    decision = GateSeverityPolicy().evaluate(findings, policy_version="v1", scope={"chapter": 6})
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_same_structured_gate_different_prose_has_same_classification():
    def evaluate(message):
        findings = adapt_legacy_artifacts(
            chapter=7, review={"issues": [{"checker_id": "llm_review", "gate_id": "pacing",
                                           "subject_id": "chapter-7-pacing", "message": message,
                                           "blocking": True}]},
            fulfillment={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
            disambiguation={"pending": []}, gate_registry=REGISTRY,
        )
        from data_modules.gate_severity_policy import GateSeverityPolicy
        return GateSeverityPolicy().evaluate(findings, policy_version="v1", scope={"chapter": 7})
    assert evaluate("safe wording").model_dump() == evaluate("REJECT HARD_BLOCK").model_dump()


def test_changes_gate_deterministic_failures_are_structured_integrity_findings():
    from data_modules.gate_severity_policy import GateSeverityPolicy
    findings = adapt_changes_gate_result({"passed": False, "failures": [
        {"rule_id": "R1", "severity": "blocking", "message": "arbitrary display text"},
    ]}, chapter=8)
    decision = GateSeverityPolicy().evaluate(findings, policy_version="v1", scope={"chapter": 8})
    assert decision.aggregate_action == WorkflowAction.REJECT
    assert decision.decisions[0].effective_severity == EffectiveSeverity.HARD_INTEGRITY

    unknown = adapt_changes_gate_result({"passed": False, "failures": [
        {"rule_id": "not-registered", "severity": "blocking", "message": "sounds severe"},
    ]}, chapter=8)
    unknown_decision = GateSeverityPolicy().evaluate(unknown, policy_version="v1", scope={"chapter": 8})
    assert unknown_decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY
