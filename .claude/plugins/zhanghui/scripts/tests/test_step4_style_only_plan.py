#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 4 must only plan expression edits.

The old plan routed every prose-category finding (setting / timeline / continuity /
character / logic) into the prose edit loop. Those can only be "fixed" by changing a fact,
which is exactly how Step 4 produced semantic drift and got rolled back. These tests pin the
style-only contract: fact findings are deferred to their owner, expression findings and
`prose diagnose` spans remain editable.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # tests/ → scripts/ → plugin/
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from data_modules.revision_planner import (  # noqa: E402
    OWNER_FACT_REVIEW,
    OWNER_PROSE_EDIT,
    build_revision_plan,
)

DRAFT = """他从怀里摸出那封旧信，指节发白。

梅叔站在门口，眸中闪过一丝复杂的神色。

“你终于来了。”梅叔说。
"""


def _review(*issues: dict) -> dict:
    return {"chapter": 3, "issues": list(issues)}


def _issue(category: str, location: str, evidence: str, **extra) -> dict:
    return {
        "severity": "high",
        "category": category,
        "location": location,
        "description": f"{category} problem",
        "evidence": evidence,
        "fix_hint": "修正",
        "blocking": False,
        **extra,
    }


CONTINUITY = _issue("continuity", "第1段", "那封旧信", gate_id="canon.contradiction")
STYLE = _issue("ai_flavor", "第2段", "眸中闪过一丝复杂的神色")

DIAGNOSIS = {
    "issues": [
        {
            "issue_type": "stock_phrase",
            "location": "第2段",
            "excerpt": "眸中闪过一丝复杂的神色",
            "evidence": "陈词滥调神态描写",
            "suggested_intervention": "改为具体言行反应",
        }
    ]
}


def test_style_only_defers_fact_findings_and_keeps_expression_targets():
    plan = build_revision_plan(
        DRAFT,
        _review(CONTINUITY, STYLE),
        chapter=3,
        require_review_binding=False,
        active_draft={},
        style_only=True,
        diagnosis=DIAGNOSIS,
    )

    target_ids = {t["issue_id"] for t in plan["targets"]}
    assert not any(t["category"] == "continuity" for t in plan["targets"])
    assert "diagnosis-" in " ".join(target_ids)
    assert any(t["category"] == "ai_flavor" for t in plan["targets"])
    assert plan["style_only"] is True
    assert plan["summary"]["diagnosis_targets"] == 1

    deferred_owners = {item["owner"] for item in plan["deferred"]}
    assert OWNER_FACT_REVIEW in deferred_owners
    assert all(item.get("repair_hint") for item in plan["deferred"])
    assert plan["summary"]["deferred_by_owner"][OWNER_FACT_REVIEW] == 1


def test_without_style_only_the_same_fact_finding_is_planned():
    plan = build_revision_plan(
        DRAFT,
        _review(CONTINUITY),
        chapter=3,
        require_review_binding=False,
        active_draft={},
    )

    assert plan["style_only"] is False
    assert any(t["category"] == "continuity" for t in plan["targets"])
    assert all(item["owner"] != OWNER_FACT_REVIEW for item in plan["deferred"])


def test_diagnosis_targets_are_editable_spans():
    plan = build_revision_plan(
        DRAFT,
        _review(),
        chapter=3,
        require_review_binding=False,
        active_draft={},
        style_only=True,
        diagnosis=DIAGNOSIS,
    )

    diagnosis = [t for t in plan["targets"] if t["issue_id"].startswith("diagnosis-")]
    assert len(diagnosis) == 1
    target = diagnosis[0]
    assert target["owner"] == OWNER_PROSE_EDIT
    assert target["kind"] == "STYLE_ONLY"
    assert target["before_text"].startswith("梅叔站在门口")


def test_whole_chapter_diagnosis_observations_are_not_editable():
    plan = build_revision_plan(
        DRAFT,
        _review(),
        chapter=3,
        require_review_binding=False,
        active_draft={},
        style_only=True,
        diagnosis={"issues": [
            {
                "issue_type": "repetitive_sentence_shape",
                "location": "全章",
                "excerpt": "",
                "evidence": "句式单调",
                "suggested_intervention": "变化句长",
            }
        ]},
    )

    assert plan["targets"] == []
    assert plan["summary"]["diagnosis_targets"] == 0


def test_repeated_phrase_observation_becomes_bounded_paragraph_targets():
    draft = """林越推开门，屋里没人。

林越把工具箱放下，林越听见隔壁有响动。

梅叔抬头看了林越一眼。

林越点头，又低头整理纸样。
"""
    plan = build_revision_plan(
        draft,
        _review(),
        chapter=3,
        require_review_binding=False,
        active_draft={},
        style_only=True,
        diagnosis={"issues": [
            {
                "issue_type": "book_specific_repeated_phrase",
                "location": "全篇词频",
                "excerpt": "词语「林越」出现 8 次",
                "evidence": "高频复现",
                "suggested_intervention": "适度替换或省略",
            }
        ]},
    )

    repeats = [t for t in plan["targets"] if t["issue_id"].startswith("diagnosis-repeat-")]
    assert len(repeats) == 3, "首个出现段保留，之后最多取 3 段"
    assert all(t["before_text"].strip() for t in repeats)
    assert all("林越" in t["before_text"] for t in repeats)
    assert {t["location_raw"] for t in repeats} == {"第2段", "第3段", "第4段"}
