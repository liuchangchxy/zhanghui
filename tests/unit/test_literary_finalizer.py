#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract tests for the formal literary-subtraction finalizer (Step 2B).

These pin the mechanism the integration relies on, not theoretical edge cases:
  1. the prompt/CLI is callable and carries the frozen five principles + guards;
  2. a candidate below the 90% length floor is rejected;
  3. a candidate that changes a number/date/ID never reaches final prose;
  4. rejection returns the Writer raw (including its CHANGES block) untouched;
  5. the old duplicate literary-polish pass (Step 2B rewrite-only + Step 4 polish)
     is no longer instructed by the skill.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from data_modules import webnovel
from data_modules.literary_finalizer import (
    build_finalizer_prompt,
    decide_finalizer_candidate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / ".claude" / "plugins" / "zhanghui" / "skills" / "webnovel-write" / "SKILL.md"
FAST_SKILL = (
    REPO_ROOT / ".claude" / "plugins" / "zhanghui" / "skills" / "webnovel-fast-write" / "SKILL.md"
)

CHANGES = (
    "<chapter_changes>\n"
    + json.dumps(
        {
            "character_state_changes": [],
            "new_plot_points": [],
            "foreshadowing_actions": [],
            "location_state_changes": [],
            "faction_state_changes": [],
            "time_progression": None,
            "item_transfers": [],
            "unresolved_questions": [],
        },
        ensure_ascii=False,
    )
    + "\n</chapter_changes>\n"
)


def _source() -> str:
    return (
        "## 第3章 旧城问路\n\n"
        "晨光从档案屋百叶窗缝里挤进来时，昨夜的潮气还没散尽。林越把压书板从第67页上撤走，"
        "纸背那两个铅笔数字又露出来：19、7。轻得像谁翻页时随手划下的，可他盯了一夜也没盯出眉目。\n\n"
        "“你查这个做什么？”乔宁把茶杯放回桌上，杯底磕出一声轻响。\n\n"
        "林越听懂了。这说明乔宁早就知道这两个数字的含义。\n\n"
        "“一九九九年八月八日，七号泵房。”他说。\n\n"
        "乔宁没有立刻回答。他把窗子推开一条缝，潮气从缝里钻进来，带着铁锈味。"
        "外面渡轮的汽笛压过屋里的沉默，拖得很长。\n\n"
        "“系统里的东西会被同步覆盖，”乔宁说，“纸不会。手写的，进网之前就填好的，改不动。”\n\n"
        "林越把这句话记下来。这意味着他必须去找纸质的交接班登记簿，而且得赶在旧档被收走之前。\n\n"
        "他把工具一件一件收进箱子，扣上锁扣。桌上的茶杯还在冒一点白气。\n\n"
        "“值班表也别看公示屏。”乔宁在他背后补了一句。\n\n"
        "林越走到门口，手放在门把上，停了一下。\n\n"
        "外面的雨还在下，落在巷子的青石板上，声音很密。"
    ) + CHANGES


def _candidate(delete_explanation: bool = True) -> str:
    text = _source().split("<chapter_changes>")[0].rstrip() + "\n"
    if delete_explanation:
        text = text.replace("林越听懂了。这说明乔宁早就知道这两个数字的含义。\n\n", "")
    return text


def _fake_judge(outcome: str = "STYLE_ONLY_SAFE"):
    def _judge(_before: str, _after: str) -> dict:
        return {"outcome": outcome, "changes": []}

    return _judge


# --------------------------------------------------------------------------- #
# 1. callable prompt
# --------------------------------------------------------------------------- #


def test_finalizer_prompt_is_callable_and_carries_the_frozen_contract(tmp_path: Path, capsys):
    project = tmp_path / "book"
    (project / ".webnovel").mkdir(parents=True)
    (project / ".webnovel" / "state.json").write_text(
        json.dumps({"project_info": {"title": "潮汐档案", "genre": "悬疑"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    draft = project / "draft.md"
    draft.write_text(_source(), encoding="utf-8")
    ctx = project / "ctx.json"
    ctx.write_text(
        json.dumps(
            {
                "story_identity": {"title": "潮汐档案", "genre": "悬疑"},
                "current_intent": {
                    "outline": "- 目标：林越追查纸背数字\n- 章末未闭合问题：登记簿在哪",
                    "directive": {"goal": "林越追查纸背数字", "forbidden_zones": []},
                },
                "constraints": {"system_constraints": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    voice = project / "voice.txt"
    voice.write_text("=== 文风锚 ===\n克制、短句、动作推进。\n", encoding="utf-8")
    prompt_file = project / "prompt.txt"
    source_file = project / "source.md"

    argv = [
        "webnovel",
        "--project-root",
        str(project),
        "prose",
        "literary-finalize-prompt",
        "--chapter",
        "3",
        "--draft-file",
        str(draft),
        "--governed-context",
        str(ctx),
        "--voice-target-file",
        str(voice),
        "--output",
        str(prompt_file),
        "--source-output",
        str(source_file),
        "--format",
        "json",
    ]
    old_argv = sys.argv
    try:
        sys.argv = argv
        with pytest.raises(SystemExit) as exc:
            webnovel.main()
    finally:
        sys.argv = old_argv

    assert exc.value.code == 0
    prompt = prompt_file.read_text(encoding="utf-8")
    assert "【只做这五条】" in prompt
    assert "三条护栏" in prompt
    assert "删解释，不删承载解释的东西" in prompt or "独立短钩子" in prompt
    assert "【原文】" in prompt
    assert "林越听懂了" in prompt
    assert "<chapter_changes>" not in prompt
    assert source_file.is_file()
    assert "<chapter_changes>" not in source_file.read_text(encoding="utf-8")


def test_prompt_builder_rejects_empty_source():
    with pytest.raises(ValueError):
        build_finalizer_prompt(source="", outline="", constraints="")


# --------------------------------------------------------------------------- #
# 2. length floor
# --------------------------------------------------------------------------- #


def test_candidate_below_90_percent_is_rejected_and_raw_is_kept():
    before = _source()
    candidate = "\n\n".join(before.split("<chapter_changes>")[0].split("\n\n")[:3]) + "\n"

    decision = decide_finalizer_candidate(before, candidate, semantic_judge=_fake_judge())

    assert decision.accepted is False
    assert any("LENGTH_BELOW_FLOOR" in r for r in decision.reasons)
    assert decision.final_text == before


# --------------------------------------------------------------------------- #
# 3. hard fact token changes
# --------------------------------------------------------------------------- #


def test_changed_date_is_rejected_and_never_reaches_final_prose():
    before = _source()
    candidate = _candidate().replace("一九九九年八月八日", "一九九九年八月九日")

    decision = decide_finalizer_candidate(before, candidate, semantic_judge=_fake_judge())

    assert decision.accepted is False
    assert "八月八日" in decision.missing_dates
    assert "八月九日" in decision.added_dates
    assert any("FACT_TOKEN_CHANGED" in r for r in decision.reasons)
    assert decision.final_text == before
    assert "八月九日" not in decision.final_text


def test_added_number_is_rejected_as_a_new_fact():
    before = _source()
    candidate = _candidate().replace("七号泵房。”他说。", "七号泵房，2024年。”他说。")

    decision = decide_finalizer_candidate(before, candidate, semantic_judge=_fake_judge())

    assert decision.accepted is False
    assert "2024" in decision.added_numbers
    assert decision.final_text == before


# --------------------------------------------------------------------------- #
# 4. fallback preserves the Writer raw, including CHANGES
# --------------------------------------------------------------------------- #


def test_semantic_rejection_returns_writer_raw_with_changes_intact():
    before = _source()
    candidate = _candidate()

    decision = decide_finalizer_candidate(
        before, candidate, semantic_judge=_fake_judge("SEMANTIC_CHANGE_PROPOSED")
    )

    assert decision.accepted is False
    assert decision.final_text == before
    assert "<chapter_changes>" in decision.final_text
    assert "SEMANTIC_GATE_REJECTED" in " ".join(decision.reasons)


def test_accepted_candidate_is_returned_only_when_the_gate_passes():
    before = _source()
    candidate = _candidate()

    decision = decide_finalizer_candidate(before, candidate, semantic_judge=_fake_judge())

    assert decision.accepted is True
    assert decision.final_text == candidate
    assert decision.semantic_outcome == "STYLE_ONLY_SAFE"
    assert decision.length_ratio >= 0.90
    assert "<chapter_changes>" not in decision.final_text


# --------------------------------------------------------------------------- #
# 5. no duplicate old literary polish in the formal skill
# --------------------------------------------------------------------------- #


def test_skill_has_one_literary_pass_and_step4_no_longer_polishes():
    text = SKILL.read_text(encoding="utf-8")
    assert "### Step 2B：文学减法定稿" in text
    assert "### Step 2B：文风适配" not in text
    assert "唯一的文学编辑环节" in text
    assert "references/style-adapter.md" not in text

    step2b = text[text.index("### Step 2B："): text.index("### Step 3：")]
    step4 = text[text.index("### Step 4："): text.index("### Step 4.5：")]
    assert "不得对同一章重复生成" in step2b
    assert "不再承担整章文学润色" in step4
    assert "references/polish-guide.md" not in step4
    assert "只处理 Step 3 Reviewer 定位的" in step4

    fast = FAST_SKILL.read_text(encoding="utf-8")
    assert "跳过 Step 2B（文学减法定稿）" in fast
    assert "快车道跳过 2B 文学减法" in fast
