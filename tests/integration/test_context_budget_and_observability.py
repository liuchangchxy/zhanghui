#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Context-budget and observability tests (task L).

`ContextManager.build_context(max_chars=...)` was an accepted-and-ignored parameter, and
`ContextRanker` only sorted — it never controlled how much context was actually assembled. These
tests pin the real behaviour, including the constraint that made the parameter dangerous to
"just implement": accepted facts must never be bought back as token savings.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "plugins" / "zhanghui" / "scripts"
for path in (SCRIPTS, SCRIPTS.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _payload() -> dict:
    return {
        "meta": {"chapter": 3},
        "canon": [{"content": f"canon fact {i}"} for i in range(40)],
        "intent": [{"content": "本章目标"}],
        "craft": [{"content": f"craft {i}"} for i in range(40)],
        "reference": [{"content": f"reference {i}"} for i in range(40)],
        "context_diagnostics": [{"message": f"diag {i}"} for i in range(40)],
        "runtime_status": {"blob": "x" * 20000},
        "core": {
            "recent_summaries": [{"content": f"summary {i}"} for i in range(10)],
            "recent_meta": [{"content": f"meta {i}"} for i in range(10)],
        },
    }


def _ranker(tmp_path: Path):
    """Bind the ranker to an explicit project root.

    `ContextRanker()` defaults to the ambient project resolution, which made these tests depend
    on wherever the suite happened to run from.
    """
    from data_modules.config import DataModulesConfig
    from data_modules.context_ranker import ContextRanker

    return ContextRanker(DataModulesConfig.from_project_root(tmp_path))


def test_rank_pack_budget_selects_instead_of_only_sorting(tmp_path: Path):
    from data_modules.context_ranker import ContextRanker

    ranker = _ranker(tmp_path)

    pack = _payload()
    ranked = ranker.rank_pack(pack, 3, budget=20000)
    selection = ranked["meta"]["ranker"]["selection"]
    assert selection, "budget must actually drop items"
    assert len(ranked["reference"]) <= ContextRanker.BUDGET_SECTION_CAPS["reference"]
    assert len(ranked["craft"]) <= ContextRanker.BUDGET_SECTION_CAPS["craft"]
    assert len(ranked["core"]["recent_summaries"]) <= ContextRanker.BUDGET_SECTION_CAPS["recent_summaries"]


def test_rank_pack_without_budget_keeps_full_pack(tmp_path: Path):
    from data_modules.context_ranker import ContextRanker

    pack = _payload()
    ranked = _ranker(tmp_path).rank_pack(pack, 3)
    assert len(ranked["reference"]) == len(pack["reference"])
    assert "selection" not in ranked["meta"]["ranker"]


def _manager(tmp_path: Path):
    from data_modules.config import DataModulesConfig
    from data_modules.context_manager import ContextManager

    cfg = DataModulesConfig.from_project_root(tmp_path)
    return ContextManager(cfg)


def test_enforce_context_budget_trims_compressible_sections(tmp_path: Path):
    manager = _manager(tmp_path)
    payload = _payload()
    original_canon = json.dumps(payload["canon"], ensure_ascii=False)
    original_intent = json.dumps(payload["intent"], ensure_ascii=False)

    result = manager._enforce_context_budget(payload, 3, 5000)

    budget = result["meta"]["context_budget"]
    assert budget["limit"] == 5000
    assert budget["before_chars"] > budget["after_chars"]
    assert "context_diagnostics" in budget["sections_trimmed"]
    assert "runtime_status" in budget["sections_trimmed"]
    # L9: Canon / Intent are never traded for token savings
    assert json.dumps(result["canon"], ensure_ascii=False) == original_canon
    assert json.dumps(result["intent"], ensure_ascii=False) == original_intent
    assert "canon" not in budget["sections_trimmed"]
    assert "intent" not in budget["sections_trimmed"]


def test_enforce_context_budget_reports_shortfall_instead_of_truncating_facts(tmp_path: Path):
    manager = _manager(tmp_path)
    payload = _payload()
    result = manager._enforce_context_budget(payload, 3, 200)
    budget = result["meta"]["context_budget"]
    assert budget["enforced"] is False
    assert budget["shortfall_chars"] > 0
    # the un-trimmable contract sections are still intact
    assert len(result["canon"]) == 40
    assert len(result["intent"]) == 1
    assert "不参与裁剪" in budget["note"]


def test_observability_summary_never_fabricates_tokens(tmp_path: Path):
    from data_modules.observability_report import build_observability_summary

    (tmp_path / ".webnovel" / "runtime" / "chapter_003" / "drafts").mkdir(parents=True)
    for draft_id in ("draft-003-a", "draft-003-b", "draft-003-c"):
        (
            tmp_path / ".webnovel" / "runtime" / "chapter_003" / "drafts" / f"{draft_id}.json"
        ).write_text(json.dumps({"draft_id": draft_id, "prose": "正文"}), encoding="utf-8")

    report = build_observability_summary(tmp_path)

    assert report["tokens"] == {
        "available": False,
        "note": "宿主未向插件提供 token 元数据；本报告不伪造 token 统计。",
    }
    entry = next(item for item in report["chapters"] if item["chapter"] == 3)
    assert entry["draft_versions"] == 3
    assert entry["reviewer_runs"] == 3
    assert entry["draft_ids"] == ["draft-003-a", "draft-003-b", "draft-003-c"]


def test_observability_summary_reads_review_metrics(tmp_path: Path):
    from data_modules.observability_report import build_observability_summary

    webnovel = tmp_path / ".webnovel"
    webnovel.mkdir(parents=True, exist_ok=True)
    db_path = webnovel / "index.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE review_metrics (start_chapter INTEGER, end_chapter INTEGER, overall_score REAL,"
        " dimension_scores TEXT, severity_counts TEXT, critical_issues TEXT, report_file TEXT,"
        " notes TEXT, created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        "INSERT INTO review_metrics VALUES (2,2,92.0,'{}','{\"high\": 0, \"medium\": 1}',"
        "'[]','','issues=3 | blocking=0','2026-10-16','2026-10-16')"
    )
    conn.commit()
    conn.close()

    report = build_observability_summary(tmp_path, chapters=[2])
    entry = report["chapters"][0]
    assert entry["review_score_latest"] == 92.0
    assert entry["severity_counts_latest"]["medium"] == 1
