#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审查结果 schema（v6）。

替代原 checker-output-schema.md 的评分制，改为结构化问题清单。
"""
from __future__ import annotations

import difflib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from security_utils import atomic_write_json
except ImportError:  # pragma: no cover
    from scripts.security_utils import atomic_write_json

VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_CATEGORIES = {
    "continuity", "setting", "character", "timeline",
    "ai_flavor", "logic", "pacing", "other",
    "beat_compliance", "foreshadow_compliance",
    "do_not_copy_violation",
}
SCORE_CATEGORIES = (
    "continuity",
    "setting",
    "character",
    "timeline",
    "ai_flavor",
    "logic",
    "pacing",
    "other",
    "beat_compliance",
    "foreshadow_compliance",
    "do_not_copy_violation",
)
CRAFT_HEURISTIC_CATEGORIES = {"beat_compliance", "foreshadow_compliance", "pacing"}
SEVERITY_PENALTIES = {
    "critical": 35.0,
    "high": 15.0,
    "medium": 6.0,
    "low": 2.0,
}


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _issue_penalty(issue: "ReviewIssue") -> float:
    return float(SEVERITY_PENALTIES.get(issue.severity, SEVERITY_PENALTIES["medium"]))


@dataclass
class ReviewIssue:
    severity: str
    category: str = "other"
    location: str = ""
    description: str = ""
    evidence: str = ""
    fix_hint: str = ""
    blocking: Optional[bool] = None
    checker_id: str = "llm_review"
    gate_id: Optional[str] = None
    authority: Optional[str] = None
    explicitness: Optional[str] = None
    subject_id: Optional[str] = None
    constraint_id: Optional[str] = None
    source_ref: Optional[str] = None
    structured_evidence: Optional[List[Dict[str, Any]]] = None
    score: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.severity not in VALID_SEVERITIES:
            self.severity = "medium"
        if self.category not in VALID_CATEGORIES:
            self.category = "other"
        if self.blocking is None:
            self.blocking = self.severity == "critical"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewResult:
    chapter: int
    issues: List[ReviewIssue] = field(default_factory=list)
    summary: str = ""
    # Draft identity this review was produced for. Optional for backward compatibility, but a
    # review that declares it can be *checked* against the draft being revised/committed —
    # without it, a stale review could be reused on a different draft with nothing noticing.
    draft_id: Optional[str] = None
    draft_fingerprint: Optional[str] = None
    draft_identity_source: str = ""
    convergence: Optional[Dict[str, Any]] = None

    @property
    def issues_count(self) -> int:
        return len(self.issues)

    @property
    def blocking_count(self) -> int:
        return sum(1 for i in self.issues if i.blocking)

    @property
    def has_blocking(self) -> bool:
        return self.blocking_count > 0

    @property
    def severity_counts(self) -> Dict[str, int]:
        counts = {level: 0 for level in ("critical", "high", "medium", "low")}
        for issue in self.issues:
            severity = issue.severity if issue.severity in counts else "medium"
            counts[severity] += 1
        return counts

    @property
    def categories(self) -> List[str]:
        return sorted(set(i.category for i in self.issues))

    @property
    def critical_issues(self) -> List[str]:
        return [
            issue.description
            for issue in self.issues
            if issue.severity == "critical" and issue.description
        ]

    def _build_dimension_scores(self) -> Dict[str, float]:
        scores = {category: 100.0 for category in SCORE_CATEGORIES}
        for issue in self.issues:
            category = issue.category if issue.category in scores else "other"
            scores[category] = _clamp_score(scores[category] - _issue_penalty(issue))
        return scores

    def _build_notes(self, categories: List[str]) -> str:
        parts: List[str] = []
        if self.summary:
            parts.append(self.summary)
        parts.append(f"issues={self.issues_count}")
        parts.append(f"blocking={self.blocking_count}")
        if categories:
            parts.append("categories=" + ",".join(categories))
        return " | ".join(parts)

    def _calculate_overall_score(self) -> float:
        score = 100.0
        for issue in self.issues:
            score -= _issue_penalty(issue)
        return _clamp_score(score)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "chapter": self.chapter,
            "issues": [i.to_dict() for i in self.issues],
            "issues_count": self.issues_count,
            "blocking_count": self.blocking_count,
            "has_blocking": self.has_blocking,
            "summary": self.summary,
        }
        if self.draft_id:
            payload["draft_id"] = self.draft_id
        if self.draft_fingerprint:
            payload["draft_fingerprint"] = self.draft_fingerprint
        if self.draft_identity_source:
            payload["draft_identity_source"] = self.draft_identity_source
        if self.convergence:
            payload["convergence"] = self.convergence
        return payload

    def to_metrics_dict(self, report_file: str = "") -> Dict[str, Any]:
        categories = self.categories
        severity_counts = self.severity_counts
        metrics = {
            "chapter": self.chapter,
            "start_chapter": self.chapter,
            "end_chapter": self.chapter,
            "overall_score": self._calculate_overall_score(),
            "dimension_scores": self._build_dimension_scores(),
            "severity_counts": severity_counts,
            "critical_issues": self.critical_issues,
            "report_file": report_file,
            "notes": self._build_notes(categories),
            "issues_count": self.issues_count,
            "blocking_count": self.blocking_count,
            "categories": categories,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        if self.convergence:
            metrics["convergence"] = self.convergence
            metrics["previous_finding_count"] = self.convergence.get("previous_finding_count", 0)
            metrics["resolved_count"] = self.convergence.get("resolved_count", 0)
            metrics["persistent_count"] = self.convergence.get("persistent_count", 0)
            metrics["uncertain_count"] = self.convergence.get("uncertain_count", 0)
            metrics["new_count"] = self.convergence.get("new_count", 0)
            metrics["finding_churn"] = self.convergence.get("finding_churn", 0)
        return metrics


def parse_review_output(chapter: int, raw: Dict[str, Any]) -> ReviewResult:
    issues = []
    for item in raw.get("issues", []):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "other"))
        checker_id = str(item.get("checker_id", "llm_review"))
        is_craft_heuristic = (
            category in CRAFT_HEURISTIC_CATEGORIES
            or checker_id == "story_craft"
            or str(item.get("gate_id", "")).startswith("story_craft.")
        )
        severity = str(item.get("severity", "medium"))
        if is_craft_heuristic and severity == "critical":
            severity = "high"
        issues.append(ReviewIssue(
            severity=severity,
            category=category,
            location=str(item.get("location", "")),
            description=str(item.get("description", "")),
            evidence=str(item.get("evidence", "")),
            fix_hint=str(item.get("fix_hint", "")),
            blocking=False if is_craft_heuristic else item.get("blocking"),
            checker_id=checker_id,
            gate_id=item.get("gate_id"),
            authority="CRAFT_HEURISTIC" if is_craft_heuristic else item.get("authority"),
            explicitness="UNKNOWN" if is_craft_heuristic else item.get("explicitness"),
            subject_id=item.get("subject_id"),
            constraint_id=item.get("constraint_id"),
            source_ref=item.get("source_ref"),
            structured_evidence=item.get("structured_evidence"),
            score=item.get("score"),
        ))
    nested_draft = raw.get("draft") if isinstance(raw.get("draft"), dict) else {}
    draft_id = raw.get("draft_id") or nested_draft.get("draft_id")
    draft_fingerprint = raw.get("draft_fingerprint") or nested_draft.get("draft_fingerprint")
    return ReviewResult(
        chapter=chapter,
        issues=issues,
        summary=str(raw.get("summary", "")),
        draft_id=str(draft_id).strip() if draft_id else None,
        draft_fingerprint=str(draft_fingerprint).strip() if draft_fingerprint else None,
        draft_identity_source=str(raw.get("draft_identity_source") or "").strip(),
        convergence=raw.get("convergence"),
    )


def compute_review_convergence(
    current: ReviewResult | Dict[str, Any],
    previous: Optional[ReviewResult | Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute review convergence telemetry between previous and current review (Issue #50 task C).

    Categorizes findings into:
    - resolved: issues in previous review that no longer appear in current review
    - persistent: issues in previous review that continue to appear in current review
    - uncertain: issues with ambiguous or partial match
    - new: issues in current review that were not present in previous review

    Tracks explicit closure for previous high/critical issues.
    """
    curr_dict = current.to_dict() if hasattr(current, "to_dict") else dict(current or {})
    prev_dict = (previous.to_dict() if hasattr(previous, "to_dict") else dict(previous or {})) if previous else None

    curr_issues = curr_dict.get("issues") or []
    if not prev_dict or not prev_dict.get("issues"):
        return {
            "has_previous_review": False,
            "previous_finding_count": 0,
            "resolved_count": 0,
            "persistent_count": 0,
            "uncertain_count": 0,
            "new_count": len(curr_issues),
            "finding_churn": len(curr_issues),
            "resolved": [],
            "persistent": [],
            "uncertain": [],
            "new": [str(i.get("description", "")) for i in curr_issues if isinstance(i, dict)],
            "high_critical_closure": [],
            "all_high_critical_closed": True,
        }

    prev_issues = prev_dict.get("issues") or []

    resolved: List[Dict[str, Any]] = []
    persistent: List[Dict[str, Any]] = []
    uncertain: List[Dict[str, Any]] = []
    matched_curr_indices: set[int] = set()

    for p_idx, p in enumerate(prev_issues):
        if not isinstance(p, dict):
            continue
        p_desc = str(p.get("description") or "").strip()
        p_cat = str(p.get("category") or "other")
        p_loc = str(p.get("location") or "")
        p_sev = str(p.get("severity") or "medium")
        p_gate = str(p.get("gate_id") or "")

        best_match_idx = -1
        best_match_score = 0.0

        for c_idx, c in enumerate(curr_issues):
            if not isinstance(c, dict) or c_idx in matched_curr_indices:
                continue
            c_desc = str(c.get("description") or "").strip()
            c_cat = str(c.get("category") or "other")
            c_loc = str(c.get("location") or "")
            c_gate = str(c.get("gate_id") or "")

            score = 0.0
            if p_gate and c_gate and p_gate == c_gate and not p_gate.startswith("story_craft.heuristic"):
                score = 1.0
            elif p_cat == c_cat:
                sim = difflib.SequenceMatcher(None, p_desc, c_desc).ratio()
                loc_match = 0.2 if p_loc and c_loc and p_loc == c_loc else 0.0
                if p_desc and c_desc and (p_desc in c_desc or c_desc in p_desc):
                    sim = max(sim, 0.85)
                score = sim + loc_match

            if score > best_match_score:
                best_match_score = score
                best_match_idx = c_idx

        info = {
            "category": p_cat,
            "severity": p_sev,
            "description": p_desc,
            "location": p_loc,
        }

        if best_match_score >= 0.7:
            matched_curr_indices.add(best_match_idx)
            persistent.append(info)
        elif best_match_score >= 0.4:
            matched_curr_indices.add(best_match_idx)
            uncertain.append(info)
        else:
            resolved.append(info)

    new_issues = [
        str(curr_issues[idx].get("description", ""))
        for idx in range(len(curr_issues))
        if idx not in matched_curr_indices and isinstance(curr_issues[idx], dict)
    ]

    high_critical_closure: List[Dict[str, Any]] = []
    for p in prev_issues:
        if not isinstance(p, dict):
            continue
        p_sev = str(p.get("severity") or "medium")
        if p_sev not in ("high", "critical"):
            continue
        p_desc = str(p.get("description") or "").strip()
        status = "resolved"
        if any(item.get("description") == p_desc for item in persistent):
            status = "persistent"
        elif any(item.get("description") == p_desc for item in uncertain):
            status = "uncertain"
        high_critical_closure.append({
            "category": p.get("category"),
            "severity": p_sev,
            "description": p_desc,
            "status": status,
        })

    all_closed = all(item["status"] == "resolved" for item in high_critical_closure)

    return {
        "has_previous_review": True,
        "previous_finding_count": len(prev_issues),
        "resolved_count": len(resolved),
        "persistent_count": len(persistent),
        "uncertain_count": len(uncertain),
        "new_count": len(new_issues),
        "finding_churn": len(resolved) + len(new_issues),
        "resolved": resolved,
        "persistent": persistent,
        "uncertain": uncertain,
        "new": new_issues,
        "high_critical_closure": high_critical_closure,
        "all_high_critical_closed": all_closed,
    }


def _read_json_if_exists(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Bad JSON in {path}") from exc


def _write_json(path: Path, payload: Any) -> None:
    atomic_write_json(path, payload, backup=True)


def append_ai_flavor_anti_patterns(project_root: str | Path, result: ReviewResult) -> int:
    root = Path(project_root).expanduser().resolve()
    path = root / ".story-system" / "anti_patterns.json"
    existing = _read_json_if_exists(path) or []
    if not isinstance(existing, list):
        existing = []

    seen_texts = {str(item.get("text") or "").strip() for item in existing if isinstance(item, dict)}
    additions: List[Dict[str, Any]] = []
    for index, issue in enumerate(result.issues, start=1):
        if issue.category != "ai_flavor" or issue.severity not in {"medium", "high", "critical"}:
            continue
        text = (issue.evidence or issue.description or "").strip()[:200]
        if not text or text in seen_texts:
            continue
        seen_texts.add(text)
        additions.append(
            {
                "text": text,
                "source_table": "review_extracted",
                "source_id": f"ch{int(result.chapter):04d}_issue_{index}",
                "category": issue.category,
                "added_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    if additions:
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(path, [*existing, *additions])
    return len(additions)
