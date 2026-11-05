"""Historical Step 2B additions must be rejected even by an over-permissive judge."""

import json
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


@pytest.mark.parametrize(
    "before_key,after_key,excerpt",
    [("003_A", "003_B", "压了很久"), ("005_before", "005_after", "门在身后合上"), ("006_B", "006_C", "扳手搁下")],
)
def test_full_historical_chapters_reject_added_beats(before_key, after_key, excerpt):
    fixture = Path(__file__).parent / "tests/fixtures/step2b_historical_prose.json"
    texts = json.loads(fixture.read_text(encoding="utf-8"))
    before, after = texts[before_key], texts[after_key]
    result = compare_semantic_facts(
        before, after, semantic_judge=lambda *_: {"outcome": "STYLE_ONLY_SAFE", "changes": []}
    )
    assert any(excerpt in item.edited_excerpt for item in result.drift_items)
    assert result.outcome == SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED
    assert evaluate_prose_quality_and_decide(before, after, result).final_text == before


@pytest.mark.parametrize("before,after", [
    ("他把扳手放下。随后他说话。", "他把扳手放下。随后他把扳手搁下，说话。"),
    ("她把书合上，放在桌边。", "她合上书，放在桌边。"),
])
def test_repeated_beat_and_rephrasing(before, after):
    result = compare_semantic_facts(before, after, semantic_judge=lambda *_: {"outcome": "STYLE_ONLY_SAFE", "changes": []})
    expected = SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED if "搁下" in after else SemanticDiffOutcome.STYLE_ONLY_SAFE
    assert result.outcome == expected


@pytest.mark.parametrize("before,after", [
    ("手心压在封皮上。", "手心压在封皮上，压了很久。"),
    ("他压着。", "他压了很久。"),
])
def test_added_duration_including_shared_verb(before, after):
    from data_modules.prose_semantic_diff import detect_added_events
    assert any("很久" in item.edited_excerpt for item in detect_added_events(before, after))


@pytest.mark.parametrize("before,after", [
    ("他把扳手放下，转身说话。她打开门。", "她打开门。他把扳手搁下，转身说话。"),
    ("他把扳手放下。随后他说话。", "他说完后把扳手搁下。"),
    ("他按了很久，终于松手。她按了很久，终于松手。", "她按了很久，终于松手。他按了很久，终于松手。"),
    ("他把扳手放下，说了一句。她把扳手放下，说了两句。", "他把扳手搁下，说了一句。她把扳手搁下，说了两句。"),
])
def test_reordered_and_synonymous_actions_are_not_added(before, after):
    from data_modules.prose_semantic_diff import detect_added_events
    assert not detect_added_events(before, after)


def test_duration_rewording_is_not_added():
    from data_modules.prose_semantic_diff import detect_added_events
    assert not detect_added_events("他压了很久。", "他压了许久。")


def test_historical_added_duration_not_cancelled_by_unrelated_removed_duration():
    fixture = Path(__file__).parent / "tests/fixtures/step2b_historical_prose.json"
    texts = json.loads(fixture.read_text(encoding="utf-8"))
    before = texts["003_A"] + "\n她停了很久。"
    after = texts["003_B"] + "\n她停下。"
    result = compare_semantic_facts(
        before, after, semantic_judge=lambda *_: {"outcome": "STYLE_ONLY_SAFE", "changes": []}
    )
    assert any("压了很久" in item.edited_excerpt for item in result.drift_items)
    gate = evaluate_prose_quality_and_decide(before, after, result)
    assert not gate.accepted
    assert gate.final_text == before


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
