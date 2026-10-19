#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression test suite for GitHub Issue #50 defect repairs.

Covers:
- Group 1 (Guard): Python interpreter option parsing and official readonly vs write injection (also in test_guard_command_contract.py).
- Group 2 (Reviewer convergence): full re-review, Draft identity unchanged, persistent/resolved/uncertain/new tracking, high/critical closure, finding churn.
- Group 3 (Context budget & telemetry): runtime governed-context -> WriterPackage char budget, section telemetry (before_chars, after_chars, section_chars, sections_trimmed, shortfall_chars), ContextRanker budget unit fix, Canon/Intent retention, entity deduplication.
- Group 4 (Creative progress obligation): progress obligation derivation, normal vs setup/transition chapters, WriterPackage prompt rendering, Intent/Craft boundary preservation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from data_modules.chapter_runtime import (
    ChapterRuntime,
    derive_chapter_progress_obligation,
)
from data_modules.config import DataModulesConfig
from data_modules.context_manager import ContextManager
from data_modules.context_ranker import ContextRanker
from data_modules.review_schema import (
    ReviewIssue,
    ReviewResult,
    compute_review_convergence,
    parse_review_output,
)


# =========================================================================== #
# Group 2: Reviewer Convergence Tests
# =========================================================================== #

def test_reviewer_convergence_first_review():
    """Initial review has no previous review; reports new_count equal to issue count."""
    curr = ReviewResult(
        chapter=1,
        issues=[
            ReviewIssue(severity="medium", category="timeline", description="时间不连贯"),
            ReviewIssue(severity="low", category="character", description="称呼略有生硬"),
        ],
        draft_id="draft-001-a1b2c3d4",
        draft_fingerprint="fp111",
    )
    conv = compute_review_convergence(curr, None)
    assert conv["has_previous_review"] is False
    assert conv["previous_finding_count"] == 0
    assert conv["new_count"] == 2
    assert conv["resolved_count"] == 0
    assert conv["persistent_count"] == 0
    assert conv["finding_churn"] == 2
    assert conv["all_high_critical_closed"] is True


def test_reviewer_convergence_re_review_tracks_resolved_persistent_and_new():
    """Re-review detects resolved, persistent, uncertain, and new issues, plus closure for high/critical."""
    prev = ReviewResult(
        chapter=1,
        issues=[
            ReviewIssue(severity="high", category="setting", description="功法品阶前后矛盾：前文玄阶中级此处写地阶"),
            ReviewIssue(severity="critical", category="logic", description="已阵亡角色在宴会上再次发言", location="第5段"),
            ReviewIssue(severity="medium", category="timeline", description="午后突然变为清晨无过渡"),
            ReviewIssue(severity="low", category="ai_flavor", description="机械套话过多"),
        ],
        draft_id="draft-001-a1b2c3d4",
        draft_fingerprint="fp111",
    )

    # In second draft:
    # 1. 功法品阶矛盾 is fixed (not in current review) -> resolved (high closure!)
    # 2. 阵亡角色发言 persists -> persistent (critical still open)
    # 3. 时间线问题 slightly modified in wording -> uncertain/persistent
    # 4. A brand new issue is discovered by full re-review
    curr = ReviewResult(
        chapter=1,
        issues=[
            ReviewIssue(severity="critical", category="logic", description="已阵亡角色在宴会上再次发言", location="第5段"),
            ReviewIssue(severity="low", category="timeline", description="午后到清晨缺少必要环境过渡描写"),
            ReviewIssue(severity="medium", category="character", description="新问题：主角性格突变无动机"),
        ],
        draft_id="draft-001-b2c3d4e5",
        draft_fingerprint="fp222",
    )

    conv = compute_review_convergence(curr, prev)
    assert conv["has_previous_review"] is True
    assert conv["previous_finding_count"] == 4
    assert conv["resolved_count"] >= 1  # 功法品阶 + ai_flavor resolved
    assert conv["persistent_count"] >= 1  # 已阵亡角色 persistent
    assert conv["new_count"] >= 1  # 主角性格突变 is new
    assert conv["finding_churn"] == conv["resolved_count"] + conv["new_count"]

    # Closure for high / critical
    closure = {item["description"]: item["status"] for item in conv["high_critical_closure"]}
    assert "功法品阶前后矛盾：前文玄阶中级此处写地阶" in closure
    assert closure["功法品阶前后矛盾：前文玄阶中级此处写地阶"] == "resolved"
    assert "已阵亡角色在宴会上再次发言" in closure
    assert closure["已阵亡角色在宴会上再次发言"] == "persistent"
    assert conv["all_high_critical_closed"] is False


