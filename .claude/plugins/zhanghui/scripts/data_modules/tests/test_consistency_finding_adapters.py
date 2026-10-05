from dataclasses import fields

from consistency.core.patch_base import Blocker
from consistency.core.patch_base import CheckContext
from consistency.patches.p5_state_revision import P5StateRevision
from consistency.patches.p1_foreshadow_dag import P1ForeshadowDAG
from consistency.patches.p7_derived_views import P7DerivedViews
from data_modules.consistency_finding_adapters import P1_P7_MAPPING, adapt_consistency_patch
from data_modules.gate_severity_policy import GateSeverityPolicy
from data_modules.gate_findings import WorkflowAction


def test_mapping_contract_covers_exactly_p1_through_p7_and_legacy_blocker_shape():
    assert set(P1_P7_MAPPING) == {
        "foreshadow_dag", "volume_anchor", "event_matrix", "pacing_tracker",
        "state_revision", "reader_contract", "derived_views",
    }
    assert {field.name for field in fields(Blocker)} >= {"patch", "chapter", "message", "fix_hint", "issue_code", "subject_id", "evidence"}
    assert not {"severity", "authority", "blocking"} & {field.name for field in fields(Blocker)}
    gates = [f"consistency.{patch}.{code}" for patch, codes in P1_P7_MAPPING.items() for code in codes]
    assert len(gates) == len(set(gates))


def test_subject_scoped_identity_survives_evidence_change_and_separates_subjects():
    first = adapt_consistency_patch([
        Blocker("state_revision", 8, "free text A", "", "revision_mismatch", "state", {"expected_revision": 2, "observed_revision": 3}),
        Blocker("state_revision", 8, "free text B", "", "revision_mismatch", "chapter", {"expected_revision": 2, "observed_revision": 3}),
    ], {"chapter": 8})
    second = adapt_consistency_patch(
            Blocker("state_revision", 8, "entirely different prose", "", "revision_mismatch", "state", {"expected_revision": 3, "observed_revision": 4}),
        {"chapter": 8})
    assert first[0].finding_id != first[1].finding_id
    assert first[0].finding_id == second[0].finding_id
    decision_a = GateSeverityPolicy().evaluate([first[0]], policy_version="v1", scope={"chapter": 8}).decisions[0]
    decision_b = GateSeverityPolicy().evaluate(second, policy_version="v1", scope={"chapter": 8}).decisions[0]
    assert decision_a.evidence_fingerprint != decision_b.evidence_fingerprint


def test_missing_identity_and_unknown_code_are_diagnostic_only():
    findings = adapt_consistency_patch([
        Blocker("state_revision", 2, "revision mismatch", "", "revision_mismatch", "state", {"expected_revision": 1}),
        Blocker("state_revision", 2, "ignore prose", "", None, None, {}),
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
            Blocker(patch, 3, "text is display-only", "", code, subject, evidence),
            {"chapter": 3})[0]
        assert finding.finding_id and finding.gate_id.endswith(code)
        if patch in {"state_revision", "foreshadow_dag"}:
            assert finding.evidence[0].identity == {**evidence, "valid": False}
        else:
            assert finding.evidence[0].identity == evidence


def test_veto_relevant_p5_and_p7_producers_emit_typed_identity_and_evidence(tmp_path):
    p5 = P5StateRevision().check(CheckContext(
        project_root=tmp_path, chapter_num=4,
        state={"_expected_revision": 3, "state": {"_revision": 4}},
        chapter_outline=None, previous_chapters=[], chapter_text=None,
    ))[0]
    assert p5.issue_code == "revision_mismatch"
    assert p5.subject_id == "chapter:4:state_revision"
    assert p5.evidence == {"expected_revision": 3, "observed_revision": 4}

    views = tmp_path / ".webnovel" / "views"
    views.mkdir(parents=True)
    (views / "foreshadow_table.md").write_text("# empty", encoding="utf-8")
    p7 = P7DerivedViews().check(CheckContext(
        project_root=tmp_path, chapter_num=4,
        state={"story_craft": {"foreshadow_chain": [{"id": "FS-4"}]}},
        chapter_outline=None, previous_chapters=[], chapter_text=None,
    ))[0]
    assert p7.issue_code == "missing_foreshadow_view_row"
    assert p7.subject_id == "foreshadow:FS-4"
    decision = GateSeverityPolicy().evaluate(
        adapt_consistency_patch([p7], {"chapter": 4}), policy_version="v1", scope={"chapter": 4},
    )
    assert decision.aggregate_action == WorkflowAction.RECOVER


def test_real_p1_cycle_is_hard_integrity_and_overdue_stays_advisory(tmp_path):
    patch = P1ForeshadowDAG()
    cycle_context = CheckContext(
        project_root=tmp_path, chapter_num=100,
        state={"story_craft": {"foreshadow_chain": [
            {"id": "A", "depends_on": ["B"]},
            {"id": "B", "depends_on": ["A"], "status": "inactive"},
            {"id": "OLD", "status": "active", "paid_off_chapter": 1},
        ]}},
        chapter_outline=None, previous_chapters=[], chapter_text=None,
    )
    rows = patch.check(cycle_context)
    cycle = next(row for row in rows if row.issue_code == "cycle")
    overdue = next(row for row in rows if row.issue_code == "overdue")
    assert cycle.subject_id == "cycle:A,B"
    assert cycle.evidence["cycle_ids"] == ["A", "B"]

    findings = adapt_consistency_patch(rows, {"chapter": 100})
    cycle_finding = next(row for row in findings if row.gate_id.endswith(".cycle"))
    overdue_finding = next(row for row in findings if row.gate_id.endswith(".overdue"))
    cycle_decision = GateSeverityPolicy().evaluate(
        [cycle_finding], policy_version="v1", scope={"chapter": 100},
    )
    overdue_decision = GateSeverityPolicy().evaluate(
        [overdue_finding], policy_version="v1", scope={"chapter": 100},
    )
    assert cycle_decision.aggregate_action == WorkflowAction.REJECT
    assert cycle_decision.decisions[0].effective_severity.value == "HARD_INTEGRITY"
    assert overdue_decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY
    assert overdue_decision.decisions[0].effective_severity.value == "ADVISORY"

    changed_cycle_context = CheckContext(
        project_root=tmp_path, chapter_num=100,
        state={"story_craft": {"foreshadow_chain": [
            {"id": "A", "depends_on": ["A", "B"]},
            {"id": "B", "depends_on": ["A"], "status": "inactive"},
            {"id": "OLD", "status": "active", "paid_off_chapter": 1},
        ]}},
        chapter_outline=None, previous_chapters=[], chapter_text=None,
    )
    changed_cycle = next(row for row in patch.check(changed_cycle_context) if row.issue_code == "cycle")
    changed_finding = adapt_consistency_patch([changed_cycle], {"chapter": 100})[0]
    assert changed_finding.finding_id == cycle_finding.finding_id
    changed_decision = GateSeverityPolicy().evaluate(
        [changed_finding], policy_version="v1", scope={"chapter": 100},
    )
    assert changed_decision.decisions[0].evidence_fingerprint != cycle_decision.decisions[0].evidence_fingerprint
