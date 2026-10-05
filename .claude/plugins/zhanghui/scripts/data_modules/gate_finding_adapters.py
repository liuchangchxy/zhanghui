"""Exact-key adapters for legacy review, fulfillment and disambiguation rows.

Classification consumes structured gate/checker/artifact identity only. Display
text is intentionally ignored.
"""
from __future__ import annotations

from typing import Any

from .gate_findings import (
    DetectedFinding, EvidenceRef, Explicitness, FindingAuthority,
    FindingCategory, ScorePayload,
)
from .story_contracts import collect_user_constraint_bindings, validated_user_constraint_metadata


DEFAULT_GATE_REGISTRY: dict[tuple[str, str, str], dict[str, Any]] = {
    ("llm_review", "pacing", "review_issue"): {
        "category": FindingCategory.CRAFT, "authority": FindingAuthority.LLM_REVIEW,
        "explicitness": Explicitness.UNKNOWN, "rule_id": "review.pacing_advisory",
    },
    ("llm_review", "canon.contradiction", "review_issue"): {
        "category": FindingCategory.CANON_CONTRADICTION, "authority": FindingAuthority.LLM_REVIEW,
        "explicitness": Explicitness.UNKNOWN, "rule_id": "review.canon_candidate",
    },
    ("disambiguation", "pending", "disambiguation_result"): {
        "category": FindingCategory.DISAMBIGUATION, "authority": FindingAuthority.SYSTEM_INTEGRITY,
        "explicitness": Explicitness.EXPLICIT, "rule_id": "disambiguation.pending",
    },
    ("fulfillment", "missed_nodes", "fulfillment_result"): {
        "category": FindingCategory.INTENT_FULFILLMENT, "authority": FindingAuthority.PLANNER_GENERATED,
        "explicitness": Explicitness.UNKNOWN, "rule_id": "intent.missed_node",
    },
    **{
        ("story_craft", gate, "review_issue"): {
            "category": FindingCategory.CRAFT, "authority": FindingAuthority.CRAFT_HEURISTIC,
            "explicitness": Explicitness.UNKNOWN, "rule_id": gate,
        }
        for gate in (
            "story_craft.heuristic", "story_craft.volume_beat", "story_craft.rhythm_curve",
            "story_craft.timed_lock", "story_craft.scene_sequel", "story_craft.hook_type",
        )
    },
}


def _enum(enum_type, value, default):
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError):
        return default


def _obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _evidence_refs(raw: Any, *, fallback_kind: str, fallback_identity: Any) -> list[EvidenceRef]:
    rows = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    out: list[EvidenceRef] = []
    for row in rows:
        if isinstance(row, EvidenceRef):
            out.append(row)
        elif isinstance(row, dict) and isinstance(row.get("kind"), str) and "identity" in row:
            try:
                out.append(EvidenceRef.model_validate(row))
            except Exception:
                continue
    if not out and fallback_identity is not None:
        out.append(EvidenceRef(kind=fallback_kind, identity=fallback_identity))
    return out


def _finding(*, chapter: int, checker_id: str, gate_id: str, category: Any,
             authority: Any, explicitness: Any, subject_id: str | None,
             evidence: list[EvidenceRef], score: Any = None, source_ref: str | None = None,
             constraint_id: str | None = None, message: str | None = None) -> DetectedFinding:
    scope = {"chapter": chapter}
    safe_subject = subject_id.strip() if isinstance(subject_id, str) and subject_id.strip() else None
    return DetectedFinding(
        gate_id=gate_id, stable_subject_key=safe_subject,
        category=_enum(FindingCategory, category, FindingCategory.WORKFLOW),
        authority=_enum(FindingAuthority, authority, FindingAuthority.LEGACY_UNKNOWN),
        explicitness=_enum(Explicitness, explicitness, Explicitness.UNKNOWN),
        scope=scope, evidence=evidence, subject_id=safe_subject,
        constraint_id=constraint_id, source_ref=source_ref,
        checker_id=checker_id or "legacy_unknown", checker_version="adapter-v1",
        score=ScorePayload.model_validate(score).model_dump(mode="json") if score is not None else None,
        message=message,
    )


