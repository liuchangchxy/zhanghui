"""Pure staged validation and resolution of immutable Canon correction lineage."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .canon_correction_schema import (
    CanonCorrection, CanonCorrectionRequest, CanonCorrectionAuthorization,
    artifact_sha256, base_commit_digest, effective_content_digest,
)
from .chapter_commit_schema import ExtractionResult
from .canon_correction_store import VerifiedCorrectionDecision


@dataclass(frozen=True, order=True)
class CorrectionDiagnostic:
    code: str
    correction_id: str = ""
    detail: str = ""


@dataclass(frozen=True)
class ValidatedLineage:
    ok: bool
    base_commit_sha256: str | None
    ordered_corrections: tuple[dict[str, Any], ...]
    revision_ids: tuple[str, ...]
    effective_revision_id: str | None
    diagnostics: tuple[CorrectionDiagnostic, ...]


def _typed_models(values: Sequence[Any], cls, label: str, diagnostics: list[CorrectionDiagnostic]):
    models = []
    for raw in values:
        try:
            models.append(raw if isinstance(raw, cls) else cls.model_validate(raw))
        except Exception as exc:
            diagnostics.append(CorrectionDiagnostic(f"INVALID_{label}", detail=str(exc)))
    return models


def _unique_by_id(models, id_field: str, diagnostics: list[CorrectionDiagnostic], label: str):
    result = {}
    for model in models:
        identity = getattr(model, id_field)
        previous = result.get(identity)
        if previous is None:
            result[identity] = model
        elif artifact_sha256(previous) != artifact_sha256(model):
            diagnostics.append(CorrectionDiagnostic(f"{label}_ID_CONFLICT", identity))
    return result


def _verified_for(req_digest: str, auth_digest: str, verifications: Sequence[Any],
                  correction_id: str, diagnostics: list[CorrectionDiagnostic]):
    if not isinstance(verifications, (tuple, list)):
        diagnostics.append(CorrectionDiagnostic("HUMAN_AUTHORITY_UNVERIFIED", correction_id))
        return False
    if any(not isinstance(item, VerifiedCorrectionDecision) for item in verifications):
        diagnostics.append(CorrectionDiagnostic("HUMAN_AUTHORITY_UNVERIFIED", correction_id, "typed verification required"))
        return False
    related = [item for item in verifications if item.request_sha256 == req_digest or item.authorization_sha256 == auth_digest]
    if len(related) > 1:
        diagnostics.append(CorrectionDiagnostic("HUMAN_AUTHORITY_CONFLICT", correction_id))
        return False
    if len(related) != 1:
        diagnostics.append(CorrectionDiagnostic("HUMAN_AUTHORITY_UNVERIFIED", correction_id))
        return False
    item = related[0]
    if item.request_sha256 != req_digest or item.authorization_sha256 != auth_digest or item.decision_status != "VERIFIED_APPROVE":
        diagnostics.append(CorrectionDiagnostic("HUMAN_AUTHORITY_UNVERIFIED", correction_id))
        return False
    return True


def validate_lineage(
    accepted_commit: dict[str, Any],
    correction_artifacts: Sequence[dict[str, Any]],
    correction_requests: Sequence[dict[str, Any]],
    correction_authorizations: Sequence[dict[str, Any]],
    decision_verifications: Sequence[VerifiedCorrectionDecision],
) -> ValidatedLineage:
    diagnostics: list[CorrectionDiagnostic] = []
    try:
        base_digest = base_commit_digest(accepted_commit)
        chapter = accepted_commit["meta"]["chapter"]
    except Exception as exc:
        diagnostics.append(CorrectionDiagnostic("INVALID_BASE", detail=str(exc)))
        return ValidatedLineage(False, None, (), (), None, tuple(sorted(set(diagnostics))))
    reqs = _unique_by_id(_typed_models(correction_requests, CanonCorrectionRequest, "REQUEST", diagnostics), "request_id", diagnostics, "REQUEST")
    auths = _unique_by_id(_typed_models(correction_authorizations, CanonCorrectionAuthorization, "AUTHORIZATION", diagnostics), "authorization_id", diagnostics, "AUTHORIZATION")
    corrections = _unique_by_id(_typed_models(correction_artifacts, CanonCorrection, "CORRECTION", diagnostics), "correction_id", diagnostics, "CORRECTION")

    auth_by_request: dict[str, list[CanonCorrectionAuthorization]] = {}
    for auth in auths.values():
        auth_by_request.setdefault(auth.request_sha256, []).append(auth)
    for request_digest, group in auth_by_request.items():
        distinct = {artifact_sha256(item) for item in group}
        if len(distinct) > 1:
            diagnostics.append(CorrectionDiagnostic("AUTHORIZATION_CONFLICT", detail=request_digest))

    valid_edges: dict[str, CanonCorrection] = {}
    for correction in corrections.values():
        cid = correction.correction_id
        if correction.chapter != chapter or correction.base_commit_sha256 != base_digest:
            diagnostics.append(CorrectionDiagnostic("CROSS_BASE_REFERENCE", cid))
            continue
        req = reqs.get(next((rid for rid, item in reqs.items() if artifact_sha256(item) == correction.request_sha256), ""))
        if req is None:
            diagnostics.append(CorrectionDiagnostic("REQUEST_NOT_FOUND_OR_MISMATCHED", cid))
            continue
        auth_group = auth_by_request.get(correction.request_sha256, [])
        matching_auth = [item for item in auth_group if item.authorization_id == correction.authorization_ref
                         and artifact_sha256(item) == correction.authorization_sha256
                         and item.request_id == req.request_id]
        if len({artifact_sha256(item) for item in auth_group}) > 1:
            continue
        if len(matching_auth) != 1:
            diagnostics.append(CorrectionDiagnostic("AUTHORIZATION_UNVERIFIED", cid))
            continue
        auth = matching_auth[0]
        if auth.choice != "APPROVE":
            diagnostics.append(CorrectionDiagnostic("AUTHORIZATION_REJECTED", cid))
            continue
        req_sha = artifact_sha256(req); auth_sha = artifact_sha256(auth)
        if not _verified_for(req_sha, auth_sha, decision_verifications, cid, diagnostics):
            continue
        semantic = (correction.chapter == req.chapter and correction.base_commit_sha256 == req.base_commit_sha256
                    and correction.parent_revision_id == req.parent_revision_id
                    and correction.parent_effective_content_sha256 == req.parent_effective_content_sha256
                    and correction.operation == req.operation
                    and correction.effective_extraction_result == req.proposed_effective_extraction_result
                    and correction.changed_paths == req.changed_paths)
        if not semantic:
            diagnostics.append(CorrectionDiagnostic("REQUEST_CORRECTION_MISMATCH", cid))
            continue
        valid_edges[cid] = correction

    if diagnostics:
        return ValidatedLineage(False, base_digest, (), (), None, tuple(sorted(set(diagnostics))))

    children: dict[str, list[CanonCorrection]] = {}
    for edge in valid_edges.values():
        children.setdefault(edge.parent_revision_id, []).append(edge)
    for parent, group in children.items():
        if len(group) > 1:
            diagnostics.append(CorrectionDiagnostic("LINEAGE_SIBLING_CONFLICT", detail=parent))
    base_revision = f"base:{base_digest}"
    revision = base_revision
    content_digest = effective_content_digest("accepted", accepted_commit["extraction_result"])
    revision_ids = [base_revision]
    ordered: list[CanonCorrection] = []
    seen: set[str] = set()
    effective_status = "accepted"
    while not diagnostics and children.get(revision):
        edge = children[revision][0]
        if edge.correction_id in seen:
            diagnostics.append(CorrectionDiagnostic("LINEAGE_CYCLE", edge.correction_id)); break
        if edge.parent_effective_content_sha256 != content_digest:
            diagnostics.append(CorrectionDiagnostic("STALE_PARENT", edge.correction_id)); break
        if edge.operation == "AMEND" and (edge.effective_extraction_result is None or effective_status != "accepted"):
            diagnostics.append(CorrectionDiagnostic("INVALID_OPERATION_TRANSITION", edge.correction_id)); break
        if edge.operation == "RETRACT":
            if effective_status != "accepted":
                diagnostics.append(CorrectionDiagnostic("INVALID_OPERATION_TRANSITION", edge.correction_id)); break
            content_digest = effective_content_digest("retracted", None)
            effective_status = "retracted"
        else:
            content_digest = effective_content_digest("accepted", edge.effective_extraction_result)
            effective_status = "accepted"
        ordered.append(edge); seen.add(edge.correction_id)
        revision = f"correction:{base_digest}:{edge.correction_id}"
        revision_ids.append(revision)
    if not diagnostics and len(seen) != len(valid_edges):
        remaining = {cid: edge for cid, edge in valid_edges.items() if cid not in seen}
        revision_owner = {f"correction:{base_digest}:{cid}": cid for cid in remaining}
        cyclic = False
        for start in remaining:
            cursor = start
            walked: set[str] = set()
            while cursor in remaining:
                if cursor in walked:
                    cyclic = True
                    break
                walked.add(cursor)
                parent = remaining[cursor].parent_revision_id
                cursor = revision_owner.get(parent, "")
            if cyclic:
                break
        diagnostics.append(CorrectionDiagnostic("LINEAGE_CYCLE" if cyclic else "LINEAGE_DISCONNECTED"))
    if diagnostics:
        return ValidatedLineage(False, base_digest, (), (), None, tuple(sorted(set(diagnostics))))
    return ValidatedLineage(True, base_digest,
                            tuple(item.model_dump(mode="json") for item in ordered),
                            tuple(revision_ids), revision, ())
