#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 3 审查结果处理。

读取 reviewer agent 的原始输出 JSON，解析为 ReviewResult，
生成 metrics 用于 index.db 沉淀。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from runtime_compat import enable_windows_utf8_stdio


def _ensure_scripts_path() -> None:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_path()

from data_modules.review_author_view import render_review_author_view
from data_modules.review_schema import append_ai_flavor_anti_patterns, parse_review_output
from security_utils import atomic_write_json, atomic_write_text
from story_craft import (
    check_rhythm_status,
    check_scene_sequel,
    check_timed_lock_deadlines,
    check_volume_beat,
)


def _resolve_report_path(project_root: Path, report_file: str) -> Path:
    root = project_root.expanduser().resolve()
    report_path = Path(report_file).expanduser()
    if not report_path.is_absolute():
        report_path = root / report_path
    report_path = report_path.resolve()
    try:
        report_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("report-file 必须位于 project_root 目录内") from exc
    return report_path


def _format_issue(issue: Dict[str, Any], index: int) -> List[str]:
    description = str(issue.get("description") or "未填写问题描述")
    severity = str(issue.get("severity") or "medium")
    category = str(issue.get("category") or "other")
    location = str(issue.get("location") or "未标注位置")
    evidence = str(issue.get("evidence") or "未提供证据")
    fix_hint = str(issue.get("fix_hint") or "未提供修复方向")
    blocking = "是" if issue.get("blocking") else "否"

    return [
        f"{index}. **{description}**",
        f"   - 严重级别：{severity}",
        f"   - 分类：{category}",
        f"   - 位置：{location}",
        f"   - 阻断：{blocking}",
        f"   - 证据：{evidence}",
        f"   - 修复方向：{fix_hint}",
    ]


def render_review_report(payload: Dict[str, Any]) -> str:
    result = payload["review_result"]
    metrics = payload["metrics"]
    issues = list(result.get("issues", []))
    blocking_issues = [issue for issue in issues if issue.get("blocking")]
    non_blocking_issues = [issue for issue in issues if not issue.get("blocking")]
    severity_counts = metrics.get("severity_counts", {})

    lines: List[str] = [
        f"# 第{payload['chapter']}章审查报告",
        "",
        render_review_author_view(payload).rstrip(),
        "",
        "## 总览",
        "",
        f"- 问题数：{result.get('issues_count', 0)}",
        f"- 阻断数：{result.get('blocking_count', 0)}",
        f"- 结论：{'需修复后重审' if result.get('has_blocking') else '无阻断问题'}",
    ]
    summary = str(result.get("summary") or "").strip()
    if summary:
        lines.append(f"- 摘要：{summary}")
    if severity_counts:
        ordered = [
            f"{level}={severity_counts.get(level, 0)}"
            for level in ("critical", "high", "medium", "low")
        ]
        lines.append(f"- 严重级别统计：{', '.join(ordered)}")

    lines.extend(["", "## 阻断问题", ""])
    if blocking_issues:
        for index, issue in enumerate(blocking_issues, start=1):
            lines.extend(_format_issue(issue, index))
            lines.append("")
    else:
        lines.append("无。")
        lines.append("")

    lines.extend(["## 其他问题", ""])
    if non_blocking_issues:
        for index, issue in enumerate(non_blocking_issues, start=1):
            lines.extend(_format_issue(issue, index))
            lines.append("")
    else:
        lines.append("无。")
        lines.append("")

    lines.extend(["## 修复方向", ""])
    if issues:
        ordered_issues = [*blocking_issues, *non_blocking_issues]
        for index, issue in enumerate(ordered_issues, start=1):
            description = str(issue.get("description") or "未填写问题描述")
            fix_hint = str(issue.get("fix_hint") or "未提供修复方向")
            lines.append(f"{index}. {description}：{fix_hint}")
    else:
        lines.append("暂无需要修复的问题。")

    return "\n".join(lines).rstrip() + "\n"


def write_review_report(project_root: Path, report_file: str, payload: Dict[str, Any]) -> Path:
    report_path = _resolve_report_path(project_root, report_file)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    # 原子写入：写入中途崩溃不会留下半截报告（M-H17）
    atomic_write_text(
        report_path, render_review_report(payload), use_lock=False, backup=False
    )
    return report_path


def _build_review_metrics_record(metrics: Dict[str, Any]):
    from data_modules.index_manager import ReviewMetrics

    return ReviewMetrics(
        start_chapter=int(metrics["start_chapter"]),
        end_chapter=int(metrics["end_chapter"]),
        overall_score=float(metrics.get("overall_score", 0.0)),
        dimension_scores=dict(metrics.get("dimension_scores", {})),
        severity_counts=dict(metrics.get("severity_counts", {})),
        critical_issues=list(metrics.get("critical_issues", [])),
        report_file=str(metrics.get("report_file", "")),
        notes=str(metrics.get("notes", "")),
    )


def build_review_artifacts(
    project_root: Path,
    chapter: int,
    review_results_path: Path,
    report_file: str = "",
) -> Dict[str, Any]:
    raw = json.loads(review_results_path.read_text(encoding="utf-8"))
    result = parse_review_output(chapter=chapter, raw=raw)
    _inject_craft_issues(project_root, result, chapter)
    anti_patterns_added = append_ai_flavor_anti_patterns(project_root, result)
    metrics = result.to_metrics_dict(report_file=report_file)
    normalized_review = result.to_dict()
    review_results_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(review_results_path, normalized_review, use_lock=False, backup=False)

    return {
        "chapter": chapter,
        "review_result": normalized_review,
        "metrics": metrics,
        "anti_patterns_added": anti_patterns_added,
    }


