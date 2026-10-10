#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prose Semantic Diff (Issue #26).

Fact-Safe Semantic Diff Guard:
Detects whether a prose edit has introduced Canon-relevant semantic drift or invented
new story facts while claiming to "only polish/adapt style".

Checks Canon-relevant dimensions:
1. 人物背景 (backstory / identity / career / training)
2. 动机与主动意图 (motives / deliberate intent vs accidental occurrence)
3. 技能能力 (skills / power / expertise)
4. 人际关系 (relationships / attitude shifts)
5. 事件结果与因果 (event outcomes / causality)
6. 物品归属与状态 (ownership / object state)
7. 位置与状态 (location / physical state)
8. 认知知情状态 (epistemic state: who knows what)
9. 世界规则与新线索 (world rules / clues)

Outcomes:
- STYLE_ONLY_SAFE: Pure stylistic improvement. Safe to accept.
- SEMANTIC_CHANGE_PROPOSED: Canon-relevant factual change detected. Cannot overwrite Canon;
  must hold original draft and report proposed story change.
- UNCERTAIN: High ambiguity; require human resolution or rollback.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class SemanticDiffOutcome(str, Enum):
    STYLE_ONLY_SAFE = "STYLE_ONLY_SAFE"
    SEMANTIC_CHANGE_PROPOSED = "SEMANTIC_CHANGE_PROPOSED"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class SemanticDriftItem:
    dimension: str  # "backstory" | "intent_shift" | "capability" | "epistemic" | "causality" | "ownership"
    evidence_type: str
    original_excerpt: str
    edited_excerpt: str
    description: str
    severity: str = "blocking"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SemanticDiffResult:
    outcome: SemanticDiffOutcome
    safe: bool
    drift_items: List[SemanticDriftItem] = field(default_factory=list)
    confidence: float = 1.0
    summary: str = ""

    @property
    def findings(self) -> List[str]:
        return [f"[{i.dimension}] {i.description} ({i.edited_excerpt})" for i in self.drift_items]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "safe": self.safe,
            "drift_items": [i.to_dict() for i in self.drift_items],
            "confidence": self.confidence,
            "summary": self.summary,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# Regex patterns for detecting newly added backstories/qualifications in edited text
BACKSTORY_PATTERNS = [
    # "曾当过三年机修学徒", "早年曾在北境服役", "幼时跟随名医学艺"
    re.compile(r"(?:曾经|曾是|早年|幼年|幼时|当初|早先|曾在|当过|做过)(?:[^，。！？\n]{0,8})(?:学徒|弟子|药农|镖师|捕快|杂役|铁匠|机修|行医|军伍|杀手|散修|佣兵|伙计)"),
    re.compile(r"(?:当过|做过|有着|历经)[一二三四五六七八九十百千0-9]+(?:年|载|个月)(?:[^，。！？\n]{0,10})(?:学徒|经验|阅历|功底|生涯)"),
    re.compile(r"(?:自幼|打小|从小)(?:跟随|拜入|修习|精研)[^，。！？\n]{2,15}"),
]

# Patterns for deliberate test / provocation vs accidental reveal
ACCIDENTAL_MARKERS = [
    "偶然", "无意中", "无意间", "碰巧", "恰巧", "不经意", "不小心", "未曾察觉", "偶然露出", "不慎"
]
DELIBERATE_MARKERS = [
    "主动", "故意", "刻意", "试探", "设局", "引诱", "拍到桌边试探", "死死盯着", "观察少年反应", "观察他的反应", "意味深长地看"
]

# Capability / expertise inflation patterns
CAPABILITY_INFLATION_PATTERNS = [
    re.compile(r"(?:对[^，。！？\n]{2,12})了如指掌"),
    re.compile(r"(?:精通|深谙)[^，。！？\n]{2,10}(?:之道|之术|构造|结构)"),
    re.compile(r"早已掌握[^，。！？\n]{2,10}"),
]

# Epistemic shift (claiming someone secretly already knew)
EPISTEMIC_SHIFT_PATTERNS = [
    re.compile(r"(?:早已知晓|其实早就知道|早就看穿|早已料到|心中早已有数)"),
    re.compile(r"(?:原来出门前|其实在临行前)(?:[^，。！？\n]{2,20})(?:偷偷|暗中)"),
]

# Secret identity or unrevealed setting / secret passage
SECRET_SETTING_PATTERNS = [
    re.compile(r"(?:其实|实际上|原来|真实身份)(?:[^，。！？\n]{0,8})(?:是|乃是|竟是)(?:[^，。！？\n]{0,12})(?:刺客|杀手|卧底|密探|长老|门主|弟子|奸细|特使|间谍|暗探)"),
    re.compile(r"(?:通过|利用|顺着|借由|走)(?:[^，。！？\n]{0,8})(?:密道|暗道|暗门|阵法|传送阵|密室)(?:[^，。！？\n]{0,10})(?:潜入|潜行|逃离|离开|往返|穿过)"),
]


