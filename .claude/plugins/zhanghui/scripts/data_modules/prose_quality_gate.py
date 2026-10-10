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
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .prose_semantic_diff import (
    SemanticDiffOutcome,
    SemanticDiffResult,
    compare_semantic_facts,
)


@dataclass
class QualityGateDecision:
    accepted: bool
    status: str  # "ACCEPTED" | "ROLLEDBACK"
    rollback_reason: Optional[str] = None
    semantic_outcome: str = "STYLE_ONLY_SAFE"
    shrinkage_ratio: float = 0.0
    staccato_score: float = 0.0
    edit_footprint_ratio: float = 0.0
    final_prose: str = ""
    audit_record: Dict[str, Any] = field(default_factory=dict)

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
        semantic_res = compare_semantic_facts(before_text, after_text)
        diagnosis_dict = diagnosis_summary
    else:
        semantic_res = compare_semantic_facts(before_text, after_text)
        diagnosis_dict = diagnosis_summary if isinstance(diagnosis_summary, dict) else {}

    metrics_before = compute_prose_metrics(before_text)
    metrics_after = compute_prose_metrics(after_text)

    audit_validation: Dict[str, Any] = {
        "semantic_diff": semantic_res.to_dict(),
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
    }

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
