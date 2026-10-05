from dataclasses import fields

from consistency.core.patch_base import Blocker
from data_modules.consistency_finding_adapters import P1_P7_MAPPING, adapt_consistency_patch
from data_modules.gate_severity_policy import GateSeverityPolicy
from data_modules.gate_findings import WorkflowAction


def test_mapping_contract_covers_exactly_p1_through_p7_and_legacy_blocker_shape():
    assert set(P1_P7_MAPPING) == {
        "foreshadow_dag", "volume_anchor", "event_matrix", "pacing_tracker",
        "state_revision", "reader_contract", "derived_views",
    }
    assert {field.name for field in fields(Blocker)} == {"patch", "chapter", "message", "fix_hint"}
    assert not {"severity", "authority", "blocking"} & {field.name for field in fields(Blocker)}
    gates = [f"consistency.{patch}.{code}" for patch, codes in P1_P7_MAPPING.items() for code in codes]
    assert len(gates) == len(set(gates))


def test_subject_scoped_identity_survives_evidence_change_and_separates_subjects():
    first = adapt_consistency_patch([
        {"patch": "state_revision", "chapter": 8, "message": "free text A", "issue_code": "revision_mismatch", "subject_id": "state", "evidence": {"expected_revision": 2, "observed_revision": 3}},
        {"patch": "state_revision", "chapter": 8, "message": "free text B", "issue_code": "revision_mismatch", "subject_id": "chapter", "evidence": {"expected_revision": 2, "observed_revision": 3}},
    ], {"chapter": 8})
    second = adapt_consistency_patch(
            {"patch": "state_revision", "chapter": 8, "message": "entirely different prose", "issue_code": "revision_mismatch", "subject_id": "state", "evidence": {"expected_revision": 3, "observed_revision": 4}},
        {"chapter": 8})
    assert first[0].finding_id != first[1].finding_id
    assert first[0].finding_id == second[0].finding_id
    decision_a = GateSeverityPolicy().evaluate([first[0]], policy_version="v1", scope={"chapter": 8}).decisions[0]
    decision_b = GateSeverityPolicy().evaluate(second, policy_version="v1", scope={"chapter": 8}).decisions[0]
    assert decision_a.evidence_fingerprint != decision_b.evidence_fingerprint


def test_missing_identity_and_unknown_code_are_diagnostic_only():
    findings = adapt_consistency_patch([
        {"patch": "state_revision", "chapter": 2, "message": "revision mismatch", "issue_code": "revision_mismatch", "subject_id": "state", "evidence": {"expected_revision": 1}},
        {"patch": "state_revision", "chapter": 2, "message": "ignore prose"},
    ], {"chapter": 2})
    decision = GateSeverityPolicy().evaluate(findings, policy_version="v1", scope={"chapter": 2})
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_every_patch_has_representative_registered_mapping():
    rows = {
        "foreshadow_dag": "cycle", "volume_anchor": "progress_deviation",
        "event_matrix": "gentle_quota", "pacing_tracker": "slow_quota",
        "state_revision": "revision_mismatch", "reader_contract": "broken_promise",
        "derived_views": "missing_foreshadow_view_row",
    }
    for patch, code in rows.items():
        evidence = {"rule": code}
        subject = f"{patch}:subject"
        if patch == "foreshadow_dag":
            evidence = {"cycle_ids": ["A", "B"], "cycle_edges": [["A", "B"], ["B", "A"]]}
            subject = "cycle:A,B"
        elif patch == "state_revision":
            evidence = {"expected_revision": 2, "observed_revision": 3}
        elif patch == "derived_views":
            evidence = {"view": "foreshadow_table.md", "foreshadow_id": "FS-X", "present": False}
            subject = "foreshadow:FS-X"
        finding = adapt_consistency_patch(
            {"patch": patch, "chapter": 3, "message": "text is display-only", "issue_code": code, "subject_id": subject, "evidence": evidence},
            {"chapter": 3})[0]
        assert finding.finding_id and finding.gate_id.endswith(code)
        if patch in {"state_revision", "foreshadow_dag"}:
            assert finding.evidence[0].identity == {**evidence, "valid": False}
        else:
            assert finding.evidence[0].identity == evidence


def test_p1_cycle_and_overdue_are_adapter_contract_mappings():
    rows = [
        {"patch": "foreshadow_dag", "chapter": 100, "issue_code": "cycle",
         "subject_id": "cycle:A,B", "evidence": {"cycle_ids": ["A", "B"],
         "cycle_edges": [["A", "B"], ["B", "A"]]}},
        {"patch": "foreshadow_dag", "chapter": 100, "issue_code": "overdue",
         "subject_id": "foreshadow:OLD", "evidence": {"deadline": 3, "observed": 100}},
    ]
    findings = adapt_consistency_patch(rows, {"chapter": 100})
    decisions = [GateSeverityPolicy().evaluate([finding], policy_version="v1",
        scope={"chapter": 100}).decisions[0] for finding in findings]
    assert decisions[0].effective_severity.value == "HARD_INTEGRITY"
    assert decisions[1].effective_severity.value == "ADVISORY"


def test_p7_stale_derived_view_is_adapter_contract_recovery_mapping():
    finding = adapt_consistency_patch({
        "patch": "derived_views", "chapter": 4, "issue_code": "missing_foreshadow_view_row",
        "subject_id": "foreshadow:FS-4", "evidence": {
            "view": "foreshadow_table.md", "foreshadow_id": "FS-4", "present": False,
        },
    }, {"chapter": 4})[0]
    decision = GateSeverityPolicy().evaluate([finding], policy_version="v1", scope={"chapter": 4})
    assert decision.aggregate_action == WorkflowAction.RECOVER
