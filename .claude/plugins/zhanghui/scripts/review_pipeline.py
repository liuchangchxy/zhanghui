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
from data_modules.review_schema import (
    append_ai_flavor_anti_patterns,
    compute_review_convergence,
    parse_review_output,
)
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
    review_mode = str(result.get("review_mode") or "full")
    skipped = list(metrics.get("skipped_dimensions") or [])
    lines.append(
        f"- 审查模式：{review_mode}"
        + (f"（未检查维度：{', '.join(skipped)}——skipped 不等于 pass）" if skipped else "（8 维全覆盖）")
    )
    defect_score = metrics.get("review_defect_score", metrics.get("overall_score"))
    if defect_score is not None:
        lines.append(
            f"- 问题扣分指标（review_defect_score）：{defect_score} / 100"
            "（由问题严重度扣分得出；100 仅表示本轮未检出缺陷，不代表文学质量或篇幅达标）"
        )
    convergence = result.get("convergence") or {}
    if convergence.get("has_previous_review"):
        lines.append(
            "- 收敛（对比上一轮）："
            f"resolved={convergence.get('resolved_count', 0)} "
            f"persistent={convergence.get('persistent_count', 0)} "
            f"uncertain={convergence.get('uncertain_count', 0)} "
            f"new={convergence.get('new_count', 0)}"
        )
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

    def _count(key: str) -> int:
        try:
            return int(metrics.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    return ReviewMetrics(
        start_chapter=int(metrics["start_chapter"]),
        end_chapter=int(metrics["end_chapter"]),
        overall_score=float(metrics.get("review_defect_score", metrics.get("overall_score", 0.0))),
        dimension_scores=dict(metrics.get("dimension_scores", {})),
        severity_counts=dict(metrics.get("severity_counts", {})),
        critical_issues=list(metrics.get("critical_issues", [])),
        report_file=str(metrics.get("report_file", "")),
        notes=str(metrics.get("notes", "")),
        previous_finding_count=_count("previous_finding_count"),
        resolved_count=_count("resolved_count"),
        persistent_count=_count("persistent_count"),
        uncertain_count=_count("uncertain_count"),
        new_count=_count("new_count"),
        finding_churn=_count("finding_churn"),
    )


class ReviewDraftIdentityError(ValueError):
    """Raised when a review declares a draft identity that contradicts the active draft."""


def _bind_review_draft_identity(project_root: Path, chapter: int, result) -> Dict[str, Any]:
    """Attach the active draft identity to a review result, or verify the declared one.

    This is the attestation point of the workflow: it runs immediately after the Reviewer, so
    "the review belongs to the draft that is active right now" is recorded here rather than
    assumed later. A review that declares an identity contradicting the active draft is
    refused outright — that is a stale review being reused, which must never pass silently.
    """
    from data_modules.revision_planner import resolve_active_draft_identity

    active = resolve_active_draft_identity(project_root, chapter)
    declared = {
        "draft_id": str(result.draft_id or ""),
        "draft_fingerprint": str(result.draft_fingerprint or ""),
        "review_subject_fingerprint": str(result.review_subject_fingerprint or ""),
    }
    if not active.get("available"):
        return {
            "available": False,
            "reason": active.get("reason", "no_active_draft"),
            "verified": False,
            "stamped": False,
            "declared": declared,
        }

    active_id = str(active.get("draft_id") or "")
    active_fp = str(active.get("draft_fingerprint") or "")
    active_subject_fp = str(active.get("review_subject_fingerprint") or "")

    if declared["review_subject_fingerprint"]:
        # Subject-bound review: the prose is the contract. Re-ingesting an unchanged prose
        # mints a new draft_id, and a `<chapter_changes>` fix mints a new full fingerprint —
        # neither changes a reviewed character, so neither invalidates this review.
        if (
            active_subject_fp
            and declared["review_subject_fingerprint"] != active_subject_fp
        ):
            raise ReviewDraftIdentityError(
                "审查结果声明的 review_subject_fingerprint 与当前在编草稿正文不一致："
                f"review={declared['review_subject_fingerprint'][:12]} "
                f"active={active_subject_fp[:12]}。"
                "这是旧审查被用于新草稿，拒绝登记；请对新草稿重新运行 Reviewer。"
            )
        result.draft_identity_source = result.draft_identity_source or "reviewer"
        return {
            "available": True,
            "verified": True,
            "stamped": False,
            "mode": "declared_review_subject",
            "draft_id": active_id,
            "draft_fingerprint": active_fp,
            "review_subject_fingerprint": active_subject_fp,
            "declared": declared,
        }

    if declared["draft_fingerprint"] and declared["draft_fingerprint"] != active_fp:
        raise ReviewDraftIdentityError(
            "审查结果声明的 draft_fingerprint 与当前在编草稿不一致："
            f"review={declared['draft_fingerprint'][:12]} active={active_fp[:12]}。"
            "这是旧审查被用于新草稿，拒绝登记；请对新草稿重新运行 Reviewer。"
        )
    if declared["draft_id"] and active_id and declared["draft_id"] != active_id:
        raise ReviewDraftIdentityError(
            "审查结果声明的 draft_id 与当前在编草稿不一致："
            f"review={declared['draft_id']} active={active_id}。请对新草稿重新运行 Reviewer。"
        )

    if declared["draft_fingerprint"] or declared["draft_id"]:
        result.draft_identity_source = result.draft_identity_source or "reviewer"
        result.review_subject_fingerprint = active_subject_fp or None
        return {
            "available": True,
            "verified": True,
            "stamped": False,
            "mode": "declared_draft_identity",
            "draft_id": active_id,
            "draft_fingerprint": active_fp,
            "review_subject_fingerprint": active_subject_fp,
            "declared": declared,
        }

    result.draft_id = active_id or None
    result.draft_fingerprint = active_fp or None
    result.review_subject_fingerprint = active_subject_fp or None
    result.draft_identity_source = "review-pipeline"
    return {
        "available": True,
        "verified": True,
        "stamped": True,
        "mode": "stamped_from_active_draft",
        "draft_id": active_id,
        "draft_fingerprint": active_fp,
        "review_subject_fingerprint": active_subject_fp,
        "declared": declared,
    }


def build_review_artifacts(
    project_root: Path,
    chapter: int,
    review_results_path: Path,
    report_file: str = "",
) -> Dict[str, Any]:
    raw = json.loads(review_results_path.read_text(encoding="utf-8"))
    result = parse_review_output(chapter=chapter, raw=raw)
    draft_binding = _bind_review_draft_identity(project_root, chapter, result)
    _inject_craft_issues(project_root, result, chapter)
    anti_patterns_added = append_ai_flavor_anti_patterns(project_root, result)
    # Review convergence tracking (Issue #50 task C)
    runtime_dir = project_root / ".webnovel" / "runtime" / f"chapter_{chapter:03d}"
    tmp_dir = project_root / ".webnovel" / "tmp"
    last_review_file = runtime_dir / "last_review.json"

    prev_review = None
    prev_review_status = "no_previous_review"
    if last_review_file.is_file():
        try:
            prev_data = json.loads(last_review_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # Reading the previous review is observational: a corrupt cache must not fail the
            # run, but it must not be indistinguishable from "there was no previous review"
            # either — the convergence telemetry would silently report a clean first round.
            prev_review_status = f"unavailable: {exc}"
            prev_data = None
        if isinstance(prev_data, dict):
            prev_subject = str(prev_data.get("review_subject_fingerprint") or "")
            curr_subject = str(result.review_subject_fingerprint or "")
            same_subject = bool(prev_subject and curr_subject and prev_subject == curr_subject)
            if not same_subject:
                prev_review = prev_data
                prev_review_status = "loaded"

    convergence_evidence_path = ""
    if prev_review is not None:
        rev_evidence = None
        # The revision artifacts live in `.webnovel/tmp/` (what the Skill writes); the runtime
        # dir is checked too for hosts that stage them there. Looking only in the runtime dir
        # meant closure evidence was effectively never found.
        for cand_ev in (
            tmp_dir / "verify_minimal_edit.json",
            tmp_dir / f"revision_plan_{chapter:04d}.json",
            tmp_dir / "revision_audit.json",
            runtime_dir / "verify_minimal_edit.json",
            runtime_dir / f"revision_plan_{chapter:04d}.json",
            runtime_dir / "revision_audit.json",
        ):
            if not cand_ev.is_file():
                continue
            try:
                ev_data = json.loads(cand_ev.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(ev_data, dict):
                rev_evidence = ev_data
                convergence_evidence_path = str(cand_ev)
                break
        result.convergence = compute_review_convergence(result, prev_review, revision_evidence=rev_evidence)
        result.convergence["revision_evidence_path"] = convergence_evidence_path
        result.convergence["revision_evidence_found"] = rev_evidence is not None
    else:
        result.convergence = compute_review_convergence(result, None)
    result.convergence["previous_review_status"] = prev_review_status

    metrics = result.to_metrics_dict(report_file=report_file)
    normalized_review = result.to_dict()
    review_results_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(review_results_path, normalized_review, use_lock=False, backup=False)

    # These two writes are the convergence authority, not decoration: `last_review.json` is
    # what the next round diffs against and `draft_reviews/<draft_id>.review.json` is the
    # per-draft attestation. Swallowing their failures produced a CLI that reported success
    # while the evidence needed to interpret the next round was never written.
    runtime_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(last_review_file, normalized_review, use_lock=False, backup=False)
    if result.draft_id:
        draft_reviews_dir = runtime_dir / "draft_reviews"
        draft_reviews_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            draft_reviews_dir / f"{result.draft_id}.review.json",
            normalized_review,
            use_lock=False,
            backup=False,
        )

    return {
        "chapter": chapter,
        "review_result": normalized_review,
        "metrics": metrics,
        "anti_patterns_added": anti_patterns_added,
        "draft_binding": draft_binding,
    }


def _craft_category_to_review_category(craft_category: str) -> str:
    """Map story_craft issue category to ReviewIssue VALID_CATEGORIES."""
    if craft_category == "foreshadow_compliance":
        return "continuity"
    if craft_category == "beat_compliance":
        return "pacing"
    return "other"


def _craft_issue_to_review_issue(issue_str: str, chapter: int, structured: dict | None = None):
    """Convert a run_craft_checks string into a ReviewIssue."""
    from data_modules.review_schema import ReviewIssue

    # Display labels remain unchanged, but heuristic provenance never carries
    # blocking authority into the shared gate policy.
    is_blocker = False

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
        checker_id="story_craft",
        gate_id=(structured or {}).get("gate_id", "story_craft.heuristic"),
        authority="CRAFT_HEURISTIC",
        explicitness="UNKNOWN",
        subject_id=(structured or {}).get("subject_id"),
        structured_evidence=(structured or {}).get("evidence", []),
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
    for record in craft.get("findings", []):
        if isinstance(record, dict) and isinstance(record.get("display"), str):
            result.issues.append(_craft_issue_to_review_issue(record["display"], chapter, record))


def chapter_to_volume(state: dict, chapter: int) -> int:
    """Return current volume.

    C3: sibling-aware — V2+ story-craft stores `volume_beats: dict[str, beat]`.
    V1 still uses singular `volume_beat: {..., volume: N}`. Falls back to 1
    when both keys are missing.

    Note: this function does NOT actually use the `chapter` argument — the
    current state model only tracks one active volume. Multi-volume support
    would require volumes_planned lookup; falls back to 1 when no beat key
    is present. Future maintainers: do NOT expect this function to
    compute volume from chapter boundaries — see _resolve_volume_for_chapter in
    dashboard/app.py for the multi-volume-aware variant.
    """
    craft = state.get("story_craft", {})
    # Prefer V2+ sibling key; fall back to V1 singular key (back-compat)
    v2_beats = craft.get("volume_beats")
    if isinstance(v2_beats, dict) and v2_beats:
        # Use the lexically largest index that has a beat (proxy for "current").
        try:
            return max(int(k) for k in v2_beats.keys())
        except (TypeError, ValueError):
            pass
    return craft.get("volume_beat", {}).get("volume", 1)


def run_craft_checks(state: dict, chapter: int) -> dict:
    """Run all story_craft checks for a given chapter. Return issues dict."""
    issues: dict[str, list[str]] = {"blockers": [], "warnings": [], "findings": []}

    def record(bucket: str, display: str, gate_id: str, subject_id: str, evidence: dict) -> None:
        issues[bucket].append(display)
        issues["findings"].append({
            "display": display, "gate_id": gate_id, "subject_id": subject_id,
            "evidence": [{"kind": "craft_observation", "identity": evidence}],
        })

    # C3: sibling-aware read for V2+ (volume_beats) with V1 fallback (volume_beat).
    craft = state.get("story_craft", {})
    active_volume_beat: dict | None = None
    if isinstance(craft.get("volume_beats"), dict) and craft["volume_beats"]:
        # Pick the active volume's beat for beat-compliance check.
        # Prefer the entry with `volume` field; otherwise pick the highest key.
        candidates = craft["volume_beats"]
        for vb in candidates.values():
            if isinstance(vb, dict) and isinstance(vb.get("volume"), int):
                active_volume_beat = vb
                break
        if active_volume_beat is None:
            try:
                top_key = max(candidates.keys(), key=lambda k: int(k))
                active_volume_beat = candidates[top_key] if isinstance(candidates[top_key], dict) else None
            except (TypeError, ValueError):
                pass
    if active_volume_beat is None and isinstance(craft.get("volume_beat"), dict):
        # V1 legacy path (kept 100% unchanged)
        active_volume_beat = craft["volume_beat"]

    # Volume beat (only if initialized)
    if active_volume_beat is not None:
        vol = active_volume_beat.get("volume")
        if isinstance(vol, int) and vol == chapter_to_volume(state, chapter):
            vol_issues = check_volume_beat(state, volume=vol)
            for index, issue in enumerate(vol_issues):
                record(
                    "warnings",
                    f"beat_compliance: {issue}", "story_craft.volume_beat",
                    f"chapter:{chapter}:volume:{vol}:beat_observation",
                    {"volume": vol, "rule_index": index},
                )

    # Rhythm
    if "rhythm_curve" in state.get("story_craft", {}):
        rhythm_status = check_rhythm_status(state)
        if rhythm_status == "block":
            n = state["story_craft"]["rhythm_curve"]["chapters_since_peak"]
            record("warnings", f"foreshadow_compliance: 节奏曲线 BLOCK：chapters_since_peak={n}",
                   "story_craft.rhythm_curve", f"chapter:{chapter}:rhythm_curve",
                   {"chapters_since_peak": n})
        elif rhythm_status == "warning":
            record("warnings", "foreshadow_compliance: 节奏曲线 WARNING",
                   "story_craft.rhythm_curve", f"chapter:{chapter}:rhythm_curve",
                   {"status": "warning"})

    # Timed locks
    if "timed_locks" in state.get("story_craft", {}):
        overdue = check_timed_lock_deadlines(state, current_chapter=chapter)
        for lock in overdue:
            record("warnings", f"foreshadow_compliance: 定时锁逾期：{lock['id']} deadline={lock['deadline_chapter']}",
                   "story_craft.timed_lock", f"timed_lock:{lock['id']}",
                   {"lock_id": lock["id"], "deadline_chapter": lock["deadline_chapter"], "observed_chapter": chapter})

    # Scene-Sequel
    from data_modules.state_validator import get_chapter_meta_entry
    cm = get_chapter_meta_entry(state, chapter)
    if cm:
        ss_issues = check_scene_sequel(cm)
        for index, issue in enumerate(ss_issues):
            record("warnings",
                   f"beat_compliance: Scene-Sequel: {issue}", "story_craft.scene_sequel",
                   f"chapter:{chapter}:scene_sequel", {"chapter": chapter, "rule_index": index})

        # Hook type
        if not cm.get("hook_type"):
            record("warnings", "foreshadow_compliance: 章末 hook_type 未声明",
                   "story_craft.hook_type", f"chapter:{chapter}:hook_type",
                   {"hook_type_present": False})

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
