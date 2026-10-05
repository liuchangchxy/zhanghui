"""Stable mapping contract from consistency observations to shared findings."""
from __future__ import annotations

from typing import Any

from .gate_findings import DetectedFinding, EvidenceRef, Explicitness, FindingAuthority, FindingCategory


_CRAFT = {"category": FindingCategory.CRAFT, "authority": FindingAuthority.CRAFT_HEURISTIC,
          "explicitness": Explicitness.UNKNOWN, "evidence_kind": "craft_observation"}
_INTEGRITY = {"category": FindingCategory.INTEGRITY, "authority": FindingAuthority.SYSTEM_INTEGRITY,
              "explicitness": Explicitness.UNKNOWN, "evidence_kind": "deterministic_validation"}

P1_P7_MAPPING: dict[str, dict[str, dict[str, Any]]] = {
    "foreshadow_dag": {
        **{code: dict(_CRAFT) for code in ("missing_id", "duplicate_id", "chronology", "overdue", "invalid_state")},
        "cycle": dict(_INTEGRITY),
    },
    "volume_anchor": {code: dict(_CRAFT) for code in ("missing_anchor", "malformed_anchor", "progress_deviation", "must_not_reveal", "invalid_state")},
    "event_matrix": {code: dict(_CRAFT) for code in ("malformed_history", "consecutive_fast", "gentle_quota", "invalid_state")},
    "pacing_tracker": {code: dict(_CRAFT) for code in ("malformed_history", "consecutive_fast", "slow_quota", "invalid_state")},
    "state_revision": {"revision_mismatch": dict(_INTEGRITY)},
    "reader_contract": {code: dict(_CRAFT) for code in ("high_expectation_debt", "unsetup_action", "endgame_limit", "high_swap_risk", "broken_promise", "invalid_state")},
    "derived_views": {"missing_foreshadow_view_row": {
        "category": FindingCategory.PROJECTION_HEALTH, "authority": FindingAuthority.SYSTEM_INTEGRITY,
        "explicitness": Explicitness.UNKNOWN, "evidence_kind": "recovery_required",
    }},
}


def _get(row: Any, name: str, default: Any = None) -> Any:
    return getattr(row, name, default) if not isinstance(row, dict) else row.get(name, default)


