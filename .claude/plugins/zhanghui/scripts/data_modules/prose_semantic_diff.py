#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prose Semantic Diff (Issue #26).

Fact-Safe Semantic Decision Architecture:
Deterministic fast-path coverage
+
Semantic judge fallback
=
Fact-safe decision

Layer 1: Deterministic Claim Extraction & Fast-Path Diff.
Covers deterministic baseline assertions (ownership, world rule polarity,
relationship, character state, backstory, motivation, capability, secret identity).
Pure surface edits with small footprint and unchanged claims are fast-path accepted.

Layer 2: Semantic Judge Fallback (Fail-Closed).
When substantial semantic rewrite potential is detected beyond deterministic coverage
(e.g., event outcome, epistemic state, causality, clue, or larger structural edits):
invokes a minimal, structured Semantic Judge contract checking all 11 dimensions.
If judge is unavailable, fails, or produces invalid output:
FAILS CLOSED to UNCERTAIN (never silently guesses STYLE_ONLY_SAFE).
"""
from __future__ import annotations

import difflib
import json
import os
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


# 11 Canonical Fact Dimensions checked by Semantic Judge
SEMANTIC_JUDGE_DIMENSIONS = [
    "backstory",           # 人物履历
    "capability",          # 能力
    "relationship",        # 关系
    "motivation",          # 动机
    "event_outcome",       # 事件结果
    "causality",           # 因果
    "ownership",           # 所有权
    "location_or_state",   # 地点/状态
    "world_rule",          # 世界规则
    "clue",                # 线索
    "epistemic",           # 知情状态
]

SemanticJudgeCallable = Callable[[str, str], Union[Dict[str, Any], str, None]]

_DEFAULT_SEMANTIC_JUDGE: Optional[SemanticJudgeCallable] = None


def set_default_semantic_judge(judge: Optional[SemanticJudgeCallable]) -> None:
    """Set global default semantic judge callback for fallback invocation."""
    global _DEFAULT_SEMANTIC_JUDGE
    _DEFAULT_SEMANTIC_JUDGE = judge


def get_default_semantic_judge() -> Optional[SemanticJudgeCallable]:
    """Get current default semantic judge callback."""
    global _DEFAULT_SEMANTIC_JUDGE
    if _DEFAULT_SEMANTIC_JUDGE is not None:
        return _DEFAULT_SEMANTIC_JUDGE
    env_judge = os.environ.get("ZHANGHUI_SEMANTIC_JUDGE_RESULT", "").strip()
    if env_judge:
        if Path(env_judge).is_file():
            content = Path(env_judge).read_text(encoding="utf-8")
            return lambda b, a: content
        return lambda b, a: env_judge
    return None


def build_semantic_judge_prompt(before_prose: str, after_prose: str) -> str:
    """Construct structured semantic judge prompt for LLM host."""
    return f"""你现在是网文事实安全裁决员（Semantic Judge）。
请对比以下【修改前正文】与【修改后正文】，严格审查是否存在任何故事事实、设定或逻辑漂移。

【审查的 11 项事实维度】：
1. 人物履历 (backstory)
2. 能力 (capability)
3. 关系 (relationship)
4. 动机 (motivation)
5. 事件结果 (event_outcome)
6. 因果 (causality)
7. 所有权 (ownership)
8. 地点/状态 (location_or_state)
9. 世界规则 (world_rule)
10. 线索 (clue)
11. 知情状态 (epistemic)

【输出要求】：
必须且仅输出以下 JSON 格式（不要包含任何其他文字或多余解释）：
{{
  "outcome": "STYLE_ONLY_SAFE | SEMANTIC_CHANGE_PROPOSED | UNCERTAIN",
  "changes": [
    {{
      "dimension": "...",
      "before": "...",
      "after": "...",
      "reason": "..."
    }}
  ]
}}

- 若所有事实、设定、因果与知情状态均完全保全，仅为语言表达润色：outcome 为 "STYLE_ONLY_SAFE"，changes 为 []。
- 若存在任何事实漂移、反转或新事实编造：outcome 为 "SEMANTIC_CHANGE_PROPOSED"，并在 changes 中详细列出各项漂移。
- 若改写幅度过大或语义严重模糊无法判断：outcome 为 "UNCERTAIN"。

=== 修改前正文 ===
{before_prose}

