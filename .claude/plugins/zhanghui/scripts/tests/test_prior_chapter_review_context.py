#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reviewer findings must survive the chapter boundary.

`review-pipeline` already persists every review to
`.webnovel/runtime/chapter_NNN/last_review.json`, but nothing read chapter N-1's copy when
chapter N started, so every chapter looked like a clean first round: the benchmark saw
`has_previous_review=false` in 20 contexts and no finding was ever re-verified across
chapters. The reviewer context now carries `prior_chapter_context` from that same file —
no second review store.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # tests/ → scripts/ → plugin/
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "data_modules"))

from data_modules.chapter_runtime import ChapterRuntime  # noqa: E402


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "book"
    (root / ".webnovel").mkdir(parents=True, exist_ok=True)
    (root / ".webnovel" / "state.json").write_text(
        json.dumps({"progress": {"current_chapter": 0}}, ensure_ascii=False), encoding="utf-8"
    )
    # A durable runtime history makes the runtime refuse to regenerate truth from scratch;
    # provide the two foundational contracts a real project already has.
    for name in ("MASTER_SETTING.json", "anti_patterns.json"):
        (root / ".webnovel" / name).write_text("{}", encoding="utf-8")
    return root


def _write_review(root: Path, chapter: int, issues: list[dict], *, draft_id: str = "") -> None:
    runtime_dir = root / ".webnovel" / "runtime" / f"chapter_{chapter:03d}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    payload = {"chapter": chapter, "issues": issues, "summary": "test"}
    if draft_id:
        payload["draft_id"] = draft_id
    (runtime_dir / "last_review.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_next_chapter_context_carries_previous_high_findings(tmp_path):
    root = _project(tmp_path)
    _write_review(root, 1, [
        {"severity": "critical", "category": "timeline",
         "location": "第2段", "description": "十年前写成十四年前", "fix_hint": "核对年数"},
        {"severity": "low", "category": "logic", "location": "第5段", "description": "小事"},
    ])

    context = ChapterRuntime(root).get_reviewer_context(chapter=2)
    prior = context["prior_chapter_context"]

    assert prior["has_previous_chapter_review"] is True
    assert prior["previous_chapter"] == 1
    assert prior["previous_review_status"] == "loaded"
    assert [item["severity"] for item in prior["high_or_critical_findings"]] == ["critical"]
    assert prior["high_or_critical_findings"][0]["category"] == "timeline"
    assert prior["instruction"]


def test_first_chapter_reports_no_previous_review(tmp_path):
    root = _project(tmp_path)
    _write_review(root, 1, [{"severity": "critical", "category": "timeline", "location": "第1段"}])

    context = ChapterRuntime(root).get_reviewer_context(chapter=1)

    assert context["prior_chapter_context"]["has_previous_chapter_review"] is False
    assert context["prior_chapter_context"]["previous_chapter"] is None


def test_a_review_from_another_chapter_is_not_misattributed(tmp_path):
    root = _project(tmp_path)
    _write_review(root, 1, [{"severity": "critical", "category": "timeline", "location": "第1段"}])
    # `.webnovel/tmp/review_results.json` holds chapter 2's own review, not chapter 1's.
    (root / ".webnovel" / "tmp").mkdir(parents=True, exist_ok=True)
    (root / ".webnovel" / "tmp" / "review_results.json").write_text(
        json.dumps({"chapter": 2, "issues": [{"severity": "critical", "category": "logic"}]},
                   ensure_ascii=False),
        encoding="utf-8",
    )

    context = ChapterRuntime(root).get_reviewer_context(chapter=2)
    prior = context["prior_chapter_context"]

    assert prior["previous_review_status"] == "loaded"
    assert prior["high_or_critical_findings"][0]["category"] == "timeline"


# --------------------------------------------------------------------------- #
# Same-chapter re-review
# --------------------------------------------------------------------------- #

def _write_active_draft(root: Path, chapter: int, draft_id: str, fingerprint: str) -> None:
    runtime_dir = root / ".webnovel" / "runtime" / f"chapter_{chapter:03d}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "draft.json").write_text(
        json.dumps({
            "chapter": chapter,
            "draft_id": draft_id,
            "draft_fingerprint": fingerprint,
            "review_subject_fingerprint": fingerprint,
            "status": "ingested",
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_same_chapter_rereview_reads_previous_round_after_new_draft(tmp_path):
    root = _project(tmp_path)
    _write_review(root, 4, [
        {"severity": "high", "category": "continuity", "location": "第23—25行",
         "description": "第二项清点记录的数量与既有事实冲突"},
        {"severity": "medium", "category": "logic", "location": "第111—117行",
         "description": "同一调阅列表先后被描述为空和剩有两条记录"},
        {"severity": "low", "category": "ai_flavor", "location": "第33段",
         "description": "重复点名"},
    ], draft_id="draft-004-round-one")
    # The revision produced a new draft identity; that must not hide round one's review.
    _write_active_draft(root, 4, "draft-004-round-two", "fp-round-two")

    context = ChapterRuntime(root).get_reviewer_context(chapter=4)
    convergence = context["convergence_context"]

    assert convergence["has_previous_review"] is True
    assert convergence["previous_review_status"] == "loaded"
    assert convergence["previous_draft_id"] == "draft-004-round-one"
    assert convergence["previous_finding_count"] == 3
    assert [item["severity"] for item in convergence["high_or_critical_findings"]] == ["high"]
    assert "chapter_mismatch" not in json.dumps(convergence, ensure_ascii=False)
    assert convergence["instruction"]


def test_first_review_does_not_call_a_previous_chapter_file_chapter_mismatch(tmp_path):
    root = _project(tmp_path)
    # Before chapter 4's first review, `.webnovel/tmp/review_results.json` still holds
    # chapter 3's accepted review. That is "no same-chapter review", not corruption.
    (root / ".webnovel" / "tmp").mkdir(parents=True, exist_ok=True)
    (root / ".webnovel" / "tmp" / "review_results.json").write_text(
        json.dumps({"chapter": 3, "issues": [{"severity": "high", "category": "continuity"}]},
                   ensure_ascii=False),
        encoding="utf-8",
    )

    context = ChapterRuntime(root).get_reviewer_context(chapter=4)
    convergence = context["convergence_context"]

    assert convergence["has_previous_review"] is False
    assert convergence["previous_review_status"] == "no_previous_review"
    assert convergence["ignored_review_candidates"] == [
        {"file": "review_results.json", "chapter": 3}
    ]
    assert "chapter_mismatch" not in json.dumps(convergence, ensure_ascii=False)


def test_chapter_five_reads_chapter_four_leftovers_without_mixing_its_own_round(tmp_path):
    root = _project(tmp_path)
    _write_review(root, 4, [
        {"severity": "high", "category": "continuity", "location": "第23—25行",
         "description": "第4章遗留高优"},
        {"severity": "critical", "category": "setting", "location": "第9段",
         "description": "第4章遗留严重"},
        {"severity": "medium", "category": "logic", "description": "中优不进入跨章遗留"},
        {"severity": "low", "category": "ai_flavor", "description": "低优不进入跨章遗留"},
    ], draft_id="draft-004-final")
    # Chapter 5's own previous round lives in the shared tmp file.
    (root / ".webnovel" / "tmp").mkdir(parents=True, exist_ok=True)
    (root / ".webnovel" / "tmp" / "review_results.json").write_text(
        json.dumps({
            "chapter": 5,
            "issues": [{"severity": "high", "category": "timeline", "description": "第5章本轮问题"}],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    context = ChapterRuntime(root).get_reviewer_context(chapter=5)
    convergence = context["convergence_context"]
    prior = context["prior_chapter_context"]

    # Same-chapter convergence reads chapter 5's own round, not chapter 4's review.
    assert convergence["has_previous_review"] is True
    assert [item["description"] for item in convergence["previous_findings"]] == ["第5章本轮问题"]

    # Cross-chapter context carries only chapter 4's high/critical leftovers.
    assert prior["has_previous_chapter_review"] is True
    assert prior["previous_chapter"] == 4
    assert prior["previous_review_status"] == "loaded"
    assert [item["severity"] for item in prior["high_or_critical_findings"]] == ["high", "critical"]
    assert "chapter_mismatch" not in json.dumps(prior, ensure_ascii=False)


def test_malformed_chapter_value_falls_back_without_crashing(tmp_path):
    root = _project(tmp_path)
    runtime_dir = root / ".webnovel" / "runtime" / "chapter_004"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "last_review.json").write_text(
        json.dumps({"chapter": "not-a-number", "issues": [{"severity": "high"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / ".webnovel" / "tmp").mkdir(parents=True, exist_ok=True)
    (root / ".webnovel" / "tmp" / "review_results.json").write_text(
        json.dumps({"chapter": 4, "issues": [{"severity": "medium", "category": "logic",
                                              "description": "本章上一轮"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    context = ChapterRuntime(root).get_reviewer_context(chapter=4)
    convergence = context["convergence_context"]

    assert convergence["has_previous_review"] is True
    assert convergence["previous_review_status"] == "loaded"
    assert convergence["previous_findings"][0]["description"] == "本章上一轮"
    assert convergence["ignored_review_candidates"][0]["file"] == "last_review.json"
