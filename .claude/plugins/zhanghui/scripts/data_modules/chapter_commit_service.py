#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Literal

from chapter_outline_loader import volume_num_for_chapter_from_state

from _shared.safe_overwrite import resolve_conflict

from .chapter_commit_schema import (
    DisambiguationResult,
    ExtractionResult,
    FulfillmentResult,
    ReviewResult,
)
from .commit_artifacts import extraction_list
from .config import DataModulesConfig
from .durable_projection import (
    DurableCommitError,
    canonical_commit_json,
    commit_path as durable_commit_path,
    read_commit_file,
    require_durable_commit_match,
)
from .event_log_store import EventLogStore
from .event_projection_router import EventProjectionRouter
from .story_contracts import write_json
from .index_manager import IndexManager
from .override_ledger_service import (
    AmendProposalTrigger,
    ensure_override_ledger_columns,
    persist_amend_proposals,
)
from .reconciliation import reconcile_changes, split_chapter_and_changes
from .gate_decision_store import GateDecisionStore
from .gate_findings import (
    DetectedFinding, EvidenceRef, FindingAuthority, FindingCategory,
    GateDecisionSet, WorkflowAction, fingerprint_policy_inputs,
)
from .gate_severity_policy import GateSeverityPolicy


@dataclass(frozen=True)
class ChapterCommitOutcome:
    """A terminal durable chapter result; transient workflow actions have no instance."""

    chapter_outcome: Literal["accepted", "rejected"]
    gate_decision_ref: str
    commit_payload: Dict[str, Any]


@dataclass(frozen=True)
class WorkflowAttemptResult:
    """Result of one policy attempt, distinct from a terminal chapter commit."""

    action: WorkflowAction
    attempt_id: str
    gate_decision_ref: str
    attempt_status: str
    chapter_outcome: ChapterCommitOutcome | None = None
    workflow_event_refs: tuple[str, ...] = ()
    inconsistency_diagnostic: Dict[str, Any] | None = None


class ChapterCommitError(RuntimeError):
    """Raised when chapter commit operations fail with caller-actionable errors."""


