#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prose Quality Gate & Rollback Protection (Issue #26).

Evaluates whether an edited prose draft is acceptable or has regressed in quality.
Guards against:
1. Fact / semantic drift (SEMANTIC_CHANGE_PROPOSED / UNCERTAIN)
2. Excessive compression / shrinkage (e.g. > 20% text lost)
3. Telegraphic / staccato rhythm regression (sentence fragmentation, choppy single-sentence paragraphs)
4. Unbounded massive rewrites

If regression is detected:
- Sets accepted = False
- Status = "ROLLEDBACK"
- Reverts final_prose to original before_text
- Preserves full audit record: before, diagnosis, edit_plan, after, validation, decision.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .prose_semantic_diff import (
    SemanticDiffOutcome,
    SemanticDiffResult,
    compare_semantic_facts,
)


# Gate statuses.
#
# PENDING_REREVIEW is deliberately *not* an acceptance: `accepted` stays False, so nothing
# downstream may treat it as reviewed prose. It means "this is a declared, bounded fact
# correction inside an in-flight draft; it is only valid once a NEW draft identity has been
# ingested and a fresh Reviewer run has been bound to it".
STATUS_ACCEPTED = "ACCEPTED"
STATUS_ROLLEDBACK = "ROLLEDBACK"
STATUS_PENDING_REREVIEW = "PENDING_REREVIEW"

OUTCOME_FACT_FIX_DECLARED = "FACT_FIX_DECLARED"

FACT_FIX_REQUIRED_ACTIONS = (
    "runtime ingest-draft（取得新 draft_id / draft_fingerprint）",
    "webnovel-writer:reviewer（对新草稿完整重审）",
    "review-pipeline --save-metrics（把新审查绑定到新草稿）",
)


@dataclass
class QualityGateDecision:
    accepted: bool
    status: str  # "ACCEPTED" | "ROLLEDBACK" | "PENDING_REREVIEW"
    rollback_reason: Optional[str] = None
    semantic_outcome: str = "STYLE_ONLY_SAFE"
    shrinkage_ratio: float = 0.0
    staccato_score: float = 0.0
    edit_footprint_ratio: float = 0.0
    final_prose: str = ""
    audit_record: Dict[str, Any] = field(default_factory=dict)
    required_actions: List[str] = field(default_factory=list)
    next_step: str = ""
    declared_fact_fix: Dict[str, Any] = field(default_factory=dict)

    @property
    def final_text(self) -> str:
        return self.final_prose

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        # Omit massive prose dumps from top-level dict summary
        res["final_prose_chars"] = len(self.final_prose)
        del res["final_prose"]
        return res

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def _split_sentences(text: str) -> List[str]:
    # Split by standard Chinese and English punctuation
    raw = re.split(r"[。！？\n!?]+", text)
    return [s.strip() for s in raw if s.strip()]


def _changed_regions(before_text: str, after_text: str) -> List[Tuple[int, int]]:
    """Character ranges of `before_text` that differ, with whitespace-only edits trimmed."""
    if before_text == after_text:
        return []
    matcher = difflib.SequenceMatcher(None, before_text, after_text, autojunk=False)
    regions: List[Tuple[int, int]] = []
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        segment = before_text[i1:i2]
        left = len(segment) - len(segment.lstrip())
        right = len(segment) - len(segment.rstrip())
        tight = (i1 + left, i2 - right)
        regions.append(tight if tight[0] < tight[1] else (i1, i2))
    return regions


