"""Immutable Phase 8 Canon correction artifact schemas and identities."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .durable_projection import canonical_commit_json, validate_chapter_commit_payload
from .chapter_commit_schema import ExtractionResult

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class CorrectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @classmethod
    def _check_id(cls, value: str) -> str:
        if not _ID.fullmatch(value) or value in {".", ".."}:
            raise ValueError("identifier is not path-safe")
        return value


class ChangedPath(CorrectionModel):
    path: str = Field(min_length=1)
    before_sha256: str
    after_sha256: str

    @model_validator(mode="after")
    def valid_digests(self):
        if not _SHA.fullmatch(self.before_sha256) or not _SHA.fullmatch(self.after_sha256):
            raise ValueError("changed path digests must be lowercase SHA-256")
        if self.before_sha256 == self.after_sha256:
            raise ValueError("changed path must change its digest")
        return self


class CanonCorrectionRequest(CorrectionModel):
    schema_version: Literal["canon-correction-request/v1"]
    request_id: str
    chapter: int = Field(ge=1)
    base_commit_sha256: str
    parent_revision_id: str
    parent_effective_content_sha256: str
    operation: Literal["AMEND", "RETRACT", "SUPERSEDE"]
    proposed_effective_status: Literal["accepted", "retracted"]
    proposed_effective_extraction_result: dict[str, Any] | None
    proposed_effective_content_sha256: str
    changed_paths: list[ChangedPath]
    proposer_provenance: dict[str, Any]
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self):
        self._check_id(self.request_id)
        for digest in (self.base_commit_sha256, self.parent_effective_content_sha256,
                       self.proposed_effective_content_sha256):
            if not _SHA.fullmatch(digest):
                raise ValueError("digest must be lowercase SHA-256")
        if self.operation == "RETRACT":
            if self.proposed_effective_status != "retracted" or self.proposed_effective_extraction_result is not None or self.changed_paths:
                raise ValueError("RETRACT requires retracted/null content and no changed paths")
        else:
            if self.proposed_effective_status != "accepted" or self.proposed_effective_extraction_result is None:
                raise ValueError("AMEND and SUPERSEDE require complete accepted ExtractionResult")
            ExtractionResult.model_validate(self.proposed_effective_extraction_result)
            if self.operation == "SUPERSEDE" and self.changed_paths:
                raise ValueError("SUPERSEDE has no changed paths")
        if self.operation != "AMEND" and self.changed_paths:
            raise ValueError("changed paths are only valid for AMEND")
        paths = [item.path for item in self.changed_paths]
        if paths != sorted(set(paths)):
            raise ValueError("changed paths must be unique and sorted")
        if not self.reason.strip():
            raise ValueError("reason must be non-empty")
        return self


class CanonCorrectionAuthorization(CorrectionModel):
    schema_version: Literal["canon-correction-authorization/v1"]
    authorization_id: str
    request_id: str
    request_sha256: str
    choice: Literal["APPROVE", "REJECT"]
    actor_ref: str = Field(min_length=1)
    decision_provenance: dict[str, Any]

    @model_validator(mode="after")
    def validate_authorization(self):
        self._check_id(self.authorization_id)
        self._check_id(self.request_id)
        if not _SHA.fullmatch(self.request_sha256):
            raise ValueError("request_sha256 must be lowercase SHA-256")
        return self


class CanonCorrection(CorrectionModel):
    schema_version: Literal["canon-correction/v1"]
    correction_id: str
    chapter: int = Field(ge=1)
    base_commit_sha256: str
    parent_revision_id: str
    parent_effective_content_sha256: str
    operation: Literal["AMEND", "RETRACT", "SUPERSEDE"]
    effective_extraction_result: dict[str, Any] | None
    changed_paths: list[ChangedPath]
    request_sha256: str
    authorization_ref: str
    authorization_sha256: str
    provenance: dict[str, Any]
    actor_ref: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_correction(self):
        self._check_id(self.correction_id)
        self._check_id(self.authorization_ref)
        for digest in (self.base_commit_sha256, self.parent_effective_content_sha256,
                       self.request_sha256, self.authorization_sha256):
            if not _SHA.fullmatch(digest):
                raise ValueError("digest must be lowercase SHA-256")
        if self.operation == "RETRACT":
            if self.effective_extraction_result is not None or self.changed_paths:
                raise ValueError("RETRACT requires null content and no changed paths")
        else:
            if self.effective_extraction_result is None:
                raise ValueError("AMEND and SUPERSEDE require complete ExtractionResult")
            ExtractionResult.model_validate(self.effective_extraction_result)
        if self.operation != "AMEND" and self.changed_paths:
            raise ValueError("changed paths are only valid for AMEND")
        paths = [item.path for item in self.changed_paths]
        if paths != sorted(set(paths)):
            raise ValueError("changed paths must be unique and sorted")
        return self


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"value is not canonical JSON: {exc}") from exc


def artifact_sha256(value: BaseModel | dict[str, Any]) -> str:
    body = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def request_sha256(request: CanonCorrectionRequest | dict[str, Any]) -> str:
    return artifact_sha256(request)


def authorization_sha256(authorization: CanonCorrectionAuthorization | dict[str, Any]) -> str:
    return artifact_sha256(authorization)


def correction_sha256(correction: CanonCorrection | dict[str, Any]) -> str:
    return artifact_sha256(correction)


def base_commit_digest(commit: dict[str, Any]) -> str:
    meta = commit.get("meta") if isinstance(commit, dict) else None
    chapter = meta.get("chapter") if isinstance(meta, dict) else None
    if isinstance(chapter, bool) or not isinstance(chapter, int) or chapter < 1:
        raise ValueError("invalid commit chapter")
    validated = validate_chapter_commit_payload(commit, expected_chapter=chapter)
    if validated["meta"].get("status") != "accepted":
        raise ValueError("only accepted chapter commits may be correction bases")
    return hashlib.sha256(canonical_commit_json(validated).encode("utf-8")).hexdigest()


def effective_content_digest(status: Literal["accepted", "retracted"], extraction: dict[str, Any] | None) -> str:
    if status == "accepted":
        if extraction is None:
            raise ValueError("accepted content requires ExtractionResult")
        ExtractionResult.model_validate(extraction)
    elif extraction is not None:
        raise ValueError("retracted content must be null")
    envelope = {"effective_status": status, "extraction_result": extraction}
    return hashlib.sha256(canonical_json(envelope).encode("utf-8")).hexdigest()
