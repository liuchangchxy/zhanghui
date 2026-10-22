#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Finding closure identity must not depend on a finding's list position.

Chapter 2 of 《海港旧信》 produced four PROSE_EDIT targets but the plan was built after two
CRAFT advisories had been deferred, so the planner numbered the fourth finding `issue-003`.
Convergence numbered it by its position in the *full* review (`issue-004`), found no matching
target, and reported a fixed low-logic finding as `uncertain` with
`unassociated_finding_id_not_in_verified_evidence`. The same offset could also let a deferred
finding claim another finding's target, because prefix matching only looked at the index.

These tests pin the shared fingerprint identity: an ordinary finding, a deferred advisory
between editable findings, several PROSE_EDIT findings, and the resolved / persistent /
uncertain classification.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # tests/ → scripts/ → plugin/
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "data_modules"))

from data_modules.review_schema import (  # noqa: E402
    ReviewIssue,
    ReviewResult,
    compute_review_convergence,
    finding_identity,
)
from data_modules.revision_planner import build_revision_plan  # noqa: E402


DRAFT = (
    "第二章 测试\n\n"
    "第一段：他把编号抄进备注栏。\n\n"
    "第二段：外面的雨停了。\n\n"
    "第三段：他听见有人在楼下喊。\n\n"
    "第四段：门没有关。\n"
)


def _issue(severity: str, category: str, description: str, location: str, **extra) -> dict:
    return {
        "severity": severity,
        "category": category,
        "description": description,
        "location": location,
        **extra,
    }


def _plan_ids(issues: list[dict]) -> list[str]:
    plan = build_revision_plan(
        DRAFT,
        {"issues": issues},
        require_review_binding=False,
    )
    return [str(target["issue_id"]) for target in plan["targets"]]


def _review(issues: list[dict], draft_id: str, fingerprint: str) -> ReviewResult:
    return ReviewResult(
        chapter=2,
        issues=[
            ReviewIssue(
                severity=item["severity"],
                category=item["category"],
                description=item["description"],
                location=item["location"],
            )
            for item in issues
        ],
        draft_id=draft_id,
        draft_fingerprint=fingerprint,
    )


def _evidence(ids: list[str], *, source: str = "draft-002-old", target: str = "draft-002-new") -> dict:
    return {
        "ok": True,
        "source_draft_id": source,
        "source_draft_fingerprint": "fp-old",
        "target_draft_id": target,
        "target_draft_fingerprint": "fp-new",
        "resolved_targets": ids,
    }


def test_ordinary_finding_identity_is_position_independent() -> None:
    finding = _issue("high", "logic", "普通问题：时间锚点冲突", "第2段")

    assert _plan_ids([finding]) == [finding_identity(finding)]


def test_deferred_advisory_between_editable_findings_does_not_shift_identity() -> None:
    """The chapter-2 shape: prose finding, advisory, prose finding, prose finding."""
    prose_a = _issue("high", "logic", "A：本站不派工单却持工单作业", "第2段")
    advisory = _issue("medium", "beat_compliance", "B：章末缺少 Sequel 反应拍", "第4段")
    prose_b = _issue("medium", "continuity", "C：第十项补核缺少正文证据", "第3段")
    prose_c = _issue("low", "logic", "D：入职那年的说法指代不明", "第1段")

    ids = _plan_ids([prose_a, advisory, prose_b, prose_c])

    # Only the three editable findings are planned; each keeps its own fingerprint identity.
    assert ids == [finding_identity(item) for item in (prose_a, prose_b, prose_c)]
    assert len(set(ids)) == 3
    # The advisory's identity is not in the plan, so it cannot be closed by someone else's ID.
    assert finding_identity(advisory) not in ids

    prev = _review([prose_a, advisory, prose_b, prose_c], "draft-002-old", "fp-old")
    curr = _review([], "draft-002-new", "fp-new")
    conv = compute_review_convergence(curr, prev, revision_evidence=_evidence(ids))

    assert conv["resolved_count"] == 3
    assert {item["description"] for item in conv["resolved"]} == {
        prose_a["description"],
        prose_b["description"],
        prose_c["description"],
    }
    # The deferred finding disappeared without evidence. It must not be resolved by the
    # fingerprint of a neighbouring finding.
    assert conv["uncertain_count"] == 1
    assert conv["uncertain"][0]["description"] == advisory["description"]
    assert conv["high_critical_closure"][0]["status"] == "resolved"


def test_multiple_prose_edits_each_resolve_against_their_own_target() -> None:
    findings = [
        _issue("high", "logic", "第一条：因果倒置", "第2段"),
        _issue("medium", "setting", "第二条：设定字段前后矛盾", "第3段"),
        _issue("medium", "timeline", "第三条：时间跨度倒流", "第4段"),
        _issue("low", "character", "第四条：称呼前后不一致", "第1段"),
    ]
    ids = _plan_ids(findings)
    assert len(set(ids)) == 4

    prev = _review(findings, "draft-002-old", "fp-old")
    curr = _review([], "draft-002-new", "fp-new")
    conv = compute_review_convergence(curr, prev, revision_evidence=_evidence(ids))

    assert conv["resolved_count"] == 4
    assert conv["uncertain_count"] == 0
    assert conv["all_high_critical_closed"] is True
    for item in conv["resolved"]:
        assert item["closure_evidence"].startswith("verified_by_revision_target:")


def test_resolved_persistent_and_uncertain_are_classified_separately() -> None:
    fixed = _issue("high", "logic", "已修复：因果倒置", "第2段")
    persistent = _issue("medium", "continuity", "仍在：清单记号未改", "第3段")
    vanished = _issue("medium", "timeline", "无证据：时间跨度倒流", "第4段")
    fixed_second = _issue("low", "character", "已修复：称呼前后不一致", "第1段")

    evidence_ids = _plan_ids([fixed, fixed_second])
    prev = _review([fixed, persistent, vanished, fixed_second], "draft-002-old", "fp-old")
    curr = _review([persistent], "draft-002-new", "fp-new")
    conv = compute_review_convergence(curr, prev, revision_evidence=_evidence(evidence_ids))

    assert conv["resolved_count"] == 2
    assert conv["persistent_count"] == 1
    assert conv["uncertain_count"] == 1
    assert conv["persistent"][0]["description"] == persistent["description"]
    assert conv["uncertain"][0]["description"] == vanished["description"]
    assert conv["uncertain"][0]["uncertain_reason"] == "unassociated_finding_id_not_in_verified_evidence"


def test_another_findings_evidence_cannot_close_a_deferred_finding() -> None:
    """The old index-prefix match let a deferred finding claim its neighbour's target."""
    advisory = _issue("medium", "beat_compliance", "建议项：缺少反应拍", "第1段")
    prose = _issue("high", "logic", "正文项：因果倒置", "第2段")

    prose_id = _plan_ids([prose])[0]
    prev = _review([advisory, prose], "draft-002-old", "fp-old")
    curr = _review([], "draft-002-new", "fp-new")
    conv = compute_review_convergence(curr, prev, revision_evidence=_evidence([prose_id]))

    statuses = {item["description"]: item["status"] for item in conv["high_critical_closure"]}
    assert statuses[prose["description"]] == "resolved"
    by_description = {item["description"]: item for item in conv["uncertain"]}
    assert advisory["description"] in by_description
    assert by_description[advisory["description"]]["uncertain_reason"] == (
        "unassociated_finding_id_not_in_verified_evidence"
    )
