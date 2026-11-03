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


def _write_review(root: Path, chapter: int, issues: list[dict]) -> None:
    runtime_dir = root / ".webnovel" / "runtime" / f"chapter_{chapter:03d}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "last_review.json").write_text(
        json.dumps({"chapter": chapter, "issues": issues, "summary": "test"}, ensure_ascii=False),
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
