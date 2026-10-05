"""Append-only persistence for authoritative GateDecision attempts and workflow inputs."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from filelock import FileLock
from pydantic import ValidationError

try:
    from security_utils import atomic_write_json
except ImportError:  # pragma: no cover
    from scripts.security_utils import atomic_write_json

from .gate_findings import GateDecisionSet
from .story_contracts import StoryContractPaths


class GateDecisionStoreError(RuntimeError):
    """Raised when an attempt record cannot safely be read or appended."""


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_STATUSES = {"pending_human", "recovery_pending", "rejected", "accepted"}


class GateDecisionStore:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).expanduser().resolve()
        self.paths = StoryContractPaths.from_project_root(self.project_root)

    def append_attempt(
        self,
        chapter: int,
        attempt_id: str,
        decision_set: GateDecisionSet,
        *,
        workflow_status: str | None = None,
        inconsistency_diagnostic: dict[str, Any] | None = None,
    ) -> Path:
        self._validate_ids(chapter, attempt_id)
        if not isinstance(decision_set, GateDecisionSet):
            decision_set = GateDecisionSet.model_validate(decision_set)
        status = workflow_status or self._status_for_action(decision_set.aggregate_action.value)
        if status not in _STATUSES:
            raise GateDecisionStoreError(f"unsupported workflow status: {status!r}")
        target = self.paths.gate_decision_json(chapter, attempt_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "schema_version": "gate-decision-attempt/v1",
            "chapter": chapter,
            "attempt_id": attempt_id,
            "workflow_status": status,
            "decision_set": decision_set.model_dump(mode="json"),
        }
        if inconsistency_diagnostic is not None:
            record["inconsistency_diagnostic"] = inconsistency_diagnostic
        with FileLock(str(target) + ".lock"):
            if target.exists():
                raise GateDecisionStoreError(f"attempt already exists and is immutable: {target}")
            atomic_write_json(target, record, use_lock=False, backup=False)
        return target

    def read_attempt(self, chapter: int, attempt_id: str) -> GateDecisionSet:
        return self.read_record(chapter, attempt_id)["decision_set"]

    def read_record(self, chapter: int, attempt_id: str) -> dict[str, Any]:
        self._validate_ids(chapter, attempt_id)
        target = self.paths.gate_decision_json(chapter, attempt_id)
        try:
            record = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError("record must be an object")
            if record.get("schema_version") != "gate-decision-attempt/v1":
                raise ValueError("unsupported attempt schema version")
            if record.get("chapter") != chapter or record.get("attempt_id") != attempt_id:
                raise ValueError("attempt identity does not match its path")
            if record.get("workflow_status") not in _STATUSES:
                raise ValueError("invalid workflow_status")
            decision_set = GateDecisionSet.model_validate(record.get("decision_set"))
            result = dict(record)
            result["decision_set"] = decision_set
            return result
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise GateDecisionStoreError(f"invalid GateDecision attempt {target}: {exc}") from exc

    def append_workflow_event(
        self, chapter: int, event_id: str, *, attempt_id: str, event_type: str,
        status: str, result: dict[str, Any] | None = None, finding_ids: list[str] | None = None,
    ) -> Path:
        self._validate_ids(chapter, attempt_id)
        if not _SAFE_ID.fullmatch(event_id or "") or not event_type.strip() or not status.strip():
            raise GateDecisionStoreError("event_id, event_type, and status are required and path-safe")
        self.read_record(chapter, attempt_id)
        target = self.paths.gate_workflow_event_json(chapter, event_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "schema_version": "gate-workflow-event/v1", "chapter": chapter,
            "event_id": event_id, "attempt_id": attempt_id,
            "event_type": event_type, "status": status,
        }
        if result is not None:
            payload["result"] = result
        if finding_ids is not None:
            payload["finding_ids"] = list(finding_ids)
        with FileLock(str(target) + ".lock"):
            if target.exists():
                raise GateDecisionStoreError(f"workflow event already exists and is immutable: {target}")
            atomic_write_json(target, payload, use_lock=False, backup=False)
        return target

    def append_human_response(
        self, chapter: int, attempt_id: str, response_id: str, *,
        finding_id: str, choice: str, actor_ref: str,
    ) -> Path:
        record = self.read_record(chapter, attempt_id)
        if record["workflow_status"] != "pending_human":
            raise GateDecisionStoreError("human responses can only resolve a pending attempt")
        if not any(d.finding_id == finding_id for d in record["decision_set"].decisions):
            raise GateDecisionStoreError("human response finding_id is not present in the pending attempt")
        self._validate_response(chapter, attempt_id, response_id, finding_id, choice, actor_ref)
        target = self.paths.gate_response_json(chapter, attempt_id, response_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "gate-human-response/v1", "chapter": chapter,
            "attempt_id": attempt_id, "response_id": response_id,
            "finding_id": finding_id, "choice": choice.strip(), "actor_ref": actor_ref.strip(),
        }
        with FileLock(str(target) + ".lock"):
            if target.exists():
                raise GateDecisionStoreError(f"human response already exists and is immutable: {target}")
            atomic_write_json(target, payload, use_lock=False, backup=False)
        return target

    @staticmethod
    def _validate_response(chapter: int, attempt_id: str, response_id: str, finding_id: str, choice: str, actor_ref: str) -> None:
        GateDecisionStore._validate_ids(chapter, attempt_id)
        if not _SAFE_ID.fullmatch(response_id or "") or not finding_id or not choice.strip() or not actor_ref.strip():
            raise GateDecisionStoreError("response ID and human choice fields are required")

    @staticmethod
    def _status_for_action(action: str) -> str:
        return {"REQUIRE_HUMAN": "pending_human", "RECOVER": "recovery_pending", "REJECT": "rejected", "ALLOW_WITH_ADVISORY": "accepted"}.get(action, "")

    @staticmethod
    def _validate_ids(chapter: int, attempt_id: str) -> None:
        if isinstance(chapter, bool) or not isinstance(chapter, int) or chapter < 1:
            raise GateDecisionStoreError("chapter must be a positive integer")
        if not _SAFE_ID.fullmatch(attempt_id or ""):
            raise GateDecisionStoreError("attempt_id must be a path-safe stable identifier")