def _craft_category_to_review_category(craft_category: str) -> str:
    """Map story_craft issue category to ReviewIssue VALID_CATEGORIES."""
    if craft_category == "foreshadow_compliance":
        return "continuity"
    if craft_category == "beat_compliance":
        return "pacing"
    return "other"


def _craft_issue_to_review_issue(issue_str: str, chapter: int):
    """Convert a run_craft_checks string into a ReviewIssue."""
    from data_modules.review_schema import ReviewIssue

    is_blocker = "BLOCKER" in issue_str or "BLOCK" in issue_str or "未声明" in issue_str or "逾期" in issue_str

    # Split "category: description" prefix
    if ":" in issue_str:
        craft_category, _, description = issue_str.partition(":")
        craft_category = craft_category.strip()
        description = description.strip()
    else:
        craft_category = "other"
        description = issue_str

    return ReviewIssue(
        severity="critical" if is_blocker else "medium",
        category=_craft_category_to_review_category(craft_category),
        location=f"chapter {chapter}",
        description=description,
        evidence="",
        fix_hint="",
        blocking=is_blocker,
    )


def _load_story_state(project_root: Path) -> dict:
    """Best-effort load of state.json from project_root. Returns empty dict if missing."""
    try:
        state_path = project_root / ".webnovel" / "state.json"
        if state_path.exists():
            return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def _inject_craft_issues(project_root: Path, result, chapter: int) -> None:
    """Load state.json (best-effort) and merge story_craft issues into result.issues."""
    state = _load_story_state(project_root)
    if not state:
        return
    craft = run_craft_checks(state, chapter)
    for blocker in craft.get("blockers", []):
        result.issues.append(_craft_issue_to_review_issue(blocker, chapter))
    for warning in craft.get("warnings", []):
        result.issues.append(_craft_issue_to_review_issue(warning, chapter))


def chapter_to_volume(state: dict, chapter: int) -> int:
    """Return current volume. Single-volume assumption: returns volume_beat.volume.

    Note: this function does NOT actually use the `chapter` argument — the current
    state model only tracks one volume_beat (the active volume). Multi-volume
    support would require volumes_planned lookup; falls back to 1 when
    volume_beat is missing. Future maintainers: do NOT expect this function to
    compute volume from chapter boundaries — see _resolve_volume_for_chapter in
    dashboard/app.py for the multi-volume-aware variant.
    """
    return state.get("story_craft", {}).get("volume_beat", {}).get("volume", 1)


def run_craft_checks(state: dict, chapter: int) -> dict:
    """Run all story_craft checks for a given chapter. Return issues dict."""
    issues: dict[str, list[str]] = {"blockers": [], "warnings": []}

    # Volume beat (only if initialized)
    if "volume_beat" in state.get("story_craft", {}):
        vol = state["story_craft"]["volume_beat"]["volume"]
        if vol == chapter_to_volume(state, chapter):
            vol_issues = check_volume_beat(state, volume=vol)
            for issue in vol_issues:
                if "BLOCKER" in issue:
                    issues["blockers"].append(f"beat_compliance: {issue}")
                else:
                    issues["warnings"].append(f"beat_compliance: {issue}")

    # Rhythm
    if "rhythm_curve" in state.get("story_craft", {}):
        rhythm_status = check_rhythm_status(state)
        if rhythm_status == "block":
            n = state["story_craft"]["rhythm_curve"]["chapters_since_peak"]
            issues["blockers"].append(
                f"foreshadow_compliance: 节奏曲线 BLOCK：chapters_since_peak={n}"
            )
        elif rhythm_status == "warning":
            issues["warnings"].append("foreshadow_compliance: 节奏曲线 WARNING")

    # Timed locks
    if "timed_locks" in state.get("story_craft", {}):
        overdue = check_timed_lock_deadlines(state, current_chapter=chapter)
        for lock in overdue:
            issues["blockers"].append(
                f"foreshadow_compliance: 定时锁逾期：{lock['id']} deadline={lock['deadline_chapter']}"
            )

    # Scene-Sequel
    cm_raw = state.get("chapter_meta")
    if not isinstance(cm_raw, dict):
        cm_raw = {}
    cm_entry = cm_raw.get(str(chapter))
    if not isinstance(cm_entry, dict):
        cm_entry = {}
    cm = cm_entry
    if cm:
        ss_issues = check_scene_sequel(cm)
        for issue in ss_issues:
            if issue.startswith("BLOCKER"):
                issues["blockers"].append(f"beat_compliance: Scene-Sequel: {issue}")
            else:
                issues["warnings"].append(f"beat_compliance: Scene-Sequel: {issue}")

        # Hook type
        if not cm.get("hook_type"):
            issues["blockers"].append(
                "foreshadow_compliance: 章末 hook_type 未声明"
            )

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Review pipeline v6")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--review-results", required=True)
    parser.add_argument("--metrics-out", default="")
    parser.add_argument("--report-file", default="")
    parser.add_argument("--save-metrics", action="store_true",
                        help="直接写入 index.db，省去单独调用 save-review-metrics")

    args = parser.parse_args()
    project_root = Path(args.project_root)
    review_results_path = Path(args.review_results)

    payload = build_review_artifacts(
        project_root=project_root,
        chapter=args.chapter,
        review_results_path=review_results_path,
        report_file=args.report_file,
    )

    if args.metrics_out:
        out_path = Path(args.metrics_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(out_path, payload["metrics"], use_lock=False, backup=False)

    if args.report_file:
        write_review_report(
            project_root=project_root,
            report_file=args.report_file,
            payload=payload,
        )

    if args.save_metrics:
        from data_modules.config import DataModulesConfig
        from data_modules.index_manager import IndexManager
        config = DataModulesConfig.from_project_root(project_root)
        manager = IndexManager(config)
        manager.save_review_metrics(_build_review_metrics_record(payload["metrics"]))

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