=== 修改后正文 ===
{after_prose}
"""


def parse_semantic_judge_response(response: Any) -> Dict[str, Any]:
    """Parse and strictly validate semantic judge response dict/string."""
    if response is None:
        raise ValueError("Semantic judge response is None")

    if isinstance(response, str):
        text = response.strip()
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        try:
            data = json.loads(text)
        except Exception as exc:
            raise ValueError(f"Failed to parse semantic judge JSON: {exc}") from exc
    elif isinstance(response, dict):
        data = response
    else:
        raise ValueError(f"Unsupported judge response type: {type(response)}")

    if not isinstance(data, dict):
        raise ValueError("Judge response must be a JSON object")

    outcome = data.get("outcome")
    if outcome not in ("STYLE_ONLY_SAFE", "SEMANTIC_CHANGE_PROPOSED", "UNCERTAIN"):
        raise ValueError(f"Invalid judge outcome: {outcome}")

    changes = data.get("changes")
    if changes is None:
        changes = []
    elif not isinstance(changes, list):
        raise ValueError("Judge changes must be a list")

    norm_changes = []
    for c in changes:
        if isinstance(c, dict):
            norm_changes.append({
                "dimension": str(c.get("dimension", "semantic_drift")),
                "before": str(c.get("before", "")),
                "after": str(c.get("after", "")),
                "reason": str(c.get("reason", "")),
            })
        else:
            raise ValueError("Each change item must be an object")

    return {
        "outcome": outcome,
        "changes": norm_changes,
    }


class SemanticDiffOutcome(str, Enum):
    STYLE_ONLY_SAFE = "STYLE_ONLY_SAFE"
    SEMANTIC_CHANGE_PROPOSED = "SEMANTIC_CHANGE_PROPOSED"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class SemanticClaim:
    """A structured factual claim extracted from prose."""
    dimension: str  # "ownership" | "world_rule" | "relationship" | "character_state" | "backstory" | "motivation" | "capability" | "event_outcome" | "epistemic" | "causality" | "clue"
    subject: str
    predicate: str
    object_value: str
    polarity: bool = True  # True: affirmative ("可以/是/由...保管"), False: negated ("不能/非/未")
    certainty: str = "definite"
    evidence_span: str = ""

    def claim_id(self) -> str:
        s_norm = self.subject.strip().replace(" ", "")
        p_norm = self.predicate.strip().replace(" ", "")
        return f"{self.dimension}::{s_norm}::{p_norm}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SemanticClaimSet:
    """Collection of structured claims extracted from a text passage."""
    claims: List[SemanticClaim] = field(default_factory=list)

    def to_dict(self) -> List[Dict[str, Any]]:
        return [c.to_dict() for c in self.claims]

    def find_by_subject_and_dimension(self, subject: str, dimension: str) -> List[SemanticClaim]:
        s_norm = subject.strip().replace(" ", "")
        return [c for c in self.claims if c.dimension == dimension and (c.subject.strip().replace(" ", "") in s_norm or s_norm in c.subject.strip().replace(" ", ""))]


@dataclass
class SemanticDriftItem:
    dimension: str
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
    before_claims: Optional[List[Dict[str, Any]]] = None
    after_claims: Optional[List[Dict[str, Any]]] = None

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
            "before_claims": self.before_claims or [],
            "after_claims": self.after_claims or [],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ----------------------------------------------------------------------
# Structured Semantic Claim Extractor
# ----------------------------------------------------------------------

def _split_clauses(text: str) -> List[str]:
    """Split text into manageable grammatical clauses."""
    raw = re.split(r"[。！？；\n!?]+", text)
    return [s.strip() for s in raw if s.strip()]


def extract_semantic_claims(text: str) -> SemanticClaimSet:
    """
    Extract structured factual claims across Canon dimensions from text clauses.
    Covers: ownership, world_rule, relationship, character_state, backstory, motivation, capability.
    """
    claims: List[SemanticClaim] = []
    clauses = _split_clauses(text)

    for clause in clauses:
        # 1. Ownership / Custody claims
        # e.g., "钥匙由林越保管", "由韩策持有", "归梅叔所有", "属于巡捕"
        m_owner = re.search(r"([^，,]+?)(?:由|归|属于)([^，,]+?)(?:保管|持有|掌管|所有|保存|存放)", clause)
        if m_owner:
            item_subj = m_owner.group(1).strip()
            custodian = m_owner.group(2).strip()
            claims.append(
                SemanticClaim(
                    dimension="ownership",
                    subject=item_subj,
                    predicate="custodian",
                    object_value=custodian,
                    polarity=True,
                    evidence_span=clause,
                )
            )

        # 2. World rule / automated system mechanism claims
        # e.g., "纸档案不能被城市网络自动改写", "纸档案可以被城市网络自动改写"
        m_rule = re.search(r"([^，,]+?)(不能|无法|不可|不得|严禁|可以|能够|能|会|可能)(?:被|由)([^，,]+?)(自动改写|覆写|抹除|破解|干预|修改)", clause)
        if m_rule:
            rule_subj = m_rule.group(1).strip()
            modal = m_rule.group(2).strip()
            actor = m_rule.group(3).strip()
            action = m_rule.group(4).strip()
            polarity = modal not in ("不能", "无法", "不可", "不得", "严禁")
            claims.append(
                SemanticClaim(
                    dimension="world_rule",
                    subject=rule_subj,
                    predicate=f"be_{action}_by_{actor}",
                    object_value=action,
                    polarity=polarity,
                    evidence_span=clause,
                )
            )

        # 3. Relationship claims
        # e.g., "乔宁只是合作伙伴", "乔宁已经是林越的恋人", "梅叔是卧底"
        m_rel = re.search(r"([^，,]+?)(?:只是|已经是|是|乃是|算作)(?:[^，,]*?)(合作伙伴|恋人|情侣|夫妻|朋友|盟友|死党|同谋|仇人|死敌|师徒|下属|亲属)", clause)
        if m_rel:
            char_subj = m_rel.group(1).strip()
            rel_type = m_rel.group(2).strip()
            claims.append(
                SemanticClaim(
                    dimension="relationship",
                    subject=char_subj,
                    predicate="relationship_role",
                    object_value=rel_type,
                    polarity=True,
                    evidence_span=clause,
                )
            )

        # 4. Character physiological state / injury result
        # e.g., "林越左手只是轻伤", "林越左手已经骨折", "林越重伤"
        m_state = re.search(r"([^，,]+?)(?:只是|已经|是|受了)?(轻伤|重伤|骨折|中毒|昏迷|痊愈|死亡|残疾|完好|无碍)", clause)
        if m_state:
            char_or_part = m_state.group(1).strip()
            # Verify subject looks like a person or body part
            if any(term in char_or_part for term in ("手", "腿", "胸", "臂", "肩", "伤", "林越", "韩策", "梅叔", "乔宁", "主角")):
                state_val = m_state.group(2).strip()
                claims.append(
                    SemanticClaim(
                        dimension="character_state",
                        subject=char_or_part,
                        predicate="physical_injury_state",
                        object_value=state_val,
                        polarity=True,
                        evidence_span=clause,
                    )
                )

        # 5. Backstory / Past profession claims
        # e.g., "想起自己当过三年机修学徒的旧事", "早年曾在北境服役"
        m_back = re.search(r"(?:曾经|曾是|早年|幼年|幼时|当初|早先|曾在|当过|做过)(?:[^，。！？\n]{0,8})(?:学徒|弟子|药农|镖师|捕快|杂役|铁匠|机修|行医|军伍|杀手|散修|佣兵|伙计)", clause)
        if m_back:
            claims.append(
                SemanticClaim(
                    dimension="backstory",
                    subject="character",
                    predicate="past_profession_or_experience",
                    object_value=m_back.group(0).strip(),
                    polarity=True,
                    evidence_span=clause,
                )
            )

        # 6. Motivation / intentionality mode
        # Accidental vs deliberate test / provocation
        if any(term in clause for term in ("偶然", "无意中", "无意间", "滑出来", "落在")):
            claims.append(
                SemanticClaim(
                    dimension="motivation",
                    subject="action_intent",
                    predicate="intentionality_mode",
                    object_value="accidental_passive",
                    polarity=True,
                    evidence_span=clause,
                )
            )
        elif any(term in clause for term in ("主动", "故意", "刻意", "试探", "拍到桌边试探", "死死盯着", "设局")):
            claims.append(
                SemanticClaim(
                    dimension="motivation",
                    subject="action_intent",
                    predicate="intentionality_mode",
                    object_value="deliberate_provocation",
                    polarity=True,
                    evidence_span=clause,
                )
            )

        # 7. Capability inflation
        m_cap = re.search(r"(?:精通|深谙|了如指掌|早已掌握)([^，,]{2,10})", clause)
        if m_cap:
            claims.append(
                SemanticClaim(
                    dimension="capability",
                    subject="character",
                    predicate="specialized_capability",
                    object_value=m_cap.group(1).strip(),
                    polarity=True,
                    evidence_span=clause,
                )
            )

        # 8. Secret Identity / Secret Passage Invention
        m_secret = re.search(r"(?:其实|实际上|原来|真实身份)(?:[^，,]{0,8})(?:是|乃是|竟是)(?:[^，,]{0,10})(?:刺客|杀手|卧底|密探|长老|门主|弟子|奸细|特使)", clause)
        if m_secret:
            claims.append(
                SemanticClaim(
                    dimension="secret_identity",
                    subject="character",
                    predicate="secret_identity",
                    object_value=m_secret.group(0).strip(),
                    polarity=True,
                    evidence_span=clause,
                )
            )
        m_passage = re.search(r"(?:通过|利用|顺着|借由|走)(?:[^，,]{0,8})(?:密道|暗道|暗门|阵法|传送阵|密室)(?:[^，,]{0,10})(?:潜入|潜行|逃离|离开|往返|穿过)", clause)
        if m_passage:
            claims.append(
                SemanticClaim(
                    dimension="secret_setting",
                    subject="location",
                    predicate="secret_passage",
                    object_value=m_passage.group(0).strip(),
                    polarity=True,
                    evidence_span=clause,
                )
            )

    return SemanticClaimSet(claims=claims)


# ----------------------------------------------------------------------
# Deterministic Semantic Comparison Engine & Judge Fallback
# ----------------------------------------------------------------------

UNCOVERED_DIMENSION_KEYWORDS = {
    "epistemic": ["亲眼", "目击", "看见", "看到", "从未看见", "未曾看见", "得知", "知晓", "察觉"],
    "event_outcome": ["关闭了", "没有关闭", "未关闭", "开启了", "没有开启", "击倒", "击退", "坍塌", "未曾关闭"],
    "causality": ["导致", "造成", "引发", "使得", "无关", "毫无关系"],
    "clue": ["写着", "字迹", "印着", "刻着", "没有任何字迹", "无字迹", "卡片背面"],
}


def touches_uncovered_dimensions(before_text: str, after_text: str) -> bool:
    """Check if any keywords representing uncovered semantic dimensions mutated."""
    for dim, kws in UNCOVERED_DIMENSION_KEYWORDS.items():
        for kw in kws:
            if (kw in before_text) != (kw in after_text):
                return True
    return False


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"[。！？\n!?]+", text) if s.strip()]


def is_surface_only_edit(before_text: str, after_text: str) -> bool:
    """
    Check if the change between before_text and after_text is a pure surface-level
    stylistic edit with a small footprint that can be safely accepted via fast-path.
    """
    if touches_uncovered_dimensions(before_text, after_text):
        return False

    b_sentences = _split_sentences(before_text)
    a_sentences = _split_sentences(after_text)
    if len(b_sentences) != len(a_sentences):
        return False

    matcher = difflib.SequenceMatcher(None, before_text, after_text)
    ratio = matcher.ratio()
    if ratio < 0.45:
        return False

    len_diff = abs(len(before_text) - len(after_text))
    max_allowed_len_diff = max(15, int(len(before_text) * 0.15))
    if len_diff > max_allowed_len_diff:
        return False

    return True


def compare_semantic_facts(
    before_text: str,
    after_text: str,
    semantic_judge: Optional[SemanticJudgeCallable] = None,
) -> SemanticDiffResult:
    """
    Compare before and after prose to verify factual and semantic preservation.
    Layer 1: Structured claim extraction & deterministic claim diffing.
    Layer 2: Fast-path for surface-only edits / Semantic Judge fallback (Fail-closed).
    """
    # 0. Fast path: exact match
    if before_text.strip() == after_text.strip():
        return SemanticDiffResult(
            outcome=SemanticDiffOutcome.STYLE_ONLY_SAFE,
            safe=True,
            drift_items=[],
            confidence=1.0,
            summary="正文未作任何语义变动，完全一致。",
        )

    # 1. Check for drastic unbounded rewrite
    matcher = difflib.SequenceMatcher(None, before_text, after_text)
    similarity = matcher.ratio()
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
                    description="相似度低于 40%，改写幅度过大，超出局部定向润色边界，无法证明事实安全。",
                    severity="blocking",
                )
            ],
            confidence=0.75,
            summary="改写范围过大且相似度过低，判定为 UNCERTAIN，需人工裁决或回滚。",
        )

    # 2. Extract structured claims from before and after
    before_claims = extract_semantic_claims(before_text)
    after_claims = extract_semantic_claims(after_text)

    drift_items: List[SemanticDriftItem] = []

    # Check 1: Ownership diff
    for after_c in after_claims.claims:
        if after_c.dimension == "ownership":
            matching = before_claims.find_by_subject_and_dimension(after_c.subject, "ownership")
            if matching:
                for before_c in matching:
                    if before_c.object_value != after_c.object_value:
                        drift_items.append(
                            SemanticDriftItem(
                                dimension="ownership",
                                evidence_type="custodian_or_owner_changed",
                                original_excerpt=before_c.evidence_span,
                                edited_excerpt=after_c.evidence_span,
                                description=(
                                    f"物品保管/归属发生冲突：'{after_c.subject}' 的保管/归属对象"
                                    f"从 '{before_c.object_value}' 变更为 '{after_c.object_value}'。"
                                ),
                                severity="blocking",
                            )
                        )

    # Check 2: World rule polarity diff
    for after_c in after_claims.claims:
        if after_c.dimension == "world_rule":
            matching = before_claims.find_by_subject_and_dimension(after_c.subject, "world_rule")
            if matching:
                for before_c in matching:
                    if before_c.polarity != after_c.polarity:
                        drift_items.append(
                            SemanticDriftItem(
                                dimension="world_rule",
                                evidence_type="rule_polarity_inverted",
                                original_excerpt=before_c.evidence_span,
                                edited_excerpt=after_c.evidence_span,
                                description=(
                                    f"世界规则/机制极性反转：'{after_c.subject}' 的不可变规则"
                                    f"从 {'肯定(可以)' if before_c.polarity else '否定(不能)'} "
                                    f"被篡改为 {'肯定(可以)' if after_c.polarity else '否定(不能)'}。"
                                ),
                                severity="blocking",
                            )
                        )

    # Check 3: Relationship diff
    for after_c in after_claims.claims:
        if after_c.dimension == "relationship":
            matching = before_claims.find_by_subject_and_dimension(after_c.subject, "relationship")
            if matching:
                for before_c in matching:
                    if before_c.object_value != after_c.object_value:
                        drift_items.append(
                            SemanticDriftItem(
                                dimension="relationship",
                                evidence_type="relationship_role_changed",
                                original_excerpt=before_c.evidence_span,
                                edited_excerpt=after_c.evidence_span,
                                description=(
                                    f"人物关系定义发生质变：'{after_c.subject}' 的关系从 "
                                    f"'{before_c.object_value}' 变更为 '{after_c.object_value}'。"
                                ),
                                severity="blocking",
                            )
                        )

    # Check 4: Character state / injury result diff
    for after_c in after_claims.claims:
        if after_c.dimension == "character_state":
            matching = before_claims.find_by_subject_and_dimension(after_c.subject, "character_state")
            if matching:
                for before_c in matching:
                    if before_c.object_value != after_c.object_value:
                        drift_items.append(
                            SemanticDriftItem(
                                dimension="character_state",
                                evidence_type="physiological_state_changed",
                                original_excerpt=before_c.evidence_span,
                                edited_excerpt=after_c.evidence_span,
                                description=(
                                    f"角色生理/伤情状态被修改：'{after_c.subject}' 的伤情从 "
                                    f"'{before_c.object_value}' 变更为 '{after_c.object_value}'。"
                                ),
                                severity="blocking",
                            )
                        )

    # Check 5: Backstory invention (new backstory not in before)
    for after_c in after_claims.claims:
        if after_c.dimension == "backstory":
            # Check if this backstory existed in before
            if not any(after_c.object_value in before_c.object_value for before_c in before_claims.claims if before_c.dimension == "backstory"):
                if after_c.object_value not in before_text:
                    drift_items.append(
                        SemanticDriftItem(
                            dimension="backstory",
                            evidence_type="new_backstory_invented",
                            original_excerpt="(原文无该人物经历描述)",
                            edited_excerpt=after_c.evidence_span,
                            description=f"Editor 擅自发明人物过往履历「{after_c.object_value}」，破坏 Canon 权威。",
                            severity="blocking",
                        )
                    )

    # Check 6: Motivation mode shift (accidental -> deliberate)
    before_intent = [c.object_value for c in before_claims.claims if c.dimension == "motivation"]
    after_intent = [c.object_value for c in after_claims.claims if c.dimension == "motivation"]
    if "accidental_passive" in before_intent and "deliberate_provocation" in after_intent:
        drift_items.append(
            SemanticDriftItem(
                dimension="motivation",
                evidence_type="accidental_action_turned_into_deliberate_test",
                original_excerpt="; ".join(c.evidence_span for c in before_claims.claims if c.dimension == "motivation"),
                edited_excerpt="; ".join(c.evidence_span for c in after_claims.claims if c.dimension == "motivation"),
                description=(
                    "Editor 将原文中角色的'偶然/被动'行为篡改为'主动试探/心机设局'，"
                    "根本性篡改了角色意图与剧情因果。"
                ),
                severity="blocking",
            )
        )

    # Check 7: Capability / Specialized skill inflation
    for after_c in after_claims.claims:
        if after_c.dimension == "capability":
            if after_c.object_value not in before_text:
                drift_items.append(
                    SemanticDriftItem(
                        dimension="capability",
                        evidence_type="unestablished_capability_asserted",
                        original_excerpt="(原文未声称该专业技能)",
                        edited_excerpt=after_c.evidence_span,
                        description=f"Editor 擅自赋予角色未经验证的新技能「{after_c.object_value}」。",
                        severity="blocking",
                    )
                )

    # Check 8: Secret identity or passage invention
    for after_c in after_claims.claims:
        if after_c.dimension in ("secret_identity", "secret_setting"):
            if after_c.object_value not in before_text:
                drift_items.append(
                    SemanticDriftItem(
                        dimension=after_c.dimension,
                        evidence_type="unauthorized_secret_setting_or_identity",
                        original_excerpt="(原文无该隐藏设定或密道身份)",
                        edited_excerpt=after_c.evidence_span,
                        description=f"Editor 擅自发明隐藏身份/秘密通道「{after_c.object_value}」修补剧情矛盾，破坏 Canon 事实权威。",
                        severity="blocking",
                    )
                )

    # 3. Decision
    if drift_items:
        return SemanticDiffResult(
            outcome=SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED,
            safe=False,
            drift_items=drift_items,
            confidence=0.95,
            summary=(
                f"结构化事实比对检测到 {len(drift_items)} 处事实/动机/规则/状态漂移！"
                "Editor 越权创造或篡改了 Canon 事实，必须保留原稿并回滚。"
            ),
            before_claims=before_claims.to_dict(),
            after_claims=after_claims.to_dict(),
        )

    # 4. Check whether deterministic fast-path coverage is sufficient (surface-only edit)
    if is_surface_only_edit(before_text, after_text):
        return SemanticDiffResult(
            outcome=SemanticDiffOutcome.STYLE_ONLY_SAFE,
            safe=True,
            drift_items=[],
            confidence=0.95,
            summary="编辑局限于表达修饰与风格适配，未引入任何新故事事实（STYLE_ONLY_SAFE）。",
            before_claims=before_claims.to_dict(),
            after_claims=after_claims.to_dict(),
        )

    # 5. Layer 2: Substantial rewrite potential beyond deterministic coverage -> Semantic Judge Fallback (Fail-Closed)
    effective_judge = semantic_judge if semantic_judge is not None else get_default_semantic_judge()
    if effective_judge is None:
        return SemanticDiffResult(
            outcome=SemanticDiffOutcome.UNCERTAIN,
            safe=False,
            drift_items=[
                SemanticDriftItem(
                    dimension="coverage_gap",
                    evidence_type="semantic_judge_unavailable",
                    original_excerpt=before_text[:80] + ("..." if len(before_text) > 80 else ""),
                    edited_excerpt=after_text[:80] + ("..." if len(after_text) > 80 else ""),
                    description="正文存在实质语义改写，但未执行/未配置 Semantic Judge，根据安全契约 fail-closed 判定为 UNCERTAIN。",
                    severity="blocking",
                )
            ],
            confidence=0.5,
            summary="正文存在实质语义改写，但未执行 Semantic Judge，根据安全契约 fail-closed 判定为 UNCERTAIN。",
            before_claims=before_claims.to_dict(),
            after_claims=after_claims.to_dict(),
        )

    try:
        raw_res = effective_judge(before_text, after_text)
        judge_data = parse_semantic_judge_response(raw_res)
    except Exception as exc:
        return SemanticDiffResult(
            outcome=SemanticDiffOutcome.UNCERTAIN,
            safe=False,
            drift_items=[
                SemanticDriftItem(
                    dimension="judge_error",
                    evidence_type="semantic_judge_failed",
                    original_excerpt=before_text[:80] + ("..." if len(before_text) > 80 else ""),
                    edited_excerpt=after_text[:80] + ("..." if len(after_text) > 80 else ""),
                    description=f"Semantic Judge 执行失败或返回非法结果 ({exc})，根据安全契约 fail-closed 判定为 UNCERTAIN。",
                    severity="blocking",
                )
            ],
            confidence=0.5,
            summary=f"Semantic Judge 执行失败或返回非法结果 ({exc})，根据安全契约 fail-closed 判定为 UNCERTAIN。",
            before_claims=before_claims.to_dict(),
            after_claims=after_claims.to_dict(),
        )

    j_outcome = judge_data["outcome"]
    if j_outcome == "SEMANTIC_CHANGE_PROPOSED":
        judge_drifts = []
        for c in judge_data.get("changes", []):
            judge_drifts.append(
                SemanticDriftItem(
                    dimension=c.get("dimension", "semantic_drift"),
                    evidence_type="semantic_judge_finding",
                    original_excerpt=c.get("before", "(原文)"),
                    edited_excerpt=c.get("after", "(改动)"),
                    description=c.get("reason", "Semantic Judge 判定发现故事事实漂移"),
                    severity="blocking",
                )
            )
        if not judge_drifts:
            judge_drifts.append(
                SemanticDriftItem(
                    dimension="semantic_drift",
                    evidence_type="semantic_judge_finding",
                    original_excerpt=before_text[:80] + ("..." if len(before_text) > 80 else ""),
                    edited_excerpt=after_text[:80] + ("..." if len(after_text) > 80 else ""),
                    description="Semantic Judge 判定发现故事事实漂移",
                    severity="blocking",
                )
            )
        return SemanticDiffResult(
            outcome=SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED,
            safe=False,
            drift_items=judge_drifts,
            confidence=0.95,
            summary=f"Semantic Judge 判定检测到 {len(judge_drifts)} 处事实漂移 (SEMANTIC_CHANGE_PROPOSED)。",
            before_claims=before_claims.to_dict(),
            after_claims=after_claims.to_dict(),
        )
    elif j_outcome == "STYLE_ONLY_SAFE":
        return SemanticDiffResult(
            outcome=SemanticDiffOutcome.STYLE_ONLY_SAFE,
            safe=True,
            drift_items=[],
            confidence=0.95,
            summary="Semantic Judge 判定事实保全，仅为语言风格润色 (STYLE_ONLY_SAFE)。",
            before_claims=before_claims.to_dict(),
            after_claims=after_claims.to_dict(),
        )
    else:
        return SemanticDiffResult(
            outcome=SemanticDiffOutcome.UNCERTAIN,
            safe=False,
            drift_items=[
                SemanticDriftItem(
                    dimension="judge_uncertain",
                    evidence_type="semantic_judge_uncertain",
                    original_excerpt=before_text[:80] + ("..." if len(before_text) > 80 else ""),
                    edited_excerpt=after_text[:80] + ("..." if len(after_text) > 80 else ""),
                    description="Semantic Judge 判定语义改写存在不确定性，需人工裁决。",
                    severity="blocking",
                )
            ],
            confidence=0.6,
            summary="Semantic Judge 判定语义改写存在不确定性，判定为 UNCERTAIN。",
            before_claims=before_claims.to_dict(),
            after_claims=after_claims.to_dict(),
        )
