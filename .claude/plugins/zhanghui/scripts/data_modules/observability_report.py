#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage-cost observability from artifacts that already exist (task L11).

The point is to answer, with evidence, "which repeated work did this chapter pay for?" —
without adding a monitoring service, a database or an external collector (L12).

Every number is derived from something already on disk:

  * `.webnovel/runtime/chapter_NNN/drafts/*.json` — every ingested draft identity, i.e. the
    real draft-version count and therefore the number of Reviewer runs a chapter needed;
  * `.webnovel/observability/data_agent_timing.jsonl` — Data Agent sub-step durations;
  * `index.db:review_metrics` — the latest review score and severity counts per chapter;
  * `index.db:tool_call_stats` — tool call counts and failures;
  * `writer_package.json` / `governed_context_*.json` — real context sizes in characters.

Anything the host does not expose is reported as `unknown` rather than fabricated. In
particular **token usage is never invented**: Claude Code does not hand token metadata to the
plugin, so `tokens` is always `{"available": false}` here.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "observability-summary/v1"


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _chapter_drafts(project_root: Path, chapter: int) -> List[Dict[str, Any]]:
    drafts_dir = project_root / ".webnovel" / "runtime" / f"chapter_{chapter:03d}" / "drafts"
    if not drafts_dir.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for path in sorted(drafts_dir.glob("*.json")):
        payload = _read_json(path) or {}
        out.append(
            {
                "draft_id": str(payload.get("draft_id") or path.stem),
                "created_at": payload.get("created_at") or payload.get("ingested_at") or "",
                "chars": len(str(payload.get("prose") or payload.get("text") or "")),
            }
        )
    return out


