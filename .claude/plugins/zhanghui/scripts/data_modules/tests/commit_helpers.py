from data_modules.reconciliation import reconcile_changes
from data_modules.gate_finding_adapters import adapt_legacy_artifacts
from data_modules.gate_findings import WorkflowAction
from data_modules.gate_severity_policy import GateSeverityPolicy
import json

EMPTY_PROPOSAL = {
    "character_state_changes": [], "new_plot_points": [],
    "foreshadowing_actions": [], "location_state_changes": [],
    "faction_state_changes": [], "time_progression": None,
    "item_transfers": [], "unresolved_questions": [],
}


def build_commit_with_reconciliation(service, **kwargs):
    extraction = kwargs.get("extraction_result", {})
    kwargs.setdefault("proposed_changes", EMPTY_PROPOSAL)
    kwargs.setdefault(
        "chapter_text",
        "test final prose\n<chapter_changes>"
        + json.dumps(kwargs["proposed_changes"], ensure_ascii=False)
        + "</chapter_changes>",
    )
    kwargs["reconciliation_result"] = reconcile_changes(
        kwargs["proposed_changes"],
        extraction,
        chapter_text=kwargs["chapter_text"],
    )
    findings = adapt_legacy_artifacts(
        chapter=kwargs["chapter"], review=kwargs["review_result"],
        fulfillment=kwargs["fulfillment_result"], disambiguation=kwargs["disambiguation_result"],
    )
    decisions = GateSeverityPolicy().evaluate(
        findings, policy_version="test-v1", scope={"chapter": kwargs["chapter"]},
    )
    if decisions.aggregate_action in {WorkflowAction.REQUIRE_HUMAN, WorkflowAction.RECOVER}:
        return None
    payload = service.build_commit(**kwargs)
    if decisions.aggregate_action == WorkflowAction.REJECT:
        payload["meta"]["status"] = "rejected"
        extraction_payload = payload.get("extraction_result") or {}
        extraction_payload["accepted_events"] = []
        extraction_payload["state_deltas"] = []
        extraction_payload["entity_deltas"] = []
    return payload
