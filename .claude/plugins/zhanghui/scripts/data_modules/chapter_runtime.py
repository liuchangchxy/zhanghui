#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChapterRuntime - Host-independent chapter orchestration facade (Issue #25).

Provides a stable, host-agnostic, machine-callable runtime surface for orchestrating
chapter lifecycles:
1. Preparation (project resolution, preflight, outline validation, Story System contract setup)
2. Writer Package retrieval (governed context, current intent, accepted Canon, fingerprints)
3. Draft Ingestion (saves draft artifact without promoting to Canon, detects stale package)
4. Native Workflow Continuation & Status queries
5. Commit Attempt (routes through canonical ChapterCommitService without creating parallel truth)
6. Projection Retry & Recovery
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from chapter_outline_loader import (
    load_chapter_execution_directive,
    load_chapter_outline,
    load_chapter_plot_structure,
    volume_num_for_chapter_from_state,
)
from project_locator import resolve_project_root

from .chapter_commit_service import ChapterCommitService, WorkflowAttemptResult
from .context_manager import ContextManager
from .gate_finding_adapters import adapt_changes_gate_result, adapt_legacy_artifacts
from .projections import retry_projection
from .reconciliation import reconcile_changes, split_chapter_and_changes
from .runtime_contract_builder import RuntimeContractBuilder
from .story_contracts import (
    StoryContractPaths,
    persist_runtime_contracts,
    persist_story_seed,
    read_json_if_exists,
)
from .story_runtime_sources import load_runtime_sources
from .story_system_engine import StorySystemEngine
from .write_gates import run_write_gate


@dataclass
class WriterPackage:
    chapter: int
    package_fingerprint: str
    source_fingerprints: dict[str, str]
    story_identity: dict[str, Any]
    current_intent: dict[str, Any]
    governed_canon: dict[str, Any]
    constraints: dict[str, Any]
    writer_context: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


@dataclass
class ChapterPrepareResult:
    ok: bool
    chapter: int
    status: str
    writer_package: Optional[WriterPackage] = None
    blockers: list[dict[str, Any]] = field(default_factory=list)
    advisories: list[dict[str, Any]] = field(default_factory=list)
    next_required_action: str = "obtain_writer_package"
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        if self.writer_package is not None:
            res["writer_package"] = self.writer_package.to_dict()
        return res

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


@dataclass
class DraftIngestResult:
    ok: bool
    chapter: int
    status: str
    draft_id: Optional[str] = None
    draft_fingerprint: Optional[str] = None
    package_fingerprint: Optional[str] = None
    next_required_action: Optional[str] = None
    required_artifacts: list[str] = field(default_factory=list)
    error_code: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


@dataclass
class ChapterCommitOutcomeResult:
    ok: bool
    chapter: int
    action: str
    attempt_id: str
    chapter_outcome: str
    gate_decision_ref: str
    durable_commit_persisted: bool
    projection_status: dict[str, Any]
    projection_success: bool
    can_retry_projection: bool
    human_decision_required: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    error: Optional[str] = None
    commit_payload: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


