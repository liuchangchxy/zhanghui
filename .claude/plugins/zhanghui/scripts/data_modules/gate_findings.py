"""Typed shared gate findings and deterministic fingerprint helpers.

This module is intentionally independent of chapter commit persistence and callers.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator, Mapping
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


class _FrozenMapping(Mapping[str, Any]):
    """Tuple-backed immutable mapping for stable identity dimensions."""

    __slots__ = ("__items",)

    def __init__(self, items: dict[str, Any]):
        object.__setattr__(self, "_FrozenMapping__items", tuple(items.items()))

    def __getitem__(self, key: str) -> Any:
        for candidate, value in self.__items:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _value in self.__items)

    def __len__(self) -> int:
        return len(self.__items)

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise TypeError("identity scope is immutable")

    def __copy__(self) -> "_FrozenMapping":
        return self

    def __deepcopy__(self, _memo: dict[int, Any]) -> "_FrozenMapping":
        return self


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, _FrozenMapping):
        return value
    if isinstance(value, Mapping):
        return _FrozenMapping({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_deep_thaw(item) for item in value]
    if isinstance(value, frozenset):
        return [_deep_thaw(item) for item in sorted(value, key=repr)]
    return value


class _StringEnum(str, Enum):
    pass


class FindingCategory(_StringEnum):
    INTEGRITY = "INTEGRITY"
    CANON_CONTRADICTION = "CANON_CONTRADICTION"
    USER_CONSTRAINT = "USER_CONSTRAINT"
    DISAMBIGUATION = "DISAMBIGUATION"
    INTENT_FULFILLMENT = "INTENT_FULFILLMENT"
    CRAFT = "CRAFT"
    STYLE = "STYLE"
    PROJECTION_HEALTH = "PROJECTION_HEALTH"
    WORKFLOW = "WORKFLOW"


class FindingAuthority(_StringEnum):
    SYSTEM_INTEGRITY = "SYSTEM_INTEGRITY"
    ACCEPTED_CANON = "ACCEPTED_CANON"
    USER_EXPLICIT = "USER_EXPLICIT"
    AUTHOR_PLAN = "AUTHOR_PLAN"
    PLANNER_GENERATED = "PLANNER_GENERATED"
    CRAFT_HEURISTIC = "CRAFT_HEURISTIC"
    LLM_REVIEW = "LLM_REVIEW"
    LEGACY_UNKNOWN = "LEGACY_UNKNOWN"


class Explicitness(_StringEnum):
    EXPLICIT = "EXPLICIT"
    IMPLICIT = "IMPLICIT"
    UNKNOWN = "UNKNOWN"


class EffectiveSeverity(_StringEnum):
    HARD_INTEGRITY = "HARD_INTEGRITY"
    HARD_CANON = "HARD_CANON"
    HARD_USER = "HARD_USER"
    HUMAN_DECISION = "HUMAN_DECISION"
    RECOVERABLE = "RECOVERABLE"
    ADVISORY = "ADVISORY"
    SCORE = "SCORE"


class WorkflowAction(_StringEnum):
    REJECT = "REJECT"
    REQUIRE_HUMAN = "REQUIRE_HUMAN"
    RECOVER = "RECOVER"
    ALLOW_WITH_ADVISORY = "ALLOW_WITH_ADVISORY"


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceRef(StrictRecord):
    kind: str = Field(min_length=1)
    identity: Any
    observed: Any = None
    expected: Any = None
    source_ref: str | None = None

    @field_validator("kind")
    @classmethod
    def strip_kind(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("evidence kind must not be blank")
        return value


class DetectedFinding(StrictRecord):
    finding_id: str | None = None
    identity_version: str = "v1"
    gate_id: str = Field(min_length=1)
    stable_subject_key: str | None = None
    category: FindingCategory
    authority: FindingAuthority
    explicitness: Explicitness = Explicitness.UNKNOWN
    scope: Mapping[str, Any]
    evidence: list[EvidenceRef]
    subject_id: str | None = None
    constraint_id: str | None = None
    source_ref: str | None = None
    checker_id: str = Field(min_length=1)
    checker_version: str = Field(min_length=1)
    suggested_severity: EffectiveSeverity | None = None
    score: dict[str, Any] | None = None
    detected_at: str | None = None
    message: str | None = None

    @field_validator("scope")
    @classmethod
    def freeze_identity_scope(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return _deep_freeze(value)

    @field_serializer("scope")
    def serialize_identity_scope(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return _deep_thaw(value)

    @field_validator("gate_id", "identity_version", "checker_id", "checker_version")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be blank")
        return value

    @field_validator("stable_subject_key", "subject_id", "constraint_id", "source_ref")
    @classmethod
    def optional_nonblank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("identity/reference values must not be blank")
        return value

    @model_validator(mode="after")
    def fill_or_check_identity(self) -> "DetectedFinding":
        if self.stable_subject_key:
            expected = stable_finding_id(
                identity_version=self.identity_version,
                gate_id=self.gate_id,
                subject_key=self.stable_subject_key,
                scope=self.scope,
            )
            if self.finding_id is not None and self.finding_id != expected:
                raise ValueError("finding_id does not match stable logical identity")
            object.__setattr__(self, "finding_id", expected)
        elif self.finding_id is not None:
            raise ValueError("finding_id requires stable_subject_key")
        if self.score is not None:
            ScorePayload.model_validate(self.score)
        return self

    @property
    def veto_capable_identity(self) -> bool:
        return self.finding_id is not None and self.stable_subject_key is not None


class ScorePayload(StrictRecord):
    kind: str = Field(min_length=1)
    value: float
    scale: tuple[float, float]

    @field_validator("kind")
    @classmethod
    def kind_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("score kind must not be blank")
        return value

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("score value must be finite")
        return value

    @field_validator("scale")
    @classmethod
    def valid_scale(cls, value: tuple[float, float]) -> tuple[float, float]:
        if len(value) != 2 or not all(math.isfinite(x) for x in value) or value[0] >= value[1]:
            raise ValueError("score scale must contain finite increasing bounds")
        return value

    @model_validator(mode="after")
    def value_in_scale(self) -> "ScorePayload":
        if not self.scale[0] <= self.value <= self.scale[1]:
            raise ValueError("score value must be within declared scale")
        return self


class GateDecision(StrictRecord):
    finding_id: str | None
    effective_severity: EffectiveSeverity
    effective_action: WorkflowAction
    policy_version: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    policy_reason: str = Field(min_length=1)
    decision_scope: dict[str, Any]
    evidence_fingerprint: str
    input_fingerprint: str
    score: ScorePayload | None = None

    @model_validator(mode="after")
    def score_only_on_score_severity(self) -> "GateDecision":
        if (self.effective_severity == EffectiveSeverity.SCORE) != (self.score is not None):
            raise ValueError("score payload is required only for SCORE decisions")
        return self


class GateDecisionSet(StrictRecord):
    decisions: list[GateDecision]
    aggregate_action: WorkflowAction

    @property
    def hard_count(self) -> int:
        hard = {EffectiveSeverity.HARD_INTEGRITY, EffectiveSeverity.HARD_CANON, EffectiveSeverity.HARD_USER}
        return sum(d.effective_severity in hard for d in self.decisions)


def _canonical_json(value: Any) -> str:
    return json.dumps(_deep_thaw(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def stable_finding_id(*, identity_version: str, gate_id: str, subject_key: str, scope: Mapping[str, Any]) -> str:
    """Hash only stable logical identity dimensions; observation evidence is excluded."""
    for name, value in (("identity_version", identity_version), ("gate_id", gate_id), ("subject_key", subject_key)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty stable value")
    if not isinstance(scope, Mapping) or not scope:
        raise ValueError("scope must be a non-empty object")
    return "gf1_" + _sha256({"identity_version": identity_version.strip(), "gate_id": gate_id.strip(), "subject_key": subject_key.strip(), "scope": scope})


def fingerprint_evidence(evidence: list[EvidenceRef]) -> str:
    return _sha256([item.model_dump(mode="json") for item in evidence])


def fingerprint_policy_inputs(findings: list[DetectedFinding], policy_version: str, scope: dict[str, Any]) -> str:
    normalized = [
        {"finding_id": f.finding_id, "identity_version": f.identity_version, "gate_id": f.gate_id,
         "stable_subject_key": f.stable_subject_key, "category": f.category.value,
         "authority": f.authority.value, "explicitness": f.explicitness.value,
         "scope": f.scope, "evidence": [e.model_dump(mode="json") for e in f.evidence],
         "subject_id": f.subject_id, "constraint_id": f.constraint_id, "source_ref": f.source_ref,
         "checker_id": f.checker_id, "checker_version": f.checker_version,
         "suggested_severity": f.suggested_severity.value if f.suggested_severity else None,
         "score": f.score}
        for f in findings
    ]
    normalized.sort(key=_canonical_json)
    return _sha256({"policy_version": policy_version, "scope": scope, "findings": normalized})