def test_reviewer_convergence_all_high_critical_closed():
    """When all high/critical issues are fixed, all_high_critical_closed is True."""
    prev = ReviewResult(
        chapter=2,
        issues=[
            ReviewIssue(severity="high", category="continuity", description="上一章重伤本章毫无痕迹"),
        ],
        draft_id="d1",
        draft_fingerprint="fp1",
    )
    curr = ReviewResult(
        chapter=2,
        issues=[
            ReviewIssue(severity="low", category="pacing", description="本章节奏略显平缓"),
        ],
        draft_id="d2",
        draft_fingerprint="fp2",
    )
    conv = compute_review_convergence(curr, prev)
    assert conv["resolved_count"] == 1
    assert conv["new_count"] == 1
    assert conv["persistent_count"] == 0
    assert conv["all_high_critical_closed"] is True


def test_reviewer_result_to_metrics_preserves_penalties_and_includes_convergence():
    """to_metrics_dict includes convergence telemetry while preserving exact penalty scoring."""
    result = ReviewResult(
        chapter=5,
        issues=[
            ReviewIssue(severity="critical", category="setting", description="破界境界错误"),
            ReviewIssue(severity="high", category="character", description="动机缺失"),
        ],
        draft_id="d1",
        draft_fingerprint="fp1",
    )
    result.convergence = {
        "previous_finding_count": 3,
        "resolved_count": 2,
        "persistent_count": 1,
        "uncertain_count": 0,
        "new_count": 1,
        "finding_churn": 3,
    }
    metrics = result.to_metrics_dict()
    # 100 - 35 (critical) - 15 (high) = 50.0
    assert metrics["overall_score"] == 50.0
    assert metrics["previous_finding_count"] == 3
    assert metrics["resolved_count"] == 2
    assert metrics["persistent_count"] == 1
    assert metrics["new_count"] == 1
    assert metrics["finding_churn"] == 3


# =========================================================================== #
# Group 3: Context Budget & Telemetry Tests
# =========================================================================== #

def test_context_ranker_budget_unit_uses_character_size():
    """ContextRanker._apply_budget decrements character count rather than item count."""
    ranker = ContextRanker()
    pack = {
        "core": {
            "recent_summaries": [
                {"chapter": 1, "summary": "A" * 500},
                {"chapter": 2, "summary": "B" * 500},
                {"chapter": 3, "summary": "C" * 500},
            ],
            "recent_meta": [
                {"chapter": 1, "hook": "D" * 300},
                {"chapter": 2, "hook": "E" * 300},
            ],
        },
        "story_skeleton": [
            {"chapter": 1, "summary": "S" * 400},
            {"chapter": 2, "summary": "T" * 400},
        ],
        "reference": [
            {"content": "Ref" * 200},
            {"content": "Ref2" * 200},
        ],
    }

    # If budget is generous (e.g. 50000 chars), section caps apply without trimming to 1
    ranked_generous = ranker.rank_pack(pack, chapter=4, budget=50000)
    assert len(ranked_generous["core"]["recent_summaries"]) == 3

    # If budget is very tight (e.g. 200 chars), later sections are shrunk towards 1
    ranked_tight = ranker.rank_pack(pack, chapter=4, budget=200)
    # The first kept section exhausts the 200 chars, subsequent sections shrink to 1
    assert len(ranked_tight["reference"]) <= 1


def test_context_manager_enforce_context_budget_telemetry_and_canon_retention(tmp_path):
    """ContextManager._enforce_context_budget adds section_chars, trims compressible sections, and never trims Canon/Intent."""
    cfg = DataModulesConfig(project_root=tmp_path)
    mgr = ContextManager(cfg)

    # Construct payload with Canon, Intent, and compressible sections
    canon_fact = "主角林动在青阳镇获得神秘石符，确凿发生于第1章。" * 10
    intent_goal = "本章目标：突破地元境初期，击退雷力。" * 5

    payload = {
        "canon": [{"content": canon_fact}],
        "intent": [{"goal": intent_goal}],
        "reference": [{"item": f"ref_{i}" * 50} for i in range(10)],
        "memory": [{"mem": f"mem_{i}" * 50} for i in range(10)],
        "runtime_status": {"debug": "x" * 200},
        "context_diagnostics": [{"log": "diag" * 50}],
    }

    # Enforce a small budget
    budget = 1200
    budgeted = mgr._enforce_context_budget(payload, chapter=2, limit=budget)

    meta = budgeted.get("meta", {}).get("context_budget", {})
    assert "before_chars" in meta
    assert "after_chars" in meta
    assert "section_chars" in meta
    assert "sections_trimmed" in meta
    assert "shortfall_chars" in meta

    # Canon and Intent must be 100% intact!
    assert budgeted["canon"][0]["content"] == canon_fact
    assert budgeted["intent"][0]["goal"] == intent_goal

    # Droppable sections (context_diagnostics, runtime_status) dropped
    assert "context_diagnostics" not in budgeted
    assert "runtime_status" not in budgeted

    # Reference or memory halved
    assert len(budgeted["reference"]) < 10

    # Section chars telemetry contains accurate section character counts
    assert "canon" in meta["section_chars"]
    assert "intent" in meta["section_chars"]
    assert meta["section_chars"]["canon"] > 0


