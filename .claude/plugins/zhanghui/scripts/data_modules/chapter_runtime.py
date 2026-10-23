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
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from chapter_outline_loader import (
    extract_outline_residual_notes,
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
from .durable_projection import discover_validated_chapter_commits
from .gate_finding_adapters import adapt_changes_gate_result, adapt_legacy_artifacts
from .projections import retry_projection
from .reconciliation import (
    prose_only_text,
    prose_subject_sha256,
    reconcile_changes,
    split_chapter_and_changes,
)
from .runtime_contract_builder import RuntimeContractBuilder
from .chapter_intent_sync import (
    chapter_is_accepted,
    effective_chapter_meta,
    outline_intent_digest,
    sync_chapter_meta,
)
from .state_validator import get_chapter_meta_entry
from .story_contracts import (
    StoryContractPaths,
    persist_runtime_contracts,
    persist_story_seed,
    read_json_if_exists,
)
from .story_runtime_sources import load_runtime_sources
from .story_system_engine import StorySystemEngine
from .writing_skill_registry import (
    render_writer_skills,
    selection_fingerprint,
)
from .write_gates import run_write_gate


# Automatic "revise -> re-review" budget (webnovel-write SKILL.md, Step 4).
# The contract is "初审 + 至多一次定向修订 + 复审", i.e. at most two review rounds.
# It used to exist only as prose: the 2026-10-21 chapter-4 Full Write ran four review
# rounds (1,090 s) because nothing counted them and the orchestrator decided a
# non-blocking medium finding was "worth a tiny fix" after the budget was spent.
AUTO_REVISION_MAX_ROUNDS = 2
AUTO_REVISION_BUDGET_SCHEMA = "auto-revision-budget/v1"

# The Context Agent contract says 1,200–1,800 hanzi. It used to be prose only: in the
# 2026-10-23 A/B the three Briefs came in at 2,874 / 3,476 / 5,188 characters and the
# Writer prompt grew with them. A limit that nothing enforces is not a limit, so sealing
# now refuses an oversized Brief instead of silently shipping it.
MAX_CREATIVE_BRIEF_CHARS = 1800


def count_brief_chars(text: str) -> int:
    """Count the Brief's characters the way the contract reads: whitespace excluded."""
    return len(re.sub(r"\s+", "", str(text or "")))


# --------------------------------------------------------------------------- #
# Writer prompt: chapter structure and scene design
# --------------------------------------------------------------------------- #
#
# The Writer used to receive `outline[:600]`, a fixed character slice. Real chapter
# outlines are ~900-1,100 characters and put the structured nodes (CBN/CPNs/CEN), the
# hook type and the chapter prohibitions at the end — exactly what the slice removed.
# The prompt now renders the parsed fields instead, and keeps only the outline lines that
# no field consumed (see `extract_outline_residual_notes`).

_SCENE_POINTER_RE = re.compile(
    r"^\s*(?:见|参见|详见|参考)\s*"
    r"(?:`|story_craft|第\s*[0-9一二三四五六七八九十]+\s*章|本章|本场|上章|前章|前文|大纲)"
)
_SCENE_NEXT_CHAPTER_RE = re.compile(r"(?:→|->|—>)\s*下章")


def _usable_scene_value(value: Any) -> str:
    """Return a plan value that can guide the scene, or "".

    Real outlines contain two kinds of non-content in Scene-Sequel fields: a dangling
    pointer (`见 story_craft 第2章 reaction 字段`) and a next-chapter hand-off
    (`… → 下章目标`). Rendering either as this chapter's plan is what made the Sequel look
    complete while telling the Writer nothing.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if _SCENE_POINTER_RE.match(text) or _SCENE_NEXT_CHAPTER_RE.search(text):
        return ""
    return text


def _first_text(*values: Any) -> str:
    for value in values:
        text = _usable_scene_value(value)
        if text:
            return text
    return ""


def build_scene_plan(directive: Dict[str, Any]) -> Dict[str, str]:
    """Normalize the chapter's Scene-Sequel fields into one usable plan.

    Scene fields fall back to the chapter-level equivalent when the outline only wrote one
    of them (the official template asks for both). Nothing is invented: an empty value
    stays empty and the prompt says so.
    """
    directive = directive or {}
    return {
        "goal": _first_text(directive.get("scene_goal"), directive.get("goal")),
        "obstacle": _first_text(
            directive.get("scene_conflict"),
            directive.get("obstacles"),
            directive.get("conflict"),
        ),
        "setback": _first_text(directive.get("scene_setback"), directive.get("cost")),
        "resolution": _first_text(
            directive.get("scene_resolution"),
            directive.get("chapter_change"),
            directive.get("conflict"),
        ),
        "reaction": _first_text(directive.get("sequel_reaction")),
        "dilemma": _first_text(directive.get("sequel_dilemma")),
        "decision": _first_text(directive.get("sequel_decision")),
    }


def _same_text(value: str, *candidates: Any) -> bool:
    return bool(value) and any(value == str(candidate or "").strip() for candidate in candidates)


def render_scene_plan_block(
    directive: Dict[str, Any],
    *,
    as_questions: bool,
) -> List[str]:
    """Render the scene plan as the seven Scene-Sequel fields, or as four questions.

    `as_questions=False` is the pre-experiment planning expression: the outline's own
    vocabulary. `as_questions=True` is the single intervention under test — the same
    information, re-expressed as four creative decisions the Writer can execute. Neither
    mode adds story material.
    """
    plan = build_scene_plan(directive)
    directive = directive or {}
    if not any(plan.values()):
        # A chapter whose outline carries no scene information gets no empty scaffold.
        return []

    if as_questions:
        lines = [
            "【场景设计四问】",
            "把本章当成一场戏来写，动笔前先回答下面四个问题；答案只能来自本章规划，不得自行加设定。",
            "1. 这一场主角现在具体想得到什么？",
            f"   {plan['goal'] or '（章纲未给出明确目标）'}",
            "2. 什么力量在现场真正阻止他？",
            f"   {plan['obstacle'] or '（章纲未给出明确阻力）'}",
            "   阻止力量不一定是人物：可以是制度、时间、证据矛盾、关系冲突或风险。",
            "3. 主角因此被迫采取什么行动或选择？",
        ]
        if plan["decision"]:
            lines.append(f"   {plan['decision']}")
        elif plan["setback"]:
            lines.append(
                f"   章纲只写了现场挫折（{plan['setback']}），没有写出主角因此被迫做出的"
                "具体行动或选择——请在本场中把它写出来。"
            )
        else:
            lines.append("   章纲未给出；请在本场中写出主角被逼出的具体行动或选择。")
        lines.extend(
            [
                "4. 场景结束后，人物/关系/局势/认知中什么已经发生实质变化？",
                f"   {plan['resolution'] or '（章纲未给出明确变化）'}",
                "   信息发现本身可以构成变化，但不能只是“又知道了一条信息”。",
            ]
        )
        return lines

    def _label(label: str, value: str, *duplicates: Any) -> str:
        if value and _same_text(value, *duplicates):
            return f"- {label}：同本章前述字段"
        return f"- {label}：{value or '（章纲未提供）'}"

    reaction_note = ""
    if not plan["reaction"] and str(directive.get("sequel_reaction") or "").strip():
        reaction_note = "：原字段只写了指针，未提供内容"
    decision_note = ""
    if not plan["decision"] and str(directive.get("sequel_decision") or "").strip():
        decision_note = "：原字段指向下一章目标，不是本章结尾的决定"

    return [
        "【场景与后续设计 (Scene-Sequel)】",
        _label("场景目标", plan["goal"], directive.get("goal")),
        _label("现场阻力", plan["obstacle"], directive.get("obstacles")),
        _label("场景挫折", plan["setback"], directive.get("cost")),
        _label("场景结果", plan["resolution"], directive.get("chapter_change")),
        f"- 后续反应：{plan['reaction']}" if plan["reaction"] else f"- 后续反应：（章纲未提供{reaction_note}）",
        f"- 后续两难：{plan['dilemma']}" if plan["dilemma"] else "- 后续两难：（章纲未提供）",
        f"- 后续决定：{plan['decision']}" if plan["decision"] else f"- 后续决定：（章纲未提供{decision_note}）",
    ]


_READER_PULL_CONFIG_LINE = re.compile(
    r"^\s*(?:hook_config|coolpoint_config|micropayoff_config|pacing_config|override_config|"
    r"preferred_types|preferred_patterns|strength_baseline|chapter_end_required|transition_allowance|"
    r"density_per_chapter|combo_interval|milestone_interval|min_per_chapter|transition_min|"
    r"stagnation_threshold|strand_quest_max|strand_fire_gap_max|transition_max_consecutive|"
    r"allowed_rationale_types|debt_multiplier|payback_window_default)\s*:"
)
_SUMMARY_READER_PULL_LINE = re.compile(
    r"^\s*(?:hook_strength|hook_type|coolpoint_patterns|reading_power)\s*:"
)


def strip_reader_pull_config(text: str) -> str:
    """Drop the raw genre reader-pull config from a profile excerpt.

    `hook_config` / `coolpoint_config` / `micropayoff_config` / `pacing_config` have no
    runtime consumer; they used to reach the Writer verbatim as a YAML wall. The prose
    around them (genre creative notes) is kept.
    """
    kept: List[str] = []
    in_fence = False
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith("#") or stripped == "---":
            # Headings and rules only labelled the config block; the prompt already names
            # the genre in its own header.
            continue
        if _READER_PULL_CONFIG_LINE.match(line):
            continue
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def strip_summary_reader_pull_fields(text: str) -> str:
    """Drop reader-pull labels that carry no meaning in a prior-chapter summary."""
    return "\n".join(
        line for line in str(text or "").splitlines()
        if not _SUMMARY_READER_PULL_LINE.match(line)
    ).strip()


def render_reader_pull_block(
    directive: Dict[str, Any],
    *,
    open_loops: Optional[List[Any]] = None,
) -> List[str]:
    """Render the chapter's reader-pull chain as three creative questions.

    Replaces the scattered hook/coolpoint/micropayoff/pacing parameters with the only
    three decisions that matter at draft time: what the reader expects, what the chapter
    actually pays off or changes, and what the reader now wants because of it. Every
    answer is drawn from the chapter's own plan and prior open loops; nothing new is
    invented, and no numeric target is imposed.
    """
    directive = directive or {}
    goal = str(directive.get("goal") or "").strip()
    obstacle = str(directive.get("obstacles") or directive.get("conflict") or "").strip()
    cost = str(directive.get("cost") or "").strip()
    change = str(directive.get("chapter_change") or "").strip()
    ending_q = str(
        directive.get("ending_question") or directive.get("chapter_end_open_question") or ""
    ).strip()

    loop_question = ""
    for loop in open_loops or []:
        if isinstance(loop, dict):
            text = str(
                loop.get("unanswered_question")
                or loop.get("hook_text")
                or loop.get("content")
                or loop.get("description")
                or ""
            ).strip()
        else:
            text = str(loop or "").strip()
        if text:
            # The projected loop carries the event, not a formulated question. Keep it short
            # so the Writer reads it as material rather than a second outline.
            loop_question = text if len(text) <= 90 else text[:90].rstrip("，。；、 ") + "…"
            break

    obstacle_text = obstacle.rstrip("。；;，, ")
    fear = obstacle_text or "（章纲未给出明确阻力）"
    if cost:
        fear = f"{fear}；最怕主角付出的代价：{cost}"

    return [
        "【追读设计三问】",
        "本章的追读链只由三件事决定。动笔前先回答问题，再让它们在正文里成立；"
        "答案只能来自本章规划与前情，不得自行加设定。",
        "1. 本章开始时，读者主要期待什么？",
        f"   - 读者现在最想知道：{loop_question or '（前情没有未闭合问题，本章可以建立一个）'}",
        f"   - 读者最想看到本章发生：{goal or '（章纲未给出明确目标）'}",
        f"   - 读者最担心：{fear}",
        "2. 本章实际满足、改变或反转了什么期待？",
        f"   - 章纲写明本章的变化：{change or '（章纲未写明；请在本章写出一个读者能看见的变化）'}",
        "   - 读者必须看见至少一种回报：回答一个问题、完成一次行动、改变一种关系、"
        "暴露一个新事实、让人物付出代价、或推翻一种认知。不能只是把问题往后拖。",
        "   - 这个回报必须来自本章场景里人物真实的行动和代价，不能由叙述者额外补一句。",
        "3. 因为本章发生的事情，读者现在更想知道/看到什么？",
        f"   - 章纲给的未闭合问题：{ending_q or '（章纲未给出；由本章已经发生的事自然引出）'}",
        "   - 新问题必须由本章已经发生的事引出，并且比旧问题更具体，指向下一步行动。"
        "如果章纲的钩子与本章实际发生的事接不上，以本章发生的事为准，不要硬加一句悬念。",
        "边界：不要求每章 cliffhanger、爽点或反转。过渡/铺垫章也要有当章回报"
        "（可以是代价、关系变化或一个新事实），但不需要制造本章没有的高潮。",
    ]


def _natural_node(value: Any) -> str:
    """Turn ``主体 | 动作 | 结果`` planning notation into one natural line.

    Every part is kept. Dropping the middle part silently deleted the action —
    for example ``许知远 | 用周期规律与邻站插值 | 得到当夜逐时潮位`` used to render
    as ``许知远：得到当夜逐时潮位``, which removed the method the chapter requires.
    """
    text = _usable_scene_value(value)
    if not text:
        return ""
    parts = [part.strip() for part in text.split("|") if part.strip()]
    if len(parts) >= 3:
        return f"{parts[0]}：{'，'.join(parts[1:])}"
    return text


def _verbatim_fact(value: Any) -> str:
    """Return a chapter-plan fact exactly as authored.

    Hard facts may not be paraphrased, so this deliberately skips normalization —
    except for a dangling pointer (``见 story_craft 第N章``), which carries no fact at
    all. A next-chapter hand-off is kept: ``→ 下章目标`` still contains this chapter's
    required outcome.
    """
    text = str(value or "").strip()
    if not text or _SCENE_POINTER_RE.match(text):
        return ""
    return text


def render_hard_facts(
    directive: Dict[str, Any],
    plot_structure: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """The chapter's "get this wrong and the chapter is broken" facts.

    In the 2026-10-23 writer-freedom A/B, arm B lost the tide-difference direction
    (``低`` became ``高``) and turned a year gap into a month gap. Both facts existed in
    the chapter plan but only in the Context Agent's Brief, which is a paraphrase and
    can be wrong. This block copies the plan fields verbatim — value, direction,
    sequence, causality and the required change — so the Writer always has an anchor
    that neither the Context Agent nor the Router can rewrite.

    The block is intentionally outside the Creative Brief: it is not material to
    interpret, it is a constraint to obey.
    """
    directive = directive or {}
    plot_structure = plot_structure or {}

    facts: List[str] = []
    change = _verbatim_fact(
        directive.get("chapter_change") or plot_structure.get("chapter_change")
    )
    if change:
        facts.append(f"- 本章变化：{change}")

    hook = _verbatim_fact(directive.get("hook") or plot_structure.get("hook"))
    if hook:
        facts.append(f"- 计划钩子：{hook}")

    nodes: List[str] = []
    cbn = _natural_node(directive.get("cbn") or plot_structure.get("cbn"))
    if cbn:
        nodes.append(cbn)
    cpns = directive.get("cpns") or plot_structure.get("cpns") or []
    if isinstance(cpns, str):
        cpns = [cpns]
    for item in cpns:
        node = _natural_node(item)
        if node:
            nodes.append(node)
    cen = _natural_node(directive.get("cen") or plot_structure.get("cen"))
    if cen:
        nodes.append(cen)
    if nodes:
        facts.append("- 必须写到的事件：")
        facts.extend(f"  - {node}" for node in nodes)

    prohibitions = directive.get("forbidden_zones") or []
    if isinstance(prohibitions, str):
        prohibitions = [prohibitions]
    prohibitions = [str(item).strip() for item in prohibitions if str(item).strip()]
    if prohibitions:
        facts.append(f"- 本章不能发生：{'；'.join(prohibitions)}")

    return facts


def render_lean_chapter_structure(
    directive: Dict[str, Any],
    plot_structure: Dict[str, Any],
    *,
    residual_notes: str = "",
    include_nodes: bool = True,
) -> List[str]:
    """The chapter skeleton without planning vocabulary (CBN/CPNs/CEN, 节拍位置)."""
    directive = directive or {}
    plot_structure = plot_structure or {}
    lines: List[str] = []

    nodes: List[str] = []
    cbn = _natural_node(directive.get("cbn") or plot_structure.get("cbn"))
    if include_nodes and cbn:
        nodes.append(cbn)
    cpns = directive.get("cpns") or plot_structure.get("cpns") or []
    if isinstance(cpns, str):
        cpns = [cpns]
    for item in cpns:
        node = _natural_node(item)
        if include_nodes and node:
            nodes.append(node)
    cen = _natural_node(directive.get("cen") or plot_structure.get("cen"))
    if include_nodes and cen:
        nodes.append(cen)
    if nodes:
        lines.append("本章必须经过：")
        lines.extend(f"- {node}" for node in nodes)

    def _as_list(value: Any) -> List[str]:
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        return [text] if text else []

    buried = _as_list(directive.get("foreshadow_buried"))
    paid = _as_list(directive.get("foreshadow_paid_off"))
    if buried:
        lines.append(f"- 本章需要埋下：{'、'.join(buried)}")
    if paid:
        lines.append(f"- 本章需要回收：{'、'.join(paid)}")

    if residual_notes:
        lines.append(f"- 章纲备注：\n{residual_notes}")

    return lines


def render_progress_obligation(obligation: Any) -> str:
    """One natural sentence for the chapter's progress requirement."""
    if not isinstance(obligation, dict):
        return ""
    if obligation.get("obligation_type") == "setup_or_transition":
        return "本章是过渡/蓄势章：准备本身可以成为内容，但结束前仍要完成准备阶段的关键一步。"
    return (
        "本章结束前必须发生实质变化（行动、信息、关系、状态、位置或资源之一），"
        "不能只停在“准备做某事”。"
    )


def _lean_event_text(content: Dict[str, Any]) -> str:
    """Render a canon event as material; drop only the raw bookkeeping.

    Events reach this renderer as ``{event_type, subject, payload}``. The payload holds
    the actual fact, so it must be unwrapped — the old path dumped the whole dict as JSON,
    and a naive "skip events" rule would silently delete hard facts (a world rule, a
    planted clue) from the Writer's input.
    """
    payload = content.get("payload")
    if isinstance(payload, dict):
        merged = {**content, **payload}
    else:
        merged = dict(content)
    event = str(merged.get("event_type") or "")
    if event == "world_rule_revealed":
        rule = merged.get("rule_content") or merged.get("content")
        return f"世界规则：{rule}" if str(rule or "").strip() else ""
    relation = merged.get("relationship") or merged.get("relation")
    if relation:
        src = str(merged.get("from_entity") or "").strip()
        dst = str(merged.get("to_entity") or "").strip()
        who = f"{src} → {dst}" if src or dst else ""
        return f"关系（{who}）：{relation}" if who else f"关系：{relation}"
    for key in ("content", "summary", "text", "description"):
        text = merged.get(key)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def render_chapter_structure(
    directive: Dict[str, Any],
    plot_structure: Dict[str, Any],
    *,
    residual_notes: str = "",
) -> List[str]:
    """Render the chapter-specific structural fields the Writer needs to execute the plan."""
    directive = directive or {}
    plot_structure = plot_structure or {}
    lines: List[str] = []

    beat = _usable_scene_value(directive.get("beat_position"))
    if beat:
        lines.append(f"- 节拍位置：{beat}")

    cbn = _usable_scene_value(directive.get("cbn") or plot_structure.get("cbn"))
    cpns = directive.get("cpns") or plot_structure.get("cpns") or []
    cen = _usable_scene_value(directive.get("cen") or plot_structure.get("cen"))
    if cbn:
        lines.append(f"- CBN：{cbn}")
    if cpns:
        if isinstance(cpns, str):
            cpns = [cpns]
        rendered_cpns = "；".join(str(item) for item in cpns if str(item).strip())
        if rendered_cpns:
            lines.append(f"- CPNs：{rendered_cpns}")
    if cen:
        lines.append(f"- CEN：{cen}")

    def _as_list(value: Any) -> List[str]:
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        return [text] if text else []

    buried = _as_list(directive.get("foreshadow_buried"))
    paid = _as_list(directive.get("foreshadow_paid_off"))
    if buried:
        lines.append(f"- 本章埋设伏笔：{'、'.join(buried)}")
    if paid:
        lines.append(f"- 本章回收伏笔：{'、'.join(paid)}")

    if residual_notes:
        lines.append(f"- 章纲备注（非结构化原文）：\n{residual_notes}")

    return lines


class AutoRevisionBudgetExhausted(RuntimeError):
    """Raised when an automatic write loop asks for a review past its budget."""

    def __init__(self, chapter: int, budget: dict[str, Any]) -> None:
        self.chapter = chapter
        self.budget = budget
        super().__init__(
            f"自动修订预算已耗尽：第 {chapter} 章已用满 "
            f"{budget.get('max_rounds')} 轮审查（初审 + 至多一次定向修订 + 复审）。"
            f"停止自动打磨：把剩余的 PROSE_EDIT / deferred 问题写进报告并进入 Step 4.5；"
            f"只有 hard gate 阻断或人工恢复才可用 --allow-over-budget 显式越过。"
        )


def derive_chapter_progress_obligation(
    chapter: int,
    directive: Optional[dict[str, Any]] = None,
    chapter_meta: Optional[dict[str, Any]] = None,
    outline: str = "",
) -> dict[str, Any]:
    """
    Derive chapter progress obligation (Issue #50 task D, PR #51 Blocker A).
    Distinguishes "preparing to do something" vs "actually progressing something this chapter".
    Advisory-only Intent/Craft guidance; not a hard gate.

    Authority & Classification rules:
    1. Prioritize explicit structured chapter type / chapter role / beat_position fields:
       - 1st priority: directive (from chapter outline, authoritative for intent)
       - 2nd priority: chapter_meta (from state.json / effective intent)
    2. The classification depends on the chapter's overall positioning, NOT accidental
       narrative keywords (e.g. '铺垫', '休整', '谋划') occurring in outline prose or goals.
    3. In the absence of an explicit setup/transition declaration, DEFAULT to normal chapter
       progression obligation. Missing chapter type must not erroneously exempt progression.
    4. Explicit setup/transition chapters allow preparation/momentum gathering to be a valid goal.
    5. In case of conflict between goal and structured chapter type, the structured chapter type
       from directive governs.
    """
    directive = directive or {}
    chapter_meta = chapter_meta or {}
    goal = str(directive.get("goal") or chapter_meta.get("goal") or "")

    # 1. Authority resolution: inspect structured fields in authoritative directive first, then chapter_meta
    explicit_type = ""
    for source in (directive, chapter_meta):
        for key in ("chapter_type", "chapter_role", "type", "role", "beat_position"):
            val = source.get(key)
            if val and isinstance(val, str) and val.strip():
                explicit_type = val.strip()
                break
        if explicit_type:
            break

    # 2. Check if the explicit chapter type declares setup/transition.
    norm_type = explicit_type.lower()
    setup_or_transition_tokens = (
        "setup",
        "transition",
        "过渡",
        "铺垫",
        "整备",
        "休整",
        "蓄势",
    )
    is_setup_or_transition = False
    if norm_type:
        is_setup_or_transition = any(token in norm_type for token in setup_or_transition_tokens)

    if is_setup_or_transition:
        desc = (
            f"本章整体定位明确为【过渡/铺垫/整备章】（定位声明：{explicit_type}）：准备与蓄势本身可作为有效目标，"
            "但本章结束前仍须完成准备阶段的关键节点闭环，不得无限期拖延。"
        )
        obligation_type = "setup_or_transition"
    else:
        goal_display = f"“{goal[:40]}”" if goal else "本章核心目标"
        desc = (
            f"本章性质判定为【正向推进章】：本章结束前，与本章 goal（{goal_display}）"
            "直接相关的核心状态必须发生实质变化（行动推进、信息推进、关系推进、状态推进、位置推进或资源推进之一）。"
            "严禁仅以'准备做某事'空转结束；章末钩子不能替代本章剧情实质兑现。"
        )
        obligation_type = "progression"

    return {
        "chapter": chapter,
        "obligation_type": obligation_type,
        "is_setup_or_transition": is_setup_or_transition,
        "explicit_type": explicit_type or None,
        "description": desc,
        "allowed_progress_dimensions": [
            "action",       # 行动推进
            "information",  # 信息推进
            "relationship", # 关系推进
            "state",        # 状态推进
            "location",     # 位置推进
            "resource",     # 资源推进
        ],
        "policy": "ADVISORY_INTENT: 指导创作推进与审查意图核验，不升级为 Canon，不作为阻断门禁。",
    }


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
    writing_skills: List[Dict[str, Any]] = field(default_factory=list)
    writing_skills_fingerprint: str = ""
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

    def to_writer_prompt(
        self,
        scene_design: bool = False,
        reader_pull: bool = False,
        writing_skills: bool = False,
        lean_input: bool = False,
    ) -> str:
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

        `scene_design=True` re-expresses the chapter's Scene-Sequel plan as four creative
        questions instead of the outline's field names. It changes framing only — the same
        plan fields feed both renderings — and exists so the scene-layer A/B experiment can
        hold every other input constant.

        `reader_pull=True` replaces the scattered reader-pull material (raw genre
        hook/coolpoint/micropayoff/pacing config, bare `hook_strength`, the preset ending
        hook as an instruction) with three creative questions: what the reader expects,
        what this chapter actually pays off, and what the reader now wants. It removes
        parameters rather than adding any; the chapter plan is unchanged.

        `writing_skills=True` appends the selected skills ("本章创作方法"): each skill's
        own principles, a short example pair, and the router's one-sentence relevance
        note — never skill ids, scores, or the router's audit reasons.

        `lean_input=True` is the "强治理、弱干预" Writer package: the same governed facts
        and chapter intent, but planning vocabulary (CBN/CPNs/CEN, beat position, the
        progress-obligation label), the duplicated Scene/Reader-Pull question blocks, and
        raw event/path dumps are removed. It removes instructions; it adds no material.
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
        core_conflict = directive.get("conflict") or ""
        obstacle = directive.get("obstacles") or core_conflict
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
            "## 本章目标" if lean_input else "## 1. 本章写作意图 (Current Intent)",
        ]
        ch_meta = intent.get("chapter_meta") or {}
        core_event = ch_meta.get("core_event")
        if goal:
            lines.append(f"- 核心目标：{goal}")
            if core_event and core_event != goal:
                lines.append(f"- 计划核心事件：{core_event}")
        elif core_event:
            lines.append(f"- 核心事件：{core_event}")
        if core_conflict:
            lines.append(f"- 本章核心冲突：{core_conflict}")
        if obstacle and obstacle != core_conflict:
            lines.append(f"- 主要阻力：{obstacle}")
        if cost:
            lines.append(f"- 付出代价：{cost}")
        hook = ch_meta.get("hook")
        hook_type = ch_meta.get("hook_type")
        # With reader_pull on, the ending question and preset hook become material for the
        # third reader-pull question below. Rendering them here as a separate instruction is
        # what produced the "nothing happened, then add a suspense line" ending.
        if not (reader_pull or lean_input):
            if ending_q:
                lines.append(f"- 章末钩子/未决问题：{ending_q}")
                if hook and hook != ending_q:
                    lines.append(f"- 预设钩子设计：{hook}（类型：{hook_type or '未指定'}）")
            elif hook:
                lines.append(f"- 章末预设钩子：{hook}（类型：{hook_type or '未指定'}）")
            elif hook_type:
                lines.append(f"- 章末钩子倾向：{hook_type}")
        if not lean_input and must_nodes:
            lines.append(f"- 必须覆盖节点：{', '.join(must_nodes)}")
        if prohibitions and not lean_input:
            # In the lean package the prohibitions are hard facts and live in the
            # protected block below, so the Writer reads them once, with the same
            # authority as the values and directions.
            lines.append(f"- 本章绝对禁区：{', '.join(prohibitions)}")
        prog_obligation = intent.get("progress_obligation") or {}
        if lean_input:
            obligation = render_progress_obligation(prog_obligation)
            if obligation:
                lines.append(f"- 本章推进要求：{obligation}")
        elif prog_obligation and isinstance(prog_obligation, dict):
            ob_desc = prog_obligation.get("description", "")
            if ob_desc:
                lines.append(f"- 剧情推进义务 (Progress Obligation)：{ob_desc}")
        if outline:
            # Structured fields first; the unparsed remainder is kept verbatim. No fixed
            # character slice: the old `outline[:600]` cut off CBN/CPNs/CEN, hook_type and
            # the chapter prohibitions on real ~900-1,100-char outlines.
            plot_structure = intent.get("plot_structure") or {}
            residual = extract_outline_residual_notes(outline)
            if lean_input:
                # The nodes are rendered once, in the protected block below; repeating
                # them here is the "same fact twice reads as two facts" failure the
                # lean package is meant to remove.
                structure_lines = render_lean_chapter_structure(
                    directive, plot_structure, residual_notes=residual, include_nodes=False
                )
            else:
                structure_lines = render_chapter_structure(
                    directive, plot_structure, residual_notes=residual
                )
            if structure_lines:
                if not lean_input:
                    lines.append("【本章章纲结构】")
                lines.extend(structure_lines)
        if not lean_input:
            # The lean package lets the Creative Brief carry the scene/reader-pull
            # conclusions. Rendering the same plan again as four + three questions is
            # what made the Writer read a checklist.
            scene_lines = render_scene_plan_block(directive, as_questions=scene_design)
            if len(scene_lines) > 1:
                lines.extend(scene_lines)
            if reader_pull:
                lines.extend(
                    render_reader_pull_block(
                        directive,
                        open_loops=writer_ctx.get("urgent_loops") or [],
                    )
                )

        if lean_input:
            # Protected facts: copied verbatim from the chapter plan. This is the one
            # region the Context Agent's Brief and the Router cannot rewrite; it exists
            # because a single wrong direction ("低" → "高") or gap type invalidates the
            # whole chapter, and a paraphrase is allowed to be wrong while the plan is not.
            hard_facts = render_hard_facts(directive, intent.get("plot_structure") or {})
            if hard_facts:
                lines.extend([
                    "",
                    "## 本章必须写对",
                    "（本节直接取自本章章纲原字段，节点只换排版、不改语义。数字、高低、先后、"
                    "增减、因果、缺口类型一律照此，不得换成另一种说法；与后面的创作方向冲突时，"
                    "以本节为准。）",
                ])
                lines.extend(hard_facts)

        lines.extend([
            "",
            "## 当前人物状态与前文事实" if lean_input else "## 2. 治理事实与前情依据 (Governed Canon)",
        ])
        char_entries: List[str] = []
        other_entries: List[str] = []
        rendered_places: set[str] = set()
        rendered_facts: set[tuple[str, str]] = set()
        appearing_chars = canon.get("appearing_characters") or []
        for c in appearing_chars:
            if isinstance(c, dict):
                c_name = str(c.get("name") or c.get("entity_id") or c.get("id") or "").strip()
                if not c_name:
                    # Never fabricate a placeholder: an unresolved entity is a data
                    # problem, not a character called "角色".
                    continue
                c_type = str(c.get("type") or "").strip()
                entity_id = str(c.get("entity_id") or c.get("id") or "").strip()
                if c_type and c_type != "角色":
                    other_entries.append(f"- {c_type}：{c_name}")
                    if c_type == "地点":
                        rendered_places.add(c_name)
                    continue
                state_items = [item for item in (c.get("state") or []) if isinstance(item, dict)]
                state_text = "；".join(
                    f"{item.get('field')}：{item.get('value')}"
                    for item in state_items
                    if str(item.get("value") or "").strip()
                )
                for item in state_items:
                    if entity_id and item.get("field"):
                        rendered_facts.add((entity_id, str(item["field"])))
                identity = f"（entity_id: {entity_id}）" if entity_id and entity_id != c_name else ""
                char_entries.append(
                    f"- {c_name}{identity}：{state_text}" if state_text else f"- {c_name}{identity}"
                )
            elif isinstance(c, str) and c.strip():
                char_entries.append(f"- {c.strip()}")

        entities = canon.get("entities") or (canon.get("context_snapshot") or {}).get("entities") or {}
        if not char_entries and isinstance(entities, dict):
            for c in (entities.get("characters") or [])[:5]:
                if isinstance(c, dict):
                    c_name = str(c.get("name") or c.get("id") or "").strip()
                    if not c_name:
                        continue
                    c_status = c.get("current_status") or c.get("status") or ""
                    char_entries.append(f"- {c_name}：{c_status}" if c_status else f"- {c_name}")

        if char_entries:
            lines.append("【登场角色与状态】")
            lines.extend(char_entries)
        if other_entries:
            lines.append("【本章相关地点/物品/组织】")
            lines.extend(other_entries)

        canon_items = canon.get("canon_items") or []
        if canon_items:
            # In the lean package an open loop already shown under Writer Context is not
            # repeated here: the same clue twice reads as two clues.
            shown_loops = {
                str(loop.get("content") or loop.get("hook_text") or loop.get("description") or "").strip()
                for loop in (writer_ctx.get("urgent_loops") or [])[:3]
                if isinstance(loop, dict)
            } if lean_input else set()
            rendered_canon: List[str] = []
            for item in canon_items:
                if not isinstance(item, dict):
                    if str(item).strip():
                        rendered_canon.append(f"- {item}")
                    continue
                content = item.get("content")
                if isinstance(content, dict) and content.get("entity_id") and content.get("field"):
                    entity_id = str(content["entity_id"])
                    field = str(content["field"])
                    if (entity_id, field) in rendered_facts:
                        # Already shown under the character's state; do not repeat it.
                        continue
                    rendered_canon.append(f"- {entity_id} · {field}：{content.get('value')}")
                elif isinstance(content, dict):
                    if lean_input:
                        event_text = _lean_event_text(content)
                        if event_text and event_text not in shown_loops:
                            rendered_canon.append(f"- {event_text}")
                    else:
                        rendered_canon.append(f"- {json.dumps(content, ensure_ascii=False)}")
                else:
                    text = content or item.get("summary") or item.get("text") or str(item)
                    rendered_canon.append(f"- {text}")
            if rendered_canon:
                lines.append("【已确认前文事实 (Accepted Canon Facts)】")
                lines.extend(rendered_canon[:8])

        scene = canon.get("scene") or {}
        loc = scene.get("location") or scene.get("location_context")
        if isinstance(loc, dict):
            loc = loc.get("current") or loc.get("name") or loc.get("location") or ""
        if loc and not (lean_input and str(loc) in rendered_places):
            lines.append(f"【场景环境】：{loc}")

        lines.extend([
            "",
            "## 创作方向" if lean_input else "## 3. 创作策划任务书 (Creative Brief)",
            self.creative_brief if self.creative_brief else "（未提供独立创作策划任务书）",
            "",
            "## 工艺与边界" if lean_input else "## 4. 调性、文风与避坑约束 (Constraints & Craft)",
        ])
        if tone:
            lines.append(f"- 核心调性：{tone}")
        if pacing:
            lines.append(f"- 叙事节奏：{pacing}")
        if voice_target:
            lines.append(f"- 文风靶向：{voice_target}")
        if anti_patterns:
            lines.append(f"- 避坑规则 (Anti-patterns)：{'; '.join(anti_patterns[:5])}")

        genre_prof = constraints.get("genre_profile") or {}
        profile_excerpt = str(genre_prof.get("profile_excerpt") or "").strip()
        if reader_pull:
            profile_excerpt = strip_reader_pull_config(profile_excerpt)
        if profile_excerpt:
            lines.append(f"【题材创作指引 ({genre_prof.get('genre', genre)})】：\n{profile_excerpt}")

        # `writing_guidance` and `methodology_strategy` are Context-Agent-facing only and are
        # intentionally NOT rendered into the Writer prompt. The producer keys
        # (`guidance_items` / `methodology`) never matched the old renderer's (`items` /
        # `strategy_card`), so these blocks were dead code. Do not "fix" the key names:
        # that would push fixed character positions ("章首300字", "每600-900字微兑现") and
        # invented observability scores into the Writer. The reader-pull block above is the
        # only reader-facing expression of this layer.

        craft_items = constraints.get("craft_items") or []
        rendered_craft = []
        for item in craft_items:
            if isinstance(item, dict):
                if item.get("source_role") in ("CONFIG",) and item.get("source_ref") in (
                    "writing_guidance", "genre_profile", "genre_profile_excerpt", "preferences"
                ):
                    continue
                c = item.get("content")
                if isinstance(c, str) and c.strip():
                    rendered_craft.append(c.strip())
                elif isinstance(c, dict) and "text" in c:
                    rendered_craft.append(str(c["text"]).strip())
                elif isinstance(c, dict) and "rule" in c:
                    rendered_craft.append(str(c["rule"]).strip())
                elif isinstance(c, dict) and "content" in c:
                    rendered_craft.append(str(c["content"]).strip())
            elif isinstance(item, str) and item.strip():
                rendered_craft.append(item.strip())
        if rendered_craft:
            lines.append("【工艺建议 (Craft Recommendations)】")
            for c_text in rendered_craft[:5]:
                lines.append(f"- {c_text}")

        # Story Craft: extract chapter-scoped narrative constraints
        story_craft = constraints.get("story_craft") or {}
        sc_lines = []
        if isinstance(story_craft, dict):
            rhythm = story_craft.get("rhythm_curve") or {}
            if isinstance(rhythm, dict):
                n_since_peak = rhythm.get("chapters_since_peak", 0)
                warn_thresh = rhythm.get("warning_threshold", 3)
                block_thresh = rhythm.get("block_threshold", 5)
                if isinstance(n_since_peak, int) and isinstance(warn_thresh, int) and n_since_peak >= warn_thresh:
                    sc_lines.append(
                        f"- 情绪节奏张力：距上次高潮已过 {n_since_peak} 章（警示阈值: {warn_thresh}，阻断阈值: {block_thresh}），本章应推进情绪释放或高潮铺垫。"
                    )

            timed_locks = story_craft.get("timed_locks") or []
            if isinstance(timed_locks, list):
                for lock in timed_locks:
                    if isinstance(lock, dict) and lock.get("status") == "active":
                        dl = lock.get("deadline_chapter")
                        desc = lock.get("description", "")
                        lid = lock.get("id", "TL")
                        if isinstance(dl, int) and dl <= self.chapter + 1:
                            sc_lines.append(f"- 剧情限时锁：[{lid}] {desc}（截止第{dl}章）")

            arc = story_craft.get("character_arc")
            if isinstance(arc, dict) and arc.get("name"):
                arc_name = arc.get("name")
                start_st = arc.get("starting_state", "")
                end_st = arc.get("ending_state", "")
                trans = arc.get("transformation", "")
                sc_lines.append(
                    f"- 人物弧光指引（{arc_name}）：从【{start_st}】向【{end_st}】转变（核心转变：{trans}）"
                )

            echoes = story_craft.get("thematic_echoes") or []
            if isinstance(echoes, list):
                for item in echoes:
                    if isinstance(item, dict):
                        premise = item.get("premise", "")
                        for echo in item.get("echoes", []):
                            if isinstance(echo, dict) and echo.get("chapter") == self.chapter:
                                sc_lines.append(f"- 主题呼应设计：命题【{premise}】—— 本章呈现：{echo.get('manifestation')}")

            foreshadow_chain = story_craft.get("foreshadow_chain") or []
            if isinstance(foreshadow_chain, list):
                for fs in foreshadow_chain:
                    if isinstance(fs, dict) and fs.get("status") == "active" and fs.get("expected_payoff_chapter") == self.chapter:
                        fs_id = fs.get("id", "FS")
                        fs_type = fs.get("type", "伏笔")
                        fs_content = fs.get("content", "")
                        payoff_m = fs.get("payoff_method", "")
                        sc_lines.append(f"- 预定伏笔回收：[{fs_id}/{fs_type}] {fs_content}（回收方式：{payoff_m}）")

            p_notes = story_craft.get("pacing_notes")
            if isinstance(p_notes, str) and p_notes.strip():
                sc_lines.append(f"- 剧情节奏备忘：{p_notes.strip()}")
            rec_scenes = story_craft.get("recommended_scenes")
            if isinstance(rec_scenes, list) and rec_scenes:
                scenes_str = "、".join(str(s) for s in rec_scenes)
                sc_lines.append(f"- 推荐场景构想：{scenes_str}")

        if sc_lines:
            lines.append("【故事工艺约束 (Story Craft Constraints)】")
            lines.extend(sc_lines)

        recent_sums = writer_ctx.get("recent_summaries") or []
        urgent_loops = writer_ctx.get("urgent_loops") or []
        ref_items = writer_ctx.get("reference") or []
        context_lines: List[str] = []
        for s in recent_sums[:3]:
            s_text = s.get("summary") if isinstance(s, dict) else str(s)
            if reader_pull or lean_input:
                # The summary's YAML head used to hand the Writer `hook_strength: strong`
                # and a hook-type label for a chapter it had already read.
                s_text = strip_summary_reader_pull_fields(s_text)
            ch_prefix = f"第{s.get('chapter')}章：" if isinstance(s, dict) and s.get("chapter") else ""
            context_lines.append(f"- 前情摘要：{ch_prefix}{s_text}")
        for loop in urgent_loops[:3]:
            l_text = (
                loop.get("hook_text")
                or loop.get("description")
                or loop.get("content")
                or loop.get("expected_payoff")
                if isinstance(loop, dict)
                else str(loop)
            )
            context_lines.append(f"- 紧急伏笔待收：{l_text}")
        rendered_refs = []
        for r in ref_items:
            if isinstance(r, dict):
                c = r.get("content") or r.get("summary") or r.get("text") or ""
                if isinstance(c, (dict, list, tuple)):
                    if lean_input:
                        # Provenance dumps (`story_craft.path: value`) are system
                        # bookkeeping, not chapter material.
                        continue
                    if isinstance(c, dict) and "path" in c and "value" in c:
                        c = f"{c['path']}: {c['value']}"
                    else:
                        c = json.dumps(c, ensure_ascii=False)
                if str(c).strip():
                    rendered_refs.append(str(c).strip())
            elif isinstance(r, str) and r.strip():
                rendered_refs.append(r.strip())
        if rendered_refs:
            context_lines.append("【参考依据 (Reference)】")
            context_lines.extend(f"- {r_text}" for r_text in rendered_refs[:3])
        if context_lines:
            lines.extend([
                "",
                "## 前情与线索" if lean_input else "## 5. 关联前情线索 (Writer Context)",
            ])
            lines.extend(context_lines)

        if writing_skills:
            lines.extend(
                render_writer_skills(
                    self.writing_skills or [],
                    heading="本章可用技巧" if lean_input else "本章创作方法",
                )
            )

        lines.extend([
            "",
            "## 交付要求" if lean_input else "## 6. 正文交付协议 (Handoff Protocol)",
            "1. 输出连贯正文，严格按中文叙事逻辑组织；",
            "2. 正文末尾必须严格附带合法的 <chapter_changes>...</chapter_changes> 结构化提案块；",
            "   提案块必须是合法 JSON 对象，包含以下 8 个标准顶级字段：",
            "   - character_state_changes (对象数组): [{\"character_id\": \"角色名\", \"new_state\": \"状态变化\", \"importance\": \"normal\"}]",
            "   - new_plot_points (对象数组): [{\"context\": \"情节发展描述\", \"importance\": \"normal\"}]",
            "   - foreshadowing_actions (对象数组): 若本章无既有伏笔操作填空数组 []",
            "   - location_state_changes (对象数组): 若无填 []",
            "   - faction_state_changes (对象数组): 若无填 []",
            "   - time_progression (对象或 null): {\"time_period\": \"时间进展描述\", \"importance\": \"normal\"}",
            "   - item_transfers (对象数组): 若无填 []",
            "   - unresolved_questions (对象数组): [{\"question\": \"章末悬念或未决问题\"}]",
            "   注意：各数组元素必须为 JSON 对象（严禁输出纯字符串数组），若无变更请使用空数组 []；",
            "   【状态变化 vs 首次登场核心契约】：",
            "   - 新角色/新地点/新物品可以正常出现在正文中；",
            "   - 首次出现的新实体不属于 state change，后续由 Data Agent 根据最终正文独立提取，并在 ChapterCommit acceptance 后进入正式账本 projection 入库；",
            "   - 提交前，严禁把尚未入库的新角色/新实体写入 character_state_changes, location_state_changes, faction_state_changes, item_transfers 等状态变更字段（若无已有实体变更，填空数组 []）；",
            "   - new_plot_points.involved_characters 当前受 R3 门禁约束，只填写 Canon/context 中【已经存在】的角色，严禁填写尚未入库的新角色；",
            "   - 新角色参与的事件仍完整记录在 new_plot_points 的情节描述（context 或 description）中；",
            "   - 极短示例：正文首次出现新角色“巡查队长赵崇”与新地点“地下档案修复室”：",
            "     正确: \"character_state_changes\": [], \"location_state_changes\": [], \"new_plot_points\": [{\"context\": \"林越在矿道遭遇巡查队长赵崇罚没产量\", \"involved_characters\": [\"lin_yue\"]}]",
            "     错误: \"character_state_changes\": [{\"character_id\": \"zhao_chong\", ...}], \"new_plot_points\": [{\"involved_characters\": [\"lin_yue\", \"zhao_chong\"]}]（尚未入库的新角色写入 state change 或 involved_characters 会被 R3 门禁阻断拒绝）；",
            "   枚举白名单约束（违规将直接被门禁拦截）：",
            "   - 所有 importance 字段值只能取: \"normal\", \"important\", \"critical\"（严禁使用 \"high\"/\"low\"/\"medium\" 等）；",
            "   - foreshadowing_actions.action 只能取: \"setup\", \"payoff\"；",
            "   - item_transfers.new_status 只能取: \"active\", \"lost\", \"destroyed\", \"sealed\"；",
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
    review_subject_fingerprint: Optional[str] = None
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
    review_subject_fingerprint: Optional[str] = None
    has_writer_package: bool = False
    is_writer_package_stale: bool = False
    package_fingerprint: Optional[str] = None
    writing_skill_ids: list[str] = field(default_factory=list)
    writing_skills_fingerprint: str = ""
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

    def _has_durable_story_history(self) -> bool:
        """Check if project has durable history indicating an existing story rather than an uninitialized project."""
        try:
            if len(discover_validated_chapter_commits(self.project_root)) > 0:
                return True
        except Exception:
            commits_dir = self.project_root / ".story-system" / "commits"
            if commits_dir.is_dir() and any(commits_dir.glob("chapter_*.commit.json")):
                return True

        state_path = self.project_root / ".webnovel" / "state.json"
        state = read_json_if_exists(state_path) or {}
        progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
        if int(progress.get("current_chapter") or 0) > 0:
            return True

        # Legacy official prose compatibility
        prose_dir = self.project_root / "正文"
        if prose_dir.is_dir() and any(prose_dir.glob("*.md")):
            return True

        return False

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

        # 1. Master setting & anti-patterns check
        master_missing = not self.paths.master_json.is_file()
        anti_missing = not self.paths.anti_patterns_json.is_file()

        if (master_missing or anti_missing) and self._has_durable_story_history():
            missing_names = []
            if master_missing:
                missing_names.append(self.paths.master_json.name)
            if anti_missing:
                missing_names.append(self.paths.anti_patterns_json.name)
            raise RuntimeError(
                f"Existing story is missing foundational contract ({', '.join(missing_names)}). "
                "Automatic truth regeneration is forbidden to protect existing story intent."
            )

        if master_missing or anti_missing:
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
        #
        # The chapter contract is a *derived* projection of the chapter outline. It records the
        # outline digest it was generated from, so a later outline edit can be detected without
        # regenerating every contract on every write (G7):
        #   * no digest yet  -> adopt the current digest, do NOT regenerate (no churn on
        #     existing projects),
        #   * digest differs and the chapter is not yet accepted -> regenerate the chapter
        #     contract from the current outline,
        #   * digest differs but the chapter is already accepted -> leave history alone.
        ch_path = self.paths.chapter_json(chapter)
        current_digest = outline_intent_digest(self.project_root, chapter)
        if not ch_path.is_file():
            seed = engine.build(
                query=query,
                genre=genre,
                chapter=chapter,
                chapter_directive=directive,
            )
            if seed.get("chapter_brief"):
                from .story_contracts import write_json, write_marked_markdown, render_chapter_markdown
                ch_path.parent.mkdir(parents=True, exist_ok=True)
                payload = dict(seed["chapter_brief"])
                payload["source_outline_digest"] = current_digest
                write_json(ch_path, payload)
                write_marked_markdown(ch_path.with_suffix(".md"), render_chapter_markdown(payload))
        else:
            existing = read_json_if_exists(ch_path) or {}
            stored_digest = str(existing.get("source_outline_digest") or "")
            if not stored_digest:
                from .story_contracts import write_json
                existing["source_outline_digest"] = current_digest
                write_json(ch_path, existing)
            elif stored_digest != current_digest and not chapter_is_accepted(self.project_root, chapter):
                seed = engine.build(
                    query=query,
                    genre=genre,
                    chapter=chapter,
                    chapter_directive=directive,
                )
                if seed.get("chapter_brief"):
                    from .story_contracts import write_json, write_marked_markdown, render_chapter_markdown
                    payload = dict(seed["chapter_brief"])
                    payload["source_outline_digest"] = current_digest
                    write_json(ch_path, payload)
                    write_marked_markdown(ch_path.with_suffix(".md"), render_chapter_markdown(payload))

        # 3. Volume brief and Review contract
        volume = volume_num_for_chapter_from_state(self.project_root, chapter) or 1
        vol_path = self.paths.volume_json(volume)
        rev_path = self.paths.review_json(chapter)
        if not vol_path.is_file() or not rev_path.is_file():
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

        # 2.5 章纲是章节规划的唯一权威。若 state.json 的派生副本与章纲漂移，
        # 对「尚未被正式接受」的章节就地刷新派生副本；已接受章节只报告、不改写历史。
        advisories: list[dict[str, Any]] = []
        advisories.extend(self._refresh_chapter_intent(chapter))
        advisories.extend(self._plan_consistency_advisories(chapter))

        # 3. Prewrite gate validation
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

    @staticmethod
    def _plan_consistency_unavailable(reason: str) -> dict[str, Any]:
        return {
            "rule": "plan.consistency_unavailable",
            "severity": "warning",
            "message": (
                "规划一致性检查未能执行，本次没有可用的规划 advisory——"
                f"这不等同于规划无问题。原因：{reason}"
            ),
            "reason": reason,
            "advisory_only": True,
        }

    def _plan_consistency_advisories(self, chapter: int) -> list[dict[str, Any]]:
        """Surface planning-stage consistency findings for this chapter.

        Only *advisories* for this chapter are surfaced here (Craft/planning heuristics must not
        become a hidden write gate — I7); deterministic blockers belong to the plan flow, which
        is where the author can actually fix them.
        """
        try:
            from .plan_consistency import run_plan_consistency
        except ImportError as exc:  # pragma: no cover
            return [self._plan_consistency_unavailable(f"import_failed: {exc}")]

        volume = volume_num_for_chapter_from_state(self.project_root, chapter) or 1
        try:
            report = run_plan_consistency(self.project_root, volume=volume)
        except Exception as exc:  # pragma: no cover - planning checks must never block prepare
            # Still advisory (a planning heuristic must never block prepare), but an empty
            # list is indistinguishable from "planning is clean". Say which one it is.
            return [self._plan_consistency_unavailable(f"{type(exc).__name__}: {exc}")]

        out: list[dict[str, Any]] = []
        for item in report.get("advisories") or []:
            if item.get("chapter") not in (None, chapter):
                continue
            out.append(
                {
                    "rule": f"plan.{item.get('code')}",
                    "severity": "warning",
                    "message": str(item.get("message") or ""),
                    "details": item.get("evidence") or {},
                    "options": item.get("options") or [],
                }
            )
        return out

    def _refresh_chapter_intent(self, chapter: int) -> list[dict[str, Any]]:
        """Bring `state.json:chapter_meta` back in line with the authoritative chapter outline.

        Returns advisories describing what happened; never raises, because a stale derived
        copy must not block an otherwise valid chapter.
        """
        advisories: list[dict[str, Any]] = []
        state_path = self.project_root / ".webnovel" / "state.json"
        state = read_json_if_exists(state_path) or {}
        try:
            _effective, provenance = effective_chapter_meta(self.project_root, chapter, state)
        except Exception as exc:  # pragma: no cover - defensive
            return [
                {
                    "rule": "chapter_intent_unavailable",
                    "severity": "warning",
                    "message": f"无法解析本章规划权威来源: {exc}",
                }
            ]

        drift = provenance.get("drift") or {}
        if not drift:
            return advisories

        try:
            result = sync_chapter_meta(self.project_root, chapter, state)
        except Exception as exc:  # pragma: no cover - defensive
            result = {"ok": False, "reason": "sync_failed", "message": str(exc)}

        if result.get("ok"):
            try:
                from security_utils import atomic_write_json

                atomic_write_json(state_path, state, backup=True)
            except Exception as exc:  # pragma: no cover - defensive
                advisories.append(
                    {
                        "rule": "chapter_intent_refresh_failed",
                        "severity": "warning",
                        "message": f"章纲与 chapter_meta 漂移，但回写失败: {exc}",
                        "details": {"drift": drift},
                    }
                )
                return advisories
            advisories.append(
                {
                    "rule": "chapter_intent_refreshed",
                    "severity": "warning",
                    "message": (
                        "章纲已更新，state.json 的 chapter_meta 派生副本已按章纲刷新"
                        f"（{len(result.get('changed_fields') or {})} 个字段）。"
                    ),
                    "details": {
                        "changed_fields": result.get("changed_fields") or {},
                        "outline_digest": result.get("outline_digest"),
                    },
                }
            )
        else:
            advisories.append(
                {
                    "rule": "chapter_intent_drift_unresolved",
                    "severity": "warning",
                    "message": str(result.get("message") or result.get("reason") or "章纲与 chapter_meta 不一致"),
                    "details": {"drift": drift, "reason": result.get("reason")},
                }
            )
        return advisories

    # ------------------------------------------------------------------ #
    # Source fingerprints (task H)
    # ------------------------------------------------------------------ #
    # The WriterPackage fingerprint decides whether an in-flight chapter's sealed inputs are
    # still valid. It used to hash the *entire* volume outline file, the *entire*
    # `state.json`, and the whole contract set — so editing chapter 8's outline invalidated
    # chapter 2's package, and any unrelated `state.json` touch (a review checkpoint, another
    # chapter's `chapter_meta`) forced a pointless re-seal.
    #
    # The scope below is the set of inputs that genuinely determine *this* chapter's writing:
    #
    #   outline            this chapter's own outline section (Intent authority)
    #   outline_prev       the previous chapter's section — its sequel_decision seeds this
    #                      chapter's goal, so a change there must invalidate (H5)
    #   outline_volume     the volume-level preamble (卷基本信息: conflict / climax), which
    #                      governs every chapter in the volume
    #   contracts          Story System contracts for this chapter (master / volume / chapter /
    #                      review / anti-patterns)
    #   state              only the governing planning/state fields, see
    #                      `_state_fingerprint_payload`
    #   latest_commit      the newest accepted commit before this chapter (Canon)
    #
    # Deliberately NOT included: derived Canon projections in `state.json`
    # (`entity_state` / `protagonist_state` / `relationships` / `world_settings` /
    # `state_changes`) and per-chapter `chapter_meta` for other chapters. Those are
    # rebuildable Projection data: the Canon that produced them is already covered by
    # `latest_commit`, and the planning fields for *this* chapter come from the outline
    # (see `chapter_intent_sync`). Excluding them is what removes the meaningless
    # re-sealings, without weakening any real upstream check.

    _STATE_FINGERPRINT_KEYS = ("project_info", "story_craft")

    def _state_fingerprint_payload(self, chapter: int, state: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key in self._STATE_FINGERPRINT_KEYS:
            if key in state:
                payload[key] = state.get(key)

        progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
        payload["progress"] = {
            key: progress.get(key)
            for key in ("current_volume", "volumes_planned", "volumes_completed", "total_volumes", "target_chapters")
            if key in progress
        }

        volumes = state.get("volumes")
        if isinstance(volumes, list):
            # Volume-level planning that can redirect this chapter's intent.
            payload["volumes"] = [
                {k: item.get(k) for k in ("volume", "title", "chapters_range", "status") if k in item}
                if isinstance(item, dict)
                else item
                for item in volumes
            ]
        return payload

    def _volume_outline_preamble(self, chapter: int) -> str:
        """Volume-level text preceding the first chapter heading (卷基本信息 等)."""
        from chapter_outline_loader import _find_volume_outline_file

        try:
            from chapter_paths import iter_outline_chapter_headings
        except ImportError:  # pragma: no cover
            from scripts.chapter_paths import iter_outline_chapter_headings

        volume_file = _find_volume_outline_file(self.project_root, chapter)
        if volume_file is None or not volume_file.is_file():
            return ""
        try:
            content = volume_file.read_text(encoding="utf-8")
        except OSError:
            return ""
        headings = iter_outline_chapter_headings(content)
        return content[: headings[0].start] if headings else content

    def compute_source_fingerprints(self, chapter: int) -> dict[str, str]:
        """Fingerprints for the authoritative inputs that govern *this* chapter."""
        from chapter_outline_loader import _find_split_outline_file

        split_file = _find_split_outline_file(self.project_root / "大纲", chapter)
        if split_file is not None:
            outline_text = split_file.read_text(encoding="utf-8")
            prev_file = _find_split_outline_file(self.project_root / "大纲", chapter - 1) if chapter > 1 else None
            prev_text = prev_file.read_text(encoding="utf-8") if prev_file is not None else ""
            volume_preamble = ""
        else:
            outline_text = load_chapter_outline(self.project_root, chapter, max_chars=None)
            if outline_text.startswith("⚠️"):
                outline_text = ""
            if chapter > 1:
                prev_text = load_chapter_outline(self.project_root, chapter - 1, max_chars=None)
                if prev_text.startswith("⚠️"):
                    prev_text = ""
            else:
                prev_text = ""
            volume_preamble = self._volume_outline_preamble(chapter)

        outline_fp = hashlib.sha256(outline_text.encode("utf-8")).hexdigest()
        outline_prev_fp = hashlib.sha256(prev_text.encode("utf-8")).hexdigest() if prev_text else "none"
        outline_volume_fp = (
            hashlib.sha256(volume_preamble.encode("utf-8")).hexdigest() if volume_preamble else "none"
        )

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

        # State file: governing planning/state fields only
        state = read_json_if_exists(self.project_root / ".webnovel" / "state.json") or {}
        state_fp = hashlib.sha256(
            json.dumps(
                self._state_fingerprint_payload(chapter, state),
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
        ).hexdigest()

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
            # `outline` is kept as the key name for this chapter's own outline section
            "outline": outline_fp,
            "outline_prev": outline_prev_fp,
            "outline_volume": outline_volume_fp,
            "contracts": contracts_fp,
            "state": state_fp,
            "latest_commit": latest_commit_fp,
        }

    def compute_package_fingerprint(
        self,
        chapter: int,
        creative_brief: Optional[str] = None,
        creative_brief_fingerprint: Optional[str] = None,
        writing_skills_fingerprint: Optional[str] = None,
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
        if writing_skills_fingerprint:
            payload["writing_skills_fingerprint"] = writing_skills_fingerprint
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def _enrich_appearing_characters(
        self,
        entries: List[Dict[str, Any]],
        *,
        ctx_mgr: ContextManager,
        state: Dict[str, Any],
        canon_items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Attach canonical name, entity type and a minimal current state to appearances.

        `appearances` only stores `entity_id` + chapter counts. Rendering that directly made
        every entry fall through to the placeholder `- 角色`. Names come from the entity
        index (the same read-only authority ContextManager uses); state comes from accepted
        canon facts, capped to a few fields so this stays a scene aid, not a character wiki.
        """
        protagonist = state.get("protagonist_state") or {}
        protagonist_id = str(protagonist.get("entity_id") or "").strip() if isinstance(protagonist, dict) else ""
        entries = list(entries or [])
        if protagonist_id and not any(
            isinstance(entry, dict) and str(entry.get("entity_id") or "") == protagonist_id
            for entry in entries
        ):
            # Appearances are grouped and ordered by recency only, so the protagonist can
            # fall off the limit on a tie. The Writer must always get the POV character.
            entries.insert(0, {"entity_id": protagonist_id})
        if not entries:
            return []
        entity_state = state.get("entity_state") or {}
        state_by_entity: Dict[str, Dict[str, Any]] = {
            str(key): value for key, value in entity_state.items() if isinstance(value, dict)
        }
        if isinstance(protagonist, dict) and protagonist.get("entity_id"):
            state_by_entity.setdefault(str(protagonist["entity_id"]), protagonist)

        facts_by_entity: Dict[str, Dict[str, Any]] = {}
        for item in canon_items:
            content = item.get("content") if isinstance(item, dict) else None
            if not isinstance(content, dict):
                continue
            entity_id = str(content.get("entity_id") or "")
            field = str(content.get("field") or "")
            if not entity_id or not field:
                continue
            chapter = item.get("chapter") or 0
            bucket = facts_by_entity.setdefault(entity_id, {})
            existing = bucket.get(field)
            if existing is None or int(chapter) >= int(existing.get("chapter") or 0):
                bucket[field] = {
                    "value": content.get("value"),
                    "chapter": chapter,
                }

        priority = (
            "location.current",
            "current_status",
            "status",
            "stance",
            "decision",
            "known_evidence",
            "inventory_status",
            "procedure_compliance",
            "role",
            "tier",
        )

        def _flatten(prefix: str, value: Any, out: Dict[str, Any]) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    _flatten(f"{prefix}.{key}" if prefix else str(key), nested, out)
            elif value not in (None, "", [], {}):
                out[prefix] = value

        def _rank(field: str) -> int:
            for index, wanted in enumerate(priority):
                if field == wanted or field.startswith(f"{wanted}."):
                    return index
            return len(priority)

        enriched: List[Dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entity_id = str(entry.get("entity_id") or entry.get("id") or "").strip()
            if not entity_id:
                continue
            try:
                entity = ctx_mgr.index_manager.get_entity(entity_id) or {}
            except Exception:
                entity = {}

            name = str(entity.get("canonical_name") or entity.get("name") or "").strip()
            if not name:
                local_state = state_by_entity.get(entity_id) or {}
                name = str(local_state.get("name") or "").strip()
            if not name and str(protagonist.get("entity_id") or "") == entity_id:
                name = str(protagonist.get("name") or "").strip()

            entity_type = str(entity.get("type") or "").strip()
            row: Dict[str, Any] = {
                "entity_id": entity_id,
                "name": name or entity_id,
                "type": entity_type,
                "last_chapter": entry.get("last_chapter"),
                "total": entry.get("total"),
            }
            if entity_type == "角色" or not entity_type:
                facts = dict(facts_by_entity.get(entity_id) or {})
                flat_state: Dict[str, Any] = {}
                _flatten("", state_by_entity.get(entity_id) or {}, flat_state)
                for field, value in flat_state.items():
                    facts.setdefault(field, {"value": value, "chapter": None})
                ordered = sorted(facts.items(), key=lambda kv: (_rank(kv[0]), str(kv[0])))
                row["state"] = [
                    {"field": field, "value": str(meta.get("value"))[:180]}
                    for field, meta in ordered[:3]
                    if str(meta.get("value") or "").strip()
                ]
            enriched.append(row)
        return enriched

    def get_governed_context(self, chapter: int, max_chars: Optional[int] = None) -> dict[str, Any]:
        """
        Extract governed factual context assembled by ContextManager.
        Consumed by Context Agent for creative planning without parallel authority querying.
        """
        self._ensure_story_contracts(chapter)
        source_fps = self.compute_source_fingerprints(chapter)

        cfg = DataModulesConfig.from_project_root(self.project_root)
        effective_max_chars = max_chars if max_chars is not None else cfg.context_max_chars
        ctx_mgr = ContextManager(cfg)
        native_ctx = ctx_mgr.build_context(chapter, max_chars=effective_max_chars)

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

        # 章节规划字段以章纲为唯一权威；state.json 里的 chapter_meta 只是派生副本。
        # Writer 与 Reviewer 都从这份 effective intent 取值，保证二者看到同一版本规划。
        chapter_meta, intent_provenance = effective_chapter_meta(self.project_root, chapter, state)
        progress_obligation = derive_chapter_progress_obligation(
            chapter=chapter,
            directive=merged_directive,
            chapter_meta=chapter_meta,
            outline=str(core.get("chapter_outline") or ""),
        )
        current_intent = {
            "chapter": chapter,
            # ContextManager caps its compatibility copy of the outline (1,500 chars), so
            # read the chapter's own outline in full here. The Writer prompt parses this;
            # using the capped copy silently reintroduced the truncation this package is
            # supposed to remove.
            "outline": load_chapter_outline(self.project_root, chapter, max_chars=None)
            or core.get("chapter_outline")
            or "",
            "directive": merged_directive,
            "plot_structure": plot_structure,
            "chapter_brief": chapter_contract.get("override_allowed") or {},
            "chapter_meta": chapter_meta,
            "chapter_meta_provenance": intent_provenance,
            "intent_items": intent_items,
            "progress_obligation": progress_obligation,
        }

        raw_canon = native_ctx.get("canon") or []
        canon_items = [
            item.to_dict() if hasattr(item, "to_dict") else (dict(item) if isinstance(item, dict) else {"content": str(item)})
            for item in raw_canon
        ]
        scene = native_ctx.get("scene") or {}
        snapshot = dict((native_ctx.get("meta") or {}).get("context_snapshot") or {})
        proj_entities = read_json_if_exists(self.project_root / ".story-system" / "projections" / "entities.json") or {}
        # proj_entities is stored in governed_canon["entities"]. snapshot["entities"] is omitted to avoid duplicate bloat.

        governed_canon = {
            "canon_items": canon_items,
            "appearing_characters": self._enrich_appearing_characters(
                scene.get("appearing_characters") or [],
                ctx_mgr=ctx_mgr,
                state=state,
                canon_items=canon_items,
            ),
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
            "genre_profile": native_ctx.get("genre_profile") or {},
            "story_craft": state.get("story_craft") or {},
        }

        raw_ref = native_ctx.get("reference") or []
        ref_items = [
            item.to_dict() if hasattr(item, "to_dict") else (dict(item) if isinstance(item, dict) else {"content": str(item)})
            for item in raw_ref
        ]
        urgent_loops = list(native_ctx.get("urgent_loops") or [])

        writer_context = {
            "reference": ref_items,
            "recent_summaries": core.get("recent_summaries") or [],
            "recent_meta": core.get("recent_meta") or [],
            "urgent_loops": urgent_loops,
            "volume_goal": volume_contract.get("volume_goal") or {},
            "selected_tropes": volume_contract.get("selected_tropes") or [],
            "must_check_nodes": review_contract.get("must_check") or [],
            "reader_signal": native_ctx.get("reader_signal") or {},
            "context_diagnostics": native_ctx.get("context_diagnostics") or [],
            "context_contract_version": (native_ctx.get("meta") or {}).get("context_contract_version") or "v3",
            "voice_target": self.get_voice_target(chapter, genre=story_identity.get("genre")).to_dict(),
        }
        context_budget = (native_ctx.get("meta") or {}).get("context_budget")
        if context_budget:
            writer_context["context_budget"] = context_budget

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
                "chapter_intent_authority": intent_provenance["authority"],
                "chapter_intent_outline_digest": intent_provenance["outline_digest"],
                "chapter_intent_drift": intent_provenance["drift"],
                "context_budget": context_budget,
            },
        }

    def get_writer_package(
        self,
        chapter: int,
        creative_brief: Optional[str] = None,
        max_chars: Optional[int] = None,
        writing_skills: Optional[List[Dict[str, Any]]] = None,
    ) -> WriterPackage:
        """
        Assemble and return the stable Native Writer Package for the specified chapter.
        Guarantees:
        - current chapter intent is present
        - accepted past Canon is present
        - future chapter intent is strictly absent
        - reuses native ContextManager as the single factual authority
        - seals creative planning brief when provided (e.g. from Context Agent)
        - seals the router's writing-skill selection when provided (provenance only; the
          Writer sees the translated chapter guidance, not the skill identities)
        - computes deterministic package fingerprint over source, brief and skill fingerprints
        """
        gov_ctx = self.get_governed_context(chapter, max_chars=max_chars)
        source_fps = gov_ctx["source_fingerprints"]
        story_identity = gov_ctx["story_identity"]
        current_intent = gov_ctx["current_intent"]
        governed_canon = gov_ctx["governed_canon"]
        constraints = gov_ctx["constraints"]
        writer_context = gov_ctx["writer_context"]

        final_brief = str(creative_brief or "").strip()
        brief_chars = count_brief_chars(final_brief)
        if final_brief and brief_chars > MAX_CREATIVE_BRIEF_CHARS:
            raise ValueError(
                f"Creative Brief 超出硬上限：{brief_chars} 字 > {MAX_CREATIVE_BRIEF_CHARS} 字。"
                "请让 Context Agent 压缩后重新封包；不要截断或改写关键事实"
                "（数字、方向、时间、因果由 Writer Package 的受保护区域承载）。"
            )
        brief_fp = hashlib.sha256(final_brief.encode("utf-8")).hexdigest() if final_brief else ""

        sealed_skills: List[Dict[str, Any]] = []
        for item in writing_skills or []:
            if not isinstance(item, dict):
                continue
            skill_id = str(item.get("id") or "").strip()
            guidance = str(item.get("chapter_guidance") or "").strip()
            if not skill_id or not guidance:
                continue
            sealed = {
                "id": skill_id,
                "chapter_guidance": guidance,
                "reason": str(item.get("reason") or "").strip(),
            }
            # The skill's own principles and examples travel with the sealed selection;
            # they are what the Writer reads, so they must be inside the fingerprint.
            for key in ("name", "principle", "example", "anti_example"):
                value = str(item.get(key) or "").strip()
                if value:
                    sealed[key] = value
            sealed_skills.append(sealed)
        skills_fp = selection_fingerprint(sealed_skills) if sealed_skills else ""

        package_fp = self.compute_package_fingerprint(
            chapter,
            creative_brief=final_brief,
            creative_brief_fingerprint=brief_fp,
            writing_skills_fingerprint=skills_fp,
        )

        meta = {
            "schema_version": "runtime-api/v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "native_context_authority": "ContextManager.build_context",
            "creative_planning_authority": "ContextAgent" if final_brief else "none",
            "is_writer_ready": bool(final_brief),
            "creative_brief_chars": brief_chars,
            "creative_brief_limit": MAX_CREATIVE_BRIEF_CHARS,
            "writing_skill_ids": [item["id"] for item in sealed_skills],
            "writing_skills_fingerprint": skills_fp,
            "context_budget": writer_context.get("context_budget"),
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
            writing_skills=sealed_skills,
            writing_skills_fingerprint=skills_fp,
            meta=meta,
        )

        # Record active package in runtime storage
        runtime_dir = self._chapter_runtime_dir(chapter)
        (runtime_dir / "writer_package.json").write_text(package.to_json(), encoding="utf-8")
        return package

    def attach_creative_brief(
        self,
        chapter: int,
        creative_brief: str,
        writing_skills: Optional[List[Dict[str, Any]]] = None,
    ) -> WriterPackage:
        """Attach an authentic creative brief from Context Agent and seal the Native Writer Package."""
        if not creative_brief or not str(creative_brief).strip():
            raise ValueError("creative_brief must be a non-empty string to seal writer package")
        return self.get_writer_package(
            chapter=chapter,
            creative_brief=str(creative_brief).strip(),
            writing_skills=writing_skills,
        )

    def _auto_revision_budget_path(self, chapter: int) -> Path:
        return self._chapter_runtime_dir(chapter) / "auto_revision_budget.json"

    def _auto_revision_budget(self, chapter: int, enforce: bool) -> dict[str, Any]:
        """Count automatic review rounds for `chapter` and enforce the Step-4 budget.

        The counter is kept by this command rather than derived from bound reviews:
        `review-pipeline` is a separate step the orchestrator can skip, and in the
        2026-10-21 chapter-4 run it was skipped for two of four rounds — so a
        derived count would have under-counted exactly when the budget was being
        exceeded. Only calls that opt in (`enforce=True`, the automatic write loops)
        advance the counter, so a human re-running /webnovel-review or
        /webnovel-revise does not consume the automatic budget.
        """
        path = self._auto_revision_budget_path(chapter)
        stored = read_json_if_exists(path) or {}
        used = int(stored.get("rounds_used") or 0)

        if enforce:
            round_number = used + 1
            exhausted = round_number > AUTO_REVISION_MAX_ROUNDS
            budget = {
                "enforced": True,
                "max_rounds": AUTO_REVISION_MAX_ROUNDS,
                "rounds_used": used if exhausted else round_number,
                "round_being_requested": round_number,
                "rounds_remaining": max(0, AUTO_REVISION_MAX_ROUNDS - round_number),
                "exhausted": exhausted,
            }
            if exhausted:
                return budget
            from security_utils import atomic_write_json

            atomic_write_json(
                path,
                {
                    "schema_version": AUTO_REVISION_BUDGET_SCHEMA,
                    "chapter": chapter,
                    "rounds_used": round_number,
                    "max_rounds": AUTO_REVISION_MAX_ROUNDS,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                backup=False,
            )
            return budget

        return {
            "enforced": False,
            "max_rounds": AUTO_REVISION_MAX_ROUNDS,
            "rounds_used": used,
            "round_being_requested": used + 1,
            "rounds_remaining": max(0, AUTO_REVISION_MAX_ROUNDS - used),
            "exhausted": used >= AUTO_REVISION_MAX_ROUNDS,
        }

    def get_reviewer_context(
        self,
        chapter: int,
        max_chars: Optional[int] = None,
        enforce_auto_budget: bool = False,
    ) -> dict[str, Any]:
        """
        Assemble and return governed context specifically needed for chapter review.
        Delivers:
        1. 事实权威 (canon_authority): 用于事实一致性检查的受治理事实与状态账本
        2. 创作意图 (creative_intent): goal, must_cover_nodes, forbidden_zones, core_event, hook, hook_type, progress_obligation
        3. 工艺建议 (craft_constraints / advisory_constraints): 启发式故事工艺与写作指引（advisory-only，不得作为阻断门禁）
        4. 本章规划信息 (chapter_planning): chapter_meta, plot_structure, forbidden_zones, must_check_nodes, blocking_rules（审查意图偏差与规划执行，不作为预授权硬门禁）
        5. 审查合同 (review_contract): 原始章级审查合同
        6. 收敛上下文 (convergence_context): 上轮审查问题跟踪与 closure 核验（Issue #50 task C）
        """
        # Fail fast: an over-budget automatic review must not pay for (or produce) a context.
        auto_revision_budget = self._auto_revision_budget(chapter, enforce=enforce_auto_budget)
        if enforce_auto_budget and auto_revision_budget["exhausted"]:
            raise AutoRevisionBudgetExhausted(chapter, auto_revision_budget)

        gov = self.get_governed_context(chapter, max_chars=max_chars)
        contracts = load_runtime_sources(self.project_root, chapter).contracts
        review_contract = contracts.get("review") or read_json_if_exists(self.paths.review_json(chapter)) or {}

        intent = gov["current_intent"]
        constraints = gov["constraints"]
        ch_meta = intent.get("chapter_meta") or {}
        governed_canon = gov.get("governed_canon") or {}

        forbidden_zones = list(intent.get("directive", {}).get("forbidden_zones", []))
        blocking_rules = list(review_contract.get("blocking_rules", []))

        advisory_constraints = {
            "story_craft": constraints.get("story_craft", {}),
            "writing_guidance": constraints.get("writing_guidance", {}),
            "anti_patterns": list(constraints.get("anti_patterns", [])),
            "policy": "ADVISORY_ONLY: Craft and methodology heuristics must not be treated as blocking gates.",
        }

        # Convergence context for re-review (Issue #50 task C)
        runtime_dir = self._chapter_runtime_dir(chapter)
        prev_review = None
        prev_review_status = "no_previous_review"
        for cand in (
            runtime_dir / "last_review.json",
            self.project_root / ".webnovel" / "tmp" / "review_results.json",
        ):
            if not cand.is_file():
                continue
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                prev_review_status = f"unreadable:{cand.name}:{exc}"
                continue
            if isinstance(data, dict) and int(data.get("chapter", 0)) == chapter:
                prev_review = data
                prev_review_status = "loaded"
                break
            prev_review_status = f"chapter_mismatch:{cand.name}"

        convergence_context: dict[str, Any]
        if prev_review and isinstance(prev_review.get("issues"), list):
            prev_issues = prev_review.get("issues") or []
            hi_crit = [
                {
                    "category": i.get("category"),
                    "severity": i.get("severity"),
                    "location": i.get("location"),
                    "description": i.get("description"),
                    "fix_hint": i.get("fix_hint"),
                }
                for i in prev_issues
                if isinstance(i, dict) and i.get("severity") in ("high", "critical")
            ]
            convergence_context = {
                "has_previous_review": True,
                "previous_review_status": prev_review_status,
                "previous_draft_id": prev_review.get("draft_id"),
                "previous_draft_fingerprint": prev_review.get("draft_fingerprint"),
                "previous_finding_count": len(prev_issues),
                "previous_findings": [
                    {
                        "category": i.get("category"),
                        "severity": i.get("severity"),
                        "location": i.get("location"),
                        "description": i.get("description"),
                        "fix_hint": i.get("fix_hint"),
                    }
                    for i in prev_issues
                    if isinstance(i, dict)
                ],
                "high_or_critical_findings": hi_crit,
                "instruction": (
                    "这是上一轮草稿的审查问题列表。本次审查仍须从头独立检查全部 8 个维度并可提出全新问题；"
                    "同时请重点核验上一轮 high/critical 问题在当前草稿中是否已得到明确解决 (closure)。"
                ),
            }
        else:
            convergence_context = {
                "has_previous_review": False,
                "previous_review_status": prev_review_status,
                "previous_finding_count": 0,
                "previous_findings": [],
                "high_or_critical_findings": [],
                "instruction": "这是本章的首次审查，请从头完整独立检查全部 8 个维度。",
            }

        return {
            "chapter": chapter,
            "canon_authority": governed_canon,
            "creative_intent": {
                "goal": intent.get("directive", {}).get("goal", ""),
                "must_cover_nodes": list(intent.get("directive", {}).get("must_cover_nodes", [])),
                "forbidden_zones": forbidden_zones,
                "core_event": ch_meta.get("core_event", ""),
                "hook": ch_meta.get("hook", ""),
                "hook_type": ch_meta.get("hook_type", ""),
                "progress_obligation": intent.get("progress_obligation") or {},
            },
            "craft_constraints": {
                "core_tone": constraints.get("core_tone", ""),
                "prohibitions": list(constraints.get("prohibitions", [])),
                "mandatory_nodes": list(constraints.get("mandatory_nodes", [])),
                "anti_patterns": list(constraints.get("anti_patterns", [])),
                "story_craft": constraints.get("story_craft", {}),
                "writing_guidance": constraints.get("writing_guidance", {}),
            },
            "advisory_constraints": advisory_constraints,
            "chapter_planning": {
                "chapter_meta": ch_meta,
                "plot_structure": intent.get("plot_structure", {}),
                "forbidden_zones": forbidden_zones,
                "must_check_nodes": list(review_contract.get("must_check", [])),
                "blocking_rules": blocking_rules,
            },
            "review_contract": review_contract,
            "convergence_context": convergence_context,
            "auto_revision_budget": auto_revision_budget,
        }

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
        saved_skills_fp = str(saved_pkg.get("writing_skills_fingerprint") or "")
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
            writing_skills_fingerprint=saved_skills_fp,
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
        # Review validity is a function of the prose the Reviewer reads, not of the whole
        # working draft: a `<chapter_changes>` reconciliation fix changes `draft_fingerprint`
        # without changing a single reviewed character. Both hashes are recorded — the full
        # one as artifact provenance, this one as the review subject.
        review_subject_fp = prose_subject_sha256(prose)
        created_at = datetime.now(timezone.utc).isoformat()

        draft_payload = {
            "draft_id": draft_id,
            "chapter": chapter,
            "package_fingerprint": package_fingerprint,
            "package_brief_fingerprint": saved_brief_fp,
            "is_writer_ready": True,
            "draft_fingerprint": draft_fp,
            "review_subject_fingerprint": review_subject_fp,
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
            review_subject_fingerprint=review_subject_fp,
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
        draft_subject_fp = None
        if draft_file.is_file():
            draft_data = read_json_if_exists(draft_file) or {}
            draft_status = "ingested"
            draft_id = draft_data.get("draft_id")
            draft_fp = draft_data.get("draft_fingerprint")
            draft_subject_fp = draft_data.get("review_subject_fingerprint") or prose_subject_sha256(
                str(draft_data.get("prose") or "")
            )

        has_pkg = pkg_file.is_file()
        is_stale = False
        pkg_fp = None
        skill_ids: List[str] = []
        skills_fp = ""
        if has_pkg:
            pkg_data = read_json_if_exists(pkg_file) or {}
            pkg_fp = pkg_data.get("package_fingerprint")
            saved_brief_fp = str(pkg_data.get("creative_brief_fingerprint") or "")
            saved_skills_fp = str(pkg_data.get("writing_skills_fingerprint") or "")
            skills_fp = saved_skills_fp
            skill_ids = [
                str(item.get("id"))
                for item in (pkg_data.get("writing_skills") or [])
                if isinstance(item, dict) and item.get("id")
            ]
            current_fp = self.compute_package_fingerprint(
                chapter,
                creative_brief_fingerprint=saved_brief_fp,
                writing_skills_fingerprint=saved_skills_fp,
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
            review_subject_fingerprint=draft_subject_fp,
            has_writer_package=has_pkg,
            is_writer_package_stale=is_stale,
            package_fingerprint=pkg_fp,
            writing_skill_ids=skill_ids,
            writing_skills_fingerprint=skills_fp,
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
            saved_skills_fp = str(saved_pkg.get("writing_skills_fingerprint") or "")
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
                writing_skills_fingerprint=saved_skills_fp,
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
                saved_skills_fp = ""
                if pkg_file.is_file():
                    saved_pkg = read_json_if_exists(pkg_file) or {}
                    saved_brief_fp = str(saved_pkg.get("creative_brief_fingerprint") or "")
                    saved_skills_fp = str(saved_pkg.get("writing_skills_fingerprint") or "")
                current_fp = self.compute_package_fingerprint(
                    chapter,
                    creative_brief_fingerprint=saved_brief_fp,
                    writing_skills_fingerprint=saved_skills_fp,
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

        # 3.5 Review <-> draft identity consistency.
        #
        # A review result that declares what it reviewed must be about the prose being
        # committed. Without this, a review produced for an earlier draft version could be
        # replayed against a newer one — the exact "旧审查被静默用于新草稿" failure mode.
        #
        # The binding key is the *review subject* (prose with the `<chapter_changes>`
        # container removed), because that is what the Reviewer read. A reconciliation fix to
        # the proposal block changes the full draft hash without changing one reviewed
        # character; re-running the Reviewer for that was pure waste (836 s over three
        # chapters). The full-draft hash and draft_id are still compared whenever the review
        # does not declare a subject fingerprint, so nothing is silently loosened for older
        # review artifacts. Reviews that declare nothing keep working (the field is optional
        # for compatibility), but a *declared contradiction* is a hard reject.
        if isinstance(rev, dict):
            declared_fp = str(rev.get("draft_fingerprint") or "").strip()
            declared_subject_fp = str(rev.get("review_subject_fingerprint") or "").strip()
            declared_id = str(rev.get("draft_id") or "").strip()
            actual_fp = hashlib.sha256(str(resolved_prose).encode("utf-8")).hexdigest()
            actual_subject_fp = prose_subject_sha256(str(resolved_prose))
            mismatches: list[str] = []
            if declared_subject_fp:
                # Subject-bound review: the prose is the contract. draft_id is allowed to
                # differ because re-ingesting an unchanged prose legitimately mints a new id.
                if declared_subject_fp != actual_subject_fp:
                    mismatches.append(
                        "review_subject_fingerprint "
                        f"declared={declared_subject_fp[:12]} actual={actual_subject_fp[:12]}"
                    )
            else:
                if declared_fp and declared_fp != actual_fp:
                    mismatches.append(
                        f"draft_fingerprint declared={declared_fp[:12]} actual={actual_fp[:12]}"
                    )
                if declared_id and draft_id and declared_id != str(draft_id):
                    mismatches.append(f"draft_id declared={declared_id} committing={draft_id}")
            if mismatches:
                return ChapterCommitOutcomeResult(
                    ok=False,
                    chapter=chapter,
                    action="reject",
                    attempt_id=f"reviewdraft-{uuid.uuid4().hex[:8]}",
                    chapter_outcome="rejected",
                    gate_decision_ref="",
                    durable_commit_persisted=False,
                    projection_status={},
                    projection_success=False,
                    can_retry_projection=False,
                    error_code="REVIEW_DRAFT_MISMATCH",
                    error=(
                        "Cannot commit: review_result 声明的草稿身份与本次提交的草稿不一致（"
                        + "; ".join(mismatches)
                        + "）。必须对新草稿重新运行 Reviewer。"
                    ),
                    next_required_action="rerun_reviewer",
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
        accepted_prose_sha = provenance.get("reconciliation_prose_sha256")
        if not accepted_prose_sha:
            raise RuntimeError(
                f"Cannot publish draft for chapter {chapter}: Durable commit missing provenance.reconciliation_prose_sha256."
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

        # Extract prose-only by parsing and removing the mandatory CHANGES proposal
        from data_modules.reconciliation import split_chapter_and_changes
        try:
            clean_prose, _ = split_chapter_and_changes(prose)
        except Exception as exc:
            raise RuntimeError(
                f"Cannot publish draft for chapter {chapter}: invalid or missing CHANGES container in staged draft: {exc}"
            ) from exc

        if not clean_prose.strip():
            raise RuntimeError(f"Cannot publish draft for chapter {chapter}: Published prose is empty after stripping protocol blocks.")

        if "<chapter_changes>" in clean_prose or "</chapter_changes>" in clean_prose:
            raise RuntimeError(
                f"Cannot publish draft for chapter {chapter}: Published prose still contains internal protocol tags."
            )

        actual_prose_sha = hashlib.sha256(clean_prose.encode("utf-8")).hexdigest()
        if actual_prose_sha != accepted_prose_sha:
            raise RuntimeError(
                f"Cannot publish draft for chapter {chapter}: ACCEPTED_PROSE_MISMATCH "
                f"(published prose SHA-256 '{actual_prose_sha}' does not match accepted commit reconciliation_prose_sha256 '{accepted_prose_sha}')."
            )

        from chapter_paths import default_chapter_draft_path
        target_file = default_chapter_draft_path(self.project_root, chapter)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(clean_prose, encoding="utf-8")
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

