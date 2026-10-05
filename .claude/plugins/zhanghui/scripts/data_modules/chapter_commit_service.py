#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

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


class ChapterCommitError(RuntimeError):
    """Raised when chapter commit operations fail with caller-actionable errors."""


class ChapterCommitService:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

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
        rejected = bool(review.blocking_count) or bool(
            fulfillment.missed_nodes
        ) or bool(disambiguation.pending)
        status = "rejected" if rejected else "accepted"
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
