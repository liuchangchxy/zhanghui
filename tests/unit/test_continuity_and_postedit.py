#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round-4 A/B: continuity facts and show-then-explain post-edit.

See study/experiments/2026-10-24-lean-continuity-postedit-ab/.
"""
from __future__ import annotations

from data_modules.chapter_runtime import (
    CONTINUITY_FACT_BUDGET_CHARS,
    render_continuity_facts,
    select_continuity_facts,
)
from data_modules.prose_diagnostics import detect_show_then_explain, diagnose_prose
from data_modules.prose_postedit import apply_show_then_explain_edits


def _canon() -> dict:
    return {
        "appearing_characters": [
            {"entity_id": "jiubaoku", "name": "旧报库", "type": "地点"},
            {"entity_id": "difangzhi", "name": "地方志办公室", "type": "地点"},
            {"entity_id": "xu_zhiyuan", "name": "许知远", "type": "角色"},
        ],
        "canon_items": [
            {
                "chapter": 2,
                "content": {
                    "event_type": "world_rule_revealed",
                    "payload": {
                        "rule_content": "旧报库在门口登记簿写下姓名与进库时间即可查阅，不需要授权。"
                    },
                },
            },
            {
                "chapter": 2,
                "content": {
                    "from_entity": "xu_zhiyuan",
                    "to_entity": "jiubaoku",
                    "relationship": "只在公开渠道查证，不留下调阅记录",
                },
            },
            {
                "chapter": 2,
                "content": {
                    "entity_id": "tongxin_zhongduan",
                    "field": "attributes.model",
                    "value": "TX-2015",
                },
            },
        ],
    }


def test_continuity_block_quotes_accepted_setting_and_rules():
    prose = {
        2: (
            "旧报库在报社后院，门口一本登记簿，写上日期就能进。\n\n"
            "许知远走进旧报库，把包放在桌上。\n\n"
            "地方志办公室在城西，一栋老楼的三层。"
        )
    }
    facts = select_continuity_facts(_canon(), prose)
    texts = [fact["text"] for fact in facts]

    assert "旧报库在报社后院，门口一本登记簿，写上日期就能进。" in texts
    assert "地方志办公室在城西，一栋老楼的三层。" in texts
    assert any("登记簿写下姓名与进库时间" in text for text in texts)
    # A sentence carrying a named character is a scene beat, not a setting fact.
    assert not any("许知远走进旧报库" in text for text in texts)
    # Internal entity ids never reach the Writer.
    assert not any("tongxin_zhongduan" in text for text in texts)
    # Relationship ids are resolved to names.
    assert any(text.startswith("许知远 与 旧报库") for text in texts)


def test_continuity_block_respects_the_budget():
    canon = _canon()
    canon["canon_items"] = [
        {
            "chapter": 3 + index,
            "content": {
                "event_type": "world_rule_revealed",
                "payload": {"rule_content": f"规则{index}：" + "很长的既有流程说明。" * 12},
            },
        }
        for index in range(20)
    ]
    facts = select_continuity_facts(canon, {})
    total = sum(len(fact["text"]) + 3 for fact in facts)
    assert total <= CONTINUITY_FACT_BUDGET_CHARS
    assert facts, "at least one fact should survive the budget"


def test_continuity_render_is_empty_without_facts():
    assert render_continuity_facts([]) == []


def test_show_then_explain_removes_restatement_but_keeps_new_inference():
    text = (
        "他把纸折好，塞回档案袋。日期对不上。\n\n"
        "也就是说，这份记录有人动过手脚。\n\n"
        "他终于明白，动手脚的人只能接触夜班登记册。"
    )
    issues = detect_show_then_explain([p for p in text.split("\n\n") if p.strip()])
    flagged = [issue.excerpt for issue in issues]
    assert flagged == ["也就是说，这份记录有人动过手脚。"]

    after, edit = apply_show_then_explain_edits(text)
    assert edit.applied_count == 1
    assert "也就是说" not in after
    # A conclusion that carries a new judgement is not a restatement.
    assert "只能接触夜班登记册" in after


def test_show_then_explain_leaves_dialogue_alone():
    text = "他说：“我明白了。”\n\n“他终于明白，这不是巧合。”"
    after, edit = apply_show_then_explain_edits(text)
    assert edit.applied_count == 0
    assert after == text


def test_diagnose_prose_reports_show_then_explain():
    report = diagnose_prose("日期对不上。\n\n也就是说，这份记录被人改过。")
    assert "show_then_explain" in report.issue_counts_by_type


def test_declared_deletion_passes_gate_but_cannot_hide_a_rewrite():
    from data_modules.prose_quality_gate import evaluate_prose_quality_and_decide

    filler = "他在桌前坐下，把纸翻到背面，又翻回来。" * 30
    sentence = "也就是说，这份记录有人动过手脚。"
    before = f"钥匙由林越保管。{filler}{sentence}"
    after = f"钥匙由林越保管。{filler}"

    accepted = evaluate_prose_quality_and_decide(
        before, after, declared_redundant=[sentence]
    )
    assert accepted.accepted, accepted.rollback_reason

    # A claim rewrite is not the declared deletion, so the semantic diff still runs.
    rewritten = f"钥匙由韩策保管。{filler}"
    rejected = evaluate_prose_quality_and_decide(
        before, rewritten, declared_redundant=[sentence]
    )
    assert not rejected.accepted
