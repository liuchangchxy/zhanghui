#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Post-edit: show-then-explain.

The 2026-10-24 lean A/B (study/experiments/2026-10-24-lean-skill-delivery-ab) showed that
removing Writer-side craft instructions lowered "too many rules" and "mechanically
executing technique", but "narrator over-explanation" got *worse*. This module repairs
that defect after the draft exists, instead of adding another pre-writing rule.

The edit is deliberately minimal: one flagged sentence is deleted, and only when the
diagnostics module has already established that it repeats the previous sentence and
carries no new number or judgement. Nothing else in the paragraph is touched.

The caller is expected to validate the result through
``ProseQualityPipeline.process_and_validate``, which rolls back on shrinkage, staccato
rhythm or semantic drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .prose_diagnostics import DiagnosisReport, detect_show_then_explain


@dataclass
class ShowThenExplainEdit:
    removed: List[str] = field(default_factory=list)
    skipped: List[Dict[str, str]] = field(default_factory=list)

    @property
    def applied_count(self) -> int:
        return len(self.removed)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.applied_count + len(self.skipped),
            "applied": self.applied_count,
            "skipped": len(self.skipped),
            "removed": list(self.removed),
            "skipped_reasons": list(self.skipped),
        }


def apply_single_edit(text: str, sentence: str) -> Tuple[Optional[str], str]:
    """Delete exactly one sentence. Returns ``(new_text, reason)``; text is None on skip."""
    sentence = str(sentence or "").strip()
    if not sentence:
        return None, "empty"
    occurrences = text.count(sentence)
    if occurrences == 0:
        return None, "not_found"
    if occurrences > 1:
        # Deleting the wrong copy is worse than leaving both.
        return None, "ambiguous_duplicate"

    paragraphs = text.split("\n\n")
    for index, paragraph in enumerate(paragraphs):
        if sentence not in paragraph:
            continue
        new_paragraph = paragraph.replace(sentence, "", 1).strip()
        if not new_paragraph.strip("。！？ \n"):
            if any(mark in paragraph for mark in ("“", "\"")):
                return None, "paragraph_protected"
            paragraphs[index] = ""
        else:
            paragraphs[index] = new_paragraph
        rebuilt = "\n\n".join(p for p in paragraphs if p.strip())
        return rebuilt.rstrip() + "\n", "applied"
    return None, "not_found"


def apply_show_then_explain_edits(
    text: str,
    report: DiagnosisReport | None = None,
) -> Tuple[str, ShowThenExplainEdit]:
    """Delete each flagged restatement sentence; leave everything else untouched.

    Ungated: the pipeline applies these one at a time and keeps only the edits the
    quality gate accepts.
    """
    report = report or DiagnosisReport(total_chars=len(text), paragraph_count=0)
    if not report.issues:
        report.issues = detect_show_then_explain(
            [p.strip() for p in text.split("\n\n") if p.strip()]
        )

    edit = ShowThenExplainEdit()
    current = text
    for issue in report.issues:
        if issue.issue_type != "show_then_explain":
            continue
        sentence = str(issue.excerpt or "").strip()
        new_text, reason = apply_single_edit(current, sentence)
        if new_text is None:
            edit.skipped.append({"sentence": sentence, "reason": reason})
            continue
        current = new_text
        edit.removed.append(sentence)
    return current, edit
