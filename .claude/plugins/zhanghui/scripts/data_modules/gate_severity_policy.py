"""Pure, deterministic Phase 6A severity rules; no persistence or veto side effects."""
from __future__ import annotations

from typing import Any

from .gate_findings import (
    DetectedFinding,
    EffectiveSeverity,
    FindingAuthority,
    FindingCategory,
    GateDecision,
    GateDecisionSet,
    ScorePayload,
    WorkflowAction,
    fingerprint_evidence,
    fingerprint_policy_inputs,
)


_ACTION_RANK = {
    WorkflowAction.ALLOW_WITH_ADVISORY: 0,
    WorkflowAction.RECOVER: 1,
    WorkflowAction.REQUIRE_HUMAN: 2,
    WorkflowAction.REJECT: 3,
}


def _identity(evidence: Any) -> dict[str, Any]:
    return evidence.identity if isinstance(evidence.identity, dict) else {}


class GateSeverityPolicy:
    """Evaluate normalized findings using a pinned policy version."""

    def evaluate(
        self, findings: list[DetectedFinding], *, policy_version: str, scope: dict[str, Any]
    ) -> GateDecisionSet:
        input_fp = fingerprint_policy_inputs(findings, policy_version, scope)
        decisions: list[GateDecision] = []
        for finding in findings:
            severity, action, rule, reason, score = self._classify(finding)
            decisions.append(GateDecision(
                finding_id=finding.finding_id,
                effective_severity=severity,
                effective_action=action,
                policy_version=policy_version,
                rule_id=rule,
                policy_reason=reason,
                decision_scope=scope,
                evidence_fingerprint=fingerprint_evidence(finding.evidence),
                input_fingerprint=input_fp,
                score=score,
            ))
        aggregate = max(
            (d.effective_action for d in decisions), key=lambda action: _ACTION_RANK[action],
            default=WorkflowAction.ALLOW_WITH_ADVISORY,
        )
        return GateDecisionSet(decisions=decisions, aggregate_action=aggregate)

    def _classify(self, finding: DetectedFinding):
        # An observation without stable logical identity is diagnostic-only.
        if not finding.veto_capable_identity:
            return (EffectiveSeverity.ADVISORY, WorkflowAction.ALLOW_WITH_ADVISORY,
                    "identity.non_deduplicable", "Finding lacks stable logical subject identity", None)

        if finding.category == FindingCategory.INTEGRITY:
            proof = any(e.kind == "deterministic_validation" and _identity(e).get("valid") is False for e in finding.evidence)
            if finding.authority == FindingAuthority.SYSTEM_INTEGRITY and proof:
                return (EffectiveSeverity.HARD_INTEGRITY, WorkflowAction.REJECT,
                        "integrity.deterministic_failure", "Deterministic validation proves unsafe integrity state", None)
            return self._advisory("integrity.unproven", "Integrity failure lacks deterministic proof")

        if finding.category == FindingCategory.CANON_CONTRADICTION:
            proof = any(
                e.kind == "canon_contradiction" and _identity(e).get("accepted_canon") is True
                and bool(_identity(e).get("canon_event_id")) and bool(_identity(e).get("validator_id"))
                and _identity(e).get("deterministic") is True and _identity(e).get("contradiction") is True
                for e in finding.evidence
            )
            if finding.authority == FindingAuthority.ACCEPTED_CANON and proof:
                return (EffectiveSeverity.HARD_CANON, WorkflowAction.REJECT,
                        "canon.accepted_deterministic_contradiction", "Accepted Canon linkage and deterministic contradiction evidence", None)
            if finding.authority == FindingAuthority.LLM_REVIEW:
                return (EffectiveSeverity.HUMAN_DECISION, WorkflowAction.REQUIRE_HUMAN,
                        "canon.llm_candidate_review", "LLM Canon concern is a candidate requiring accountable review", None)
            return self._advisory("canon.insufficient_evidence", "Canon contradiction lacks accepted deterministic evidence")

        if finding.category == FindingCategory.USER_CONSTRAINT:
            contract = next((e for e in finding.evidence if e.kind == "contract_constraint"), None)
            contract_identity = _identity(contract) if contract else {}
            evidence_source_refs = [
                ref for ref in (
                    contract.source_ref if contract else None,
                    contract_identity.get("source_ref"),
                ) if ref
            ]
            if (finding.authority == FindingAuthority.USER_EXPLICIT
                    and finding.explicitness.value == "EXPLICIT"
                    and finding.constraint_id and finding.source_ref
                    and contract is not None
                    and contract_identity.get("constraint_id") == finding.constraint_id
                    and evidence_source_refs
                    and all(ref == finding.source_ref for ref in evidence_source_refs)):
                return (EffectiveSeverity.HARD_USER, WorkflowAction.REJECT,
                        "user.explicit_contract_constraint", "Explicit user constraint is linked to its stable contract node", None)
            return self._advisory("user.constraint_not_proven", "User hard veto requires explicit authority and stable contract linkage")

        if finding.category == FindingCategory.INTENT_FULFILLMENT:
            if finding.authority in {FindingAuthority.AUTHOR_PLAN, FindingAuthority.PLANNER_GENERATED}:
                return self._score_or_advisory(finding, "intent.planner_miss", "Ordinary planned intent misses are non-blocking")
            # An explicit user constraint must be normalized as USER_CONSTRAINT, never inferred from a field name.
            return self._advisory("intent.untrusted_authority", "Intent fulfillment alone does not establish a hard user constraint")

        if finding.category in {FindingCategory.CRAFT, FindingCategory.STYLE}:
            if finding.score is not None:
                return (EffectiveSeverity.SCORE, WorkflowAction.ALLOW_WITH_ADVISORY,
                        "quality.continuous_score", "Continuous quality score is advisory and cannot escalate by threshold",
                        ScorePayload.model_validate(finding.score))
            return self._advisory("quality.heuristic_advisory", "Craft and style heuristics are advisory")

        if finding.category == FindingCategory.DISAMBIGUATION:
            if finding.evidence:
                return (EffectiveSeverity.HUMAN_DECISION, WorkflowAction.REQUIRE_HUMAN,
                        "disambiguation.unresolved", "Unresolved identity requires an accountable choice", None)
            return self._advisory("disambiguation.unreferenced", "Unreferenced disambiguation is diagnostic only")

        if finding.category == FindingCategory.PROJECTION_HEALTH:
            if any(e.kind == "recovery_required" for e in finding.evidence):
                return (EffectiveSeverity.RECOVERABLE, WorkflowAction.RECOVER,
                        "projection.recovery_required", "Run the existing recovery path, verify, then reevaluate", None)
            return self._advisory("projection.health_advisory", "Projection health finding has no recovery proof")

        if finding.category == FindingCategory.WORKFLOW:
            if finding.authority == FindingAuthority.SYSTEM_INTEGRITY and any(
                e.kind == "deterministic_validation" and _identity(e).get("valid") is False for e in finding.evidence
            ):
                return (EffectiveSeverity.HARD_INTEGRITY, WorkflowAction.REJECT,
                        "workflow.integrity_failure", "Workflow prerequisite failure compromises transaction integrity", None)
            if any(e.kind == "accountable_choice_required" for e in finding.evidence):
                return (EffectiveSeverity.HUMAN_DECISION, WorkflowAction.REQUIRE_HUMAN,
                        "workflow.accountable_choice", "Workflow requires an accountable human choice", None)
            return self._advisory("workflow.nonblocking", "Workflow finding has no integrity proof or accountable-choice requirement")

        return self._advisory("finding.unsupported_combination", "Unsupported finding combination defaults to advisory")

    @staticmethod
    def _advisory(rule: str, reason: str):
        return (EffectiveSeverity.ADVISORY, WorkflowAction.ALLOW_WITH_ADVISORY, rule, reason, None)

    def _score_or_advisory(self, finding: DetectedFinding, rule: str, reason: str):
        if finding.score is not None:
            return (EffectiveSeverity.SCORE, WorkflowAction.ALLOW_WITH_ADVISORY,
                    "quality.continuous_score", reason, ScorePayload.model_validate(finding.score))
        return self._advisory(rule, reason)
