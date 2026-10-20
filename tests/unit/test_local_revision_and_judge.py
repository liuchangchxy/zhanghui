#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-module contract tests for tasks E (local revision) and F (Semantic Judge).

These are intentionally not "does module X work" tests — they check the hand-offs that were
broken in the real acceptance run:

* Reviewer output (paragraph references / quotes / advisory findings) -> a usable targeted
  revision plan, with no `## §N` headings anywhere in the prose;
* a host-authored minimal edit -> boundary verification that rejects out-of-scope rewriting;
* a stale or unbound Semantic Judge verdict -> fail-closed UNCERTAIN, never a silent accept;
* a bound verdict for the same prose -> STYLE_ONLY_SAFE and acceptance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "plugins" / "zhanghui" / "scripts"
for path in (SCRIPTS, SCRIPTS.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


DRAFT = "\n".join(
    [
        "第2章 十年前的日期",
        "",
        "许知远把那张抄录纸摊平，一共记了七行。",
        "他数了第三遍，还是七行，可是前面写的是八行。",
        "“不是打印的，是手写的。”老周说。",
        "",
        "窗外的雨没停，档案室的灯管嗡嗡响。",
    ]
)


def _bound_reviewer_json(
    draft: str = DRAFT,
    *,
    issues: list | None = None,
    draft_id: str = "draft-002-abcdef12",
) -> dict:
    """A reviewer result that declares which draft it reviewed.

    Reviewer output now carries the draft identity it was produced for (and `review-pipeline`
    stamps it when the reviewer omits it), which is what lets `revise plan` refuse a stale
    review instead of silently locating old findings in a new draft.
    """
    import hashlib

    payload = _reviewer_json()
    if issues is not None:
        payload["issues"] = list(issues)
    payload["draft_id"] = draft_id
    payload["draft_fingerprint"] = hashlib.sha256(draft.encode("utf-8")).hexdigest()
    return payload


def _active_draft(draft: str = DRAFT, *, draft_id: str = "draft-002-abcdef12") -> dict:
    import hashlib

    return {
        "available": True,
        "draft_id": draft_id,
        "draft_fingerprint": hashlib.sha256(draft.encode("utf-8")).hexdigest(),
    }


def _reviewer_json() -> dict:
    return {
        "chapter": 2,
        "issues": [
            {
                "severity": "high",
                "category": "continuity",
                "location": "第3段",
                "description": "第3段的行数「七行」与后文记载不一致。",
                "fix_hint": "把这一段的数字改成与前文一致。",
                "blocking": True,
            },
            {
                "severity": "low",
                "category": "logic",
                "location": "问题句附近（原文引用见描述）",
                "description": "同段介质描述冲突：「不是打印的，是手写的」。",
                "fix_hint": "只保留可核验差异。",
                "blocking": False,
            },
            {
                "severity": "medium",
                "category": "other",
                "location": "chapter 2",
                "description": "定时锁逾期：TL-004",
                "fix_hint": "",
                "blocking": False,
                "gate_id": "story_craft.timed_lock",
            },
        ],
    }


# --------------------------------------------------------------------------- #
# E: plan
# --------------------------------------------------------------------------- #


def test_plan_locates_paragraph_and_quote_without_section_headings():
    from data_modules.revision_planner import build_revision_plan

    plan = build_revision_plan(DRAFT, _bound_reviewer_json(), chapter=2, draft_id="draft-002-abc", active_draft=_active_draft())
    assert "§" not in DRAFT  # the prose has no §N structure at all

    targets = plan["targets"]
    assert [t["locator"] for t in targets] == ["paragraph", "quote"]
    assert targets[0]["line_start"] == 3
    assert targets[0]["file_line_start"] == 4
    assert targets[0]["before_text"] == "他数了第三遍，还是七行，可是前面写的是八行。"
    assert targets[1]["before_text"] == "“不是打印的，是手写的。”老周说。"
    assert targets[0]["blocking"] is True
    assert targets[1]["anchor_quote"] == "不是打印的，是手写的"
    assert plan["summary"]["blocking"] == 1
    # `summary.advisory` counts planned targets that are not blocking — here the non-blocking
    # logic finding, which *is* prose-editable and therefore stays in the plan.
    assert plan["summary"]["advisory"] == 1
    assert plan["summary"]["unresolved"] == 0
    # chapter-scope findings must not become editable spans
    assert len(plan["editable_spans"]) == 2
    # The 定时锁逾期 finding is a Craft heuristic: it is reported with its owner and a repair
    # hint instead of being handed to a prose editor that cannot fix it.
    deferred = plan["deferred"]
    assert [item["owner"] for item in deferred] == ["ADVISORY"]
    assert deferred[0]["repair_hint"]
    assert plan["summary"]["deferred_by_owner"]["ADVISORY"] == 1


DUAL_REF_DRAFT = "\n".join(
    [
        "# 第1章 被改过的一行",
        "",
        "他数了一遍。记录本上共有七行。",
        "",
        "回到第 5 行。",
        "",
        "四个数字是蓝的。",
    ]
)


def _dual_ref_review(**issue_overrides) -> dict:
    import hashlib

    issue = {
        "severity": "high",
        "category": "setting",
        "location": "正文第3行（第3段）",
        "description": "前一段确认八行，紧接着又写“记录本上共有七行”。",
        "evidence": "正文第3行“共七行”；世界观要求每页固定八行。",
        "fix_hint": "删除七行表述，保留八行。",
        "blocking": False,
    }
    issue.update(issue_overrides)
    return {
        "chapter": 1,
        "draft_id": "draft-001-dualref",
        "draft_fingerprint": hashlib.sha256(DUAL_REF_DRAFT.encode("utf-8")).hexdigest(),
        "issues": [issue],
    }


def test_plan_resolves_dual_line_paragraph_reference_to_the_quoted_line():
    """`正文第3行（第3段）` must follow the physical line, not the Nth non-empty paragraph.

    The live acceptance run lost a fact correction here: the file had a heading and blank
    lines, so the 3rd non-empty paragraph was a different paragraph than line 3. The plan was
    marked resolvable against the wrong span, which would have re-written an unrelated
    sentence. A quoted anchor must break the tie in favour of the span that actually contains
    the finding.
    """
    from data_modules.revision_planner import build_revision_plan

    plan = build_revision_plan(
        DUAL_REF_DRAFT,
        _dual_ref_review(),
        chapter=1,
        active_draft=_active_draft(DUAL_REF_DRAFT, draft_id="draft-001-dualref"),
    )
    target = plan["targets"][0]
    assert target["locator"] == "line"
    assert target["resolvable"] is True
    assert target["file_line_start"] == 3
    assert "七行" in target["before_text"]
    assert "回到第 5 行" not in target["before_text"]


def test_plan_refuses_to_guess_when_line_and_paragraph_disagree_without_evidence():
    """Two disagreeing locators and no quoted anchor must become an explicit ambiguity."""
    from data_modules.revision_planner import build_revision_plan

    review = _dual_ref_review(
        description="行数与前文不一致。",
        evidence="",
        fix_hint="按前文行数修正。",
    )
    plan = build_revision_plan(
        DUAL_REF_DRAFT,
        review,
        chapter=1,
        active_draft=_active_draft(DUAL_REF_DRAFT, draft_id="draft-001-dualref"),
    )
    target = plan["targets"][0]
    assert target["resolvable"] is False
    assert target["locator"] == "unresolved"
    assert target["ambiguity"] == "line_paragraph_conflict"
    assert plan["editable_spans"] == []


def test_plan_defers_advisory_findings_and_includes_them_only_on_request():
    """Scope is decided by *ownership*, not by "non-blocking means rewrite it".

    The old contract put every non-blocking finding into the plan, so an unfixable Craft
    advisory kept the edit loop spinning. Now only `PROSE_EDIT` findings are planned; a
    Craft advisory is deferred with its owner unless the caller explicitly opts in.
    """
    from data_modules.revision_planner import build_revision_plan

    default = build_revision_plan(DRAFT, _bound_reviewer_json(), chapter=2, active_draft=_active_draft())
    assert default["summary"]["total"] == 2
    assert default["summary"]["deferred"] == 1
    assert [item["owner"] for item in default["deferred"]] == ["ADVISORY"]

    opted_in = build_revision_plan(
        DRAFT, _bound_reviewer_json(), chapter=2, active_draft=_active_draft(), include_advisory=True
    )
    assert opted_in["summary"]["total"] == 3
    assert opted_in["summary"]["deferred"] == 0

    blocking_only = build_revision_plan(
        DRAFT, _bound_reviewer_json(), chapter=2, active_draft=_active_draft(), blocking_only=True
    )
    assert blocking_only["summary"]["total"] == 1
    assert blocking_only["summary"]["blocking"] == 1


def test_plan_reports_ambiguity_instead_of_guessing():
    from data_modules.revision_planner import build_revision_plan

    ambiguous = "第一段有「同一句话」。\n\n第二段也有「同一句话」。\n"
    plan = build_revision_plan(
        ambiguous,
        _bound_reviewer_json(
            ambiguous,
            draft_id="draft-001-aaaaaaaa",
            issues=[
                {
                    "severity": "low",
                    "category": "logic",
                    "location": "某处",
                    "description": "问题出在「同一句话」上。",
                    "fix_hint": "改掉。",
                    "blocking": False,
                }
            ],
        ),
        chapter=1,
        active_draft=_active_draft(ambiguous, draft_id="draft-001-aaaaaaaa"),
    )
    target = plan["targets"][0]
    assert target["resolvable"] is False
    assert target["ambiguity"] == "ambiguous_quote"
    assert plan["editable_spans"] == []


def test_plan_classifies_kind_for_safety_routing():
    from data_modules.revision_planner import (
        KIND_CANON_HISTORY,
        KIND_LOCAL_FACT,
        KIND_STYLE_ONLY,
        build_revision_plan,
    )

    issues = [
        {"severity": "low", "category": "ai_flavor", "location": "第3段", "description": "套话", "fix_hint": "删", "blocking": False},
        {"severity": "high", "category": "timeline", "location": "第4段", "description": "时间冲突", "fix_hint": "改", "blocking": True},
    ]
    plan = build_revision_plan(
        DRAFT, _bound_reviewer_json(issues=issues), chapter=2, active_draft=_active_draft()
    )
    kinds = [t["kind"] for t in plan["targets"]]
    assert KIND_STYLE_ONLY in kinds
    assert KIND_LOCAL_FACT in kinds

    canon = build_revision_plan(
        DRAFT,
        _bound_reviewer_json(issues=issues),
        chapter=2,
        active_draft=_active_draft(),
        rejected=True,
    )
    assert all(t["kind"] == KIND_CANON_HISTORY for t in canon["targets"])


# --------------------------------------------------------------------------- #
# E: apply / verify
# --------------------------------------------------------------------------- #


def test_apply_and_verify_accepts_minimal_edit():
    from data_modules.revision_planner import apply_edits, build_revision_plan, verify_minimal_edit

    plan = build_revision_plan(
        DRAFT,
        _bound_reviewer_json(issues=[_reviewer_json()["issues"][0]]),
        chapter=2,
        active_draft=_active_draft(),
    )
    target = plan["targets"][0]
    fixed = target["before_text"].replace("七行", "八行")
    updated, report = apply_edits(DRAFT, plan, [{"target_id": target["issue_id"], "new_text": fixed}])

    assert report["changed"] is True
    verification = verify_minimal_edit(DRAFT, updated, plan)
    assert verification["boundary_ok"] is True
    assert verification["ok"] is True
    assert verification["resolved_targets"] == [target["issue_id"]]
    assert verification["untouched_targets"] == []
    assert "他数了第三遍，还是八行" in updated
    # everything outside the planned paragraph is byte-identical
    assert updated.replace(fixed, target["before_text"]) == DRAFT


def test_apply_rejects_out_of_scope_rewrite():
    """改一个数字不能变成重写整章。"""
    from data_modules.revision_planner import build_revision_plan, verify_minimal_edit

    plan = build_revision_plan(
        DRAFT, _bound_reviewer_json(), chapter=2, active_draft=_active_draft()
    )
    started = plan["editable_spans"][0]["start"]
    rewritten = DRAFT[:started] + DRAFT[started:] + "\n\n他又把整章重新写了一遍。\n"

    verification = verify_minimal_edit(DRAFT, rewritten, plan)
    assert verification["boundary_ok"] is False
    assert verification["ok"] is False
    assert verification["out_of_scope_changes"]


def test_apply_detects_draft_drift():
    from data_modules.revision_planner import RevisionApplyError, apply_edits, build_revision_plan

    plan = build_revision_plan(
        DRAFT, _bound_reviewer_json(), chapter=2, active_draft=_active_draft()
    )
    span = plan["editable_spans"][0]
    drifted = DRAFT[: span["start"]] + "别人改过了" + DRAFT[span["end"] :]

    with pytest.raises(RevisionApplyError):
        apply_edits(drifted, plan, [{"target_id": plan["targets"][0]["issue_id"], "new_text": "x"}])


def test_apply_reports_no_op_so_the_draft_identity_is_not_recycled():
    from data_modules.revision_planner import apply_edits, build_revision_plan

    plan = build_revision_plan(
        DRAFT, _bound_reviewer_json(), chapter=2, active_draft=_active_draft()
    )
    target = plan["targets"][0]
    _updated, report = apply_edits(DRAFT, plan, [{"target_id": target["issue_id"], "new_text": target["before_text"]}])
    assert report["changed"] is False
    assert report["edits_that_changed_text"] == 0


def test_verify_reports_untouched_targets():
    from data_modules.revision_planner import build_revision_plan, verify_minimal_edit

    plan = build_revision_plan(
        DRAFT, _bound_reviewer_json(), chapter=2, active_draft=_active_draft()
    )
    first = plan["targets"][0]
    edited = DRAFT.replace(first["before_text"], first["before_text"].replace("七行", "八行"))
    verification = verify_minimal_edit(DRAFT, edited, plan)
    assert verification["boundary_ok"] is True
    assert [t["issue_id"] for t in verification["untouched_targets"]] == [plan["targets"][1]["issue_id"]]


# --------------------------------------------------------------------------- #
# F: Semantic Judge host round trip
# --------------------------------------------------------------------------- #


BEFORE = "他把记录本合上，一共七行。"
AFTER = "他合上记录本，一共七行。"


def test_judge_request_is_bound_to_the_prose_pair():
    from data_modules.prose_judge_host import build_judge_request, sha256_text

    request = build_judge_request(BEFORE, AFTER, chapter=2)
    assert request["before_sha256"] == sha256_text(BEFORE)
    assert request["after_sha256"] == sha256_text(AFTER)
    assert request["chapter"] == 2
    assert "Semantic Judge" in request["prompt"]
    # the host is told the exact schema to answer with
    assert request["response_schema"]["outcome"].startswith("STYLE_ONLY_SAFE")


def test_judge_request_includes_canon_constraints_when_given():
    from data_modules.prose_judge_host import build_judge_request

    request = build_judge_request(BEFORE, AFTER, canon_constraints={"prohibitions": ["不得提前透光第8章反转"]})
    assert "不得提前透光第8章反转" in request["prompt"]


def test_bound_style_verdict_accepts_the_edit():
    from data_modules.prose_judge_host import bind_judge_response, make_bound_judge_callable
    from data_modules.prose_semantic_diff import compare_semantic_facts

    verdict = bind_judge_response(
        {"outcome": "STYLE_ONLY_SAFE", "changes": []}, BEFORE, AFTER, chapter=2
    )
    judge = make_bound_judge_callable(verdict, BEFORE, AFTER, chapter=2)
    result = compare_semantic_facts(BEFORE, AFTER, semantic_judge=judge)
    assert result.outcome.value == "STYLE_ONLY_SAFE"
    assert result.safe is True


def test_judge_verdict_cannot_be_replayed_onto_different_prose():
    """F9: 旧 Judge 结果不得复用到另一份正文。"""
    from data_modules.prose_judge_host import (
        JudgeBindingError,
        bind_judge_response,
        make_bound_judge_callable,
        validate_binding,
    )
    from data_modules.prose_semantic_diff import compare_semantic_facts

    verdict = bind_judge_response({"outcome": "STYLE_ONLY_SAFE", "changes": []}, BEFORE, AFTER, chapter=2)

    with pytest.raises(JudgeBindingError):
        validate_binding(verdict, BEFORE, "他合上本子，一共七行。", chapter=2)

    other_judge = make_bound_judge_callable(verdict, BEFORE, "完全不同的正文。", chapter=2)
    result = compare_semantic_facts(BEFORE, "完全不同的正文。", semantic_judge=other_judge)
    assert result.outcome.value == "UNCERTAIN"
    assert result.safe is False


def test_unbound_verdict_is_refused_and_fails_closed():
    from data_modules.prose_judge_host import JudgeBindingError, validate_binding
    from data_modules.prose_semantic_diff import compare_semantic_facts

    with pytest.raises(JudgeBindingError):
        validate_binding({"outcome": "STYLE_ONLY_SAFE", "changes": []}, BEFORE, AFTER, chapter=2)

    result = compare_semantic_facts(BEFORE, AFTER, semantic_judge=lambda b, a: {"outcome": "STYLE_ONLY_SAFE", "changes": []})
    # a callable that returns a raw unbound dict is still a valid judge answer for the
    # in-process API; the *environment/file* paths are the ones that must be bound.
    assert result.outcome.value == "STYLE_ONLY_SAFE"


def test_env_supplied_verdict_must_be_bound(monkeypatch, tmp_path):
    """The env path is the one that can go stale between runs, so it must carry binding."""
    from data_modules.prose_judge_host import build_judge_request
    from data_modules.prose_semantic_diff import compare_semantic_facts

    stale = tmp_path / "stale-verdict.json"
    stale.write_text(json.dumps({"outcome": "STYLE_ONLY_SAFE", "changes": []}), encoding="utf-8")
    monkeypatch.setenv("ZHANGHUI_SEMANTIC_JUDGE_RESULT", str(stale))
    import data_modules.prose_semantic_diff as diff

    monkeypatch.setattr(diff, "_DEFAULT_SEMANTIC_JUDGE", None)
    result = compare_semantic_facts(
        "他合上了记录本，屋里安静下来，雨还在下。", "他合上记录本，屋里安静下来，窗外的雨还在下着。"
    )
    assert result.outcome.value == "UNCERTAIN"

    request = build_judge_request(
        "他合上了记录本，屋里安静下来，雨还在下。",
        "他合上记录本，屋里安静下来，窗外的雨还在下着。",
    )
    bound = {
        "kind": "verdict",
        "outcome": "STYLE_ONLY_SAFE",
        "changes": [],
        "before_sha256": request["before_sha256"],
        "after_sha256": request["after_sha256"],
    }
    stale.write_text(json.dumps(bound), encoding="utf-8")
    monkeypatch.setattr(diff, "_DEFAULT_SEMANTIC_JUDGE", None)
    result = compare_semantic_facts(
        "他合上了记录本，屋里安静下来，雨还在下。", "他合上记录本，屋里安静下来，窗外的雨还在下着。"
    )
    assert result.outcome.value == "STYLE_ONLY_SAFE"


def test_semantic_change_proposed_is_never_accepted():
    """F6: 危险事实改写不得被放行（即使 Judge 声称只是风格）。"""
    from data_modules.prose_judge_host import bind_judge_response, make_bound_judge_callable
    from data_modules.prose_pipeline import ProseQualityPipeline

    before = "他把船位记在旧航道。"
    after = "他把船位记在现用航道。"
    verdict = bind_judge_response(
        {
            "outcome": "SEMANTIC_CHANGE_PROPOSED",
            "changes": [{"dimension": "location_or_state", "before": "旧航道", "after": "现用航道", "reason": "地点被改写"}],
        },
        before,
        after,
    )
    result = ProseQualityPipeline(Path(".")).process_and_validate(
        before, after, chapter=2, semantic_judge=make_bound_judge_callable(verdict, before, after)
    )
    assert result.status == "ROLLEDBACK"
    assert result.ok is False
    assert result.semantic_outcome == "SEMANTIC_CHANGE_PROPOSED"
    assert result.final_prose == before