class ChapterCommitService:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def evaluate_after_human_response(
        self, chapter: int, findings: list[DetectedFinding], *,
        prior_attempt_id: str, response_id: str, finding_id: str,
        choice: str, actor_ref: str, **attempt_kwargs: Any,
    ) -> WorkflowAttemptResult:
        """Append a human choice to its pending attempt, then evaluate a new attempt."""
        GateDecisionStore(self.project_root).append_human_response(
            chapter, prior_attempt_id, response_id, finding_id=finding_id,
            choice=choice, actor_ref=actor_ref,
        )
        attempt_kwargs.pop("attempt_id", None)
        return self.evaluate_attempt(
            chapter, findings, attempt_id=response_id, **attempt_kwargs,
        )

    def evaluate_attempt(
        self,
        chapter: int,
        findings: list[DetectedFinding],
        *,
        attempt_id: str,
        policy_version: str,
        scope: dict[str, Any],
        review_result: Dict[str, Any],
        fulfillment_result: Dict[str, Any],
        disambiguation_result: Dict[str, Any],
        extraction_result: Dict[str, Any],
        chapter_text: str,
        proposed_changes: Dict[str, Any],
        reconciliation_result: Dict[str, Any] | None = None,
        cached_decision_set: GateDecisionSet | dict[str, Any] | None = None,
        effective_hard_count: int | None = None,
        refresh_findings: Callable[[dict[str, Any] | None], list[DetectedFinding]] | None = None,
        on_conflict: str | None = None,
    ) -> WorkflowAttemptResult:
        """Recompute policy, persist its authoritative attempt, and route the action."""
        if not isinstance(findings, list) or any(not isinstance(item, DetectedFinding) for item in findings):
            raise ChapterCommitError("evaluate_attempt requires a list of normalized DetectedFinding records")
        policy = GateSeverityPolicy()
        decisions = policy.evaluate(findings, policy_version=policy_version, scope=scope)
        diagnostics: dict[str, Any] = {}
        if cached_decision_set is not None:
            try:
                cached = cached_decision_set if isinstance(cached_decision_set, GateDecisionSet) else GateDecisionSet.model_validate(cached_decision_set)
                if cached.model_dump(mode="json") != decisions.model_dump(mode="json"):
                    diagnostics["cached_decision_mismatch"] = True
            except Exception:
                diagnostics["cached_decision_mismatch"] = True
        if effective_hard_count is not None and effective_hard_count != decisions.hard_count:
            diagnostics["effective_hard_count_mismatch"] = {
                "supplied": effective_hard_count, "recomputed": decisions.hard_count,
            }
        diagnostic = diagnostics or None
        store = GateDecisionStore(self.project_root)
        action = decisions.aggregate_action
        if action == WorkflowAction.REQUIRE_HUMAN:
            path = store.append_attempt(chapter, attempt_id, decisions, workflow_status="pending_human", inconsistency_diagnostic=diagnostic)
            ref = self._gate_decision_ref(path)
            return WorkflowAttemptResult(action, attempt_id, ref, "pending_human", inconsistency_diagnostic=diagnostic)
        if action == WorkflowAction.RECOVER:
            if not self._is_projection_recovery(findings, decisions):
                raise ChapterCommitError("RECOVER is supported only for the existing projection-health recovery path")
            path = store.append_attempt(chapter, attempt_id, decisions, workflow_status="recovery_pending", inconsistency_diagnostic=diagnostic)
            ref = self._gate_decision_ref(path)
            event_id = f"{attempt_id}.recovery-pending"
            pending_event = store.append_workflow_event(
                chapter, event_id, attempt_id=attempt_id, event_type="recovery_pending", status="started",
                finding_ids=[d.finding_id for d in decisions.decisions if d.finding_id],
            )
            try:
                from .projection_rebuild import rebuild_projections
                rebuild_result = rebuild_projections(self.project_root)
            except Exception:
                # Exception classes are not veto evidence. The next policy attempt
                # receives a structured ambiguous recovery outcome instead.
                rebuild_result = None
            succeeded = self._verified_rebuild_success(rebuild_result)
            status = "recovery_succeeded" if succeeded else "recovery_failed"
            event_result = self._recovery_event_result(rebuild_result)
            event_path = store.append_workflow_event(
                chapter, f"{attempt_id}.{status}", attempt_id=attempt_id,
                event_type=status, status="verified" if succeeded else "unverified",
                result=event_result,
                finding_ids=[d.finding_id for d in decisions.decisions if d.finding_id],
            )
            refresh_failed = refresh_findings is None
            if refresh_failed:
                refreshed = []
            else:
                try:
                    refreshed = refresh_findings(rebuild_result)
                    if not isinstance(refreshed, list) or any(not isinstance(item, DetectedFinding) for item in refreshed):
                        raise TypeError("finding refresher returned a non-normalized result")
                except Exception:
                    # An unavailable checker is an ambiguous workflow condition, not
                    # a hard failure inferred from the exception class.
                    refreshed = []
                    refresh_failed = True
            refreshed.append(self._recovery_observation_finding(chapter, attempt_id, rebuild_result, succeeded))
            if refresh_failed:
                refreshed.append(DetectedFinding(
                    gate_id="workflow.refresh_findings", stable_subject_key=f"{attempt_id}:refresh-findings",
                    category=FindingCategory.WORKFLOW, authority=FindingAuthority.SYSTEM_INTEGRITY,
                    scope={"chapter": chapter, "workflow": "projection-recovery"},
                    evidence=[EvidenceRef(kind="accountable_choice_required", identity={"refresh_available": False})],
                    checker_id="chapter_commit_service", checker_version="v1",
                ))
            next_attempt = f"{attempt_id}.recovery-1"
            followup = self.evaluate_attempt(
                chapter, refreshed, attempt_id=next_attempt, policy_version=policy_version,
                scope=scope, review_result=review_result, fulfillment_result=fulfillment_result,
                disambiguation_result=disambiguation_result, extraction_result=extraction_result,
                chapter_text=chapter_text, proposed_changes=proposed_changes,
                reconciliation_result=reconciliation_result, on_conflict=on_conflict,
                refresh_findings=refresh_findings,
            )
            return WorkflowAttemptResult(
                followup.action, followup.attempt_id, followup.gate_decision_ref,
                followup.attempt_status, followup.chapter_outcome,
                (self._gate_decision_ref(pending_event), self._gate_decision_ref(event_path), *followup.workflow_event_refs),
                diagnostic or followup.inconsistency_diagnostic,
            )

        binding = {
            "gate_decision_ref": self._gate_decision_ref(
                store.append_attempt(
                    chapter, attempt_id, decisions,
                    workflow_status="rejected" if action == WorkflowAction.REJECT else "accepted",
                    inconsistency_diagnostic=diagnostic,
                )
            ),
            "input_fingerprint": decisions.decisions[0].input_fingerprint if decisions.decisions else fingerprint_policy_inputs(findings, policy_version, scope),
            "policy_version": policy_version,
            "final_action": action.value,
        }
        payload = self.build_commit(
            chapter=chapter, review_result=review_result, fulfillment_result=fulfillment_result,
            disambiguation_result=disambiguation_result, extraction_result=extraction_result,
            chapter_text=chapter_text, proposed_changes=proposed_changes,
            reconciliation_result=reconciliation_result,
        )
        is_rejected = action == WorkflowAction.REJECT
        payload["meta"]["status"] = "rejected" if is_rejected else "accepted"
        if is_rejected:
            extraction = payload.get("extraction_result") or {}
            extraction["accepted_events"] = []
            extraction["state_deltas"] = []
            extraction["entity_deltas"] = []
        payload["gate_decision_binding"] = binding
        durable = self.apply_projections(payload, on_conflict=on_conflict)
        outcome = ChapterCommitOutcome(
            chapter_outcome="rejected" if is_rejected else "accepted",
            gate_decision_ref=binding["gate_decision_ref"], commit_payload=durable,
        )
        return WorkflowAttemptResult(
            action, attempt_id, binding["gate_decision_ref"],
            "rejected" if is_rejected else "accepted", outcome,
            inconsistency_diagnostic=diagnostic,
        )

    def _gate_decision_ref(self, path: Path) -> str:
        return path.resolve().relative_to(self.project_root.resolve()).as_posix()

    @staticmethod
    def _is_recovery_finding(finding: DetectedFinding) -> bool:
        return finding.category == FindingCategory.PROJECTION_HEALTH and any(
            evidence.kind == "recovery_required" for evidence in finding.evidence
        )

    @classmethod
    def _is_projection_recovery(cls, findings: list[DetectedFinding], decisions: GateDecisionSet) -> bool:
        return decisions.aggregate_action == WorkflowAction.RECOVER and any(cls._is_recovery_finding(f) for f in findings)

    @staticmethod
    def _verified_rebuild_success(result: Any) -> bool:
        return (
            isinstance(result, dict)
            and result.get("schema_version") == "webnovel-projections/v1"
            and result.get("action") == "rebuild"
            and result.get("ok") is True
            and result.get("error") is None
            and isinstance(result.get("results"), list)
            and all(isinstance(row, dict) and row.get("ok") is True for row in result["results"])
        )

    @staticmethod
    def _recovery_event_result(result: Any) -> dict[str, Any]:
        if not isinstance(result, dict) or result.get("schema_version") != "webnovel-projections/v1":
            return {"schema_valid": False, "ok": False}
        error = result.get("error") if isinstance(result.get("error"), dict) else None
        return {
            "schema_valid": True,
            "ok": result.get("ok") is True,
            "action": result.get("action"),
            "error": {"projection": error.get("projection"), "chapter": error.get("chapter")} if error else None,
        }

    @classmethod
    def _recovery_observation_finding(cls, chapter: int, attempt_id: str, result: Any, succeeded: bool) -> DetectedFinding:
        scope = {"chapter": chapter, "workflow": "projection-recovery"}
        evidence: list[EvidenceRef]
        category = FindingCategory.PROJECTION_HEALTH
        authority = FindingAuthority.CRAFT_HEURISTIC
        if succeeded:
            evidence = [EvidenceRef(kind="recovery_verified", identity={"action": "rebuild", "ok": True})]
        else:
            event = cls._recovery_event_result(result)
            error = result.get("error") if isinstance(result, dict) and isinstance(result.get("error"), dict) else {}
            projection = error.get("projection")
            failure_chapter = error.get("chapter")
            deterministic_projection_names = {"prepare", "state", "index", "summary", "memory", "vector", "events", "intent_diagnostics", "validation"}
            if event.get("schema_valid") and event.get("ok") is False and projection in deterministic_projection_names and isinstance(failure_chapter, int) and failure_chapter > 0:
                category = FindingCategory.INTEGRITY
                authority = FindingAuthority.SYSTEM_INTEGRITY
                evidence = [EvidenceRef(kind="deterministic_validation", identity={"valid": False, "projection": projection, "chapter": failure_chapter})]
            else:
                category = FindingCategory.WORKFLOW
                authority = FindingAuthority.SYSTEM_INTEGRITY
                evidence = [EvidenceRef(kind="accountable_choice_required", identity={"recovery_result": "ambiguous"})]
        return DetectedFinding(
            gate_id="projection.recovery_result", stable_subject_key=f"{attempt_id}:recovery-result",
            category=category, authority=authority, scope=scope, evidence=evidence,
            checker_id="projection_rebuild", checker_version="v1",
        )

    def build_commit(
        self,
        chapter: int,
        review_result: Dict[str, Any],
        fulfillment_result: Dict[str, Any],
        disambiguation_result: Dict[str, Any],
        extraction_result: Dict[str, Any],
        chapter_text: str | None = None,
        proposed_changes: Dict[str, Any] | None = None,
        reconciliation_result: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        review = ReviewResult.model_validate(review_result)
        fulfillment = FulfillmentResult.model_validate(fulfillment_result)
        disambiguation = DisambiguationResult.model_validate(disambiguation_result)
        extraction = ExtractionResult.model_validate(extraction_result)
        if not isinstance(chapter_text, str) or proposed_changes is None:
            raise ChapterCommitError(
                "final chapter_text and proposed_changes are required; reconciliation artifacts do not authorize commits"
            )
        try:
            _, parsed_proposal = split_chapter_and_changes(chapter_text)
            if parsed_proposal != proposed_changes:
                raise ValueError("proposed_changes do not match CHANGES parsed from final chapter")
            expected_reconciliation = reconcile_changes(
                proposed_changes, extraction.model_dump(), chapter_text=chapter_text
            )
            if expected_reconciliation["status"] != "passed":
                raise ValueError("reconciliation did not pass; chapter commit is blocked")
            if reconciliation_result is not None and reconciliation_result != expected_reconciliation:
                raise ValueError("reconciliation audit artifact is stale or does not match service recomputation")
            accepted_payload = expected_reconciliation["accepted_payload"]
        except ValueError as exc:
            raise ChapterCommitError(str(exc)) from exc
        # Derived audit data is deliberately calculated here. Caller supplied JSON
        # can only be compared for freshness; it cannot grant commit authority.
        reconciliation_result = expected_reconciliation
        # This is only the canonical payload builder. Final status/veto comes
        # from evaluate_attempt() after service-owned policy recomputation.
        status = "accepted"
        volume = volume_num_for_chapter_from_state(self.project_root, chapter) or 1
        accepted_events = EventLogStore(self.project_root).normalize_events(
            chapter, accepted_payload["accepted_events"]
        )
        extraction_payload = extraction.model_dump()
        extraction_payload["accepted_events"] = accepted_events
        extraction_payload["state_deltas"] = accepted_payload["state_deltas"]
        extraction_payload["entity_deltas"] = accepted_payload["entity_deltas"]
        return {
            "meta": {
                "schema_version": "story-system/v1",
                "chapter": chapter,
                "status": status,
            },
            "contract_refs": {
                "master": "MASTER_SETTING.json",
                "volume": f"volume_{volume:03d}.json",
                "chapter": f"chapter_{chapter:03d}.json",
                "review": f"chapter_{chapter:03d}.review.json",
            },
            "provenance": {
                "write_fact_role": "chapter_commit",
                "projection_role": "derived_read_models",
                "legacy_state_role": "projection_only",
                "reconciliation_schema": reconciliation_result["schema_version"],
                "reconciliation_observed_sha256": reconciliation_result["observed_sha256"],
                "reconciliation_prose_sha256": reconciliation_result["prose_sha256"],
                "reconciliation_proposed_sha256": reconciliation_result["proposed_sha256"],
                "reconciliation_chapter_sha256": reconciliation_result["chapter_sha256"],
            },
            "outline_snapshot": {
                "planned_nodes": fulfillment.planned_nodes,
                "covered_nodes": fulfillment.covered_nodes,
                "missed_nodes": fulfillment.missed_nodes,
                "extra_nodes": fulfillment.extra_nodes,
            },
            "review_result": review.model_dump(),
            "fulfillment_result": fulfillment.model_dump(),
            "disambiguation_result": disambiguation.model_dump(),
            "extraction_result": extraction_payload,
        }

    def persist_commit(
        self,
        payload: Dict[str, Any],
        on_conflict: str | None = None,
    ) -> Path:
        # Projection execution is mutable operational state. It is never part
        # of the canonical chapter transaction record.
        payload = dict(payload)
        payload.pop("projection_status", None)
        target = self.project_root / ".story-system" / "commits"
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"chapter_{int(payload['meta']['chapter']):03d}.commit.json"
        if path.exists() and on_conflict == "overwrite":
            raise ChapterCommitError(
                f"Conflict policy rejected: overwrite is forbidden for canonical chapter commits: {path}"
            )
        if not path.exists():
            higher = self._higher_commit_chapters(int(payload["meta"]["chapter"]))
            if higher:
                chapter = int(payload["meta"]["chapter"])
                raise ChapterCommitError(
                    f"Chapter commits must be created in increasing chapter order; "
                    f"chapter {chapter} follows existing chapter {max(higher)}"
                )
            projected = self._projected_current_chapter()
            chapter = int(payload["meta"]["chapter"])
            if chapter < projected:
                raise ChapterCommitError(
                    f"Chapter commits must follow projected state in increasing order; "
                    f"chapter {chapter} < projected chapter {projected}"
                )
        # 守卫：chapter commit 是不可变的 point-in-time snapshot，不支持 append/ask
        try:
            resolve_conflict(exists=path.exists(), path=path, mode=on_conflict)
        except (FileExistsError, ValueError, RuntimeError) as exc:
            # default 模式 (FileExistsError) + append (ValueError) + ask (RuntimeError)
            # 统一转 ChapterCommitError
            raise ChapterCommitError(f"Conflict policy rejected: {exc}") from exc
        # SKIP 短路守卫（per Lesson 1）：resolve_conflict 只打印 SKIP，必须显式返回
        if on_conflict == "skip" and path.exists():
            return path
        write_json(path, payload)
        return path

    def _projection_writers(self) -> dict[str, Any]:
        from .index_projection_writer import IndexProjectionWriter
        from .memory_projection_writer import MemoryProjectionWriter
        from .state_projection_writer import StateProjectionWriter
        from .summary_projection_writer import SummaryProjectionWriter
        from .vector_projection_writer import VectorProjectionWriter

        return {
            "state": StateProjectionWriter(self.project_root),
            "index": IndexProjectionWriter(self.project_root),
            "summary": SummaryProjectionWriter(self.project_root),
            "memory": MemoryProjectionWriter(self.project_root),
            "vector": VectorProjectionWriter(self.project_root),
        }

    def _writer_status(self, result: dict[str, Any]) -> str:
        if result.get("applied"):
            return "done"
        reason = str(result.get("reason") or "").strip()
        if reason in {"not_required", "commit_rejected"}:
            return "skipped"
        if reason.startswith("error:"):
            return f"failed:{reason[6:] or 'writer_error'}"
        return "skipped"

    def apply_projection_writers(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        status = str((payload.get("meta") or {}).get("status") or "")
        if status not in {"accepted", "rejected"}:
            return payload

        commit_path = self._commit_path(payload)
        try:
            require_durable_commit_match(self.project_root, payload)
        except DurableCommitError as exc:
            raise ChapterCommitError(str(exc)) from exc

        payload.setdefault("projection_status", {})
        if not isinstance(payload["projection_status"], dict):
            payload["projection_status"] = {}

        writers = self._projection_writers()
        router = EventProjectionRouter()
        required_writers = set(router.required_writers(payload))
        writer_results: dict[str, dict[str, Any]] = {}

        if status == "accepted":
            try:
                chapter = int((payload.get("meta") or {}).get("chapter") or 0)
                EventLogStore(self.project_root).write_events(
                    chapter, extraction_list(payload, "accepted_events")
                )
                writer_results["events"] = {"status": "done", "result": {"applied": True}}
                payload["projection_status"]["events"] = "done"
            except Exception as exc:
                writer_results["events"] = {"status": "failed", "error": str(exc)}
                payload["projection_status"]["events"] = f"failed:{exc}"
        else:
            writer_results["events"] = {"status": "skipped", "reason": "commit_rejected"}
            payload["projection_status"]["events"] = "skipped"

        if status == "accepted":
            try:
                chapter = int((payload.get("meta") or {}).get("chapter") or 0)
                accepted_events = extraction_list(payload, "accepted_events")
                proposals = AmendProposalTrigger().check(chapter, accepted_events)
                if proposals:
                    manager = IndexManager(DataModulesConfig.from_project_root(self.project_root))
                    with manager._get_conn() as conn:
                        ensure_override_ledger_columns(conn)
                        persist_amend_proposals(conn, chapter, proposals)
                        conn.commit()
                writer_results["amend_proposals"] = {"status": "done", "count": len(proposals)}
                payload["projection_status"]["amend_proposals"] = "done"
            except Exception as exc:
                writer_results["amend_proposals"] = {"status": "failed", "error": str(exc)}
                payload["projection_status"]["amend_proposals"] = f"failed:{exc}"
        for name in getattr(router, "PROJECTION_ORDER", tuple(writers)):
            if name == "events":
                continue
            if name not in writers:
                continue
            writer = writers[name]
            if name not in required_writers:
                payload["projection_status"][name] = "skipped"
                writer_results[name] = {"status": "skipped", "reason": "not_required"}
                continue
            try:
                result = writer.apply(payload)
                payload["projection_status"][name] = self._writer_status(result)
                writer_results[name] = {
                    "status": payload["projection_status"][name],
                    "result": result,
                }
            except Exception as exc:
                payload["projection_status"][name] = f"failed:{exc}"
                writer_results[name] = {"status": "failed", "error": str(exc)}
        try:
            from .projection_log import append_projection_run

            append_projection_run(
                self.project_root,
                payload,
                writer_results,
                commit_path=commit_path,
            )
        except Exception:
            pass
        return payload

    def apply_projections(
        self,
        payload: Dict[str, Any],
        on_conflict: str | None = None,
    ) -> Dict[str, Any]:
        status = str((payload.get("meta") or {}).get("status") or "")
        if status not in {"accepted", "rejected"}:
            return payload

        if status == "accepted":
            chapter = int((payload.get("meta") or {}).get("chapter") or 0)
            accepted_events = extraction_list(payload, "accepted_events")
            extraction = payload.setdefault("extraction_result", {})
            if not isinstance(extraction, dict):
                extraction = {}
                payload["extraction_result"] = extraction
            extraction["accepted_events"] = EventLogStore(self.project_root).normalize_events(
                chapter, accepted_events
            )
        payload.pop("projection_status", None)
        commit_path = self.persist_commit(payload, on_conflict=on_conflict)
        if on_conflict == "skip":
            payload = self._read_commit(commit_path)
        return self.apply_projection_writers(payload)

    def _commit_path(self, payload: Dict[str, Any]) -> Path:
        chapter = int((payload.get("meta") or {}).get("chapter") or 0)
        return durable_commit_path(self.project_root, chapter)

    def _higher_commit_chapters(self, chapter: int) -> list[int]:
        commits_dir = self.project_root / ".story-system" / "commits"
        result = []
        if not commits_dir.is_dir():
            return result
        for path in commits_dir.glob("chapter_*.commit.json"):
            try:
                existing = int(path.stem.split("_")[1].split(".")[0])
            except (IndexError, ValueError):
                continue
            if existing > chapter:
                result.append(existing)
        return result

    def _projected_current_chapter(self) -> int:
        import json

        state_path = self.project_root / ".webnovel" / "state.json"
        if not state_path.is_file():
            return 0
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            return max(0, int(((state.get("progress") or {}).get("current_chapter") or 0)))
        except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError):
            return 0

    @staticmethod
    def _canonical_json(payload: Dict[str, Any]) -> str:
        return canonical_commit_json(payload)

    @staticmethod
    def _read_commit(path: Path) -> Dict[str, Any]:
        try:
            return read_commit_file(path)
        except DurableCommitError as exc:
            raise ChapterCommitError(str(exc)) from exc
