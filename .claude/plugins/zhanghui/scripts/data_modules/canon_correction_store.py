"""Append-only persistence for staged Canon correction requests and decisions."""
from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from filelock import FileLock

from .canon_correction_schema import (
    CanonCorrectionRequest, CanonCorrectionAuthorization, CanonCorrection, artifact_sha256,
    base_commit_digest, effective_content_digest, canonical_json,
)
from .durable_projection import read_durable_commit

_SHA = re.compile(r"^[0-9a-f]{64}$")


class CorrectionStoreError(RuntimeError):
    """A correction artifact could not be safely appended."""


@dataclass(frozen=True)
class VerifiedCorrectionDecision:
    """Transient typed verifier output; Phase 8 creates it only in test fixtures."""
    verification_id: str
    request_sha256: str
    authorization_sha256: str
    authority_identity: str
    decision_status: str

    def __post_init__(self):
        if not all(isinstance(item, str) and item.strip() for item in (
            self.verification_id, self.request_sha256, self.authorization_sha256,
            self.authority_identity,
        )):
            raise ValueError("verification identity and bindings must be non-empty strings")
        if self.decision_status not in {"VERIFIED_APPROVE", "VERIFIED_REJECT"}:
            raise ValueError("invalid verified decision status")


def correction_target_dir(root: str | Path, chapter: int, base_sha256: str) -> Path:
    if isinstance(chapter, bool) or not isinstance(chapter, int) or chapter < 1:
        raise CorrectionStoreError("INVALID_CHAPTER")
    if not isinstance(base_sha256, str) or not _SHA.fullmatch(base_sha256):
        raise CorrectionStoreError("INVALID_BASE_DIGEST")
    return Path(root).expanduser().resolve() / ".story-system" / "corrections" / f"chapter_{chapter:03d}" / base_sha256


def _load_base(root: Path, chapter: int, expected_digest: str) -> dict[str, Any]:
    try:
        commit = read_durable_commit(root, chapter)
        digest = base_commit_digest(commit)
    except Exception as exc:
        raise CorrectionStoreError(f"INVALID_BASE: {exc}") from exc
    if digest != expected_digest:
        raise CorrectionStoreError("CROSS_BASE_REFERENCE")
    return commit