def adapt_consistency_patch(patch_result: Any, chapter_scope: dict[str, Any]) -> list[DetectedFinding]:
    rows = patch_result if isinstance(patch_result, list) else [patch_result]
    findings: list[DetectedFinding] = []
    chapter = chapter_scope.get("chapter")
    for row in rows:
        patch = _get(row, "patch")
        code = _get(row, "issue_code")
        subject = _get(row, "subject_id")
        raw_evidence = _get(row, "evidence", {})
        mapping = P1_P7_MAPPING.get(patch, {}).get(code) if isinstance(patch, str) and isinstance(code, str) else None
        input_ref = _get(row, "input_ref", {})
        source_fingerprint = input_ref.get("source_input_fingerprint") if isinstance(input_ref, dict) else None
        if not mapping:
            diagnostic_identity = {"patch": patch, "issue_code": code}
            if isinstance(source_fingerprint, str) and source_fingerprint:
                diagnostic_identity["source_input_fingerprint"] = source_fingerprint
            findings.append(DetectedFinding(
                gate_id=f"consistency.{patch or 'unknown'}.diagnostic",
                category=FindingCategory.WORKFLOW, authority=FindingAuthority.LEGACY_UNKNOWN,
                explicitness=Explicitness.UNKNOWN, scope=dict(chapter_scope), evidence=[
                    EvidenceRef(kind="legacy_diagnostic", identity=diagnostic_identity)
                ], checker_id="consistency.legacy", checker_version="adapter-v1",
                source_ref=(input_ref.get("source") if isinstance(input_ref, dict)
                            and isinstance(input_ref.get("source"), str) else None),
            ))
            continue
        structured_subject = subject if isinstance(subject, str) and subject.strip() else None
        evidence_identity = dict(raw_evidence) if isinstance(raw_evidence, dict) else {}
        has_structured_evidence = bool(evidence_identity)
        if isinstance(source_fingerprint, str) and source_fingerprint:
            evidence_identity["source_input_fingerprint"] = source_fingerprint
        # Craft observations with concrete evidence remain typed without an
        # invented identity. Integrity/recovery mappings require a stable
        # subject before they can carry their stronger policy semantics.
        evidence_is_sufficient = has_structured_evidence and (
            structured_subject is not None or mapping["category"] == FindingCategory.CRAFT
        )
        if patch == "state_revision":
            expected = evidence_identity.get("expected_revision")
            observed = evidence_identity.get("observed_revision")
            evidence_is_sufficient = (
                evidence_is_sufficient and isinstance(expected, int) and not isinstance(expected, bool)
                and isinstance(observed, int) and not isinstance(observed, bool) and expected != observed
            )
        elif patch == "foreshadow_dag" and code == "cycle":
            cycle_ids = evidence_identity.get("cycle_ids")
            cycle_edges = evidence_identity.get("cycle_edges")
            evidence_is_sufficient = (
                evidence_is_sufficient
                and isinstance(cycle_ids, list) and len(cycle_ids) >= 1
                and all(isinstance(item, str) and item for item in cycle_ids)
                and cycle_ids == sorted(set(cycle_ids))
                and structured_subject == f"cycle:{','.join(cycle_ids)}"
                and isinstance(cycle_edges, list) and bool(cycle_edges)
                and all(isinstance(edge, (list, tuple)) and len(edge) == 2
                        and edge[0] in cycle_ids and edge[1] in cycle_ids for edge in cycle_edges)
            )
        elif patch == "derived_views":
            evidence_is_sufficient = (
                evidence_is_sufficient and evidence_identity.get("view") == "foreshadow_table.md"
                and evidence_identity.get("present") is False
                and isinstance(evidence_identity.get("foreshadow_id"), str)
                and structured_subject == f"foreshadow:{evidence_identity.get('foreshadow_id')}"
        )
        if not evidence_is_sufficient:
            diagnostic_identity = {"patch": patch, "issue_code": code}
            if isinstance(source_fingerprint, str) and source_fingerprint:
                diagnostic_identity["source_input_fingerprint"] = source_fingerprint
            findings.append(DetectedFinding(
                gate_id=f"consistency.{patch}.{code}.diagnostic",
                category=FindingCategory.WORKFLOW, authority=FindingAuthority.LEGACY_UNKNOWN,
                explicitness=Explicitness.UNKNOWN, scope=dict(chapter_scope), evidence=[
                    EvidenceRef(kind="legacy_diagnostic", identity=diagnostic_identity)
                ], checker_id=f"consistency.{patch}", checker_version="adapter-v1",
                source_ref=(input_ref.get("source") if isinstance(input_ref, dict)
                            and isinstance(input_ref.get("source"), str) else None),
            ))
            continue
        if mapping["evidence_kind"] == "deterministic_validation":
            evidence_identity = {**evidence_identity, "valid": False}
        findings.append(DetectedFinding(
            gate_id=f"consistency.{patch}.{code}", stable_subject_key=structured_subject,
            category=mapping["category"], authority=mapping["authority"],
            explicitness=mapping["explicitness"], scope=dict(chapter_scope),
            evidence=[EvidenceRef(kind=mapping["evidence_kind"], identity=evidence_identity)],
            subject_id=structured_subject,
            source_ref=(input_ref.get("source") if isinstance(input_ref, dict)
                        and isinstance(input_ref.get("source"), str) else None),
            checker_id=_get(row, "checker_id") or f"consistency.{patch}",
            checker_version=_get(row, "checker_version") or "adapter-v1",
        ))
    return findings