def adapt_legacy_artifacts(*, chapter: int, review: dict[str, Any], fulfillment: dict[str, Any],
                           disambiguation: dict[str, Any], gate_registry: dict | None = None,
                           contract_payloads: dict[str, Any] | None = None) -> list[DetectedFinding]:
    registry = {**DEFAULT_GATE_REGISTRY, **(gate_registry or {})}
    findings: list[DetectedFinding] = []
    contract_bindings = collect_user_constraint_bindings(contract_payloads or {})

    issues = review.get("issues") if isinstance(review, dict) else None
    if isinstance(issues, list):
        for row in issues:
            item = _obj(row)
            checker = item.get("checker_id") or "llm_review"
            gate = item.get("gate_id")
            if not isinstance(gate, str) or not gate:
                # Category and display labels are not gate identity. Retain a
                # diagnostic, but without a registered logical subject it is
                # never eligible for deduplication or veto.
                findings.append(_finding(chapter=chapter, checker_id=checker,
                    gate_id="legacy.review_issue.missing_gate", category=FindingCategory.WORKFLOW,
                    authority=FindingAuthority.LEGACY_UNKNOWN, explicitness=Explicitness.UNKNOWN,
                    subject_id=None, evidence=[EvidenceRef(kind="legacy_diagnostic",
                        identity={"artifact_type": "review_issue"})], message=item.get("message")))
                continue
            mapping = registry.get((checker, gate, "review_issue"))
            subject = item.get("subject_id")
            if not mapping:
                evidence = _evidence_refs(item.get("structured_evidence"), fallback_kind="legacy_diagnostic",
                                          fallback_identity={"artifact_type": "review_issue", "gate_id": gate})
                findings.append(_finding(chapter=chapter, checker_id=checker, gate_id=f"legacy.{gate}",
                    category=FindingCategory.WORKFLOW, authority=FindingAuthority.LEGACY_UNKNOWN,
                    explicitness=Explicitness.UNKNOWN, subject_id=None, evidence=evidence,
                    message=item.get("message")))
                continue
            evidence = _evidence_refs(item.get("structured_evidence"), fallback_kind="review_evidence",
                fallback_identity={"gate_id": gate, "subject_id": subject} if subject else None)
            category = mapping.get("category", FindingCategory.WORKFLOW)
            authority = mapping.get("authority", FindingAuthority.LEGACY_UNKNOWN)
            explicitness = mapping.get("explicitness", Explicitness.UNKNOWN)
            constraint_id = item.get("constraint_id")
            source_ref = item.get("source_ref")
            # Only validated contract metadata can turn a missed/violated item into USER_CONSTRAINT.
            if (item.get("category") == "USER_CONSTRAINT"
                    and item.get("authority") == "USER_EXPLICIT"
                    and item.get("explicitness") == "EXPLICIT"
                    and isinstance(constraint_id, str) and constraint_id.strip()
                    and isinstance(source_ref, str) and source_ref.strip()
                    and any(e.kind == "contract_constraint"
                            and isinstance(e.identity, dict)
                            and e.identity.get("constraint_id") == constraint_id
                            and e.identity.get("source_ref") == source_ref for e in evidence)
                    and contract_bindings.get(constraint_id, {}).get("source_ref") == source_ref):
                category, authority, explicitness = FindingCategory.USER_CONSTRAINT, FindingAuthority.USER_EXPLICIT, Explicitness.EXPLICIT
            elif category == FindingCategory.USER_CONSTRAINT:
                # A registry label cannot grant user authority by itself. If
                # the current contract does not prove the binding, retain the
                # row only as non-authoritative workflow diagnostic.
                category, authority, explicitness = (
                    FindingCategory.WORKFLOW, FindingAuthority.LEGACY_UNKNOWN, Explicitness.UNKNOWN
                )
            elif authority == FindingAuthority.LLM_REVIEW and category == FindingCategory.CANON_CONTRADICTION:
                # LLM-only canon allegations remain human candidates, never HARD_CANON.
                pass
            findings.append(_finding(chapter=chapter, checker_id=checker, gate_id=gate,
                category=category, authority=authority, explicitness=explicitness,
                subject_id=subject, evidence=evidence, constraint_id=constraint_id,
                source_ref=source_ref, score=mapping.get("score"), message=item.get("message")))

    pending = disambiguation.get("pending") if isinstance(disambiguation, dict) else None
    if isinstance(pending, list):
        for row in pending:
            item = _obj(row)
            subject = item.get("subject_id") or item.get("id")
            evidence = _evidence_refs(item.get("structured_evidence") or item.get("evidence"),
                fallback_kind="unresolved_identity", fallback_identity={"subject_id": subject} if subject else None)
            findings.append(_finding(chapter=chapter, checker_id="disambiguation", gate_id="disambiguation.pending",
                category=FindingCategory.DISAMBIGUATION, authority=FindingAuthority.SYSTEM_INTEGRITY,
                explicitness=Explicitness.EXPLICIT, subject_id=subject if isinstance(subject, str) else None,
                evidence=evidence, message=item.get("message")))

    missed = fulfillment.get("missed_nodes") if isinstance(fulfillment, dict) else None
    if isinstance(missed, list):
        for row in missed:
            item = _obj(row)
            node_id = item.get("node_id") or item.get("id")
            contract_binding = validated_user_constraint_metadata(item)
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            authority = (contract_binding or {}).get("authority") or (meta.get("authority") or ("AUTHOR_PLAN" if item.get("source") == "author" else "PLANNER_GENERATED"))
            explicitness = (contract_binding or {}).get("explicitness") or meta.get("explicitness", "UNKNOWN")
            constraint_id = (contract_binding or {}).get("constraint_id") or meta.get("constraint_id")
            source_ref = (contract_binding or {}).get("source_ref") or meta.get("source_ref")
            registered_binding = contract_bindings.get(str(constraint_id)) if constraint_id else None
            valid_user_binding = (
                contract_binding is not None and registered_binding is not None
                and registered_binding.get("source_ref") == contract_binding.get("source_ref")
            )
            category = FindingCategory.USER_CONSTRAINT if valid_user_binding else FindingCategory.INTENT_FULFILLMENT
            if valid_user_binding:
                evidence = [EvidenceRef(kind="contract_constraint", identity={
                    "constraint_id": constraint_id, "source_ref": source_ref,
                    "contract_node_id": node_id,
                }, source_ref=source_ref)]
            else:
                evidence = _evidence_refs(item.get("structured_evidence"), fallback_kind="missed_plan_node",
                                          fallback_identity={"node_id": node_id} if node_id else None)
            findings.append(_finding(chapter=chapter, checker_id="fulfillment", gate_id="fulfillment.missed_nodes",
                category=category, authority=authority, explicitness=explicitness,
                subject_id=(constraint_id if valid_user_binding else node_id) if isinstance((constraint_id if valid_user_binding else node_id), str) else None,
                evidence=evidence,
                constraint_id=constraint_id if isinstance(constraint_id, str) else None,
                source_ref=source_ref if isinstance(source_ref, str) else None))

    # A count is never expanded into synthetic rows or a veto-capable identity.
    if (not issues) and isinstance(review, dict) and review.get("blocking_count", 0):
        findings.append(_finding(chapter=chapter, checker_id="legacy_review", gate_id="legacy.review_count_only",
            category=FindingCategory.WORKFLOW, authority=FindingAuthority.LEGACY_UNKNOWN,
            explicitness=Explicitness.UNKNOWN, subject_id=None,
            evidence=[EvidenceRef(kind="count_only_diagnostic", identity={"artifact_type": "review_result"})]))
    return findings


