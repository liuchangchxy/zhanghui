#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unresolved high/critical FACT_REVIEW findings must not auto-publish.

Step 4 is a style-only pass, so a fact/continuity finding is deferred to
`owner=FACT_REVIEW` rather than rewritten. The Reviewer correctly leaves every raw
finding `blocking=false` (only the shared policy may decide), which used to mean the
chapter could commit and publish while a high-severity fact problem was still open.

The rule under test is deliberately narrow:

* only high / critical,
* only explicit fact dimensions (setting / timeline / continuity / character / logic),
* only when the revision planner would assign FACT_REVIEW,
* only while the finding is still present in the current review.

medium/low findings are advisories, and pure-expression findings are untouched.
"""

from __future__ import annotations

import json

from data_modules.gate_finding_adapters import adapt_unresolved_fact_review
from data_modules.gate_findings import WorkflowAction
from data_modules.gate_severity_policy import GateSeverityPolicy


def _review(*issues):
    return {"chapter": 4, "issues": list(issues)}


def _decide(review):
    findings = adapt_unresolved_fact_review(chapter=4, review=review)
    decision = GateSeverityPolicy().evaluate(
        findings, policy_version="gate-policy/v1", scope={"chapter": 4}
    )
    return findings, decision


def _issue(severity, category, **extra):
    return {
        "severity": severity,
        "category": category,
        "blocking": False,
        "description": "第二项清点记录的数量与既有事实冲突",
        "location": "第23—25行",
        **extra,
    }


def test_high_fact_review_is_blocked():
    findings, decision = _decide(_review(_issue("high", "continuity")))

    assert len(findings) == 1
    assert findings[0].gate_id == "review.fact_review_unresolved"
    assert decision.aggregate_action == WorkflowAction.REQUIRE_HUMAN


def test_critical_fact_review_is_blocked():
    findings, decision = _decide(_review(_issue("critical", "setting")))

    assert len(findings) == 1
    assert decision.aggregate_action == WorkflowAction.REQUIRE_HUMAN


def test_medium_fact_review_stays_advisory():
    findings, decision = _decide(_review(_issue("medium", "continuity")))

    assert findings == []
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_low_fact_review_stays_advisory():
    findings, decision = _decide(_review(_issue("low", "logic")))

    assert findings == []
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_high_pure_expression_is_not_blocked():
    findings, decision = _decide(_review(
        _issue("high", "ai_flavor"),
        _issue("critical", "pacing"),
        _issue("high", "foreshadow_compliance"),
    ))

    assert findings == []
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_high_fact_review_that_disappeared_after_fix_allows_commit():
    # The formal fact correction was applied and the new review no longer reports it.
    findings, decision = _decide(_review())

    assert findings == []
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_high_fact_review_explicitly_marked_resolved_allows_commit():
    findings, decision = _decide(_review(_issue("high", "continuity", resolved=True)))
    assert findings == []
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY

    findings, decision = _decide(_review(_issue("high", "continuity", status="resolved")))
    assert findings == []
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_high_missing_artifact_is_not_misclassified_as_a_fact_edit():
    # Owner routing wins: a missing artifact is repaired in the pipeline, not by
    # rewriting prose, so it must not be reported as a FACT_REVIEW blocker here.
    findings, decision = _decide(_review(_issue(
        "high", "continuity",
        description="上一章摘要缺失 summary_result.json missing，无法核对连续性",
    )))
    assert findings == []
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_gate_routes_the_blocker_to_pending_human_at_commit_service(tmp_path):
    """The shared service must stop at pending_human rather than accepting."""
    from data_modules.chapter_commit_service import ChapterCommitService
    from data_modules.tests.commit_helpers import EMPTY_PROPOSAL

    findings, _ = _decide(_review(_issue("high", "continuity")))
    service = ChapterCommitService(tmp_path)
    result = service.evaluate_attempt(
        4,
        findings,
        attempt_id="attempt-fact-review",
        policy_version="gate-policy/v1",
        scope={"chapter": 4},
        review_result={"blocking_count": 0, "issues": [_issue("high", "continuity")]},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
        chapter_text="final prose\n<chapter_changes>" + json.dumps(EMPTY_PROPOSAL) + "</chapter_changes>",
        proposed_changes=EMPTY_PROPOSAL,
    )

    assert result.action == WorkflowAction.REQUIRE_HUMAN
    assert result.attempt_status == "pending_human"