def _fact_fix_verdict(
    before_text: str,
    after_text: str,
    declared_fact_fix: Dict[str, Any],
) -> Tuple[bool, str, Dict[str, Any]]:
    """Check that a declared fact correction is bounded to its declared LOCAL_FACT spans.

    Returns `(ok, reason, details)`. A legal in-flight correction must *not* have to be blessed
    as STYLE_ONLY_SAFE — it is a fact change, and pretending otherwise is exactly the pressure
    that produced the earlier conflict. What makes it safe instead is: it is bounded to spans
    the Reviewer's own findings pointed at, it introduces no deterministic fact drift, and it is
    only valid after a fresh draft identity + fresh review.
    """
    declared_sha = str(declared_fact_fix.get("draft_sha256") or "")
    actual_sha = hashlib.sha256(before_text.encode("utf-8")).hexdigest()
    details: Dict[str, Any] = {
        "draft_sha256_matches": bool(declared_sha) and declared_sha == actual_sha,
        "declared_draft_sha256": declared_sha,
        "actual_draft_sha256": actual_sha,
    }
    if not declared_sha:
        return False, "fact-fix 声明缺少 draft_sha256：无法确认修订计划来自当前草稿。", details
    if declared_sha != actual_sha:
        return (
            False,
            "fact-fix 声明与当前正文不一致（修订计划是为另一版草稿生成的）："
            f"plan={declared_sha[:12]} actual={actual_sha[:12]}。",
            details,
        )

    spans = declared_fact_fix.get("spans") or []
    normalised: List[Tuple[int, int, str]] = []
    for span in spans:
        if not isinstance(span, dict):
            continue
        try:
            start, end = int(span.get("start")), int(span.get("end"))
        except (TypeError, ValueError):
            continue
        normalised.append((start, end, str(span.get("kind") or "")))
    details["declared_spans"] = [
        {"start": s, "end": e, "kind": k} for s, e, k in normalised
    ]
    if not normalised:
        return False, "fact-fix 声明没有任何可编辑区间：没有可核验的修订范围。", details

    local_fact_spans = [(s, e) for s, e, kind in normalised if kind == "LOCAL_FACT"]
    details["local_fact_spans"] = [{"start": s, "end": e} for s, e in local_fact_spans]
    if not local_fact_spans:
        return (
            False,
            "fact-fix 声明的区间里没有 LOCAL_FACT 目标：只有审查定位到的事实类问题才走这条路径。",
            details,
        )

    regions = _changed_regions(before_text, after_text)
    details["changed_regions"] = [{"start": s, "end": e} for s, e in regions]
    out_of_scope = [
        {"start": s, "end": e}
        for s, e in regions
        if not any(lo <= s and e <= hi for lo, hi in local_fact_spans)
    ]
    details["out_of_scope_regions"] = out_of_scope
    if out_of_scope:
        return (
            False,
            "fact-fix 改动越出 LOCAL_FACT 区间：本次修改包含计划范围之外的正文改动（"
            f"{out_of_scope[:3]}）。越界改动必须走完整重审，不能借事实纠错放行。",
            details,
        )
    return True, "", details


def compute_prose_metrics(text: str) -> Dict[str, Any]:
    """Compute structural metrics (chars, sentences, avg length, staccato ratio)."""
    sentences = _split_sentences(text)
    avg_len = sum(len(s) for s in sentences) / len(sentences) if sentences else 0.0
    short_ratio = sum(1 for s in sentences if len(s) < 12) / len(sentences) if sentences else 0.0
    return {
        "chars": len(text),
        "sentence_count": len(sentences),
        "avg_sentence_len": round(avg_len, 2),
        "short_sentence_ratio": round(short_ratio, 4),
    }


