#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Literary subtraction finalizer: prompt assembly + deterministic guards.

The five editing principles and the three guards below are the ones frozen and held
out in `experiments/jarvis-literary-heldout-20261107` (PR #67). This module puts
that verified pass on the formal writing path. It adds no agent, router, database,
state system, literary score, or new semantic-classification framework:

* the editing call is made by the host model through the skill;
* fact safety reuses `compare_semantic_facts` / the existing host judge;
* the only new deterministic layer is the acceptance guard the experiment already
  used (length floor, numbers/dates/codes, protected terms).

Core rule: 删解释，不删承载解释的东西。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .prose_quality_gate import evaluate_prose_quality_and_decide
from .prose_semantic_diff import (
    SemanticDiffOutcome,
    SemanticDiffResult,
    compare_semantic_facts,
)
from .reconciliation import prose_only_text

FINALIZER_VERSION = "literary-subtraction-v2"

# The judge may only wave a change through when it explicitly tagged it as discourse-layer
# compression. Anything else (missing/UNKNOWN impact, deterministic claim/ownership diff,
# judge error, UNCERTAIN) stays blocking: fail-closed.
DISCOURSE_EVIDENCE_TYPE = "semantic_judge_discourse"

# Even if the judge tags one of these as DISCOURSE, the finalizer refuses it. These are
# object-level facts that a single mis-tag must never be able to change silently.
# Dimensions that are context-dependent (event_outcome / location_or_state / clue /
# causality) are left to the judge's rubric: deleting a summary of an event that is
# still shown in the retained action, or reordering the same actions, is compression,
# not a state change, and a blanket dimension block would recreate the old false rollback.
STORY_STATE_DIMENSIONS = frozenset({"ownership", "world_rule"})

# The five duties, verbatim from the held-out experiment prompt (PR #67).
FIVE_PRINCIPLES = """【只做这五条】
1. **删掉叙述者对刚发生的动作或对白的意义总结。**
   典型形态：“他听懂了”“这说明……”“不问比问更压人”“不是怕，是烦”“昨天是防备一个生人，今天是辨认一个对手”。
   动作、对白和未解问题已经能让读者得出这个判断时，删掉总结句。每章最多保留一处真正必要的内心判断。

2. **对白已经说清的信息，叙述者不再翻译。**
   把“林越听懂了。放在网上的东西……”这类翻译段删掉，或改成人物的一句短回应、一个手上的动作。不新增对白信息。

3. **同一信息在章内被反复转述时，只留一处。**
   删掉“总结—再总结”的段落，以及章末把线索逐条复盘的清单式收束。保留信息第一次出现的位置，或保留一个未解问题，不同时保留两者。

4. **章末收在已有的具体动作、画面或新消息上。**
   不收在“他明白了 / 他得去查……”的总结排比上。若原文最后已经有一个动作或画面，删掉它前面的总结段，让那个动作或画面自己落地。

5. **用原文已有的时间限制、身体限制、被发现的危险来组织段落。**
   把静态问答改成带动作节拍的对话：递纸、关门、收拾工具、换姿势、看表。只使用原文已有的动作和物件；不新增会改变信息状态的动作、道具或场景。"""

# The three guards, verbatim from the held-out experiment prompt (PR #67).
THREE_GUARDS = """【三条护栏（硬约束，优先于精简）】
1. **保护推进信息。** 不得删除：明确的下一步动作、下一步调查方向、时间/地点硬限制、章末钩子、影响后续行动选择的信息。可以删这些信息前后的解释性总结，但不能删信息本身。
2. **保护必要推理连接。** 对于“具体数字 / 物件 / 证据 → 角色得出的关键结论”，如果该结论不是读者可以立即、唯一推出的，必须保留连接句。允许压缩措辞，不允许整段删除。
3. **长度硬约束。** 修订稿不得低于原文正文的 90%；低于 90% 即视为本次编辑失败。不要为了凑长度补写原文没有的内容；宁可保留原句，也不要把场景删空。"""

PROTECTIONS = """【必须保住（比提高更重要）】
- **保住句段自然度**：不要为了简洁把句子压成电报体；不要制造排比、金句、三连短句；长短句照原文的呼吸来。
- **保住场景沉浸**：保留具体的器物、声音、气味、身体动作和空间位置；不要删到只剩对话。过渡段可以收紧，但不能抽空现场。
- **不把正文压成摘要**：不删承担冲突、人物关系、悬念或推理功能的对白和细节。删的只能是不承担这些功能的解释句。
- **不改事实层**：不改任何事件、动作结果、人物知情状态、物品归属、时间地点、数字日期编号、专业术语。术语照抄。
- **不新增**：不新增原文没有的事实、线索、推断结论、人物、场景或对白信息；不提前揭示后文信息。
- **保留标题和段落顺序**：只允许在段内调整句子顺序。

以下内容**不是**“作者解释”，不得删除：
- 独立短钩子（如“明天。”）；
- 承载潜台词的动作（如“乔宁的手没把钥匙推回来”）；
- 简短的情绪落点句；
- 章末的感官句；
- 具体的物件、声音、气味、身体动作、空间位置；
- 明确的下一步动作、调查方向、时间/地点硬约束；
- 必要的“证据 → 结论”推理连接；
- 承担人物关系、冲突、悬念或推理功能的对话。"""

OUTPUT_RULE = """【输出】
只输出修订后的完整正文，从标题开始，到原文最后一段结束。不要写“以下是修订稿”，不要解释改了什么。"""

PROMPT_HEADER = """你是这部长篇小说的文学编辑，负责一章的文学减法定稿。你拿到的是一章已经由 Writer 写出的工作草稿，情节与事实已经成立。你这一次只做一件事：**在不改变故事的前提下，提高阅读吸引力，减少作者替读者解释。**

【本书与本章】
书名：{title}
章节：第{chapter}章
类型：{genre}。第三人称限知。高压、克制，以动作、对话与具体物件推进。"""


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def strip_packaging(text: str) -> str:
    """Remove Zhanghui packaging lines (fingerprint footer) so they are never edited.

    This is the same normalisation the held-out experiment applied before feeding a
    chapter to the editor. It only removes the known packaging forms; prose is untouched.
    """
    text = (text or "").replace("\r\n", "\n")
    text = re.sub(r"(?m)^\s*\*\*封包验证指纹[^\n]*\n?", "", text)
    text = re.sub(r"(?m)^\s*封包验证指纹[^\n]*\n?", "", text)
    text = re.sub(r"(?m)^\s*[0-9a-f]{64}\s*$\n?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def body_prose(text: str) -> str:
    """Whitespace-free prose body: no packaging, no `<chapter_changes>`, no heading line."""
    prose = strip_packaging(prose_only_text(text))
    lines = prose.splitlines()
    if lines and re.match(
        r"^#{0,4}\s*第\s*[0-9零一二三四五六七八九十百千两]+\s*章", lines[0].strip()
    ):
        lines = lines[1:]
    return re.sub(r"\s", "", "\n".join(lines))


def _heading_line(text: str) -> str:
    for line in text.replace("\r\n", "\n").splitlines():
        if line.strip():
            return line.strip()
    return ""


def clean_finalizer_output(raw: str, source: str) -> Tuple[str, Dict[str, Any]]:
    """Normalise a host-model reply into a candidate prose file.

    Mechanical only: strips a code fence / leading meta line, collapses blank runs,
    restores the source heading when the model omitted it, and drops one exact
    duplicated adjacent paragraph. It never edits prose content.
    """
    text = (raw or "").replace("\r\n", "\n").strip()
    text = re.sub(r"^```(?:markdown|md)?\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    lines = text.splitlines()
    while lines and re.match(r"^(以下是|修订稿|定稿|【修订|---+\s*$|好的[，,])", lines[0].strip()):
        lines.pop(0)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines).strip()).strip()

    notes: Dict[str, Any] = {"heading_prepended": False, "dedup_removed_chars": 0}
    heading = _heading_line(source)
    if heading and not text.startswith(heading):
        text = heading + "\n\n" + text
        notes["heading_prepended"] = True

    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(parts) >= 3 and parts[1] == parts[2] and len(parts[1]) > 20:
        notes["dedup_removed_chars"] = len(parts[2])
        parts.pop(2)
    return strip_packaging("\n\n".join(parts).strip()), notes


# --------------------------------------------------------------------------- #
# Fact tokens (set comparison, not occurrence counts)
# --------------------------------------------------------------------------- #


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def _codes(text: str) -> set[str]:
    return set(re.findall(r"\b[A-Za-z]{1,5}[-–]?\d+[A-Za-z0-9-]*\b", text))


def _dates(text: str) -> set[str]:
    patterns = (
        r"\d{4}\s*[年./-]\s*\d{1,2}(?:\s*[月./-]\s*\d{1,2}\s*日?)?",
        r"[一二三四五六七八九十]{1,3}\s*月\s*[一二三四五六七八九十]{1,3}\s*日",
        r"\d{1,2}\s*/\s*\d{1,2}",
    )
    found: set[str] = set()
    for pattern in patterns:
        found.update(re.findall(pattern, text))
    return found


def fact_tokens(text: str) -> Dict[str, set[str]]:
    return {"numbers": _numbers(text), "dates": _dates(text), "codes": _codes(text)}


# --------------------------------------------------------------------------- #
# Prompt assembly
# --------------------------------------------------------------------------- #


def outline_field(outline: str, label: str) -> str:
    match = re.search(rf"(?m)^\s*-\s*{re.escape(label)}[：:]\s*(.+?)\s*$", outline)
    return match.group(1).strip() if match else ""


def build_constraints(ctx: Dict[str, Any]) -> str:
    """Assemble the hard-limit list from an existing governed-context payload."""
    intent = (ctx or {}).get("current_intent") or {}
    outline = str(intent.get("outline") or "").strip()
    directive = intent.get("directive") or {}
    goal = directive.get("goal") or outline_field(outline, "目标")
    forbidden = directive.get("forbidden_zones") or []
    end_question = directive.get("chapter_end_open_question") or outline_field(
        outline, "章末未闭合问题"
    )
    key_change = outline_field(outline, "关键变化")
    system = ((ctx or {}).get("constraints") or {}).get("system_constraints") or []

    lines = [
        "# 本章硬限制清单（生成前冻结，不可删除、不可写反）",
        "",
        "## 本章目标（结果不得改变）",
        f"- {goal}" if goal else "- （outline 未单列目标；按本章 outline 执行）",
        "",
        "## 本章必须发生的推进",
        "- 本章结束前，与目标直接相关的核心状态必须发生实质变化；"
        "不得只以“准备做某事”结束。",
    ]
    if key_change:
        lines.append(f"- 关键变化：{key_change}")
    lines += ["", "## 本章禁区（不得写出，不得提前揭示）"]
    lines += [f"- {z}" for z in forbidden] if forbidden else ["- （无额外禁区）"]
    lines += [
        "",
        "## 章末未闭合问题（不得提前关闭）",
        f"- {end_question}" if end_question else "- 无",
        "",
        "## 系统约束",
    ]
    lines += [f"- {s}" for s in system] if system else ["- 无"]
    lines += [
        "",
        "## 事实层保护（硬）",
        "- 不得改动原文写出的数字、日期、编号、专业术语、事件结果、人物知情状态、"
        "物品归属、时间与地点。",
        "- 不得删除原文中明确的下一步动作、下一步调查方向、时间/地点硬限制、章末钩子、"
        "影响后续行动选择的信息。可以删它们前后的解释性总结，但不能删信息本身。",
        "- 对于“具体数字/物件/证据 → 角色得出的关键结论”，如果该结论不是读者可以立即、"
        "唯一推出的，必须保留连接句；允许压缩措辞，不允许整段删除。",
    ]
    return "\n".join(lines).strip() + "\n"


def first_sentences(text: str, limit: int = 2) -> str:
    """First one or two sentences of a next-chapter opening/outline (hook context only)."""
    lines = [ln.strip() for ln in (text or "").replace("\r\n", "\n").splitlines() if ln.strip()]
    if lines and re.match(r"^#{0,4}\s*第\s*[0-9零一二三四五六七八九十百千两]+\s*章", lines[0]):
        lines = lines[1:]
    lines = [ln for ln in lines if not ln.startswith("#")]
    if not lines:
        return ""
    first = lines[0]
    parts = re.split(r"(?<=[。！？])", first)
    picked = "".join(parts[:limit]).strip()
    return picked or first.strip()


def build_finalizer_prompt(
    *,
    source: str,
    outline: str,
    constraints: str,
    next_opening: str = "",
    voice_target: str = "",
    title: str = "",
    chapter: int = 0,
    genre: str = "",
) -> str:
    """Build the single literary-subtraction prompt for one chapter."""
    if not (source or "").strip():
        raise ValueError("source prose is empty")
    next_block = (next_opening or "").strip() or (
        "（本章没有可用的下一章开头。章末保护信息请按原文最后一次明确的动作、"
        "新消息或下一步计划判断。）"
    )
    voice_block = (voice_target or "").strip() or "（无额外文风锚；以原文语感为准。）"
    header = PROMPT_HEADER.format(
        title=(title or "（未提供）").strip(),
        chapter=chapter or "（未提供）",
        genre=(genre or "（未提供）").strip(),
    )
    sections = [
        header,
        "",
        "【本章意图（不可偏离）】",
        (outline or "").strip() or "（未提供）",
        "",
        "【本章硬限制清单（不可删除、不可写反）】",
        (constraints or "").strip() or "（未提供）",
        "",
        "【人物与文风锚（只学语气与叙事距离，不引入其中任何事实）】",
        voice_block,
        "",
        "【下一章开头（只用于判断本章章末哪些信息承担推进功能；不得在正文中引用、解释或提前透露下一章内容）】",
        next_block,
        "",
        FIVE_PRINCIPLES,
        "",
        THREE_GUARDS,
        "",
        PROTECTIONS,
        "",
        OUTPUT_RULE,
        "",
        "【原文】",
        source.strip(),
    ]
    return "\n".join(sections).strip() + "\n"


# --------------------------------------------------------------------------- #
# Acceptance guard
# --------------------------------------------------------------------------- #


@dataclass
class FinalizerDecision:
    accepted: bool
    final_text: str
    reasons: List[str] = field(default_factory=list)
    length_ratio: float = 0.0
    before_body_chars: int = 0
    after_body_chars: int = 0
    missing_numbers: List[str] = field(default_factory=list)
    added_numbers: List[str] = field(default_factory=list)
    missing_dates: List[str] = field(default_factory=list)
    added_dates: List[str] = field(default_factory=list)
    missing_codes: List[str] = field(default_factory=list)
    added_codes: List[str] = field(default_factory=list)
    missing_terms: List[str] = field(default_factory=list)
    semantic_outcome: str = ""
    gate_status: str = ""
    gate_details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "length_ratio": round(self.length_ratio, 4),
            "before_body_chars": self.before_body_chars,
            "after_body_chars": self.after_body_chars,
            "missing_numbers": self.missing_numbers,
            "added_numbers": self.added_numbers,
            "missing_dates": self.missing_dates,
            "added_dates": self.added_dates,
            "missing_codes": self.missing_codes,
            "added_codes": self.added_codes,
            "missing_terms": self.missing_terms,
            "semantic_outcome": self.semantic_outcome,
            "gate_status": self.gate_status,
            "gate_details": self.gate_details,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def _sorted(values: Iterable[str]) -> List[str]:
    return sorted(set(values))


def _blocks_acceptance(item: Any) -> bool:
    """A judge/deterministic finding blocks unless the judge explicitly called it discourse.

    The judge's `DISCOURSE` tag was introduced by the finalizer-only rubric (`--state-impact`).
    Other flows never emit it, so their results are unaffected. Object-level dimensions are
    refused even when tagged DISCOURSE.
    """
    if getattr(item, "evidence_type", "") != DISCOURSE_EVIDENCE_TYPE:
        return True
    return getattr(item, "dimension", "") in STORY_STATE_DIMENSIONS


def decide_finalizer_candidate(
    before_text: str,
    candidate_text: str,
    *,
    chapter: int = 0,
    semantic_judge: Optional[Callable[[str, str], Any]] = None,
    min_length_ratio: float = 0.90,
    protected_terms: Sequence[str] = (),
    raw_draft_text: Optional[str] = None,
) -> FinalizerDecision:
    """Accept or reject a finalizer candidate; on any failure return the Writer raw.

    `before_text` is the prose the editor was shown (packaging/CHANGES removed).
    `raw_draft_text` is the full working draft to preserve on rejection; when omitted,
    `before_text` is returned unchanged. The existing semantic gate is invoked with
    the same before/after pair the host judge was asked about, so binding stays intact.

    Acceptance distinguishes two classes of judge finding:
    * story-state change (event/knowledge/decision/action/ownership/space-time/clue/
      necessary causality, or anything unclassified) -> reject;
    * discourse-layer compression explicitly tagged `DISCOURSE` -> allowed, because the
      story state is unchanged and only the narration stopped re-explaining it.
    """
    fallback_text = before_text if raw_draft_text is None else raw_draft_text
    before_body = body_prose(before_text)
    after_body = body_prose(candidate_text)
    before_chars, after_chars = len(before_body), len(after_body)
    ratio = after_chars / max(1, before_chars)

    decision = FinalizerDecision(
        accepted=False,
        final_text=fallback_text,
        length_ratio=ratio,
        before_body_chars=before_chars,
        after_body_chars=after_chars,
    )

    if before_chars == 0:
        decision.reasons.append("EMPTY_SOURCE：原稿正文为空，无法定稿。")
        return decision
    if after_chars == 0:
        decision.reasons.append("EMPTY_CANDIDATE：定稿候选正文为空，保留原稿。")
        return decision
    if ratio < min_length_ratio:
        decision.reasons.append(
            f"LENGTH_BELOW_FLOOR：定稿正文为原稿的 {ratio:.2%}，低于 {min_length_ratio:.0%} 下限。"
        )
        return decision

    before_tokens = fact_tokens(before_body)
    after_tokens = fact_tokens(after_body)
    decision.missing_numbers = _sorted(before_tokens["numbers"] - after_tokens["numbers"])
    decision.added_numbers = _sorted(after_tokens["numbers"] - before_tokens["numbers"])
    decision.missing_dates = _sorted(before_tokens["dates"] - after_tokens["dates"])
    decision.added_dates = _sorted(after_tokens["dates"] - before_tokens["dates"])
    decision.missing_codes = _sorted(before_tokens["codes"] - after_tokens["codes"])
    decision.added_codes = _sorted(after_tokens["codes"] - before_tokens["codes"])
    if any(
        (
            decision.missing_numbers,
            decision.added_numbers,
            decision.missing_dates,
            decision.added_dates,
            decision.missing_codes,
            decision.added_codes,
        )
    ):
        decision.reasons.append(
            "FACT_TOKEN_CHANGED：数字/日期/编号发生增删改，事实层被触碰，保留原稿。"
        )
        return decision

    decision.missing_terms = [t for t in protected_terms if t and t in before_body and t not in after_body]
    if decision.missing_terms:
        decision.reasons.append("PROTECTED_TERM_MISSING：受保护术语被删除或替换。")
        return decision

    gate_before = strip_packaging(prose_only_text(before_text))
    semantic_res = compare_semantic_facts(
        gate_before, candidate_text, semantic_judge=semantic_judge
    )
    blocking = [d for d in semantic_res.drift_items if _blocks_acceptance(d)]
    allowed = [d for d in semantic_res.drift_items if not _blocks_acceptance(d)]
    discourse_only = (
        semantic_res.outcome == SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED
        and not blocking
    )
    if discourse_only:
        # The judge found only discourse-layer compression. Hand the quality gate a clean
        # semantic result so it does not roll the chapter back for wording alone; the
        # deterministic fact-token / length guards above still apply.
        semantic_res = SemanticDiffResult(
            outcome=SemanticDiffOutcome.STYLE_ONLY_SAFE,
            safe=True,
            drift_items=[],
            confidence=semantic_res.confidence,
            summary="仅删除话语层解释，故事状态未变。",
            before_claims=semantic_res.before_claims,
            after_claims=semantic_res.after_claims,
        )

    gate = evaluate_prose_quality_and_decide(
        before_text=gate_before,
        after_text=candidate_text,
        diagnosis_summary=semantic_res,
        semantic_judge=None,
        max_shrinkage_ratio=max(0.0, 1.0 - min_length_ratio),
    )
    decision.semantic_outcome = gate.semantic_outcome
    decision.gate_status = gate.status
    decision.gate_details = {
        "rollback_reason": gate.rollback_reason,
        "staccato_score": gate.staccato_score,
        "edit_footprint_ratio": gate.edit_footprint_ratio,
        "required_actions": list(gate.required_actions),
        "discourse_only": discourse_only,
        "allowed_changes": [d.to_dict() for d in allowed],
        "blocking_changes": [d.to_dict() for d in blocking],
    }
    if gate.accepted and gate.semantic_outcome == "STYLE_ONLY_SAFE":
        decision.accepted = True
        decision.final_text = candidate_text
        return decision

    decision.reasons.append(
        f"SEMANTIC_GATE_REJECTED：status={gate.status}, semantic_outcome={gate.semantic_outcome}"
        + (f"；{gate.rollback_reason}" if gate.rollback_reason else "")
    )
    return decision
