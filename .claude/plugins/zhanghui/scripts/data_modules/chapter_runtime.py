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
from changes_gate import run_changes_gate

from .chapter_commit_service import (
    ChapterCommitService,
    WorkflowAttemptResult,
    ChapterCommitError,
)
from .config import DataModulesConfig
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
    creative_brief: str = ""
    creative_brief_fingerprint: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def constraints_and_craft(self) -> dict[str, Any]:
        """Alias exposing governed constraints and craft items."""
        return self.constraints

    @property
    def is_writer_ready(self) -> bool:
        """True only when an authentic creative brief has been attached and sealed."""
        return bool(self.creative_brief and self.creative_brief.strip())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["constraints_and_craft"] = self.constraints
        data["is_writer_ready"] = self.is_writer_ready
        return data

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_writer_prompt(self) -> str:
        """
        Format the unified, canonical prompt for the Writer model.
        Guarantees input parity across Claude Skill Writer and External Host Writer
        by semantically rendering all 6 governed layers:
        1. story_identity
        2. current_intent
        3. governed_canon
        4. creative_brief
        5. constraints & craft
        6. relevant writer_context
        """
        if not self.is_writer_ready:
            raise RuntimeError(
                f"Cannot render writer prompt: WriterPackage for chapter {self.chapter} is unsealed "
                "(missing authentic creative_brief). Context Agent creative brief must be attached first."
            )

        story_id = self.story_identity or {}
        intent = self.current_intent or {}
        directive = intent.get("directive") or {}
        canon = self.governed_canon or {}
        constraints = self.constraints or {}
        writer_ctx = self.writer_context or {}

        title = story_id.get("title", "")
        genre = story_id.get("genre", "")
        readers = story_id.get("target_readers", "")
        vol = story_id.get("current_volume", 1)

        goal = directive.get("goal") or ""
        conflict = directive.get("conflict") or directive.get("obstacles") or ""
        cost = directive.get("cost") or ""
        ending_q = directive.get("ending_question") or directive.get("chapter_end_open_question") or ""
        must_nodes = list(directive.get("must_cover_nodes") or constraints.get("mandatory_nodes") or [])
        prohibitions = list(directive.get("forbidden_zones") or constraints.get("prohibitions") or [])
        outline = str(intent.get("outline") or "").strip()

        tone = constraints.get("core_tone") or ""
        pacing = constraints.get("pacing_strategy") or ""
        anti_patterns = list(constraints.get("anti_patterns") or [])
        voice_target = (writer_ctx.get("voice_target") or {}).get("target_voice", "")

        lines = [
            f"=== 写作任务：第{self.chapter}章 ===",
            f"书名：{title} | 题材：{genre} | 目标读者：{readers} | 卷次：第{vol}卷",
            "",
            "## 1. 本章写作意图 (Current Intent)",
        ]
        if goal:
            lines.append(f"- 核心目标：{goal}")
        if conflict:
            lines.append(f"- 主要阻力：{conflict}")
        if cost:
            lines.append(f"- 付出代价：{cost}")
        if ending_q:
            lines.append(f"- 章末钩子/未决问题：{ending_q}")
        if must_nodes:
            lines.append(f"- 必须覆盖节点：{', '.join(must_nodes)}")
        if prohibitions:
            lines.append(f"- 本章绝对禁区：{', '.join(prohibitions)}")
        if outline:
            outline_snippet = outline[:600] + ("..." if len(outline) > 600 else "")
            lines.append(f"- 大纲参考：\n{outline_snippet}")

        lines.extend([
            "",
            "## 2. 治理事实与前情依据 (Governed Canon)",
        ])
        char_entries = []
        appearing_chars = canon.get("appearing_characters") or []
        for c in appearing_chars:
            if isinstance(c, dict):
                c_name = c.get("name") or c.get("id") or "角色"
                c_status = c.get("current_status") or c.get("status") or ""
                char_entries.append(f"- {c_name}：当前状态【{c_status}】" if c_status else f"- {c_name}")
            elif isinstance(c, str):
                char_entries.append(f"- {c}")

        entities = canon.get("entities") or (canon.get("context_snapshot") or {}).get("entities") or {}
        if not char_entries and isinstance(entities, dict):
            for c in (entities.get("characters") or [])[:5]:
                if isinstance(c, dict):
                    c_name = c.get("name") or c.get("id") or "角色"
                    c_status = c.get("current_status") or c.get("status") or ""
                    char_entries.append(f"- {c_name}：当前状态【{c_status}】" if c_status else f"- {c_name}")

        if char_entries:
            lines.append("【登场角色与状态】")
            lines.extend(char_entries)

        canon_items = canon.get("canon_items") or []
        if canon_items:
            lines.append("【已确认前文事实 (Accepted Canon Facts)】")
            for item in canon_items[:8]:
                if isinstance(item, dict):
                    content = item.get("content") or item.get("summary") or item.get("text") or str(item)
                    lines.append(f"- {content}")
                else:
                    lines.append(f"- {item}")

        scene = canon.get("scene") or {}
        loc = scene.get("location") or scene.get("location_context")
        if loc:
            lines.append(f"【场景环境】：{loc}")

        lines.extend([
            "",
            "## 3. 创作策划任务书 (Creative Brief)",
            self.creative_brief if self.creative_brief else "（未提供独立创作策划任务书）",
            "",
            "## 4. 调性、文风与避坑约束 (Constraints & Craft)",
        ])
        if tone:
            lines.append(f"- 核心调性：{tone}")
        if pacing:
            lines.append(f"- 叙事节奏：{pacing}")
        if voice_target:
            lines.append(f"- 文风靶向：{voice_target}")
        if anti_patterns:
            lines.append(f"- 避坑规则 (Anti-patterns)：{'; '.join(anti_patterns[:5])}")

        recent_sums = writer_ctx.get("recent_summaries") or []
        urgent_loops = writer_ctx.get("urgent_loops") or []
        if recent_sums or urgent_loops:
            lines.extend([
                "",
                "## 5. 关联前情线索 (Writer Context)",
            ])
            for s in recent_sums[:3]:
                s_text = s.get("summary") if isinstance(s, dict) else str(s)
                lines.append(f"- 前情摘要：{s_text}")
            for loop in urgent_loops[:3]:
                l_text = loop.get("hook_text") or loop.get("description") if isinstance(loop, dict) else str(loop)
                lines.append(f"- 紧急伏笔待收：{l_text}")

        lines.extend([
            "",
            "## 6. 正文交付协议 (Handoff Protocol)",
            "1. 输出连贯正文，严格按中文叙事逻辑组织；",
            "2. 正文末尾必须严格附带 <chapter_changes>...</chapter_changes> 结构化提案块；",
            f"3. 封包验证指纹：{self.package_fingerprint}",
        ])
        return "\n".join(lines)


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
    next_required_action: Optional[str] = None
    required_artifacts: Optional[list[str]] = None

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

    def prepare(
        self,
        chapter: int,
        *,
        with_package: bool = True,
        creative_brief: Optional[str] = None,
    ) -> ChapterPrepareResult:
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
        advisories: list[dict[str, Any]] = []
        try:
            gate_res = run_write_gate(self.project_root, chapter=chapter, stage="prewrite")
        except Exception as exc:
            return ChapterPrepareResult(
                ok=False,
                chapter=chapter,
                status="prewrite_gate_failed",
                writer_package=None,
                blockers=[{
                    "rule": "prewrite_gate_execution",
                    "code": "prewrite_gate_exception",
                    "message": f"Prewrite gate execution failed: {exc}",
                }],
                advisories=[],
                next_required_action="fix_gate_infrastructure",
                error=f"Prewrite gate execution failed: {exc}",
            )

        gate_ok = bool(gate_res.get("ok", False))
        gate_errors = list(gate_res.get("errors") or [])
        gate_warnings = list(gate_res.get("warnings") or [])

        if not gate_ok:
            return ChapterPrepareResult(
                ok=False,
                chapter=chapter,
                status="blocked",
                writer_package=None,
                blockers=gate_errors,
                advisories=gate_warnings,
                next_required_action="resolve_prewrite_blockers",
                error="Prewrite validation detected blockers",
            )

        advisories.extend(gate_warnings)

        # 4. Writer package preparation
        writer_package = None
        if with_package:
            try:
                writer_package = self.get_writer_package(chapter, creative_brief=creative_brief)
            except Exception as exc:
                return ChapterPrepareResult(
                    ok=False,
                    chapter=chapter,
                    status="writer_package_error",
                    blockers=[{"rule": "writer_package", "message": str(exc)}],
                    advisories=advisories,
                    error=f"Failed to assemble writer package: {exc}",
                )

        if writer_package:
            next_action = "ingest_draft" if writer_package.is_writer_ready else "attach_creative_brief"
        else:
            next_action = "obtain_writer_package"

        return ChapterPrepareResult(
            ok=True,
            chapter=chapter,
            status="ready",
            writer_package=writer_package,
            blockers=[],
            advisories=advisories,
            next_required_action=next_action,
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

    def compute_package_fingerprint(
        self,
        chapter: int,
        creative_brief: Optional[str] = None,
        creative_brief_fingerprint: Optional[str] = None,
    ) -> str:
        """Deterministic fingerprint computed over chapter, source inputs, and creative brief."""
        source_fps = self.compute_source_fingerprints(chapter)
        state = read_json_if_exists(self.project_root / ".webnovel" / "state.json") or {}
        project_info = state.get("project_info") if isinstance(state.get("project_info"), dict) else {}
        title = str(project_info.get("title") or "")
        genre = str(project_info.get("genre") or "")
        brief_fp = creative_brief_fingerprint or (
            hashlib.sha256(creative_brief.encode("utf-8")).hexdigest()
            if creative_brief
            else ""
        )
        payload: dict[str, Any] = {
            "chapter": chapter,
            "title": title,
            "genre": genre,
            "source_fingerprints": source_fps,
        }
        if brief_fp:
            payload["creative_brief_fingerprint"] = brief_fp
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def get_governed_context(self, chapter: int) -> dict[str, Any]:
        """
        Extract governed factual context assembled by ContextManager.
        Consumed by Context Agent for creative planning without parallel authority querying.
        """
        self._ensure_story_contracts(chapter)
        source_fps = self.compute_source_fingerprints(chapter)

        cfg = DataModulesConfig.from_project_root(self.project_root)
        ctx_mgr = ContextManager(cfg)
        native_ctx = ctx_mgr.build_context(chapter)

        core = native_ctx.get("core") or {}
        state = read_json_if_exists(self.project_root / ".webnovel" / "state.json") or {}
        project_info = state.get("project_info") if isinstance(state.get("project_info"), dict) else {}
        progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
        volume = progress.get("current_volume") or volume_num_for_chapter_from_state(self.project_root, chapter) or 1

        story_identity = {
            "title": str(project_info.get("title") or ""),
            "genre": str(project_info.get("genre") or ""),
            "target_readers": str(project_info.get("target_readers") or ""),
            "current_volume": volume,
            "chapter": chapter,
        }

        directive = load_chapter_execution_directive(self.project_root, chapter)
        plot_structure = native_ctx.get("plot_structure") or load_chapter_plot_structure(self.project_root, chapter)
        chapter_contract = (native_ctx.get("story_contract") or {}).get("chapter") or read_json_if_exists(self.paths.chapter_json(chapter)) or {}
        if not chapter_contract:
            all_ch_contracts = read_json_if_exists(self.project_root / ".story-system" / "chapter_contracts.json") or {}
            chapter_contract = all_ch_contracts.get(str(chapter)) or all_ch_contracts.get(chapter) or {}

        merged_directive = dict(directive)
        for k in ("goal", "conflict", "cost", "must_cover_nodes", "forbidden_zones", "ending_question"):
            if not merged_directive.get(k) and chapter_contract.get(k):
                merged_directive[k] = chapter_contract.get(k)

        raw_intent = native_ctx.get("intent") or []
        intent_items: list[dict[str, Any]] = []
        for item in raw_intent:
            item_d = item.to_dict() if hasattr(item, "to_dict") else (dict(item) if isinstance(item, dict) else {"content": str(item)})
            item_ch = item_d.get("chapter")
            if item_ch is not None and isinstance(item_ch, int) and item_ch > chapter:
                continue
            intent_items.append(item_d)

        current_intent = {
            "chapter": chapter,
            "outline": core.get("chapter_outline") or load_chapter_outline(self.project_root, chapter, max_chars=None),
            "directive": merged_directive,
            "plot_structure": plot_structure,
            "chapter_brief": chapter_contract.get("override_allowed") or {},
            "intent_items": intent_items,
        }

        raw_canon = native_ctx.get("canon") or []
        canon_items = [
            item.to_dict() if hasattr(item, "to_dict") else (dict(item) if isinstance(item, dict) else {"content": str(item)})
            for item in raw_canon
        ]
        scene = native_ctx.get("scene") or {}
        snapshot = (native_ctx.get("meta") or {}).get("context_snapshot") or {}
        proj_entities = read_json_if_exists(self.project_root / ".story-system" / "projections" / "entities.json") or {}
        if proj_entities and not snapshot.get("entities"):
            snapshot["entities"] = proj_entities

        governed_canon = {
            "canon_items": canon_items,
            "appearing_characters": scene.get("appearing_characters") or [],
            "entities": proj_entities,
            "scene": scene,
            "memory": native_ctx.get("memory") or [],
            "long_term_memory": native_ctx.get("long_term_memory") or [],
            "context_snapshot": snapshot,
        }

        raw_craft = native_ctx.get("craft") or []
        craft_items = [
            item.to_dict() if hasattr(item, "to_dict") else (dict(item) if isinstance(item, dict) else {"content": str(item)})
            for item in raw_craft
        ]
        prefs = native_ctx.get("preferences") or {}
        contracts = native_ctx.get("story_contract") or {}
        master_contract = (
            contracts.get("master")
            or read_json_if_exists(self.paths.master_json)
            or read_json_if_exists(self.project_root / ".story-system" / "master_contract.json")
            or {}
        )
        volume_contract = contracts.get("volume") or read_json_if_exists(self.paths.volume_json(volume)) or {}
        review_contract = contracts.get("review") or {}
        anti_patterns = read_json_if_exists(self.paths.anti_patterns_json) or []

        core_tone = (
            master_contract.get("core_tone")
            or master_contract.get("master_constraints", {}).get("core_tone", "")
            or prefs.get("tone")
            or ""
        )
        pacing_strategy = (
            master_contract.get("pacing_strategy")
            or master_contract.get("master_constraints", {}).get("pacing_strategy", "")
            or volume_contract.get("pacing_strategy", "")
        )
        raw_anti = anti_patterns or master_contract.get("anti_patterns") or []
        anti_patterns_list = [
            (row.get("text") if isinstance(row, dict) else str(row))
            for row in raw_anti
            if (isinstance(row, dict) and row.get("text")) or isinstance(row, str)
        ]

        constraints = {
            "craft_items": craft_items,
            "preferences": prefs,
            "core_tone": core_tone,
            "pacing_strategy": pacing_strategy,
            "system_constraints": volume_contract.get("system_constraints") or core_tone,
            "prohibitions": list(plot_structure.get("prohibitions") or []),
            "mandatory_nodes": list(plot_structure.get("mandatory_nodes") or []),
            "anti_patterns": anti_patterns_list,
            "writing_guidance": native_ctx.get("writing_guidance") or {},
        }

        raw_ref = native_ctx.get("reference") or []
        ref_items = [
            item.to_dict() if hasattr(item, "to_dict") else (dict(item) if isinstance(item, dict) else {"content": str(item)})
            for item in raw_ref
        ]
        writer_context = {
            "reference": ref_items,
            "volume_goal": volume_contract.get("volume_goal") or {},
            "selected_tropes": volume_contract.get("selected_tropes") or [],
            "must_check_nodes": review_contract.get("must_check") or [],
            "reader_signal": native_ctx.get("reader_signal") or {},
            "context_diagnostics": native_ctx.get("context_diagnostics") or [],
            "context_contract_version": (native_ctx.get("meta") or {}).get("context_contract_version") or "v3",
            "voice_target": self.get_voice_target(chapter, genre=story_identity.get("genre")).to_dict(),
        }

        return {
            "chapter": chapter,
            "source_fingerprints": source_fps,
            "story_identity": story_identity,
            "current_intent": current_intent,
            "governed_canon": governed_canon,
            "constraints": constraints,
            "writer_context": writer_context,
            "meta": {
                "schema_version": "governed-context/v1",
                "authority": "ContextManager.build_context",
            },
        }

    def get_writer_package(
        self,
        chapter: int,
        creative_brief: Optional[str] = None,
    ) -> WriterPackage:
        """
        Assemble and return the stable Native Writer Package for the specified chapter.
        Guarantees:
        - current chapter intent is present
        - accepted past Canon is present
        - future chapter intent is strictly absent
        - reuses native ContextManager as the single factual authority
        - seals creative planning brief when provided (e.g. from Context Agent)
        - computes deterministic package fingerprint over source and brief fingerprints
        """
        gov_ctx = self.get_governed_context(chapter)
        source_fps = gov_ctx["source_fingerprints"]
        story_identity = gov_ctx["story_identity"]
        current_intent = gov_ctx["current_intent"]
        governed_canon = gov_ctx["governed_canon"]
        constraints = gov_ctx["constraints"]
        writer_context = gov_ctx["writer_context"]

        final_brief = str(creative_brief or "").strip()
        brief_fp = hashlib.sha256(final_brief.encode("utf-8")).hexdigest() if final_brief else ""

        package_fp = self.compute_package_fingerprint(
            chapter,
            creative_brief=final_brief,
            creative_brief_fingerprint=brief_fp,
        )

        meta = {
            "schema_version": "runtime-api/v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "native_context_authority": "ContextManager.build_context",
            "creative_planning_authority": "ContextAgent" if final_brief else "none",
            "is_writer_ready": bool(final_brief),
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
            creative_brief=final_brief,
            creative_brief_fingerprint=brief_fp,
            meta=meta,
        )

        # Record active package in runtime storage
        runtime_dir = self._chapter_runtime_dir(chapter)
        (runtime_dir / "writer_package.json").write_text(package.to_json(), encoding="utf-8")
        return package

    def attach_creative_brief(self, chapter: int, creative_brief: str) -> WriterPackage:
        """Attach an authentic creative brief from Context Agent and seal the Native Writer Package."""
        if not creative_brief or not str(creative_brief).strip():
            raise ValueError("creative_brief must be a non-empty string to seal writer package")
        return self.get_writer_package(chapter=chapter, creative_brief=str(creative_brief).strip())

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

        # Active sealed writer package check
        pkg_file = self._chapter_runtime_dir(chapter) / "writer_package.json"
        if not pkg_file.is_file():
            return DraftIngestResult(
                ok=False,
                chapter=chapter,
                status="writer_package_missing",
                error_code="WRITER_PACKAGE_MISSING",
                error="No active writer package found for chapter: generate and seal a writer package first.",
                package_fingerprint=package_fingerprint,
            )

        saved_pkg = read_json_if_exists(pkg_file) or {}
        saved_brief_fp = str(saved_pkg.get("creative_brief_fingerprint") or "")
        saved_is_writer_ready = bool(saved_pkg.get("is_writer_ready") or False)
        saved_brief = str(saved_pkg.get("creative_brief") or "").strip()

        if not saved_is_writer_ready or not saved_brief_fp or not saved_brief:
            return DraftIngestResult(
                ok=False,
                chapter=chapter,
                status="writer_package_unsealed",
                error_code="WRITER_PACKAGE_UNSEALED",
                error="Writer package is unsealed: Context Agent creative brief must be attached first.",
                package_fingerprint=package_fingerprint,
            )

        current_fp = self.compute_package_fingerprint(
            chapter,
            creative_brief_fingerprint=saved_brief_fp,
        )
        if package_fingerprint != current_fp:
            base_unsealed_fp = self.compute_package_fingerprint(chapter)
            if package_fingerprint == base_unsealed_fp:
                return DraftIngestResult(
                    ok=False,
                    chapter=chapter,
                    status="writer_package_unsealed",
                    error_code="WRITER_PACKAGE_UNSEALED",
                    error="Supplied package fingerprint is unsealed: writer path requires sealed package fingerprint.",
                    package_fingerprint=package_fingerprint,
                )
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
            "package_brief_fingerprint": saved_brief_fp,
            "is_writer_ready": True,
            "draft_fingerprint": draft_fp,
            "created_at": created_at,
            "metadata": metadata or {},
            "prose": prose,
            "status": "ingested",
        }

        runtime_dir = self._chapter_runtime_dir(chapter)
        drafts_dir = runtime_dir / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        (drafts_dir / f"{draft_id}.json").write_text(
            json.dumps(draft_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
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
            saved_brief_fp = str(pkg_data.get("creative_brief_fingerprint") or "")
            current_fp = self.compute_package_fingerprint(
                chapter,
                creative_brief_fingerprint=saved_brief_fp,
            )
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
        review_result: Optional[dict[str, Any]] = None,
        fulfillment_result: Optional[dict[str, Any]] = None,
        disambiguation_result: Optional[dict[str, Any]] = None,
        extraction_result: Optional[dict[str, Any]] = None,
        reconciliation_result: Optional[dict[str, Any]] = None,
        proposed_changes: Optional[dict[str, Any]] = None,
        human_response: Optional[dict[str, Any]] = None,
        on_conflict: Optional[str] = None,
        artifacts: Optional[dict[str, Any]] = None,
        _internal_direct_prose: Optional[str] = None,
        _internal_package_fingerprint: Optional[str] = None,
    ) -> ChapterCommitOutcomeResult:
        """
        Attempt a durable chapter commit via the canonical ChapterCommitService boundary.
        Maintains the invariant: draft != Canon until accepted through ChapterCommit.
        Enforces mandatory draft_id binding to staged drafts.
        """
        # 1. Mandatory draft_id check (unless internal compatibility direct prose is used)
        if not draft_id and _internal_direct_prose is None:
            return ChapterCommitOutcomeResult(
                ok=False,
                chapter=chapter,
                action="reject",
                attempt_id=f"nodraft-{uuid.uuid4().hex[:8]}",
                chapter_outcome="rejected",
                gate_decision_ref="",
                durable_commit_persisted=False,
                projection_status={},
                projection_success=False,
                can_retry_projection=False,
                error_code="WORKFLOW_INCOMPLETE",
                error="Missing required draft_id: ingest draft first.",
                next_required_action="ingest_draft",
                required_artifacts=["draft_id"],
            )

        # 2. Resolve staged draft and verify integrity
        if draft_id:
            runtime_dir = self._chapter_runtime_dir(chapter)
            draft_file = runtime_dir / "drafts" / f"{draft_id}.json"
            if not draft_file.is_file():
                active_file = runtime_dir / "draft.json"
                if active_file.is_file():
                    active_data = read_json_if_exists(active_file) or {}
                    if active_data.get("draft_id") == draft_id:
                        draft_file = active_file
            if not draft_file.is_file():
                return ChapterCommitOutcomeResult(
                    ok=False,
                    chapter=chapter,
                    action="reject",
                    attempt_id=f"unknowndraft-{uuid.uuid4().hex[:8]}",
                    chapter_outcome="rejected",
                    gate_decision_ref="",
                    durable_commit_persisted=False,
                    projection_status={},
                    projection_success=False,
                    can_retry_projection=False,
                    error_code="UNKNOWN_DRAFT",
                    error=f"Draft ID not found in staging for chapter {chapter}: {draft_id}",
                    next_required_action="ingest_draft",
                )

            draft_data = read_json_if_exists(draft_file) or {}
            if draft_data.get("chapter") != chapter:
                return ChapterCommitOutcomeResult(
                    ok=False,
                    chapter=chapter,
                    action="reject",
                    attempt_id=f"chmismatch-{uuid.uuid4().hex[:8]}",
                    chapter_outcome="rejected",
                    gate_decision_ref="",
                    durable_commit_persisted=False,
                    projection_status={},
                    projection_success=False,
                    can_retry_projection=False,
                    error_code="UNKNOWN_DRAFT",
                    error=f"Draft chapter {draft_data.get('chapter')} does not match requested chapter {chapter}",
                    next_required_action="ingest_draft",
                )

            staged_prose = str(draft_data.get("prose") or "")
            expected_fp = draft_data.get("draft_fingerprint")
            actual_fp = hashlib.sha256(staged_prose.encode("utf-8")).hexdigest()
            if actual_fp != expected_fp:
                return ChapterCommitOutcomeResult(
                    ok=False,
                    chapter=chapter,
                    action="reject",
                    attempt_id=f"fpmismatch-{uuid.uuid4().hex[:8]}",
                    chapter_outcome="rejected",
                    gate_decision_ref="",
                    durable_commit_persisted=False,
                    projection_status={},
                    projection_success=False,
                    can_retry_projection=False,
                    error_code="DRAFT_FINGERPRINT_MISMATCH",
                    error="Staged draft content has been modified or corrupted (fingerprint mismatch).",
                    next_required_action="ingest_draft",
                )

            draft_pkg_fp = draft_data.get("package_fingerprint")
            pkg_file = runtime_dir / "writer_package.json"
            if not pkg_file.is_file():
                return ChapterCommitOutcomeResult(
                    ok=False,
                    chapter=chapter,
                    action="reject",
                    attempt_id=f"nopkg-{uuid.uuid4().hex[:8]}",
                    chapter_outcome="rejected",
                    gate_decision_ref="",
                    durable_commit_persisted=False,
                    projection_status={},
                    projection_success=False,
                    can_retry_projection=False,
                    error_code="WRITER_PACKAGE_MISSING",
                    error="Cannot commit: Active writer package not found for chapter.",
                    next_required_action="obtain_writer_package",
                )

            saved_pkg = read_json_if_exists(pkg_file) or {}
            saved_brief_fp = str(saved_pkg.get("creative_brief_fingerprint") or "")
            saved_is_writer_ready = bool(saved_pkg.get("is_writer_ready") or False)
            if not saved_is_writer_ready or not saved_brief_fp:
                return ChapterCommitOutcomeResult(
                    ok=False,
                    chapter=chapter,
                    action="reject",
                    attempt_id=f"unsealed-{uuid.uuid4().hex[:8]}",
                    chapter_outcome="rejected",
                    gate_decision_ref="",
                    durable_commit_persisted=False,
                    projection_status={},
                    projection_success=False,
                    can_retry_projection=False,
                    error_code="WRITER_PACKAGE_UNSEALED",
                    error="Cannot commit: Active writer package is unsealed (missing Context Agent creative brief).",
                    next_required_action="obtain_writer_package",
                )

            draft_pkg_fp = draft_data.get("package_fingerprint")
            draft_brief_fp = draft_data.get("package_brief_fingerprint")
            if not draft_brief_fp or not draft_data.get("is_writer_ready", True):
                return ChapterCommitOutcomeResult(
                    ok=False,
                    chapter=chapter,
                    action="reject",
                    attempt_id=f"unsealed-{uuid.uuid4().hex[:8]}",
                    chapter_outcome="rejected",
                    gate_decision_ref="",
                    durable_commit_persisted=False,
                    projection_status={},
                    projection_success=False,
                    can_retry_projection=False,
                    error_code="WRITER_PACKAGE_UNSEALED",
                    error="Cannot commit: Staged draft was not created against a sealed Native Writer Package.",
                    next_required_action="obtain_writer_package",
                )

            current_pkg_fp = self.compute_package_fingerprint(
                chapter,
                creative_brief_fingerprint=saved_brief_fp,
            )
            base_unsealed_fp = self.compute_package_fingerprint(chapter)
            if draft_pkg_fp == base_unsealed_fp or not draft_pkg_fp:
                return ChapterCommitOutcomeResult(
                    ok=False,
                    chapter=chapter,
                    action="reject",
                    attempt_id=f"unsealed-{uuid.uuid4().hex[:8]}",
                    chapter_outcome="rejected",
                    gate_decision_ref="",
                    durable_commit_persisted=False,
                    projection_status={},
                    projection_success=False,
                    can_retry_projection=False,
                    error_code="WRITER_PACKAGE_UNSEALED",
                    error="Cannot commit: Staged draft was created with an unsealed package fingerprint.",
                    next_required_action="obtain_writer_package",
                )

            if draft_pkg_fp != current_pkg_fp or draft_brief_fp != saved_brief_fp:
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
                    error="Cannot commit: Authoritative inputs changed since writer package was generated.",
                    next_required_action="obtain_writer_package",
                )
            resolved_prose = staged_prose
        else:
            resolved_prose = _internal_direct_prose or ""
            if _internal_package_fingerprint:
                pkg_file = runtime_dir / "writer_package.json"
                saved_brief_fp = ""
                if pkg_file.is_file():
                    saved_pkg = read_json_if_exists(pkg_file) or {}
                    saved_brief_fp = str(saved_pkg.get("creative_brief_fingerprint") or "")
                current_fp = self.compute_package_fingerprint(
                    chapter,
                    creative_brief_fingerprint=saved_brief_fp,
                )
                if _internal_package_fingerprint != current_fp:
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
                        next_required_action="obtain_writer_package",
                    )

        # 3. Required semantic workflow artifacts validation (NO FAKE DEFAULTS)
        art = artifacts or {}
        rev = review_result if review_result is not None else art.get("review_result")
        ext = extraction_result if extraction_result is not None else art.get("extraction_result")
        ful = fulfillment_result if fulfillment_result is not None else art.get("fulfillment_result")
        dis = disambiguation_result if disambiguation_result is not None else art.get("disambiguation_result")
        rec = reconciliation_result if reconciliation_result is not None else art.get("reconciliation_result")

        missing_artifacts = []
        if rev is None:
            missing_artifacts.append("review_result")
        if ext is None:
            missing_artifacts.append("extraction_result")
        if ful is None:
            missing_artifacts.append("fulfillment_result")
        if dis is None:
            missing_artifacts.append("disambiguation_result")
        if rec is None:
            missing_artifacts.append("reconciliation_result")

        if missing_artifacts:
            return ChapterCommitOutcomeResult(
                ok=False,
                chapter=chapter,
                action="reject",
                attempt_id=f"missingart-{uuid.uuid4().hex[:8]}",
                chapter_outcome="rejected",
                gate_decision_ref="",
                durable_commit_persisted=False,
                projection_status={},
                projection_success=False,
                can_retry_projection=False,
                error_code="REQUIRED_ARTIFACTS_MISSING",
                error=f"Required semantic workflow artifacts missing: {', '.join(missing_artifacts)}",
                required_artifacts=missing_artifacts,
                next_required_action=f"generate_{missing_artifacts[0]}",
            )

        # Parse proposed changes from prose if not passed
        if proposed_changes is None:
            proposed_changes = art.get("proposed_changes")
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

        # 4. Authoritative changes-gate execution
        db_path = self.project_root / ".webnovel" / "index.db"
        state_path = self.project_root / ".webnovel" / "state.json"
        changes_gate_res = run_changes_gate(
            chapter_text=resolved_prose,
            db_path=db_path if db_path.is_file() else None,
            state_path=state_path if state_path.is_file() else None,
            chapter=chapter,
        )
        gate_result = changes_gate_res.to_dict()

        # Adapt findings
        contracts = load_runtime_sources(self.project_root, chapter).contracts
        findings = adapt_legacy_artifacts(
            chapter=chapter,
            review=rev,
            fulfillment=ful,
            disambiguation=dis,
            contract_payloads=contracts,
        )
        findings.extend(adapt_changes_gate_result(gate_result, chapter=chapter))

        attempt_id = f"runtime-{uuid.uuid4().hex[:8]}"
        attempt_kwargs = {
            "policy_version": "phase6a-v1",
            "scope": {"chapter": chapter},
            "review_result": rev,
            "fulfillment_result": ful,
            "disambiguation_result": dis,
            "extraction_result": ext,
            "chapter_text": resolved_prose,
            "proposed_changes": proposed_changes,
            "reconciliation_result": rec,
            "on_conflict": on_conflict,
        }

        service = ChapterCommitService(self.project_root)
        try:
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
        except (ChapterCommitError, ValueError) as exc:
            return ChapterCommitOutcomeResult(
                ok=False,
                chapter=chapter,
                action="reject",
                attempt_id=attempt_id,
                chapter_outcome="rejected",
                gate_decision_ref="",
                durable_commit_persisted=False,
                projection_status={},
                projection_success=False,
                can_retry_projection=False,
                error=str(exc),
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

    def publish_accepted_draft(
        self,
        chapter: int,
        draft_id: str,
    ) -> Path:
        """
        Publish the exact accepted staged draft to 正文/第NNNN章[-title].md.
        Enforces invariants:
        - Only publishes if durable commit exists with status == 'accepted'.
        - draft_id is strictly required (no guessing, no active draft fallback).
        - Candidate staged draft SHA-256 must exactly match accepted commit's
          provenance.reconciliation_chapter_sha256.
        - Fails closed if commit is rejected, missing, or SHA-256 does not match.
        """
        if not draft_id or not isinstance(draft_id, str) or not draft_id.strip():
            raise ValueError(f"Cannot publish draft for chapter {chapter}: explicit draft_id is required.")
        target_draft_id = draft_id.strip()

        commit_file = self.paths.commit_json(chapter)
        if not commit_file.is_file():
            raise RuntimeError(f"Cannot publish draft for chapter {chapter}: No durable commit exists.")

        commit_data = read_json_if_exists(commit_file) or {}
        commit_meta = commit_data.get("meta") or {}
        commit_status = str(commit_meta.get("status") or "")
        if commit_status != "accepted":
            raise RuntimeError(
                f"Cannot publish draft for chapter {chapter}: Durable commit status is '{commit_status}', not 'accepted'."
            )

        provenance = commit_data.get("provenance") or {}
        accepted_sha = provenance.get("reconciliation_chapter_sha256")
        if not accepted_sha:
            raise RuntimeError(
                f"Cannot publish draft for chapter {chapter}: Durable commit missing provenance.reconciliation_chapter_sha256."
            )

        runtime_dir = self._chapter_runtime_dir(chapter)
        draft_file = runtime_dir / "drafts" / f"{target_draft_id}.json"
        if not draft_file.is_file():
            active_file = runtime_dir / "draft.json"
            if active_file.is_file():
                active_data = read_json_if_exists(active_file) or {}
                if active_data.get("draft_id") == target_draft_id:
                    draft_file = active_file
        if not draft_file.is_file():
            raise RuntimeError(f"Cannot publish draft for chapter {chapter}: Staged draft '{target_draft_id}' not found.")

        draft_data = read_json_if_exists(draft_file) or {}
        prose = str(draft_data.get("prose") or "")
        if not prose.strip():
            raise RuntimeError(f"Cannot publish draft for chapter {chapter}: Staged draft prose is empty.")

        expected_fp = draft_data.get("draft_fingerprint")
        actual_fp = hashlib.sha256(prose.encode("utf-8")).hexdigest()
        if expected_fp and actual_fp != expected_fp:
            raise RuntimeError(f"Cannot publish draft for chapter {chapter}: Draft internal fingerprint mismatch.")

        if actual_fp != accepted_sha:
            raise RuntimeError(
                f"Cannot publish draft for chapter {chapter}: ACCEPTED_DRAFT_MISMATCH "
                f"(draft SHA-256 '{actual_fp}' does not match accepted commit reconciliation_chapter_sha256 '{accepted_sha}')."
            )

        from chapter_paths import default_chapter_draft_path
        target_file = default_chapter_draft_path(self.project_root, chapter)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(prose, encoding="utf-8")
        return target_file

    def retry_projection(self, chapter: int) -> dict[str, Any]:
        """Replay or retry projections from the existing durable commit."""
        return retry_projection(self.project_root, chapter=chapter)

    def get_voice_target(self, chapter: int = 1, genre: Optional[str] = None):
        """Obtain positive voice target for chapter authoring and editing (Issue #26)."""
        from .prose_voice_target import build_voice_target
        return build_voice_target(self.project_root, chapter=chapter, genre=genre)

    def get_prose_pipeline(self):
        """Obtain ProseQualityPipeline coordinator (Issue #26)."""
        from .prose_pipeline import ProseQualityPipeline
        return ProseQualityPipeline(self.project_root)

    def _commit_direct_internal(
        self,
        chapter: int,
        prose: str,
        package_fingerprint: Optional[str] = None,
        **kwargs: Any,
    ) -> ChapterCommitOutcomeResult:
        """Internal compatibility helper for direct prose commit. Not for public happy path."""
        return self.commit(
            chapter=chapter,
            _internal_direct_prose=prose,
            _internal_package_fingerprint=package_fingerprint,
            **kwargs,
        )

