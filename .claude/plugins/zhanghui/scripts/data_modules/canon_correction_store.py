"""Append-only persistence for staged Canon correction requests and decisions."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from filelock import FileLock

from .canon_correction_schema import (
    CanonCorrectionRequest, CanonCorrectionAuthorization, artifact_sha256,
    base_commit_digest, effective_content_digest, canonical_json,
)
from .durable_projection import read_durable_commit

_SHA = re.compile(r"^[0-9a-f]{64}$")


class CorrectionStoreError(RuntimeError):
    """A correction artifact could not be safely appended."""


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
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CorrectionStoreError("ID_CONFLICT: existing artifact is unreadable") from exc
        if canonical_json(existing) == canonical_json(value):
            return
        raise CorrectionStoreError("ID_CONFLICT: artifact ID already has different content")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        # An interrupted partial write must never be overwritten automatically.
        raise


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