def evaluate_prose_quality_and_decide(
    before_text: str,
    after_text: str,
    diagnosis_summary: Optional[Any] = None,
    edit_plan: Optional[str] = None,
    max_shrinkage_ratio: float = 0.20,  # Max allowable length reduction (20%)
    semantic_judge: Optional[Callable[[str, str], Any]] = None,
    declared_fact_fix: Optional[Dict[str, Any]] = None,
) -> QualityGateDecision:
    """Evaluate edited prose against quality and fact-safety criteria, rolling back if regressed."""
    before_len = len(before_text)
    after_len = len(after_text)

    # 1. Semantic Fact Diff Check (Hard Block)
    if isinstance(diagnosis_summary, SemanticDiffResult):
        semantic_res = diagnosis_summary
        diagnosis_dict = {}
    elif isinstance(diagnosis_summary, dict) and "outcome" in diagnosis_summary:
        # Caller passed serialized semantic diff
        semantic_res = compare_semantic_facts(before_text, after_text, semantic_judge=semantic_judge)
        diagnosis_dict = diagnosis_summary
    else:
        semantic_res = compare_semantic_facts(before_text, after_text, semantic_judge=semantic_judge)
        diagnosis_dict = diagnosis_summary if isinstance(diagnosis_summary, dict) else {}

    metrics_before = compute_prose_metrics(before_text)
    metrics_after = compute_prose_metrics(after_text)

    audit_validation: Dict[str, Any] = {
        "semantic_diff": semantic_res.to_dict(),
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
    }

    # 1. Semantic Fact Drift Check (Hard Block on explicit drift)
    if semantic_res.outcome == SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED:
        reason = f"触发事实安全红线回滚：{semantic_res.summary}"
        audit_record = {
            "before": before_text,
            "diagnosis": diagnosis_dict,
            "edit_plan": edit_plan or "",
            "after": after_text,
            "validation": audit_validation,
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "decision": {
                "accepted": False,
                "status": "ROLLEDBACK",
                "rollback_reason": reason,
            },
        }
        return QualityGateDecision(
            accepted=False,
            status="ROLLEDBACK",
            rollback_reason=reason,
            semantic_outcome=semantic_res.outcome.value,
            final_prose=before_text,
            audit_record=audit_record,
        )

    # 2. Text Shrinkage Check
    shrinkage = (before_len - after_len) / before_len if before_len > 0 else 0.0
    audit_validation["shrinkage_ratio"] = round(shrinkage, 4)

    if shrinkage > max_shrinkage_ratio and before_len >= 80:
        reason = (
            f"篇幅异常缩水回滚：正文字数减少了 {shrinkage * 100:.1f}% "
            f"({before_len}字 -> {after_len}字，超过允许阈值 {max_shrinkage_ratio * 100:.0f}%)"
        )
        audit_record = {
            "before": before_text,
            "diagnosis": diagnosis_dict,
            "edit_plan": edit_plan or "",
            "after": after_text,
            "validation": audit_validation,
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "decision": {
                "accepted": False,
                "status": "ROLLEDBACK",
                "rollback_reason": reason,
            },
        }
        return QualityGateDecision(
            accepted=False,
            status="ROLLEDBACK",
            rollback_reason=reason,
            semantic_outcome=semantic_res.outcome.value,
            shrinkage_ratio=shrinkage,
            final_prose=before_text,
            audit_record=audit_record,
        )

    # 3. Telegraphic / Staccato Rhythm Regression Check
    avg_len_before = metrics_before["avg_sentence_len"]
    avg_len_after = metrics_after["avg_sentence_len"]
    short_after_ratio = metrics_after["short_sentence_ratio"]

    # If average sentence length dropped drastically (> 40%) AND short sentences dominate (> 60%)
    staccato_drop = (avg_len_before - avg_len_after) / avg_len_before if avg_len_before > 0 else 0.0
    audit_validation["avg_sentence_len_before"] = round(avg_len_before, 2)
    audit_validation["avg_sentence_len_after"] = round(avg_len_after, 2)
    audit_validation["short_sentence_ratio_after"] = round(short_after_ratio, 4)

    if avg_len_before >= 18 and staccato_drop > 0.40 and short_after_ratio > 0.60:
        reason = (
            f"电报体节奏严重退化回滚：平均句长自 {avg_len_before:.1f} 字骤降至 {avg_len_after:.1f} 字 "
            f"(跌幅 {staccato_drop * 100:.1f}%)，短句占比高达 {short_after_ratio * 100:.1f}%，丧失叙事呼吸感。"
        )
        audit_record = {
            "before": before_text,
            "diagnosis": diagnosis_dict,
            "edit_plan": edit_plan or "",
            "after": after_text,
            "validation": audit_validation,
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "decision": {
                "accepted": False,
                "status": "ROLLEDBACK",
                "rollback_reason": reason,
            },
        }
        return QualityGateDecision(
            accepted=False,
            status="ROLLEDBACK",
            rollback_reason=reason,
            semantic_outcome=semantic_res.outcome.value,
            shrinkage_ratio=shrinkage,
            staccato_score=staccato_drop,
            final_prose=before_text,
            audit_record=audit_record,
        )

    # 3.4 Declared in-flight fact correction (governed draft revision path).
    #
    # A legitimate factual correction inside a draft that has NOT been accepted (e.g. the
    # Reviewer found "七行" where the prose establishes 八行) must not be forced through the
    # STYLE_ONLY_SAFE gate: it is a fact change, and calling it "style only" would be a lie
    # the system then has to live with. It is instead governed: bounded to the spans the
    # Reviewer's own findings point at, required to introduce no deterministic fact drift, and
    # valid **only** after a new draft identity plus a fresh Reviewer run.
    if semantic_res.outcome != SemanticDiffOutcome.STYLE_ONLY_SAFE and declared_fact_fix:
        fact_fix_ok, fact_fix_reason, fact_fix_details = _fact_fix_verdict(
            before_text, after_text, declared_fact_fix
        )
        audit_validation["declared_fact_fix"] = fact_fix_details
        if fact_fix_ok:
            audit_record = {
                "before": before_text,
                "diagnosis": diagnosis_dict,
                "edit_plan": edit_plan or "",
                "after": after_text,
                "validation": audit_validation,
                "metrics_before": metrics_before,
                "metrics_after": metrics_after,
                "decision": {
                    "accepted": False,
                    "status": STATUS_PENDING_REREVIEW,
                    "rollback_reason": None,
                    "semantic_outcome": OUTCOME_FACT_FIX_DECLARED,
                },
            }
            return QualityGateDecision(
                accepted=False,
                status=STATUS_PENDING_REREVIEW,
                rollback_reason=None,
                semantic_outcome=OUTCOME_FACT_FIX_DECLARED,
                shrinkage_ratio=shrinkage,
                staccato_score=staccato_drop,
                final_prose=after_text,
                audit_record=audit_record,
                required_actions=list(FACT_FIX_REQUIRED_ACTIONS),
                next_step=(
                    "事实纠错已登记，但**尚未通过审查**：必须重新 runtime ingest-draft 取得新 "
                    "draft_id，对新草稿完整重跑 Reviewer，再用 review-pipeline --save-metrics "
                    "把新审查绑定到新草稿；在此之前不得提交或发布。"
                ),
                declared_fact_fix=dict(declared_fact_fix),
            )
        reason = f"触发事实安全红线回滚：{fact_fix_reason}"
        audit_record = {
            "before": before_text,
            "diagnosis": diagnosis_dict,
            "edit_plan": edit_plan or "",
            "after": after_text,
            "validation": audit_validation,
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "decision": {
                "accepted": False,
                "status": STATUS_ROLLEDBACK,
                "rollback_reason": reason,
            },
        }
        return QualityGateDecision(
            accepted=False,
            status=STATUS_ROLLEDBACK,
            rollback_reason=reason,
            semantic_outcome=semantic_res.outcome.value,
            shrinkage_ratio=shrinkage,
            staccato_score=staccato_drop,
            final_prose=before_text,
            audit_record=audit_record,
        )

    # 3.5 Semantic Uncertainty Check (Fail-Closed on UNCERTAIN)
    if semantic_res.outcome != SemanticDiffOutcome.STYLE_ONLY_SAFE:
        reason = f"触发事实安全红线回滚：{semantic_res.summary}"
        audit_record = {
            "before": before_text,
            "diagnosis": diagnosis_dict,
            "edit_plan": edit_plan or "",
            "after": after_text,
            "validation": audit_validation,
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "decision": {
                "accepted": False,
                "status": "ROLLEDBACK",
                "rollback_reason": reason,
            },
        }
        return QualityGateDecision(
            accepted=False,
            status="ROLLEDBACK",
            rollback_reason=reason,
            semantic_outcome=semantic_res.outcome.value,
            shrinkage_ratio=shrinkage,
            staccato_score=staccato_drop,
            final_prose=before_text,
            audit_record=audit_record,
        )

    # 4. Check Passed: Accept Edited Prose
    matcher = difflib.SequenceMatcher(None, before_text, after_text)
    similarity = matcher.ratio()
    edit_footprint = 1.0 - similarity

    audit_record = {
        "before": before_text,
        "diagnosis": diagnosis_dict,
        "edit_plan": edit_plan or "",
        "after": after_text,
        "validation": audit_validation,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "decision": {
            "accepted": True,
            "status": "ACCEPTED",
            "rollback_reason": None,
        },
    }

    return QualityGateDecision(
        accepted=True,
        status="ACCEPTED",
        rollback_reason=None,
        semantic_outcome=semantic_res.outcome.value,
        shrinkage_ratio=shrinkage,
        staccato_score=staccato_drop,
        edit_footprint_ratio=round(edit_footprint, 4),
        final_prose=after_text,
        audit_record=audit_record,
    )
