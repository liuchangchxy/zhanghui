#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prose Quality Pipeline v2 (Issue #26).

Unified coordinator implementing:
Positive Voice Target -> Draft -> Actual Prose Diagnosis -> Targeted Editing ->
Semantic Fact Diff -> Quality Regression Check -> Accept / Rollback.

Provides both programmatic Python interface and command-line entry points.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .prose_voice_target import VoiceTarget, build_voice_target
from .prose_diagnostics import DiagnosisReport, ProseIssue, diagnose_prose
from .prose_semantic_diff import (
    SemanticDiffOutcome,
    SemanticDiffResult,
    compare_semantic_facts,
)
from .prose_quality_gate import (
    QualityGateDecision,
    evaluate_prose_quality_and_decide,
)


@dataclass
class ProsePipelineResult:
    ok: bool
    status: str  # "ACCEPTED" | "ROLLEDBACK"
    chapter: int
    before_chars: int
    after_chars: int
    diagnosis: Dict[str, Any]
    semantic_outcome: str
    rollback_reason: Optional[str]
    final_prose: str
    audit_record: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "chapter": self.chapter,
            "before_chars": self.before_chars,
            "after_chars": self.after_chars,
            "diagnosis": self.diagnosis,
            "semantic_outcome": self.semantic_outcome,
            "rollback_reason": self.rollback_reason,
            "audit_record": self.audit_record,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class ProseQualityPipeline:
    """Prose quality pipeline v2 orchestrator."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)

    def get_voice_target(self, chapter: int = 1, genre: Optional[str] = None) -> VoiceTarget:
        """Obtain positive voice target for the book/chapter."""
        return build_voice_target(self.project_root, chapter=chapter, genre=genre)

    def diagnose(self, text: str, voice_target: Optional[VoiceTarget] = None) -> DiagnosisReport:
        """Diagnose actual defects in chapter prose without global rewriting."""
        target = voice_target or self.get_voice_target()
        return diagnose_prose(text, voice_target=target)

    def format_targeted_editor_prompt(
        self,
        draft_text: str,
        diagnosis: DiagnosisReport,
        voice_target: Optional[VoiceTarget] = None,
    ) -> str:
        """Format targeted editor prompt providing diagnosis issues and strict fact boundaries."""
        target = voice_target or self.get_voice_target()
        prompt_lines = [
            target.format_prompt_block(),
            "",
            "=== 本章定向缺陷诊断 (Diagnose First) ===",
        ]
        if not diagnosis.issues:
            prompt_lines.append("本章无显著模板套话，无需大幅改写，仅在必要处做微调润色。")
        else:
            for idx, iss in enumerate(diagnosis.issues, 1):
                prompt_lines.append(
                    f"{idx}. [{iss.issue_type}] 位置: {iss.location} | 摘录: 「{iss.excerpt}」"
                )
                prompt_lines.append(f"   诊断依据: {iss.evidence} | 建议修改: {iss.suggested_intervention}")

        prompt_lines.extend([
            "",
            "=== Editor 严格操作守则 ===",
            "1. 【局部定向修改】：只针对上述诊断出的具体问题及最小必要上下文做修改，严禁全章无边界大改写！",
            "2. 【事实绝对安全】：严禁自作主张为角色编造过往经历、人脉、师承、新技能或新设定（如发现剧情漏洞，输出 SEMANTIC_CHANGE_PROPOSED，绝不得自行圆场）；",
            "3. 【保留呼吸感】：保留自然的中长句、安静过渡和正常情绪表达，严禁把全文碎切成电报体！",
            "4. 【字数保护】：润色后字数不得出现大幅异常缩水（缩水率严禁超过 15%）。",
        ])
        return "\n".join(prompt_lines)

    build_editor_prompt = format_targeted_editor_prompt

    def process_and_validate(
        self,
        before_text: str,
        after_text: str,
        chapter: int = 1,
        diagnosis_report: Optional[DiagnosisReport] = None,
        edit_plan: Optional[str] = None,
        semantic_judge: Optional[Callable[[str, str], Any]] = None,
    ) -> ProsePipelineResult:
        """
        Validate edited prose through Fact-Safe Semantic Diff & Quality Regression Gate.
        Automatically accepts safe improvements or rolls back to before_text if regressed.
        """
        diag = diagnosis_report or self.diagnose(before_text)
        decision = evaluate_prose_quality_and_decide(
            before_text=before_text,
            after_text=after_text,
            diagnosis_summary=diag.to_dict(),
            edit_plan=edit_plan,
            semantic_judge=semantic_judge,
        )

        return ProsePipelineResult(
            ok=decision.accepted,
            status=decision.status,
            chapter=chapter,
            before_chars=len(before_text),
            after_chars=len(after_text),
            diagnosis=diag.to_dict(),
            semantic_outcome=decision.semantic_outcome,
            rollback_reason=decision.rollback_reason,
            final_prose=decision.final_prose,
            audit_record=decision.audit_record,
        )