@dataclass
class ChapterStatusResult:
    chapter: int
    draft_status: str
    draft_id: Optional[str] = None
    draft_fingerprint: Optional[str] = None
    has_writer_package: bool = False
    is_writer_package_stale: bool = False
    package_fingerprint: Optional[str] = None
    commit_status: str = "none"
    durable_commit_exists: bool = False
    projection_status: dict[str, Any] = field(default_factory=dict)
    can_retry_projection: bool = False
    human_decision_required: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class ChapterRuntime:
    """Public orchestration facade for host-independent chapter execution."""

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(resolve_project_root(project_root) if project_root else resolve_project_root())
        self.paths = StoryContractPaths.from_project_root(self.project_root)
        self.runtime_base_dir = self.project_root / ".webnovel" / "runtime"

    def _chapter_runtime_dir(self, chapter: int) -> Path:
        dir_path = self.runtime_base_dir / f"chapter_{chapter:03d}"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _default_csv_dir(self) -> Path:
        candidates = [
            Path(__file__).resolve().parent.parent.parent / "references" / "csv",
            Path(__file__).resolve().parent.parent / "references" / "csv",
            self.project_root / "references" / "csv",
        ]
        for c in candidates:
            if c.is_dir():
                return c
        return candidates[0]

    def _ensure_story_contracts(self, chapter: int) -> None:
        """Ensure Story System 4 contracts exist without caller needing to know their internal paths."""
        state_path = self.project_root / ".webnovel" / "state.json"
        state = read_json_if_exists(state_path) or {}
        project_info = state.get("project_info") if isinstance(state.get("project_info"), dict) else {}
        genre = str(project_info.get("genre") or "玄幻")

        directive = load_chapter_execution_directive(self.project_root, chapter)
        query = str(directive.get("goal") or f"第{chapter}章")

        csv_dir = self._default_csv_dir()
        engine = StorySystemEngine(csv_dir=csv_dir)

        # 1. Master setting & anti-patterns
        if not self.paths.master_json.is_file() or not self.paths.anti_patterns_json.is_file():
            seed = engine.build(
                query=query,
                genre=genre,
                chapter=chapter,
                chapter_directive=directive,
            )
            persist_story_seed(
                project_root=self.project_root,
                master_payload=seed["master_setting"],
                chapter_payload=seed.get("chapter_brief"),
                anti_patterns=seed["anti_patterns"],
            )

        # 2. Chapter contract
        if not self.paths.chapter_json(chapter).is_file():
            seed = engine.build(
                query=query,
                genre=genre,
                chapter=chapter,
                chapter_directive=directive,
            )
            if seed.get("chapter_brief"):
                from .story_contracts import write_json, write_marked_markdown, render_chapter_markdown
                ch_path = self.paths.chapter_json(chapter)
                ch_path.parent.mkdir(parents=True, exist_ok=True)
                write_json(ch_path, seed["chapter_brief"])
                write_marked_markdown(ch_path.with_suffix(".md"), render_chapter_markdown(seed["chapter_brief"]))

        # 3. Volume brief and Review contract
        volume = volume_num_for_chapter_from_state(self.project_root, chapter) or 1
        if not self.paths.volume_json(volume).is_file() or not self.paths.review_json(chapter).is_file():
            builder = RuntimeContractBuilder(self.project_root)
            volume_brief, review_contract = builder.build_for_chapter(chapter)
            persist_runtime_contracts(self.project_root, chapter, volume_brief, review_contract)

    def prepare(self, chapter: int, *, with_package: bool = True) -> ChapterPrepareResult:
        """
        Validate environment, native outline, and Story System contracts.
        Returns structured blockers / advisories.
        """
        if chapter < 1:
            return ChapterPrepareResult(
                ok=False,
                chapter=chapter,
                status="invalid_chapter",
                blockers=[{"rule": "chapter_positive", "message": f"Chapter must be positive: {chapter}"}],
                error=f"Invalid chapter number: {chapter}",
            )

        state_path = self.project_root / ".webnovel" / "state.json"
        if not state_path.is_file():
            return ChapterPrepareResult(
                ok=False,
                chapter=chapter,
                status="missing_project",
                blockers=[{"rule": "state_json_present", "message": "Missing .webnovel/state.json"}],
                error="Project root does not contain .webnovel/state.json",
            )

        # 1. Native outline validation
        outline = load_chapter_outline(self.project_root, chapter, max_chars=None)
        if not outline or outline.startswith("⚠️"):
            return ChapterPrepareResult(
                ok=False,
                chapter=chapter,
                status="missing_outline",
                blockers=[{
                    "rule": "outline_present",
                    "message": f"Chapter outline missing or invalid for chapter {chapter}: {outline}",
                }],
                error=f"Chapter outline missing or invalid for chapter {chapter}",
            )

        # 2. Native Story System contracts preparation
        try:
            self._ensure_story_contracts(chapter)
        except Exception as exc:
            return ChapterPrepareResult(
                ok=False,
                chapter=chapter,
                status="contract_generation_failed",
                blockers=[{"rule": "contracts_ready", "message": f"Failed to prepare Story System contracts: {exc}"}],
                error=str(exc),
            )

        # 3. Prewrite gate validation
        blockers: list[dict[str, Any]] = []
        advisories: list[dict[str, Any]] = []
        try:
            gate_res = run_write_gate(self.project_root, chapter=chapter, stage="prewrite")
            for item in gate_res.get("issues", []):
                msg = str(item)
                if "BLOCKER" in msg.upper() or "ERROR" in msg.upper():
                    blockers.append({"gate": "prewrite", "message": msg})
                else:
                    advisories.append({"gate": "prewrite", "message": msg})
        except Exception as exc:
            advisories.append({"gate": "prewrite", "message": f"Prewrite gate diagnostic: {exc}"})

        if blockers:
            return ChapterPrepareResult(
                ok=False,
                chapter=chapter,
                status="blocked",
                blockers=blockers,
                advisories=advisories,
                error="Prewrite validation detected blockers",
            )

        # 4. Writer package preparation
        writer_package = None
        if with_package:
            try:
                writer_package = self.get_writer_package(chapter)
            except Exception as exc:
                return ChapterPrepareResult(
                    ok=False,
                    chapter=chapter,
                    status="writer_package_error",
                    blockers=[{"rule": "writer_package", "message": str(exc)}],
                    advisories=advisories,
                    error=f"Failed to assemble writer package: {exc}",
                )

        return ChapterPrepareResult(
            ok=True,
            chapter=chapter,
            status="ready",
            writer_package=writer_package,
            blockers=[],
            advisories=advisories,
            next_required_action="ingest_draft" if writer_package else "obtain_writer_package",
        )

    def compute_source_fingerprints(self, chapter: int) -> dict[str, str]:
        """Compute fingerprints for authoritative inputs governing this chapter."""
        outline = load_chapter_outline(self.project_root, chapter, max_chars=None)
        
        # Also check volume outline file if present
        from chapter_outline_loader import _find_volume_outline_file, _find_split_outline_file
        outline_file = _find_split_outline_file(self.project_root / "大纲", chapter) or _find_volume_outline_file(self.project_root, chapter)
        file_bytes = outline_file.read_bytes() if outline_file and outline_file.is_file() else b""
        outline_fp = hashlib.sha256(file_bytes + outline.encode("utf-8")).hexdigest()

        # Story system contracts
        volume = volume_num_for_chapter_from_state(self.project_root, chapter) or 1
        contracts_data = {
            "master": read_json_if_exists(self.paths.master_json) or {},
            "anti_patterns": read_json_if_exists(self.paths.anti_patterns_json) or [],
            "volume": read_json_if_exists(self.paths.volume_json(volume)) or {},
            "chapter": read_json_if_exists(self.paths.chapter_json(chapter)) or {},
            "review": read_json_if_exists(self.paths.review_json(chapter)) or {},
        }
        contracts_fp = hashlib.sha256(
            json.dumps(contracts_data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        # State file
        state_path = self.project_root / ".webnovel" / "state.json"
        state_bytes = state_path.read_bytes() if state_path.is_file() else b"{}"
        state_fp = hashlib.sha256(state_bytes).hexdigest()

        # Latest accepted commit before this chapter
        sources = load_runtime_sources(self.project_root, chapter)
        latest_commit = sources.latest_accepted_commit
        latest_commit_fp = (
            hashlib.sha256(
                json.dumps(latest_commit, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            if latest_commit
            else "none"
        )

        return {
            "outline": outline_fp,
            "contracts": contracts_fp,
            "state": state_fp,
            "latest_commit": latest_commit_fp,
        }

    def compute_package_fingerprint(self, chapter: int) -> str:
        """Deterministic fingerprint computed over chapter and source inputs."""
        source_fps = self.compute_source_fingerprints(chapter)
        state = read_json_if_exists(self.project_root / ".webnovel" / "state.json") or {}
        project_info = state.get("project_info") if isinstance(state.get("project_info"), dict) else {}
        title = str(project_info.get("title") or "")
        genre = str(project_info.get("genre") or "")
        payload = {
            "chapter": chapter,
            "title": title,
            "genre": genre,
            "source_fingerprints": source_fps,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def get_writer_package(self, chapter: int) -> WriterPackage:
        """
        Assemble and return the stable Writer Package for the specified chapter.
        Guarantees:
        - current chapter intent is present
        - accepted past Canon is present
        - future chapter intent is strictly absent
        """
        self._ensure_story_contracts(chapter)
        source_fps = self.compute_source_fingerprints(chapter)
        package_fp = self.compute_package_fingerprint(chapter)

        state = read_json_if_exists(self.project_root / ".webnovel" / "state.json") or {}
        project_info = state.get("project_info") if isinstance(state.get("project_info"), dict) else {}
        volume = volume_num_for_chapter_from_state(self.project_root, chapter) or 1

        story_identity = {
            "title": str(project_info.get("title") or ""),
            "genre": str(project_info.get("genre") or ""),
            "target_readers": str(project_info.get("target_readers") or ""),
            "current_volume": volume,
            "chapter": chapter,
        }

        # Current chapter intent ONLY (future chapters never loaded)
        outline = load_chapter_outline(self.project_root, chapter, max_chars=None)
        directive = load_chapter_execution_directive(self.project_root, chapter)
        plot_structure = load_chapter_plot_structure(self.project_root, chapter)
        chapter_contract = read_json_if_exists(self.paths.chapter_json(chapter)) or {}

        current_intent = {
            "chapter": chapter,
            "outline": outline,
            "directive": directive,
            "plot_structure": plot_structure,
            "chapter_brief": chapter_contract.get("override_allowed") or {},
        }

        # Governed Canon from past accepted commits before this chapter
        sources = load_runtime_sources(self.project_root, chapter)
        latest_accepted = sources.latest_accepted_commit

        accepted_entities: dict[str, Any] = {}
        accepted_events: list[dict[str, Any]] = []
        if latest_accepted:
            ext = latest_accepted.get("extraction_result") or {}
            for ed in ext.get("entity_deltas", []) or []:
                if isinstance(ed, dict) and ed.get("entity_id"):
                    accepted_entities[ed["entity_id"]] = ed.get("current") or {}
            accepted_events = list(ext.get("accepted_events", []) or [])

        governed_canon = {
            "latest_accepted_commit_chapter": (latest_accepted.get("meta") or {}).get("chapter") if latest_accepted else None,
            "accepted_entities": accepted_entities,
            "recent_accepted_events": accepted_events[-10:],
        }

        # Constraints
        master_contract = read_json_if_exists(self.paths.master_json) or {}
        volume_contract = read_json_if_exists(self.paths.volume_json(volume)) or {}
        review_contract = read_json_if_exists(self.paths.review_json(chapter)) or {}
        anti_patterns = read_json_if_exists(self.paths.anti_patterns_json) or []

        constraints = {
            "system_constraints": volume_contract.get("system_constraints") or master_contract.get("master_constraints", {}).get("core_tone", ""),
            "prohibitions": list(plot_structure.get("prohibitions") or []),
            "mandatory_nodes": list(plot_structure.get("mandatory_nodes") or []),
            "anti_patterns": [row.get("text", "") for row in anti_patterns if isinstance(row, dict) and row.get("text")],
            "core_tone": master_contract.get("master_constraints", {}).get("core_tone", ""),
            "pacing_strategy": master_contract.get("master_constraints", {}).get("pacing_strategy", ""),
        }

        # Context (genre profile, promises, writer guidance)
        writer_context = {
            "volume_goal": volume_contract.get("volume_goal") or {},
            "selected_tropes": volume_contract.get("selected_tropes") or [],
            "must_check_nodes": review_contract.get("must_check") or [],
        }

        meta = {
            "schema_version": "runtime-api/v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        package = WriterPackage(
            chapter=chapter,
            package_fingerprint=package_fp,
            source_fingerprints=source_fps,
            story_identity=story_identity,
            current_intent=current_intent,
            governed_canon=governed_canon,
            constraints=constraints,
            writer_context=writer_context,
            meta=meta,
        )

        # Record active package in runtime storage
        runtime_dir = self._chapter_runtime_dir(chapter)
        (runtime_dir / "writer_package.json").write_text(package.to_json(), encoding="utf-8")
        return package

    def ingest_draft(
        self,
        chapter: int,
        prose: str,
        package_fingerprint: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> DraftIngestResult:
        """
        Accept externally generated prose draft without promoting it to Canon.
        Validates package freshness against authoritative sources.
        """
        if chapter < 1:
            return DraftIngestResult(
                ok=False,
                chapter=chapter,
                status="invalid_chapter",
                error_code="INVALID_CHAPTER",
                error=f"Invalid chapter number: {chapter}",
            )

        if not isinstance(prose, str) or not prose.strip():
            return DraftIngestResult(
                ok=False,
                chapter=chapter,
                status="empty_prose",
                error_code="EMPTY_PROSE",
                error="Prose content must be a non-empty string",
            )

        # Stale package check
        current_fp = self.compute_package_fingerprint(chapter)
        if package_fingerprint != current_fp:
            return DraftIngestResult(
                ok=False,
                chapter=chapter,
                status="stale_writer_package",
                error_code="STALE_WRITER_PACKAGE",
                error="Writer package is stale: authoritative inputs have changed since package generation.",
                package_fingerprint=package_fingerprint,
            )

        draft_id = f"draft-{chapter:03d}-{uuid.uuid4().hex[:8]}"
        draft_fp = hashlib.sha256(prose.encode("utf-8")).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat()

        draft_payload = {
            "draft_id": draft_id,
            "chapter": chapter,
            "package_fingerprint": package_fingerprint,
            "draft_fingerprint": draft_fp,
            "created_at": created_at,
            "metadata": metadata or {},
            "prose": prose,
            "status": "ingested",
        }

        runtime_dir = self._chapter_runtime_dir(chapter)
        (runtime_dir / "draft.json").write_text(
            json.dumps(draft_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (runtime_dir / "draft.md").write_text(prose, encoding="utf-8")

        return DraftIngestResult(
            ok=True,
            chapter=chapter,
            status="draft_ingested",
            draft_id=draft_id,
            draft_fingerprint=draft_fp,
            package_fingerprint=package_fingerprint,
            next_required_action="review_and_extract",
            required_artifacts=[
                "review_result",
                "extraction_result",
                "fulfillment_result",
                "disambiguation_result",
                "reconciliation_result",
            ],
        )

    def get_status(self, chapter: int) -> ChapterStatusResult:
        """Query draft state, package freshness, commit outcome, and projection status."""
        runtime_dir = self._chapter_runtime_dir(chapter)
        draft_file = runtime_dir / "draft.json"
        pkg_file = runtime_dir / "writer_package.json"

        draft_status = "none"
        draft_id = None
        draft_fp = None
        if draft_file.is_file():
            draft_data = read_json_if_exists(draft_file) or {}
            draft_status = "ingested"
            draft_id = draft_data.get("draft_id")
            draft_fp = draft_data.get("draft_fingerprint")

        has_pkg = pkg_file.is_file()
        is_stale = False
        pkg_fp = None
        if has_pkg:
            pkg_data = read_json_if_exists(pkg_file) or {}
            pkg_fp = pkg_data.get("package_fingerprint")
            current_fp = self.compute_package_fingerprint(chapter)
            is_stale = (pkg_fp != current_fp)

        # Durable commit status
        commit_file = self.paths.commit_json(chapter)
        durable_exists = commit_file.is_file()
        commit_status = "none"
        projection_status: dict[str, Any] = {}
        can_retry = False
        if durable_exists:
            commit_data = read_json_if_exists(commit_file) or {}
            commit_status = (commit_data.get("meta") or {}).get("status") or "unknown"
            projection_status = commit_data.get("projection_status") or {}
            can_retry = True

        return ChapterStatusResult(
            chapter=chapter,
            draft_status=draft_status,
            draft_id=draft_id,
            draft_fingerprint=draft_fp,
            has_writer_package=has_pkg,
            is_writer_package_stale=is_stale,
            package_fingerprint=pkg_fp,
            commit_status=commit_status,
            durable_commit_exists=durable_exists,
            projection_status=projection_status,
            can_retry_projection=can_retry,
        )

    def commit(
        self,
        chapter: int,
        *,
        draft_id: Optional[str] = None,
        prose: Optional[str] = None,
        package_fingerprint: Optional[str] = None,
        review_result: Optional[dict[str, Any]] = None,
        fulfillment_result: Optional[dict[str, Any]] = None,
        disambiguation_result: Optional[dict[str, Any]] = None,
        extraction_result: Optional[dict[str, Any]] = None,
        reconciliation_result: Optional[dict[str, Any]] = None,
        proposed_changes: Optional[dict[str, Any]] = None,
        human_response: Optional[dict[str, Any]] = None,
        on_conflict: Optional[str] = None,
        artifacts: Optional[dict[str, Any]] = None,
    ) -> ChapterCommitOutcomeResult:
        """
        Attempt a durable chapter commit via the canonical ChapterCommitService boundary.
        Maintains the invariant: draft != Canon until accepted through ChapterCommit.
        """
        # Stale package check if package_fingerprint is provided
        if package_fingerprint:
            current_fp = self.compute_package_fingerprint(chapter)
            if package_fingerprint != current_fp:
                return ChapterCommitOutcomeResult(
                    ok=False,
                    chapter=chapter,
                    action="reject",
                    attempt_id=f"stale-{uuid.uuid4().hex[:8]}",
                    chapter_outcome="rejected",
                    gate_decision_ref="",
                    durable_commit_persisted=False,
                    projection_status={},
                    projection_success=False,
                    can_retry_projection=False,
                    error_code="STALE_WRITER_PACKAGE",
                    error="Cannot commit: Writer package is stale.",
                )

        # Resolve prose
        resolved_prose = prose
        runtime_dir = self._chapter_runtime_dir(chapter)
        if resolved_prose is None:
            draft_file = runtime_dir / "draft.json"
            if draft_file.is_file():
                draft_data = read_json_if_exists(draft_file) or {}
                resolved_prose = draft_data.get("prose")

        if not isinstance(resolved_prose, str) or not resolved_prose.strip():
            return ChapterCommitOutcomeResult(
                ok=False,
                chapter=chapter,
                action="reject",
                attempt_id=f"noprose-{uuid.uuid4().hex[:8]}",
                chapter_outcome="rejected",
                gate_decision_ref="",
                durable_commit_persisted=False,
                projection_status={},
                projection_success=False,
                can_retry_projection=False,
                error_code="MISSING_PROSE",
                error="No prose text or ingested draft available for commit.",
            )

        # Unpack artifacts bundle if passed
        art = artifacts or {}
        review_result = review_result or art.get("review_result")
        fulfillment_result = fulfillment_result or art.get("fulfillment_result")
        disambiguation_result = disambiguation_result or art.get("disambiguation_result")
        extraction_result = extraction_result or art.get("extraction_result")
        reconciliation_result = reconciliation_result or art.get("reconciliation_result")
        proposed_changes = proposed_changes or art.get("proposed_changes")

        # Parse proposed changes from prose if not passed
        if proposed_changes is None:
            try:
                _, parsed_proposal = split_chapter_and_changes(resolved_prose)
                proposed_changes = parsed_proposal
            except Exception:
                from changes_gate import REQUIRED_TOP_LEVEL_FIELDS
                proposed_changes = {
                    k: [] if "changes" in k or "points" in k or "transfers" in k or "questions" in k else None
                    for k in REQUIRED_TOP_LEVEL_FIELDS
                }

        # Default extraction result if omitted
        if extraction_result is None:
            extraction_result = {
                "accepted_events": [],
                "state_deltas": [],
                "entity_deltas": [],
                "chapter_meta": {},
            }

        # Default reconciliation if omitted
        if reconciliation_result is None:
            reconciliation_result = reconcile_changes(
                proposed_changes, extraction_result, chapter_text=resolved_prose
            )

        # Default fulfillment if omitted
        if fulfillment_result is None:
            directive = load_chapter_execution_directive(self.project_root, chapter)
            nodes = list(directive.get("must_cover_nodes") or [])
            fulfillment_result = {
                "planned_nodes": nodes,
                "covered_nodes": nodes,
                "missed_nodes": [],
                "extra_nodes": [],
            }

        # Default disambiguation if omitted
        if disambiguation_result is None:
            disambiguation_result = {"pending": []}

        # Default review result if omitted
        if review_result is None:
            review_result = {
                "blocking_count": 0,
                "must_check_results": [],
                "blocking_rule_results": [],
            }

        # Changes gate validation
        from changes_gate import parse_changes, check_r01_protocol, check_r02_enums
        gate_failures: list[dict[str, Any]] = []
        parsed, parse_err = parse_changes(resolved_prose)
        if parse_err:
            gate_failures.append({
                "rule_id": "R0", "severity": "blocking", "message": parse_err, "location": "chapter_text"
            })
        elif isinstance(parsed, dict):
            for f in check_r01_protocol(parsed):
                gate_failures.append({"rule_id": f.rule_id, "severity": f.severity, "message": f.message, "location": f.location})
            for f in check_r02_enums(parsed):
                gate_failures.append({"rule_id": f.rule_id, "severity": f.severity, "message": f.message, "location": f.location})

        # Also allow explicit gate failures or issues from caller
        if isinstance(review_result, dict):
            for row in review_result.get("failures", []):
                if isinstance(row, dict):
                    gate_failures.append(row)
            for row in review_result.get("issues", []):
                if isinstance(row, dict) and row.get("checker_id") == "changes_gate":
                    rule_id = str(row.get("gate_id") or "").replace("changes_gate.", "") or "R1"
                    gate_failures.append({
                        "rule_id": rule_id,
                        "severity": "blocking",
                        "message": str(row.get("message") or "changes gate violation"),
                        "location": "review",
                    })

        gate_result = {
            "passed": not any(f.get("severity") == "blocking" for f in gate_failures),
            "failures": gate_failures,
        }

        # Adapt findings
        contracts = load_runtime_sources(self.project_root, chapter).contracts
        findings = adapt_legacy_artifacts(
            chapter=chapter,
            review=review_result,
            fulfillment=fulfillment_result,
            disambiguation=disambiguation_result,
            contract_payloads=contracts,
        )
        findings.extend(adapt_changes_gate_result(gate_result, chapter=chapter))

        attempt_id = f"runtime-{uuid.uuid4().hex[:8]}"
        attempt_kwargs = {
            "policy_version": "phase6a-v1",
            "scope": {"chapter": chapter},
            "review_result": review_result,
            "fulfillment_result": fulfillment_result,
            "disambiguation_result": disambiguation_result,
            "extraction_result": extraction_result,
            "chapter_text": resolved_prose,
            "proposed_changes": proposed_changes,
            "reconciliation_result": reconciliation_result,
            "on_conflict": on_conflict,
        }

        service = ChapterCommitService(self.project_root)
        if human_response:
            attempt = service.evaluate_after_human_response(
                chapter,
                findings,
                prior_attempt_id=str(human_response.get("prior_attempt_id") or ""),
                response_id=str(human_response.get("response_id") or attempt_id),
                finding_id=str(human_response.get("finding_id") or ""),
                choice=str(human_response.get("choice") or ""),
                actor_ref=str(human_response.get("actor_ref") or "runtime_caller"),
                **attempt_kwargs,
            )
        else:
            attempt = service.evaluate_attempt(
                chapter=chapter,
                findings=findings,
                attempt_id=attempt_id,
                **attempt_kwargs,
            )

        is_accepted = attempt.attempt_status == "accepted"
        is_rejected = attempt.attempt_status == "rejected"
        is_pending_human = attempt.attempt_status == "pending_human"

        commit_file = self.paths.commit_json(chapter)
        durable_persisted = commit_file.is_file()

        proj_status = {}
        if attempt.chapter_outcome and attempt.chapter_outcome.commit_payload:
            proj_status = attempt.chapter_outcome.commit_payload.get("projection_status") or {}
        proj_success = bool(proj_status) and not any(str(v).startswith("failed") for v in proj_status.values())

        human_req = None
        if is_pending_human:
            human_req = {
                "attempt_id": attempt.attempt_id,
                "gate_decision_ref": attempt.gate_decision_ref,
                "status": "pending_human",
            }

        return ChapterCommitOutcomeResult(
            ok=is_accepted and proj_success,
            chapter=chapter,
            action=attempt.action.value,
            attempt_id=attempt.attempt_id,
            chapter_outcome=attempt.attempt_status,
            gate_decision_ref=attempt.gate_decision_ref,
            durable_commit_persisted=durable_persisted,
            projection_status=proj_status,
            projection_success=proj_success,
            can_retry_projection=durable_persisted,
            human_decision_required=human_req,
            commit_payload=attempt.chapter_outcome.commit_payload if attempt.chapter_outcome else None,
            error=None if is_accepted else f"Commit outcome was {attempt.attempt_status}",
        )

    def retry_projection(self, chapter: int) -> dict[str, Any]:
        """Replay or retry projections from the existing durable commit."""
        return retry_projection(self.project_root, chapter=chapter)