def adapt_changes_gate_result(gate_result: dict[str, Any], *, chapter: int) -> list[DetectedFinding]:
    """Normalize CHANGES failures from registered rules and structured severity."""
    findings: list[DetectedFinding] = []
    failures = gate_result.get("failures") if isinstance(gate_result, dict) else None
    if not isinstance(failures, list):
        return findings
    deterministic_rules = {"R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"}
    hard_rules = {"R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7"}
    for row in failures:
        item = _obj(row)
        rule_id = item.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            findings.append(_finding(chapter=chapter, checker_id="changes_gate", gate_id="changes_gate.unknown",
                category=FindingCategory.WORKFLOW, authority=FindingAuthority.LEGACY_UNKNOWN,
                explicitness=Explicitness.UNKNOWN, subject_id=None,
                evidence=[EvidenceRef(kind="legacy_diagnostic", identity={"checker_id": "changes_gate"})]))
            continue
        if rule_id not in deterministic_rules:
            findings.append(_finding(chapter=chapter, checker_id="changes_gate", gate_id=f"changes_gate.{rule_id}",
                category=FindingCategory.WORKFLOW, authority=FindingAuthority.LEGACY_UNKNOWN,
                explicitness=Explicitness.UNKNOWN, subject_id=None,
                evidence=[EvidenceRef(kind="unsupported_rule_diagnostic", identity={"rule_id": rule_id})]))
            continue
        severity = item.get("severity")
        location = item.get("location")
        subject = f"changes-rule:{rule_id}:{location}" if isinstance(location, str) and location.strip() else None
        if severity != "blocking" or rule_id not in hard_rules:
            # Only registered blocking rules can establish hard integrity;
            # advisory, missing, and unknown values remain non-authoritative.
            is_r8_advisory = rule_id == "R8"
            findings.append(_finding(chapter=chapter, checker_id="changes_gate",
                gate_id=f"changes_gate.{rule_id}.advisory" if severity == "advisory" else f"changes_gate.{rule_id}.unclassified",
                category=FindingCategory.CRAFT if is_r8_advisory else FindingCategory.WORKFLOW,
                authority=FindingAuthority.CRAFT_HEURISTIC if is_r8_advisory else FindingAuthority.LEGACY_UNKNOWN,
                explicitness=Explicitness.UNKNOWN, subject_id=subject,
                evidence=[EvidenceRef(kind="advisory_observation" if severity == "advisory" else "legacy_diagnostic",
                    identity={"rule_id": rule_id, "location": location} if isinstance(location, str) else {"rule_id": rule_id})]))
            continue
        findings.append(_finding(chapter=chapter, checker_id="changes_gate", gate_id=f"changes_gate.{rule_id}",
            category=FindingCategory.INTEGRITY, authority=FindingAuthority.SYSTEM_INTEGRITY,
            explicitness=Explicitness.UNKNOWN, subject_id=subject,
            evidence=[EvidenceRef(kind="deterministic_validation", identity={"valid": False, "rule_id": rule_id,
                **({"location": location} if isinstance(location, str) else {})})]))
    return findings
