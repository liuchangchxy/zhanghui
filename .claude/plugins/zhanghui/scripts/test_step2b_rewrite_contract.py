"""Historical Step 2B additions must be rejected even by an over-permissive judge."""

from pathlib import Path

import pytest

from data_modules.prose_quality_gate import evaluate_prose_quality_and_decide
from data_modules.prose_semantic_diff import SemanticDiffOutcome, compare_semantic_facts


def test_existing_action_can_be_rephrased():
    before = "他把记录本合上，一共七行。"
    after = "他合上记录本，一共七行。"
    result = compare_semantic_facts(
        before, after, semantic_judge=lambda *_: {"outcome": "STYLE_ONLY_SAFE", "changes": []}
    )
    assert result.outcome == SemanticDiffOutcome.STYLE_ONLY_SAFE
    assert evaluate_prose_quality_and_decide(before, after, result).accepted


def test_rewrite_contract_includes_historical_counterexamples():
    """Check the written contract only; this does not test automatic detection."""
    skill = (Path(__file__).resolve().parents[1] / "skills/webnovel-write/SKILL.md").read_text()
    assert "严格 rewrite-only" in skill
    assert "不得新增、删除或改变任何情节动作" in skill
    assert "候选不得增加「压了很久」" in skill
    assert "候选不得增加关门、锁舌落下及其声音" in skill


@pytest.mark.parametrize(
    "before,after",
    [
        (
            "还有两项对不上。老周把单子还给他，起身去开门。",
            "还有两项对不上。他把清点单翻到第二项，推过去一点，又收回来。老周把单子还给他，起身去开门。",
        ),
        (
            "科长说：老周打电话到科里了。",
            "科长手指在值班表边缘敲了两下，说：老周打电话到科里了。",
        ),
    ],
)
def test_historical_added_actions_are_rejected(before, after):
    result = compare_semantic_facts(
        before, after, semantic_judge=lambda *_: {"outcome": "STYLE_ONLY_SAFE", "changes": []}
    )
    assert result.outcome == SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED
    assert any(item.evidence_type == "added_action_not_in_before" for item in result.drift_items)
    gate = evaluate_prose_quality_and_decide(before, after, result)
    assert not gate.accepted
    assert gate.final_text == before
