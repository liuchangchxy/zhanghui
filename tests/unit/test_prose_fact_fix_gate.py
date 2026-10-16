#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Three-way distinction in the prose gate (independent-acceptance follow-up, issue 1).

    legal in-flight draft fact correction  → PENDING_REREVIEW (bounded, owes a fresh review)
    illegal fact tampering                 → ROLLEDBACK
    pure style modification                → ACCEPTED (STYLE_ONLY_SAFE)

The old gate only had ACCEPTED/ROLLEDBACK, and its only way to accept a fact change was to
have a Judge call it `STYLE_ONLY_SAFE`. That forced a legitimate "七行 → 八行" correction to be
either mislabelled as style or rolled back — both wrong.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "plugins" / "zhanghui" / "scripts"
for path in (SCRIPTS, SCRIPTS.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


BEFORE = "他翻开记录本，数了一遍。\n记录本上共有七行。\n他把数字抄了下来。\n"
FACT_FIXED = BEFORE.replace("七行", "八行")
STYLE_EDIT = BEFORE.replace("他把数字抄了下来。", "他把那个数字抄了下来。")
TAMPERED = BEFORE.replace("记录本上共有七行。", "记录本上共有七行，而且他早就知道这件事。")
# a change entirely outside the span the Reviewer pointed at
OUT_OF_SPAN_EDIT = BEFORE.replace("他把数字抄了下来。", "他把数字抄了下来，又讲给了同事听。")
REWRITE = BEFORE + "他把整本记录本重新抄了一遍，又把每一页都拍了照。\n"


def _declaration(before: str, span_text: str = "记录本上共有七行。", *, kind: str = "LOCAL_FACT") -> dict:
    """The declaration `prose validate --revision-plan` builds from a revision plan.

    `span_text` is the smallest editable region the Reviewer's finding pointed at — the gate
    checks that the edit set stays inside it.
    """
    start = before.index(span_text)
    return {
        "source": "revision_plan",
        "draft_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
        "target_ids": ["issue-000-test"],
        "spans": [
            {"start": start, "end": start + len(span_text), "kind": kind, "issue_id": "issue-000-test"}
        ],
    }


def _gate(before: str, after: str, **kwargs):
    from data_modules.prose_quality_gate import evaluate_prose_quality_and_decide

    return evaluate_prose_quality_and_decide(before, after, **kwargs)


# --------------------------------------------------------------------------- #
# 1. legal fact correction
# --------------------------------------------------------------------------- #


def test_legal_fact_correction_is_not_rolled_back():
    decision = _gate(BEFORE, FACT_FIXED, declared_fact_fix=_declaration(BEFORE))

    assert decision.status == "PENDING_REREVIEW"
    assert decision.semantic_outcome == "FACT_FIX_DECLARED"
    assert decision.rollback_reason is None
    assert decision.final_prose == FACT_FIXED


def test_legal_fact_correction_is_not_disguised_as_style_only():
    decision = _gate(BEFORE, FACT_FIXED, declared_fact_fix=_declaration(BEFORE))

    assert decision.semantic_outcome != "STYLE_ONLY_SAFE"
    assert decision.accepted is False, "事实纠错不等于「已通过审查」"
    assert decision.required_actions
    actions = " ".join(a.lower() for a in decision.required_actions)
    assert "ingest-draft" in actions
    assert "reviewer" in actions
    assert "尚未通过审查" in decision.next_step


def test_pending_rereview_is_never_an_acceptance():
    """`ok` 必须为假：任何下游都不得把它当成已审正文。"""
    from data_modules.prose_pipeline import ProseQualityPipeline

    result = ProseQualityPipeline(Path(".")).process_and_validate(
        BEFORE, FACT_FIXED, chapter=1, declared_fact_fix=_declaration(BEFORE)
    )
    payload = result.to_dict()

    assert result.ok is False
    assert payload["status"] == "PENDING_REREVIEW"
    assert payload["gate"] == "PENDING_REREVIEW"
    assert payload["requires_rereview"] is True
    assert payload["semantic_outcome"] == "FACT_FIX_DECLARED"


def test_fact_correction_without_any_declaration_still_fails_closed():
    """未声明的改写仍然 fail-closed —— 事实纠错路径不是「免检通道」。"""
    decision = _gate(BEFORE, FACT_FIXED)
    assert decision.status == "ROLLEDBACK"
    assert decision.semantic_outcome == "UNCERTAIN"


# --------------------------------------------------------------------------- #
# 2. illegal tampering
# --------------------------------------------------------------------------- #


def test_change_outside_the_declared_span_is_rolled_back():
    """声明只覆盖审查指到的那一句；其它句子的改动仍然越界。"""
    decision = _gate(BEFORE, OUT_OF_SPAN_EDIT, declared_fact_fix=_declaration(BEFORE))

    assert decision.status == "ROLLEDBACK"
    assert decision.final_prose == BEFORE
    assert "越出 LOCAL_FACT 区间" in decision.rollback_reason


def test_extra_text_added_inside_the_span_needs_the_reviewer_to_decide():
    """段落内的追加文字落在声明区间内 → 不能靠确定性层自动放行或自动否掉，
    必须交给强制重审；这正是 PENDING_REREVIEW 存在的意义。"""
    decision = _gate(BEFORE, TAMPERED, declared_fact_fix=_declaration(BEFORE))

    assert decision.status == "PENDING_REREVIEW"
    assert decision.accepted is False
    assert any("reviewer" in a for a in decision.required_actions)


def test_chapter_rewrite_declared_as_a_fact_fix_is_rolled_back():
    decision = _gate(BEFORE, REWRITE, declared_fact_fix=_declaration(BEFORE))

    assert decision.status == "ROLLEDBACK"
    assert decision.final_prose == BEFORE


def test_declaration_for_another_draft_is_rolled_back():
    """修订计划为另一版草稿生成时，声明与当前正文不匹配。"""
    stale = dict(_declaration(BEFORE))
    stale["draft_sha256"] = "0" * 64
    decision = _gate(BEFORE, FACT_FIXED, declared_fact_fix=stale)

    assert decision.status == "ROLLEDBACK"
    assert "与当前正文不一致" in decision.rollback_reason


def test_declaration_without_local_fact_spans_is_rolled_back():
    decision = _gate(
        BEFORE, FACT_FIXED, declared_fact_fix=_declaration(BEFORE, kind="STYLE_ONLY")
    )

    assert decision.status == "ROLLEDBACK"
    assert "没有 LOCAL_FACT 目标" in decision.rollback_reason


def test_deterministic_fact_drift_still_hard_blocks_even_when_declared():
    """确定性层抓到的事实漂移优先于任何声明。"""
    before = "那把钥匙由老周保管。"
    after = "那把钥匙由郑培保管。"
    declaration = {
        "source": "revision_plan",
        "draft_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
        "spans": [{"start": 0, "end": len(before), "kind": "LOCAL_FACT", "issue_id": "i"}],
    }
    decision = _gate(before, after, declared_fact_fix=declaration)

    assert decision.status == "ROLLEDBACK"
    assert decision.semantic_outcome == "SEMANTIC_CHANGE_PROPOSED"
    assert decision.final_prose == before


# --------------------------------------------------------------------------- #
# 3. pure style
# --------------------------------------------------------------------------- #


def test_pure_style_edit_is_still_accepted_as_style_only_safe():
    """纯风格修改走 Judge 判定为 STYLE_ONLY_SAFE → 接受（与事实纠错路径互不影响）。"""
    from data_modules.prose_judge_host import bind_judge_response, make_bound_judge_callable

    verdict = bind_judge_response(
        {"outcome": "STYLE_ONLY_SAFE", "changes": []}, BEFORE, STYLE_EDIT, chapter=1
    )
    decision = _gate(
        BEFORE, STYLE_EDIT, semantic_judge=make_bound_judge_callable(verdict, BEFORE, STYLE_EDIT)
    )

    assert decision.status == "ACCEPTED"
    assert decision.accepted is True
    assert decision.semantic_outcome == "STYLE_ONLY_SAFE"
    assert decision.required_actions == []


def test_style_path_without_a_judge_still_fails_closed():
    """没有 Judge 背书时，非事实纠错路径仍然 fail-closed（没有放宽安全检查）。"""
    decision = _gate(BEFORE, STYLE_EDIT)
    assert decision.status == "ROLLEDBACK"
    assert decision.semantic_outcome == "UNCERTAIN"


def test_style_edit_inside_the_declared_span_is_not_rolled_back():
    """声明区间内的表达改动不会因为存在事实声明就被否掉。"""
    # STYLE_EDIT only rewrites the third line, so declare a span covering exactly that line
    declaration = _declaration(BEFORE, "他把数字抄了下来。")
    decision = _gate(BEFORE, STYLE_EDIT, declared_fact_fix=declaration)

    assert decision.status != "ROLLEDBACK"
    assert decision.final_prose == STYLE_EDIT


def test_out_of_plan_style_edit_is_refused_while_a_declaration_is_in_force():
    """带声明时「只允许计划内改动」是硬契约：计划外的句子即使是风格改动也退回计划。"""
    declaration = _declaration(BEFORE)  # only the numeric sentence is declared
    decision = _gate(BEFORE, STYLE_EDIT, declared_fact_fix=declaration)

    assert decision.status == "ROLLEDBACK"
    assert "越出 LOCAL_FACT 区间" in decision.rollback_reason