def _exclusive_create(path: Path, value: dict[str, Any]) -> None:
    data = (canonical_json(value) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise CorrectionStoreError("ID_CONFLICT: existing artifact is unreadable") from exc
            if canonical_json(existing) == canonical_json(value):
                return
            raise CorrectionStoreError("ID_CONFLICT: artifact ID already has different content")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _parent_is_base(request: CanonCorrectionRequest, commit: dict[str, Any]) -> None:
    digest = request.base_commit_sha256
    if request.parent_revision_id != f"base:{digest}":
        raise CorrectionStoreError("INVALID_PARENT: no correction revision exists")
    expected = effective_content_digest("accepted", commit["extraction_result"])
    if request.parent_effective_content_sha256 != expected:
        raise CorrectionStoreError("STALE_PARENT")


def append_correction_request(root: str | Path, request: CanonCorrectionRequest | dict[str, Any]):
    try:
        model = request if isinstance(request, CanonCorrectionRequest) else CanonCorrectionRequest.model_validate(request)
    except Exception as exc:
        raise CorrectionStoreError(f"INVALID_REQUEST: {exc}") from exc
    project_root = Path(root).expanduser().resolve()
    commit = _load_base(project_root, model.chapter, model.base_commit_sha256)
    _parent_is_base(model, commit)
    proposed = effective_content_digest(model.proposed_effective_status, model.proposed_effective_extraction_result)
    if proposed != model.proposed_effective_content_sha256:
        raise CorrectionStoreError("CONTENT_DIGEST_MISMATCH")
    target = correction_target_dir(project_root, model.chapter, model.base_commit_sha256)
    lock = target.parent / f"{target.name}.lock"
    with FileLock(str(lock)):
        path = target / "requests" / f"{model.request_id}.request.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        body = model.model_dump(mode="json")
        _exclusive_create(path, body)
    return model


def append_correction_authorization(root: str | Path, authorization: CanonCorrectionAuthorization | dict[str, Any]):
    try:
        model = authorization if isinstance(authorization, CanonCorrectionAuthorization) else CanonCorrectionAuthorization.model_validate(authorization)
    except Exception as exc:
        raise CorrectionStoreError(f"INVALID_AUTHORIZATION: {exc}") from exc
    project_root = Path(root).expanduser().resolve()
    # Locate the unique namespace by exact request ID and digest, then validate its base.
    chapters_root = project_root / ".story-system" / "corrections"
    matches = list(chapters_root.glob(f"chapter_*/*/requests/{model.request_id}.request.json")) if chapters_root.exists() else []
    matches = [path for path in matches if path.is_file()]
    exact_matches = []
    for path in matches:
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if artifact_sha256(body) == model.request_sha256:
            exact_matches.append(path)
    matches = exact_matches
    if len(matches) != 1:
        raise CorrectionStoreError("REQUEST_NOT_FOUND_OR_AMBIGUOUS")
    target = matches[0].parents[1]
    try:
        request_body = json.loads(matches[0].read_text(encoding="utf-8"))
        request_model = CanonCorrectionRequest.model_validate(request_body)
    except Exception as exc:
        raise CorrectionStoreError("INVALID_PERSISTED_REQUEST") from exc
    if request_model.request_id != model.request_id or artifact_sha256(request_body) != model.request_sha256:
        raise CorrectionStoreError("REQUEST_DIGEST_MISMATCH")
    if request_model.chapter != int(target.parent.name.removeprefix("chapter_")) or request_model.base_commit_sha256 != target.name:
        raise CorrectionStoreError("CROSS_BASE_REFERENCE")
    _load_base(project_root, request_model.chapter, request_model.base_commit_sha256)
    lock = target.parent / f"{target.name}.lock"
    with FileLock(str(lock)):
        auth_dir = target / "authorizations"
        auth_dir.mkdir(parents=True, exist_ok=True)
        existing_decisions: dict[str, dict[str, Any]] = {}
        for path in sorted(auth_dir.glob("*.authorization.json")):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                valid = CanonCorrectionAuthorization.model_validate(item)
            except Exception as exc:
                raise CorrectionStoreError("AUTHORIZATION_CONFLICT: invalid stored authorization") from exc
            if valid.request_sha256 == model.request_sha256:
                existing_decisions[artifact_sha256(item)] = item
        body = model.model_dump(mode="json")
        body_digest = artifact_sha256(body)
        if existing_decisions and body_digest not in existing_decisions:
            raise CorrectionStoreError("AUTHORIZATION_CONFLICT")
        path = auth_dir / f"{model.authorization_id}.authorization.json"
        _exclusive_create(path, body)
    return model


def _require_verified_decision(request_digest: str, authorization_digest: str,
                               verifications: tuple | list) -> None:
    if not isinstance(verifications, (tuple, list)):
        raise CorrectionStoreError("HUMAN_AUTHORITY_UNVERIFIED")
    if any(not isinstance(item, VerifiedCorrectionDecision) for item in verifications):
        raise CorrectionStoreError("HUMAN_AUTHORITY_UNVERIFIED: typed verification required")
    related = [item for item in verifications if item.request_sha256 == request_digest
               or item.authorization_sha256 == authorization_digest]
    if len(related) > 1:
        raise CorrectionStoreError("HUMAN_AUTHORITY_CONFLICT")
    if len(related) != 1:
        raise CorrectionStoreError("HUMAN_AUTHORITY_UNVERIFIED")
    decision = related[0]
    if (decision.request_sha256 != request_digest
            or decision.authorization_sha256 != authorization_digest
            or decision.decision_status != "VERIFIED_APPROVE"):
        raise CorrectionStoreError("HUMAN_AUTHORITY_UNVERIFIED")


def _current_tip(target: Path, base_digest: str, base_extraction: dict[str, Any]) -> tuple[str, str]:
    base_revision = f"base:{base_digest}"
    base_content = effective_content_digest("accepted", base_extraction)
    correction_dir = target / "corrections"
    artifacts: dict[str, CanonCorrection] = {}
    if correction_dir.exists():
        for path in sorted(correction_dir.glob("*.correction.json")):
            try:
                model = CanonCorrection.model_validate(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                raise CorrectionStoreError("LINEAGE_INVALID") from exc
            if model.base_commit_sha256 != base_digest or model.chapter != int(target.parent.name.removeprefix("chapter_")):
                raise CorrectionStoreError("CROSS_BASE_REFERENCE")
            old = artifacts.get(model.correction_id)
            if old is not None and artifact_sha256(old) != artifact_sha256(model):
                raise CorrectionStoreError("LINEAGE_ID_CONFLICT")
            artifacts[model.correction_id] = model
    children: dict[str, list[CanonCorrection]] = {}
    for model in artifacts.values():
        children.setdefault(model.parent_revision_id, []).append(model)
    if any(len(items) > 1 for items in children.values()):
        raise CorrectionStoreError("LINEAGE_SIBLING_CONFLICT")
    revision, content = base_revision, base_content
    seen: set[str] = set()
    while children.get(revision):
        edge = children[revision][0]
        if edge.correction_id in seen or edge.parent_effective_content_sha256 != content:
            raise CorrectionStoreError("LINEAGE_INVALID")
        seen.add(edge.correction_id)
        revision = f"correction:{base_digest}:{edge.correction_id}"
        content = (effective_content_digest("retracted", None) if edge.operation == "RETRACT"
                   else effective_content_digest("accepted", edge.effective_extraction_result))
    if len(seen) != len(artifacts):
        raise CorrectionStoreError("LINEAGE_INVALID")
    return revision, content


def append_correction(root: str | Path, correction: CanonCorrection | dict[str, Any], *,
                      request: CanonCorrectionRequest | dict[str, Any],
                      authorization: CanonCorrectionAuthorization | dict[str, Any],
                      decision_verifications: list[VerifiedCorrectionDecision] | tuple[VerifiedCorrectionDecision, ...]):
    try:
        corr = correction if isinstance(correction, CanonCorrection) else CanonCorrection.model_validate(correction)
        req = request if isinstance(request, CanonCorrectionRequest) else CanonCorrectionRequest.model_validate(request)
        auth = authorization if isinstance(authorization, CanonCorrectionAuthorization) else CanonCorrectionAuthorization.model_validate(authorization)
    except Exception as exc:
        raise CorrectionStoreError(f"INVALID_ARTIFACT: {exc}") from exc
    if auth.choice != "APPROVE":
        raise CorrectionStoreError("AUTHORIZATION_REJECTED")
    if (corr.chapter != req.chapter or corr.base_commit_sha256 != req.base_commit_sha256
            or corr.parent_revision_id != req.parent_revision_id
            or corr.parent_effective_content_sha256 != req.parent_effective_content_sha256
            or corr.operation != req.operation
            or corr.effective_extraction_result != req.proposed_effective_extraction_result
            or corr.changed_paths != req.changed_paths
            or corr.request_sha256 != artifact_sha256(req)
            or auth.request_id != req.request_id or auth.request_sha256 != artifact_sha256(req)
            or corr.authorization_ref != auth.authorization_id
            or corr.authorization_sha256 != artifact_sha256(auth)):
        raise CorrectionStoreError("REQUEST_AUTHORIZATION_MISMATCH")
    _require_verified_decision(corr.request_sha256, corr.authorization_sha256, decision_verifications)
    project_root = Path(root).expanduser().resolve()
    target = correction_target_dir(project_root, corr.chapter, corr.base_commit_sha256)
    req_path = target / "requests" / f"{req.request_id}.request.json"
    auth_path = target / "authorizations" / f"{auth.authorization_id}.authorization.json"
    with FileLock(str(target.parent / f"{target.name}.lock")):
        try:
            stored_req = json.loads(req_path.read_text(encoding="utf-8"))
            stored_auth = json.loads(auth_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CorrectionStoreError("REQUEST_OR_AUTHORIZATION_NOT_FOUND") from exc
        if artifact_sha256(stored_req) != artifact_sha256(req) or artifact_sha256(stored_auth) != artifact_sha256(auth):
            raise CorrectionStoreError("REQUEST_OR_AUTHORIZATION_MISMATCH")
        commit = _load_base(project_root, corr.chapter, corr.base_commit_sha256)
        auth_dir = target / "authorizations"
        distinct = set()
        for path in auth_dir.glob("*.authorization.json"):
            item = CanonCorrectionAuthorization.model_validate(json.loads(path.read_text(encoding="utf-8")))
            if item.request_sha256 == corr.request_sha256:
                distinct.add(artifact_sha256(item))
        if distinct != {corr.authorization_sha256}:
            raise CorrectionStoreError("AUTHORIZATION_CONFLICT")
        correction_dir = target / "corrections"
        final_path = correction_dir / f"{corr.correction_id}.correction.json"
        body = corr.model_dump(mode="json")
        current_revision, current_digest = _current_tip(target, corr.base_commit_sha256, commit["extraction_result"])
        if final_path.exists():
            try:
                existing = json.loads(final_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise CorrectionStoreError("ID_CONFLICT") from exc
            if artifact_sha256(existing) == artifact_sha256(body):
                # An exact retry is allowed only when the complete current chain is valid.
                request_values = [json.loads(path.read_text(encoding="utf-8")) for path in (target / "requests").glob("*.request.json")]
                authorization_values = [json.loads(path.read_text(encoding="utf-8")) for path in auth_dir.glob("*.authorization.json")]
                correction_values = [json.loads(path.read_text(encoding="utf-8")) for path in correction_dir.glob("*.correction.json")]
                from .canon_correction_resolver import validate_lineage
                retry_lineage = validate_lineage(commit, correction_values, request_values, authorization_values, decision_verifications)
                if not retry_lineage.ok:
                    code = retry_lineage.diagnostics[0].code if retry_lineage.diagnostics else "LINEAGE_INVALID"
                    raise CorrectionStoreError(code)
                return corr
            raise CorrectionStoreError("ID_CONFLICT")
        if req.parent_revision_id != current_revision or req.parent_effective_content_sha256 != current_digest:
            raise CorrectionStoreError("STALE_PARENT")
        try:
            all_requests = [json.loads(path.read_text(encoding="utf-8")) for path in (target / "requests").glob("*.request.json")]
            all_authorizations = [json.loads(path.read_text(encoding="utf-8")) for path in auth_dir.glob("*.authorization.json")]
            all_corrections = [json.loads(path.read_text(encoding="utf-8")) for path in correction_dir.glob("*.correction.json")] if correction_dir.exists() else []
        except Exception as exc:
            raise CorrectionStoreError("LINEAGE_INVALID: stored artifact cannot be read") from exc
        from .canon_correction_resolver import validate_lineage
        lineage = validate_lineage(commit, all_corrections, all_requests, all_authorizations, decision_verifications)
        if not lineage.ok:
            code = lineage.diagnostics[0].code if lineage.diagnostics else "LINEAGE_INVALID"
            raise CorrectionStoreError(code)
        correction_dir.mkdir(parents=True, exist_ok=True)
        _exclusive_create(final_path, body)
    return corr
