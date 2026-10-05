import pytest

from pathlib import Path

from scripts.consistency.core.patch_base import CheckContext, PatchFinding
from scripts.consistency.patches.p1_foreshadow_dag import P1ForeshadowDAG
from scripts.consistency.patches.p5_state_revision import P5StateRevision
from scripts.consistency.patches.p7_derived_views import P7DerivedViews
from data_modules.consistency_finding_adapters import P1_P7_MAPPING, adapt_consistency_patch
from data_modules.gate_severity_policy import GateSeverityPolicy
from data_modules.gate_findings import WorkflowAction


def test_mapping_contract_covers_exactly_p1_through_p7():
    assert set(P1_P7_MAPPING) == {
        "foreshadow_dag", "volume_anchor", "event_matrix", "pacing_tracker",
        "state_revision", "reader_contract", "derived_views",
    }
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


def test_diagnostic_findings_keep_runner_source_fingerprint():
    for row in (
        {"patch": "unknown_patch", "issue_code": "mystery", "input_ref": {"source_input_fingerprint": "abc123"}},
        PatchFinding(patch="foreshadow_dag", chapter=2, issue_code="cycle", message="cycle",
                     input_ref={"source_input_fingerprint": "def456"}),
    ):
        finding = adapt_consistency_patch(row, {"chapter": 2})[0]
        fingerprint = finding.evidence[0].identity["source_input_fingerprint"]
        assert fingerprint in {"abc123", "def456"}
        assert finding.authority.value == "LEGACY_UNKNOWN"


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


def test_unknown_legacy_row_wording_is_diagnostic_and_never_policy_authority():
    finding = adapt_consistency_patch(
        {"patch": "foreshadow_dag", "chapter": 2, "message": "BLOCKER: cycle detected", "fix_hint": "stop writing"},
        {"chapter": 2},
    )[0]
    decision = GateSeverityPolicy().evaluate([finding], policy_version="v1", scope={"chapter": 2})
    assert finding.authority.value == "LEGACY_UNKNOWN"
    assert finding.gate_id.endswith("diagnostic")
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


@pytest.mark.parametrize(
    ("patch", "issue_code", "evidence"),
    [
        ("volume_anchor", "progress_deviation", {"expected": 2, "observed": 3}),
        ("event_matrix", "gentle_quota", {"count": 1, "minimum": 2}),
        ("pacing_tracker", "slow_quota", {"count": 0, "minimum": 1}),
    ],
)
def test_craft_finding_with_evidence_and_no_subject_keeps_typed_mapping(patch, issue_code, evidence):
    finding = adapt_consistency_patch(
        PatchFinding(patch=patch, chapter=3, issue_code=issue_code, message="display only", evidence=evidence),
        {"chapter": 3},
    )[0]
    decision = GateSeverityPolicy().evaluate([finding], policy_version="v1", scope={"chapter": 3})
    assert finding.authority.value == "CRAFT_HEURISTIC"
    assert finding.category.value == "CRAFT"
    assert finding.stable_subject_key is None
    assert finding.subject_id is None
    assert decision.decisions[0].effective_severity.value in {"ADVISORY", "SCORE"}
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_real_p1_cycle_output_flows_through_adapter_and_shared_policy():
    ctx = CheckContext(
        project_root=Path("/tmp"), chapter_num=5,
        state={"story_craft": {"foreshadow_chain": [
            {"id": "A", "depends_on": ["B"]}, {"id": "B", "depends_on": ["A"]},
        ]}},
        chapter_outline=None, previous_chapters=[], chapter_text=None,
    )
    producer_rows = P1ForeshadowDAG().check(ctx)
    cycle = next(row for row in producer_rows if row.issue_code == "cycle")
    finding = adapt_consistency_patch(producer_rows, {"chapter": 5})[0]
    decision = GateSeverityPolicy().evaluate([finding], policy_version="v1", scope={"chapter": 5})
    assert cycle.subject_id == "cycle:A,B"
    assert finding.gate_id == "consistency.foreshadow_dag.cycle"
    assert decision.decisions[0].effective_severity.value == "HARD_INTEGRITY"


def test_real_p5_revision_output_requires_subject_and_maps_through_policy():
    ctx = CheckContext(
        project_root=Path("/tmp"), chapter_num=5,
        state={"state": {"_revision": 3}, "_expected_revision": 2},
        chapter_outline=None, previous_chapters=[], chapter_text=None,
    )
    row = P5StateRevision().check(ctx)[0]
    finding = adapt_consistency_patch(row, {"chapter": 5})[0]
    decision = GateSeverityPolicy().evaluate([finding], policy_version="v1", scope={"chapter": 5})
    assert row.issue_code == "revision_mismatch"
    assert finding.subject_id == "state:_revision"
    assert decision.decisions[0].effective_severity.value == "HARD_INTEGRITY"


def test_real_p7_projection_output_maps_to_recovery_without_commit_policy():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        views = root / ".webnovel" / "views"
        views.mkdir(parents=True)
        (views / "foreshadow_table.md").write_text("| fs-present |\n", encoding="utf-8")
        ctx = CheckContext(
            project_root=root, chapter_num=5,
            state={"state": {"_revision": 9}, "story_craft": {"foreshadow_chain": {"dag": [{"id": "fs-missing"}]}}},
            chapter_outline=None, previous_chapters=[], chapter_text=None,
        )
        row = P7DerivedViews().check(ctx)[0]
        finding = adapt_consistency_patch(row, {"chapter": 5})[0]
        decision = GateSeverityPolicy().evaluate([finding], policy_version="v1", scope={"chapter": 5})
        assert row.issue_code == "missing_foreshadow_view_row"
        assert finding.category.value == "PROJECTION_HEALTH"
        assert finding.subject_id == "foreshadow:fs-missing"
        assert decision.aggregate_action == WorkflowAction.RECOVER