def _review_metrics(project_root: Path) -> Dict[int, Dict[str, Any]]:
    db_path = project_root / ".webnovel" / "index.db"
    if not db_path.is_file():
        return {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return {}
    try:
        rows = conn.execute(
            "SELECT start_chapter, end_chapter, overall_score, severity_counts, notes, updated_at "
            "FROM review_metrics"
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()

    out: Dict[int, Dict[str, Any]] = {}
    for start, end, score, severities, notes, updated_at in rows:
        chapter = int(start or end or 0)
        if chapter <= 0:
            continue
        try:
            severity_counts = json.loads(severities) if isinstance(severities, str) else (severities or {})
        except json.JSONDecodeError:
            severity_counts = {}
        out[chapter] = {
            "overall_score": score,
            "severity_counts": severity_counts,
            "notes": notes or "",
            "updated_at": updated_at or "",
        }
    return out


def _tool_call_stats(project_root: Path) -> Dict[str, Any]:
    db_path = project_root / ".webnovel" / "index.db"
    if not db_path.is_file():
        return {"available": False}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return {"available": False}
    try:
        total = conn.execute("SELECT COUNT(*) FROM tool_call_stats").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM tool_call_stats WHERE success = 0").fetchone()[0]
        by_tool = conn.execute(
            "SELECT tool_name, COUNT(*) FROM tool_call_stats GROUP BY tool_name ORDER BY COUNT(*) DESC LIMIT 10"
        ).fetchall()
    except sqlite3.Error:
        return {"available": False}
    finally:
        conn.close()
    return {
        "available": True,
        "total": int(total),
        "failed": int(failed),
        "top_tools": [{"tool": name, "calls": int(calls)} for name, calls in by_tool],
    }


def _data_agent_timing(project_root: Path, chapter: Optional[int]) -> List[Dict[str, Any]]:
    path = project_root / ".webnovel" / "observability" / "data_agent_timing.jsonl"
    if not path.is_file():
        return []
    entries: List[Dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if chapter is not None and int(payload.get("chapter") or 0) not in (0, chapter):
            continue
        entries.append(payload)
    return entries


def _context_sizes(project_root: Path, chapter: int) -> Dict[str, Any]:
    tmp = project_root / ".webnovel" / "tmp"
    runtime_dir = project_root / ".webnovel" / "runtime" / f"chapter_{chapter:03d}"
    sizes: Dict[str, Any] = {}
    for key, path in (
        ("writer_package", runtime_dir / "writer_package.json"),
        ("governed_context", tmp / f"governed_context_{chapter:04d}.json"),
        ("reviewer_context", tmp / f"reviewer_context_{chapter:04d}.json"),
        ("creative_brief", tmp / f"creative_brief_{chapter:04d}.txt"),
        ("writer_prompt", tmp / f"writer_prompt_{chapter:04d}.txt"),
    ):
        if path.is_file():
            sizes[key] = path.stat().st_size
    return sizes


def build_observability_summary(
    project_root: str | Path,
    *,
    chapters: Optional[List[int]] = None,
) -> Dict[str, Any]:
    root = Path(project_root)
    metrics = _review_metrics(root)

    if chapters is None:
        runtime_dir = root / ".webnovel" / "runtime"
        found: set[int] = set()
        if runtime_dir.is_dir():
            for child in runtime_dir.iterdir():
                if child.is_dir() and child.name.startswith("chapter_"):
                    try:
                        found.add(int(child.name.split("_", 1)[1]))
                    except ValueError:
                        continue
        chapters = sorted(found | set(metrics))

    per_chapter: List[Dict[str, Any]] = []
    total_drafts = 0
    for chapter in chapters:
        drafts = _chapter_drafts(root, chapter)
        total_drafts += len(drafts)
        metric = metrics.get(chapter) or {}
        entry: Dict[str, Any] = {
            "chapter": chapter,
            "draft_versions": len(drafts),
            "draft_ids": [item["draft_id"] for item in drafts],
            # one Reviewer run per ingested draft is the workflow contract (any prose change
            # requires a fresh review), so this is the reviewer-run count, not a guess about
            # how long each run took.
            "reviewer_runs": len(drafts),
            "review_score_latest": metric.get("overall_score"),
            "severity_counts_latest": metric.get("severity_counts") or {},
            "review_updated_at": metric.get("updated_at") or "",
            "context_sizes": _context_sizes(root, chapter),
            "data_agent_timing": _data_agent_timing(root, chapter),
        }
        entry["return_reason_evidence"] = (
            f"{len(drafts)} 个草稿身份 ⇒ 至少 {len(drafts)} 次审查；"
            "具体返稿原因见各轮 review_results.json / review_metrics.notes"
        )
        per_chapter.append(entry)

    return {
        "schema_version": SCHEMA_VERSION,
        "project_root": str(root),
        "chapters": per_chapter,
        "totals": {
            "chapters": len(per_chapter),
            "draft_versions": total_drafts,
            "reviewer_runs": total_drafts,
        },
        "tool_call_stats": _tool_call_stats(root),
        "tokens": {
            "available": False,
            "note": "宿主未向插件提供 token 元数据；本报告不伪造 token 统计。",
        },
    }


def format_observability_text(report: Dict[str, Any]) -> str:
    lines = [
        f"observability chapters={report['totals']['chapters']} "
        f"draft_versions={report['totals']['draft_versions']} "
        f"reviewer_runs={report['totals']['reviewer_runs']}"
    ]
    for entry in report.get("chapters") or []:
        lines.append(
            f"  第{entry['chapter']}章: drafts={entry['draft_versions']} "
            f"reviewer_runs={entry['reviewer_runs']} score={entry['review_score_latest']}"
        )
        if entry["context_sizes"]:
            sizes = ", ".join(f"{k}={v}B" for k, v in entry["context_sizes"].items())
            lines.append(f"      context: {sizes}")
        for timing in entry.get("data_agent_timing") or []:
            total = timing.get("total_ms") or timing.get("TOTAL")
            if total:
                lines.append(f"      data-agent total: {total} ms")
    stats = report.get("tool_call_stats") or {}
    if stats.get("available"):
        lines.append(f"  tool calls: {stats['total']} (failed {stats['failed']})")
    lines.append(f"  tokens: {report['tokens']['note']}")
    return "\n".join(lines)
