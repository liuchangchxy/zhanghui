#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 2B must not accept an added action just because the Judge says STYLE_ONLY_SAFE.

The host model is the Semantic Judge in normal operation, so a wrong `STYLE_ONLY_SAFE`
verdict is a product-level hole, not an operator mistake. The deterministic guard has to
stand on its own: an after-only clause with a material action verb, no matching action on
the same object in the original, is a new event.

Allowed rephrasings are covered too — reordering an existing action, rewriting rhythm and
tone, and tweaking environment description must stay style-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "plugins" / "zhanghui" / "scripts"
for path in (SCRIPTS, SCRIPTS.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from data_modules.prose_quality_gate import evaluate_prose_quality_and_decide  # noqa: E402
from data_modules.prose_semantic_diff import (  # noqa: E402
    SemanticDiffOutcome,
    compare_semantic_facts,
)


def _style_only_judge(before: str, after: str):
    """A Judge that always (and here, wrongly) claims the edit is style-only."""
    return {"outcome": "STYLE_ONLY_SAFE", "changes": []}


# --------------------------------------------------------------------------- #
# Allowed: same events, different surface
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "before, after",
    [
        # action reordered around the same object
        ("他把记录本合上，一共七行。", "他合上记录本，一共七行。"),
        # rhythm/tone rewrite; no new beat
        (
            "不得不说，梅叔这个人其实并不好打交道。\n"
            "林越心中暗自想到，今晚必须要拿到那本账册。\n"
            "他深吸了一口冷气，走上前去，敲了敲油腻的柜台。\n",
            "梅叔在黑街里出了名的难打交道。\n"
            "今晚无论如何得拿到那本账册。\n"
            "林越裹紧领口迎着冷风走上前，抬手扣了扣油腻的柜台。\n",
        ),
        # environment description tweak, no new action
        (
            "雨下到后半夜，渐渐变成了细密的雨丝。檐角滴着水。",
            "雨下到后半夜，已化作细密的雨丝。檐角的水滴得更急了。",
        ),
    ],
)
def test_existing_beat_rewrites_remain_style_only_safe(before: str, after: str):
    result = compare_semantic_facts(before, after, semantic_judge=_style_only_judge)

    assert result.outcome == SemanticDiffOutcome.STYLE_ONLY_SAFE
    assert result.safe is True
    gate = evaluate_prose_quality_and_decide(before, after, result)
    assert gate.accepted is True


# --------------------------------------------------------------------------- #
# Rejected: new action / interaction / discovery / causality
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "before, after, expected_evidence",
    [
        # Added object manipulation: the original has no "翻清单"
        (
            "他把记录本合上。",
            "他把记录本合上，又翻开清单逐项查看。",
            "added_action_not_in_before",
        ),
        # Added movement to a new location
        (
            "他站在屋里，看着桌上那摞还没清完的单子。",
            "他站在屋里，看着桌上那摞还没清完的单子，忽然走到窗边。",
            "added_action_not_in_before",
        ),
        # Added inspection
        ("他拿起外套。", "他拿起外套，检查钥匙。", "added_action_not_in_before"),
        # Added character interaction
        ("他站在门口。", "他站在门口，拉住老周的手。", "added_action_not_in_before"),
        # Added discovery
        ("屋里很静。", "屋里很静，他发现桌上多了一把钥匙。", "added_action_not_in_before"),
        # Added causality
        ("他回到工位。", "因为下雨，他留在工位。", "added_causality_not_in_before"),
    ],
)
def test_added_beat_is_blocked_even_when_judge_says_style_only(
    before: str, after: str, expected_evidence: str
):
    result = compare_semantic_facts(before, after, semantic_judge=_style_only_judge)

    assert result.outcome == SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED
    assert result.safe is False
    assert any(item.evidence_type == expected_evidence for item in result.drift_items)

    gate = evaluate_prose_quality_and_decide(before, after, result)
    assert gate.accepted is False
    assert gate.status == "ROLLEDBACK"
    assert gate.final_text == before


def test_guard_runs_before_the_judge_and_cannot_be_overridden_by_it():
    """The wrong verdict is not even the deciding input: the guard fires deterministically."""
    calls: list[tuple[str, str]] = []

    def judge(before: str, after: str):
        calls.append((before, after))
        return {"outcome": "STYLE_ONLY_SAFE", "changes": []}

    before = "他把记录本合上。"
    after = "他把记录本合上，又翻开清单逐项查看。"
    result = compare_semantic_facts(before, after, semantic_judge=judge)

    assert result.outcome == SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED
    # A deterministic block does not need the Judge's permission, so it is never consulted.
    assert calls == []
