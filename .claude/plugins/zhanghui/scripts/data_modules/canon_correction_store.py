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


@dataclass(frozen=True)
class ActivationResult:
    ok: bool
    activated: bool
    publication_record_id: str
    record_sha256: str
    semantic_activation_id: str
    effective_history_digest: str
    generation_id: str
    effective_revision_id: str
    correction_id: str
    diagnostics: tuple[str, ...] = ()


def activate_correction(project_root: str | Path, correction_id: str,
                        authorization: CanonCorrectionAuthorization | dict[str, Any]) -> ActivationResult:
    """Publish an approved candidate through one complete immutable generation."""
    from .effective_history import (
        CandidateEffectiveHistorySnapshot, EffectiveHistoryStore, _snapshot_digests,
    )
    from .projection_generation import ProjectionGeneration
    from .projection_rebuild import build_effective_generation

    root = Path(project_root).expanduser().resolve()
    try:
        supplied_auth = (authorization if isinstance(authorization, CanonCorrectionAuthorization)
                         else CanonCorrectionAuthorization.model_validate(authorization))
    except Exception as exc:
        raise CorrectionStoreError(f"INVALID_AUTHORIZATION:{exc}") from exc
    correction_paths = list((root / ".story-system/corrections").glob(
        f"chapter_*/*/corrections/{correction_id}.correction.json"))
    if len(correction_paths) != 1:
        raise CorrectionStoreError("CORRECTION_NOT_FOUND_OR_AMBIGUOUS")
    correction_path = correction_paths[0]
    try:
        correction = json.loads(correction_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CorrectionStoreError("CORRECTION_ARTIFACT_INVALID") from exc
    if correction.get("correction_id") != correction_id:
        raise CorrectionStoreError("CORRECTION_ID_MISMATCH")
    target_namespace = correction_path.parent.parent
    auth_path = target_namespace / "authorizations" / f"{supplied_auth.authorization_id}.authorization.json"
    try:
        persisted_auth = CanonCorrectionAuthorization.model_validate(
            json.loads(auth_path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise CorrectionStoreError("AUTHORIZATION_ARTIFACT_NOT_FOUND") from exc
    if artifact_sha256(persisted_auth) != artifact_sha256(supplied_auth):
        raise CorrectionStoreError("AUTHORIZATION_ARTIFACT_MISMATCH")
    if (supplied_auth.choice != "APPROVE"
            or correction.get("authorization_ref") != supplied_auth.authorization_id
            or correction.get("authorization_sha256") != artifact_sha256(supplied_auth)):
        raise CorrectionStoreError("APPROVED_AUTHORIZATION_REQUIRED")

    protocol = ProjectionGeneration(root)
    try:
        pinned = protocol.pin_active_generation()
        current_publication = protocol.latest_publication_for_recovery()
    except Exception as exc:
        raise CorrectionStoreError(f"ACTIVE_PUBLICATION_INVALID:{exc}") from exc
    if pinned is None or current_publication is None:
        raise CorrectionStoreError("ACTIVATION_MANAGED_PROJECT_REQUIRED")
    history_store = EffectiveHistoryStore()
    active = history_store.read_active_snapshot(root)
    if not active.ok:
        raise CorrectionStoreError("ACTIVE_HISTORY_BLOCKED:" + ";".join(active.diagnostics))
    if (pinned.publication_record_sha256 != current_publication.record_sha256
            or active.activation_record_id != pinned.publication_record_id):
        raise CorrectionStoreError("ACTIVE_PUBLICATION_CHANGED_DURING_ACTIVATION")
    candidate = history_store.resolve_candidate(root, correction_id)
    if not candidate.ok:
        raise CorrectionStoreError("CANDIDATE_BLOCKED:" + ";".join(candidate.diagnostics))
    if candidate.base_set_digest != active.base_set_digest:
        raise CorrectionStoreError("ACTIVE_CANDIDATE_BASE_SET_MISMATCH")
    chapter = int(correction["chapter"])
    candidate_entry = candidate.chapters.get(chapter)
    if candidate_entry is None or correction_id not in candidate_entry.applied_correction_ids:
        raise CorrectionStoreError("TARGET_CORRECTION_NOT_EFFECTIVE")

    active_entry = active.chapters.get(chapter)
    if active_entry and correction_id in active_entry.applied_correction_ids:
        latest = protocol.latest_publication()
        if latest is None or latest.record_sha256 != pinned.publication_record_sha256:
            raise CorrectionStoreError("ACTIVE_PUBLICATION_CHANGED_DURING_ACTIVATION")
        return ActivationResult(True, False, pinned.publication_record_id,
                                pinned.publication_record_sha256, pinned.semantic_activation_id,
                                active.effective_history_digest, pinned.generation_id,
                                active_entry.effective_revision_id, correction_id)

    chapters = dict(active.chapters)
    chapters[chapter] = candidate_entry
    base_set_digest, lineage_digest, history_digest = _snapshot_digests(chapters)
    if base_set_digest != active.base_set_digest:
        raise CorrectionStoreError("ACTIVE_CANDIDATE_BASE_SET_MISMATCH")
    dependency_by_path: dict[str, dict[str, str]] = {}
    for row in (*active.dependencies, *candidate.dependencies):
        existing = dependency_by_path.get(row["path"])
        if existing and existing["sha256"] != row["sha256"]:
            raise CorrectionStoreError("ACTIVE_CANDIDATE_DEPENDENCY_CONFLICT")
        dependency_by_path[row["path"]] = dict(row)
    dependencies = tuple(sorted(dependency_by_path.values(), key=lambda row: (row["kind"], row["path"])))
    artifact_dependencies = [row for row in dependencies
                             if row["kind"] in {"correction", "request", "authorization"}]
    correction_lineage_digest = artifact_sha256({
        "effective_lineage_digest": lineage_digest,
        "artifacts": artifact_dependencies,
    })
    namespace_by_path = {row["path"]: dict(row) for row in active.lineage_namespace_checks}
    namespace_by_path.update({row["path"]: dict(row) for row in candidate.lineage_namespace_checks})
    merged_candidate = CandidateEffectiveHistorySnapshot(
        True, correction_id, chapters, history_digest, (), dependencies,
        base_set_digest, correction_lineage_digest, history_digest,
        tuple(sorted(namespace_by_path.values(), key=lambda row: row["path"])),
    )
    try:
        built = build_effective_generation(root, merged_candidate,
                                           previous_generation_id=pinned.generation_id)
    except Exception as exc:
        raise CorrectionStoreError(f"GENERATION_BUILD_FAILED:{exc}") from exc
    try:
        publication = protocol.publish_generation(
            built["validated_generation"], current_publication.record_sha256,
            correction_lineage_digest)
    except Exception as exc:
        try:
            committed = protocol.latest_publication()
        except Exception:
            committed = None
        if (committed is not None
                and committed.body.get("effective_history_digest") == history_digest
                and committed.body.get("previous_record_sha256") == current_publication.record_sha256
                and any(row.get("chapter") == chapter
                        and row.get("effective_revision_id") == candidate_entry.effective_revision_id
                        and correction_id in row.get("applied_correction_ids", [])
                        for row in committed.body.get("chapter_closure", []))):
            return ActivationResult(True, True, committed.publication_record_id,
                                    committed.record_sha256,
                                    committed.body["semantic_activation_id"], history_digest,
                                    committed.body["generation_id"],
                                    candidate_entry.effective_revision_id, correction_id)
        raise CorrectionStoreError(f"ACTIVATION_PUBLICATION_FAILED:{exc}") from exc
    return ActivationResult(True, True, publication.publication_record_id,
                            publication.record_sha256, publication.body["semantic_activation_id"],
                            history_digest, publication.body["generation_id"],
                            candidate_entry.effective_revision_id, correction_id)


def correction_target_dir(root: str | Path, chapter: int, base_sha256: str) -> Path:
    if isinstance(chapter, bool) or not isinstance(chapter, int) or chapter < 1:
        raise CorrectionStoreError("INVALID_CHAPTER")
    if not isinstance(base_sha256, str) or not _SHA.fullmatch(base_sha256):
        raise CorrectionStoreError("INVALID_BASE_DIGEST")
    return Path(root).expanduser().resolve() / ".story-system" / "corrections" / f"chapter_{chapter:03d}" / base_sha256


def build_correction_review_package(
    request: CanonCorrectionRequest | dict[str, Any], *,
    parent_status: str,
    parent_extraction: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the canonical semantic payload that the interactive workflow displays."""
    try:
        req = request if isinstance(request, CanonCorrectionRequest) else CanonCorrectionRequest.model_validate(request)
    except Exception as exc:
        raise CorrectionStoreError(f"INVALID_REQUEST: {exc}") from exc
    parent_digest = effective_content_digest(parent_status, parent_extraction)
    if parent_digest != req.parent_effective_content_sha256:
        raise CorrectionStoreError("STALE_PARENT")
    body = {
        "request_id": req.request_id,
        "request_sha256": artifact_sha256(req),
        "chapter": req.chapter,
        "base_commit_sha256": req.base_commit_sha256,
        "parent_revision_id": req.parent_revision_id,
        "parent_effective_content_sha256": req.parent_effective_content_sha256,
        "operation": req.operation,
        "changed_paths": [item.model_dump(mode="json") for item in req.changed_paths],
        "before": {"status": parent_status, "extraction_result": parent_extraction},
        "after": {
            "status": req.proposed_effective_status,
            "extraction_result": req.proposed_effective_extraction_result,
            "content_sha256": req.proposed_effective_content_sha256,
        },
        "reason": req.reason,
    }
    return {**body, "challenge_sha256": artifact_sha256(body)}


def verify_phase9_correction_decision(
    request: CanonCorrectionRequest | dict[str, Any],
    authorization: CanonCorrectionAuthorization | dict[str, Any],
    review_package: dict[str, Any],
) -> VerifiedCorrectionDecision:
    """Validate exact request/auth/challenge bindings and return a transient result."""
    try:
        req = request if isinstance(request, CanonCorrectionRequest) else CanonCorrectionRequest.model_validate(request)
        auth = authorization if isinstance(authorization, CanonCorrectionAuthorization) else CanonCorrectionAuthorization.model_validate(authorization)
    except Exception as exc:
        raise CorrectionStoreError(f"INVALID_DECISION: {exc}") from exc
    confirmation = auth.decision_provenance.get("phase9_confirmation")
    if not isinstance(confirmation, dict):
        raise CorrectionStoreError("PHASE9_CONFIRMATION_REQUIRED")
    required = {"kind", "challenge_sha256", "interaction_id", "interaction_surface", "confirmed_at"}
    if set(confirmation) != required or confirmation.get("kind") != "interactive-workflow-confirmation/v1":
        raise CorrectionStoreError("INVALID_PHASE9_CONFIRMATION")
    if not all(isinstance(confirmation.get(key), str) and confirmation[key].strip()
               for key in ("interaction_id", "interaction_surface", "confirmed_at")):
        raise CorrectionStoreError("INVALID_PHASE9_CONFIRMATION")
    if (auth.request_id != req.request_id
            or auth.request_sha256 != artifact_sha256(req)):
        raise CorrectionStoreError("REQUEST_AUTHORIZATION_MISMATCH")
    canonical = dict(review_package)
    supplied_digest = canonical.pop("challenge_sha256", None)
    if supplied_digest != artifact_sha256(canonical) or review_package != {
        **canonical, "challenge_sha256": supplied_digest,
    }:
        raise CorrectionStoreError("CHALLENGE_MISMATCH")
    if (review_package.get("request_id") != req.request_id
            or review_package.get("request_sha256") != artifact_sha256(req)
            or review_package.get("base_commit_sha256") != req.base_commit_sha256
            or review_package.get("parent_revision_id") != req.parent_revision_id
            or review_package.get("parent_effective_content_sha256") != req.parent_effective_content_sha256
            or review_package.get("operation") != req.operation
            or review_package.get("after", {}).get("status") != req.proposed_effective_status
            or review_package.get("after", {}).get("extraction_result") != req.proposed_effective_extraction_result
            or review_package.get("after", {}).get("content_sha256") != req.proposed_effective_content_sha256
            or review_package.get("changed_paths") != [item.model_dump(mode="json") for item in req.changed_paths]
            or confirmation.get("challenge_sha256") != supplied_digest):
        raise CorrectionStoreError("CHALLENGE_MISMATCH")
    before = review_package.get("before")
    if not isinstance(before, dict) or set(before) != {"status", "extraction_result"}:
        raise CorrectionStoreError("CHALLENGE_MISMATCH")
    try:
        expected_package = build_correction_review_package(
            req, parent_status=before["status"], parent_extraction=before["extraction_result"],
        )
    except Exception as exc:
        raise CorrectionStoreError("CHALLENGE_MISMATCH") from exc
    if expected_package != review_package:
        raise CorrectionStoreError("CHALLENGE_MISMATCH")
    return VerifiedCorrectionDecision(
        f"phase9-{secrets.token_hex(16)}", artifact_sha256(req), artifact_sha256(auth),
        "interactive-workflow", "VERIFIED_" + auth.choice,
    )


def record_interactive_correction_decision(
    root: str | Path,
    request: CanonCorrectionRequest | dict[str, Any],
    review_package: dict[str, Any],
    *,
    choice: str | None,
    authorization_id: str,
    interaction_id: str,
    interaction_surface: str,
    confirmed_at: str,
    actor_ref: str = "local-user-workflow",
) -> CanonCorrectionAuthorization:
    """Persist a user workflow answer as the existing immutable authorization."""
    if choice not in {"APPROVE", "REJECT"}:
        raise CorrectionStoreError("DECISION_REQUIRED")
    req = request if isinstance(request, CanonCorrectionRequest) else CanonCorrectionRequest.model_validate(request)
    auth = CanonCorrectionAuthorization.model_validate({
        "schema_version": "canon-correction-authorization/v1",
        "authorization_id": authorization_id,
        "request_id": req.request_id,
        "request_sha256": artifact_sha256(req),
        "choice": choice,
        "actor_ref": actor_ref,
        "decision_provenance": {
            "phase9_confirmation": {
                "kind": "interactive-workflow-confirmation/v1",
                "challenge_sha256": review_package.get("challenge_sha256"),
                "interaction_id": interaction_id,
                "interaction_surface": interaction_surface,
                "confirmed_at": confirmed_at,
            }
        },
    })
    verify_phase9_correction_decision(req, auth, review_package)
    return append_correction_authorization(root, auth)


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


def _read_json_artifacts(directory: Path, pattern: str) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise CorrectionStoreError("LINEAGE_INVALID: artifact namespace is not a directory")
    values = []
    for path in sorted(directory.glob(pattern)):
        try:
            values.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            raise CorrectionStoreError("LINEAGE_INVALID: stored artifact cannot be read") from exc
    return values


def append_correction_request(
    root: str | Path,
    request: CanonCorrectionRequest | dict[str, Any],
    *,
    decision_verifications: list[VerifiedCorrectionDecision] | tuple[VerifiedCorrectionDecision, ...] = (),
):
    try:
        model = request if isinstance(request, CanonCorrectionRequest) else CanonCorrectionRequest.model_validate(request)
    except Exception as exc:
        raise CorrectionStoreError(f"INVALID_REQUEST: {exc}") from exc
    project_root = Path(root).expanduser().resolve()
    commit = _load_base(project_root, model.chapter, model.base_commit_sha256)
    proposed = effective_content_digest(model.proposed_effective_status, model.proposed_effective_extraction_result)
    if proposed != model.proposed_effective_content_sha256:
        raise CorrectionStoreError("CONTENT_DIGEST_MISMATCH")
    target = correction_target_dir(project_root, model.chapter, model.base_commit_sha256)
    lock = target.parent / f"{target.name}.lock"
    with FileLock(str(lock)):
        path = target / "requests" / f"{model.request_id}.request.json"
        body = model.model_dump(mode="json")
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise CorrectionStoreError("ID_CONFLICT: existing request is unreadable") from exc
            if canonical_json(existing) == canonical_json(body):
                return model
            raise CorrectionStoreError("ID_CONFLICT: request ID already has different content")

        from .canon_correction_resolver import resolve_effective_history

        requests = _read_json_artifacts(target / "requests", "*.request.json")
        authorizations = _read_json_artifacts(target / "authorizations", "*.authorization.json")
        corrections = _read_json_artifacts(target / "corrections", "*.correction.json")
        current = resolve_effective_history(
            commit, corrections, requests, authorizations, decision_verifications,
        )
        if not current.ok:
            code = current.diagnostics[0].code if current.diagnostics else "LINEAGE_INVALID"
            raise CorrectionStoreError(code)
        if (model.parent_revision_id != current.effective_revision_id
                or model.parent_effective_content_sha256 != current.effective_content_sha256):
            raise CorrectionStoreError("STALE_PARENT")

        path.parent.mkdir(parents=True, exist_ok=True)
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
    corrections_root = project_root / ".story-system" / "corrections"
    interaction_lock = corrections_root / ".authorization-interactions.lock"
    with FileLock(str(interaction_lock)):
        lock = target.parent / f"{target.name}.lock"
        with FileLock(str(lock)):
            auth_dir = target / "authorizations"
            auth_dir.mkdir(parents=True, exist_ok=True)
            existing_decisions: dict[str, dict[str, Any]] = {}
            new_confirmation = model.decision_provenance.get("phase9_confirmation")
            new_interaction_id = new_confirmation.get("interaction_id") if isinstance(new_confirmation, dict) else None
            for path in sorted(corrections_root.glob("chapter_*/*/authorizations/*.authorization.json")):
                try:
                    item = json.loads(path.read_text(encoding="utf-8"))
                    valid = CanonCorrectionAuthorization.model_validate(item)
                except Exception as exc:
                    raise CorrectionStoreError("AUTHORIZATION_CONFLICT: invalid stored authorization") from exc
                if path.parent == auth_dir and valid.request_sha256 == model.request_sha256:
                    existing_decisions[artifact_sha256(item)] = item
                existing_confirmation = valid.decision_provenance.get("phase9_confirmation")
                if (new_interaction_id and isinstance(existing_confirmation, dict)
                        and existing_confirmation.get("interaction_id") == new_interaction_id
                        and valid.request_sha256 != model.request_sha256):
                    raise CorrectionStoreError("INTERACTION_REPLAY")
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
        from .canon_correction_resolver import resolve_effective_history

        all_requests = _read_json_artifacts(target / "requests", "*.request.json")
        all_authorizations = _read_json_artifacts(auth_dir, "*.authorization.json")
        all_corrections = _read_json_artifacts(correction_dir, "*.correction.json")
        current = resolve_effective_history(
            commit, all_corrections, all_requests, all_authorizations, decision_verifications,
        )
        if not current.ok:
            code = current.diagnostics[0].code if current.diagnostics else "LINEAGE_INVALID"
            raise CorrectionStoreError(code)
        if final_path.exists():
            try:
                existing = json.loads(final_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise CorrectionStoreError("ID_CONFLICT") from exc
            if artifact_sha256(existing) == artifact_sha256(body):
                return corr
            raise CorrectionStoreError("ID_CONFLICT")
        if (req.parent_revision_id != current.effective_revision_id
                or req.parent_effective_content_sha256 != current.effective_content_sha256):
            raise CorrectionStoreError("STALE_PARENT")

        candidate_history = resolve_effective_history(
            commit, [*all_corrections, body], all_requests, all_authorizations,
            decision_verifications,
        )
        expected_revision = f"correction:{corr.base_commit_sha256}:{corr.correction_id}"
        if (not candidate_history.ok
                or candidate_history.effective_revision_id != expected_revision
                or candidate_history.applied_correction_ids
                != (*current.applied_correction_ids, corr.correction_id)):
            code = (candidate_history.diagnostics[0].code
                    if candidate_history.diagnostics else "LINEAGE_INVALID")
            raise CorrectionStoreError(code)
        correction_dir.mkdir(parents=True, exist_ok=True)
        _exclusive_create(final_path, body)
    return corr