def test_context_budget_shortfall_reported_when_uncompressible_exceeds_budget(tmp_path):
    """If Canon and Intent alone exceed the budget, factual content is kept and shortfall is reported."""
    cfg = DataModulesConfig(project_root=tmp_path)
    mgr = ContextManager(cfg)

    huge_canon = "不可压缩的核心已确认设定事实。" * 200
    payload = {
        "canon": [{"content": huge_canon}],
        "intent": [{"goal": "核心目标"}],
        "reference": [{"item": "r1"}],
    }

    tight_limit = 500
    budgeted = mgr._enforce_context_budget(payload, chapter=1, limit=tight_limit)
    meta = budgeted["meta"]["context_budget"]

    # Canon is not cut!
    assert budgeted["canon"][0]["content"] == huge_canon
    # Shortfall is accurately reported
    assert meta["shortfall_chars"] > 0
    assert meta["enforced"] is False


def test_governed_canon_entity_deduplication(tmp_path):
    """governed_canon['entities'] contains projected entities; snapshot['entities'] is omitted to avoid duplicate bloat."""
    # Setup test project
    (tmp_path / ".story-system" / "projections").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    proj_entities = {
        "characters": [{"name": "林动", "current_status": "淬体九重"}],
        "items": [{"name": "神秘石符"}],
    }
    (tmp_path / ".story-system" / "projections" / "entities.json").write_text(
        json.dumps(proj_entities, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps({"project_info": {"title": "武动乾坤", "genre": "玄幻"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    runtime = ChapterRuntime(tmp_path)
    gov_ctx = runtime.get_governed_context(chapter=1)

    canon = gov_ctx["governed_canon"]
    assert canon["entities"] == proj_entities
    # snapshot must NOT duplicate entities
    snapshot = canon["context_snapshot"]
    assert "entities" not in snapshot


# =========================================================================== #
# Group 4: Creative Chapter Progress Obligation Tests
# =========================================================================== #

def test_chapter_progress_obligation_normal_chapter():
    """Normal progression chapter receives positive state change requirement."""
    ob = derive_chapter_progress_obligation(
        chapter=5,
        directive={"goal": "击败黑风寨二当家，夺取破障丹"},
        chapter_meta={"core_event": "黑风寨激战"},
        outline="林动单枪匹马杀入黑风寨，经过苦战击溃二当家，缴获战利品。",
    )
    assert ob["obligation_type"] == "progression"
    assert ob["is_setup_or_transition"] is False
    assert "实质变化" in ob["description"]
    assert "严禁仅以'准备做某事'空转结束" in ob["description"]
    assert "action" in ob["allowed_progress_dimensions"]


def test_chapter_progress_obligation_setup_transition_chapter():
    """Explicit setup/transition chapter allows preparation as valid goal without forcing premature climax."""
    for keyword in ("过渡章", "休整整备", "战前铺垫", "setup and gather supplies"):
        ob = derive_chapter_progress_obligation(
            chapter=6,
            directive={"goal": f"战后休整与物资整备 ({keyword})"},
            chapter_meta={"core_event": "清点战利品并疗伤"},
            outline="林动在密室疗伤，研究新获得的石符奥秘，为前往大荒宗做准备。",
        )
        assert ob["obligation_type"] == "setup_or_transition"
        assert ob["is_setup_or_transition"] is True
        assert "准备与蓄势本身可作为有效目标" in ob["description"]


def test_writer_package_prompt_renders_progress_obligation(tmp_path):
    """WriterPackage.to_writer_prompt renders chapter progress obligation under intent section."""
    (tmp_path / ".story-system" / "projections").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps({"project_info": {"title": "测试小说", "genre": "仙侠"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    runtime = ChapterRuntime(tmp_path)
    pkg = runtime.get_writer_package(chapter=1, creative_brief="第一章任务书：开篇入道")
    prompt = pkg.to_writer_prompt()

    assert "## 1. 本章写作意图 (Current Intent)" in prompt
    assert "剧情推进义务 (Progress Obligation)" in prompt