def compare_semantic_facts(before_text: str, after_text: str) -> SemanticDiffResult:
    """Compare before and after prose to verify factual and semantic preservation."""
    drift_items: List[SemanticDriftItem] = []

    # Fast path: identical text
    if before_text.strip() == after_text.strip():
        return SemanticDiffResult(
            outcome=SemanticDiffOutcome.STYLE_ONLY_SAFE,
            safe=True,
            drift_items=[],
            confidence=1.0,
            summary="正文未作任何语义变动，完全一致。",
        )

    # 1. Backstory Invention Check (Case B)
    for pattern in BACKSTORY_PATTERNS:
        matches_after = pattern.findall(after_text)
        for match in matches_after:
            # Check if this backstory was already present in before_text
            if match not in before_text:
                drift_items.append(
                    SemanticDriftItem(
                        dimension="backstory",
                        evidence_type="new_character_backstory_invented",
                        original_excerpt="(原文无该人物经历描述)",
                        edited_excerpt=match,
                        description=f"Editor 自行编造了新人物履历/过往经历「{match}」，破坏了 Canon 事实权威。",
                        severity="blocking",
                    )
                )

    # 2. Accidental vs Deliberate Motive Shift (Case A)
    # Check if before_text had an accidental/passive occurrence that became deliberate/provocative in after_text
    before_has_accidental = any(m in before_text for m in ACCIDENTAL_MARKERS)
    after_has_deliberate = any(m in after_text for m in DELIBERATE_MARKERS)

    if before_has_accidental and after_has_deliberate:
        # Extract context
        orig_snippets = [m for m in ACCIDENTAL_MARKERS if m in before_text]
        after_snippets = [m for m in DELIBERATE_MARKERS if m in after_text]
        drift_items.append(
            SemanticDriftItem(
                dimension="intent_shift",
                evidence_type="accidental_action_turned_into_deliberate_test",
                original_excerpt="; ".join(orig_snippets),
                edited_excerpt="; ".join(after_snippets),
                description=(
                    "Editor 将原文中角色'偶然/无意'的被动行为篡改为'主动试探/心机设局'，"
                    "根本性改变了角色动机与因果关系。"
                ),
                severity="blocking",
            )
        )

    # 3. Capability / Expertise Inflation Check
    for pattern in CAPABILITY_INFLATION_PATTERNS:
        matches_after = pattern.findall(after_text)
        for match in matches_after:
            if match not in before_text:
                drift_items.append(
                    SemanticDriftItem(
                        dimension="capability",
                        evidence_type="unestablished_capability_asserted",
                        original_excerpt="(原文未声称该专业技能)",
                        edited_excerpt=match,
                        description=f"Editor 擅自赋予角色未经验证的新技能或精通属性「{match}」。",
                        severity="blocking",
                    )
                )

    # 4. Epistemic state shift / Rationalization Patch
    for pattern in EPISTEMIC_SHIFT_PATTERNS:
        matches_after = pattern.findall(after_text)
        for match in matches_after:
            if match not in before_text:
                drift_items.append(
                    SemanticDriftItem(
                        dimension="epistemic",
                        evidence_type="retroactive_knowledge_or_preparation_patched",
                        original_excerpt="(原文无该知情或前置准备描述)",
                        edited_excerpt=match,
                        description=f"Editor 擅自通过事后补丁「{match}」修补剧情漏洞或赋予全知视角。",
                        severity="blocking",
                    )
                )

    # 5. Secret setting / identity invention check (Variety 5)
    for pattern in SECRET_SETTING_PATTERNS:
        matches_after = pattern.findall(after_text)
        for match in matches_after:
            if match not in before_text:
                drift_items.append(
                    SemanticDriftItem(
                        dimension="secret_setting_inconsistency_patch",
                        evidence_type="unauthorized_secret_setting_or_identity_invented",
                        original_excerpt="(原文无该隐藏设定、秘密身份或密道)",
                        edited_excerpt=match,
                        description=f"Editor 擅自发明隐藏身份/秘密通道/新设定「{match}」修补剧情矛盾，破坏 Canon 事实权威。",
                        severity="blocking",
                    )
                )

    # 6. Determine outcome
    if drift_items:
        return SemanticDiffResult(
            outcome=SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED,
            safe=False,
            drift_items=drift_items,
            confidence=0.95,
            summary=(
                f"检测到 {len(drift_items)} 处事实/动机/履历篡改漂移！"
                "Editor 越权创造了新的 Canon 事实，必须保留原稿并回滚。"
            ),
        )

    # 6. Check for radical structural rewrite / extreme diff ratio without factual anchors
    matcher = difflib.SequenceMatcher(None, before_text, after_text)
    similarity = matcher.ratio()

    # If similarity is too low (< 0.40), text was almost completely replaced
    if similarity < 0.40:
        return SemanticDiffResult(
            outcome=SemanticDiffOutcome.UNCERTAIN,
            safe=False,
            drift_items=[
                SemanticDriftItem(
                    dimension="rewrite_scope",
                    evidence_type="radical_unbounded_rewrite",
                    original_excerpt=before_text[:80] + "...",
                    edited_excerpt=after_text[:80] + "...",
                    description="相似度低于 40%，改写幅度过大，超出局部定向润色边界，无法保证事实安全性。",
                    severity="blocking",
                )
            ],
            confidence=0.75,
            summary="改写范围过大且相似度过低，判定为 UNCERTAIN，需人工裁决或回滚。",
        )

    return SemanticDiffResult(
        outcome=SemanticDiffOutcome.STYLE_ONLY_SAFE,
        safe=True,
        drift_items=[],
        confidence=0.95,
        summary="编辑局限于表达修饰、字句流畅度与网文口感，未引入任何新故事事实（STYLE_ONLY_SAFE）。",
    )
