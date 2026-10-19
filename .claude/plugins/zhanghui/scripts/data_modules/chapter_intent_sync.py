#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chapter intent authority convergence (task G).

The problem, as observed in the real acceptance run: a chapter's planning information lives
in **two** places that nobody keeps in sync —

* `大纲/第N卷-详细大纲.md` — the chapter outline the planner authored (Intent), and
* `.webnovel/state.json` → `chapter_meta["N"]` — a second copy written by
  `story-craft set-chapter-meta`.

After the author edited chapter 2's outline to stop leaking the chapter-8 reveal, the stale
`chapter_meta["2"].scene_resolution` (which still said "确认日期正是旧航道事故当天") was carried
straight into `runtime reviewer-context`, so the Reviewer kept reasoning about a plan the
author had already withdrawn.

Authority rule implemented here
------------------------------
For a chapter's planning fields the **chapter outline is the single authority**; the
`chapter_meta` copy in `state.json` is a *derived* INTENT projection. Derived data never
overrides its source:

* the governed Writer/Reviewer context is built from the outline-derived intent, so Writer and
  Reviewer always see the same current plan (G6);
* drift between the stored copy and the outline is detected and reported (G3/G4);
* the stored copy is refreshed from the outline, but only for chapters that are **not yet
  accepted** — a chapter's planning fields must never rewrite the history behind an accepted
  Canon commit (G5);
* nothing here touches Canon, entities or accepted facts — this module only moves INTENT.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple


SCHEMA_VERSION = "chapter-intent/v1"

# outline directive key -> chapter_meta key (all keys exist in
# story_craft.ALLOWED_CHAPTER_META_FIELDS, so a refresh cannot introduce unknown fields)
OUTLINE_TO_META: Dict[str, str] = {
    "beat_position": "beat_position",
    "hook_type": "hook_type",
    "scene_goal": "scene_goal",
    "scene_conflict": "scene_conflict",
    "scene_setback": "scene_setback",
    "scene_resolution": "scene_resolution",
    "sequel_reaction": "sequel_reaction",
    "sequel_dilemma": "sequel_dilemma",
    "sequel_decision": "sequel_decision",
    "foreshadow_buried": "foreshadow_buried",
    "foreshadow_paid_off": "foreshadow_paid_off",
    "time_anchor": "time_anchor",
    "antagonist_tier": "villain_tier",
    "strand": "strand",
    "cbn": "CBN",
    "cpns": "CPNs",
    "cen": "CEN",
    "must_cover_nodes": "must_cover",
    "forbidden_zones": "forbidden",
    "chapter_type": "chapter_type",
    "chapter_role": "chapter_role",
}

# narrative intent fields the outline states directly; kept in the *effective* view only
# (they are not chapter_meta allowlist fields, so they are never written into state.json)
OUTLINE_NARRATIVE_KEYS = (
    "goal", "conflict", "cost", "hook", "chapter_change", "chapter_end_open_question",
    "chapter_type", "chapter_role",
)


# The outline template lets the planner write a *pointer* instead of a value
# (e.g. `sequel_reaction：见 \`story_craft\` 第2章 reaction 字段`). A pointer is not a plan,
# so it must never overwrite a real derived value.
_PLACEHOLDER_RE = re.compile(
    r"^(?:见\s*`?\w+`?.*字段|同上|同前|无|无。|待定|tbd|todo|n/?a|-|—|…|\.\.\.)$",
    re.IGNORECASE,
)


def _is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return bool(_PLACEHOLDER_RE.match(value.strip()))
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _normalized(value: Any) -> Any:
    """Comparison key that ignores trailing full stops and surrounding whitespace.

    Without this, `scene_goal` differing only by a final `。` would be reported as drift and
    trigger a pointless refresh on every prepare.
    """
    if isinstance(value, str):
        return re.sub(r"\s+", "", value).rstrip("。.；;")
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    return value


def _load_outline_directive(project_root: Path, chapter: int) -> Dict[str, Any]:
    try:
        from chapter_outline_loader import load_chapter_execution_directive
    except ImportError:  # pragma: no cover
        from scripts.chapter_outline_loader import load_chapter_execution_directive

    try:
        return load_chapter_execution_directive(Path(project_root), chapter) or {}
    except Exception:
        return {}


def outline_intent_digest(project_root: Path, chapter: int) -> str:
    """Stable digest of the chapter's authoritative planning input (its outline section)."""
    try:
        from chapter_outline_loader import load_chapter_outline
    except ImportError:  # pragma: no cover
        from scripts.chapter_outline_loader import load_chapter_outline

    try:
        outline = load_chapter_outline(Path(project_root), chapter, max_chars=None)
    except Exception:
        outline = ""
    payload = f"chapter={chapter}\n{outline}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stored_chapter_meta(state: Mapping[str, Any], chapter: int) -> Dict[str, Any]:
    try:
        from .state_validator import get_chapter_meta_entry
    except ImportError:  # pragma: no cover
        from data_modules.state_validator import get_chapter_meta_entry

    entry = get_chapter_meta_entry(state, chapter)
    return dict(entry) if isinstance(entry, Mapping) else {}


def outline_meta_fields(project_root: Path, chapter: int) -> Dict[str, Any]:
    """The outline-derived subset of chapter_meta (only fields the outline actually states)."""
    directive = _load_outline_directive(project_root, chapter)
    fields: Dict[str, Any] = {}
    for outline_key, meta_key in OUTLINE_TO_META.items():
        value = directive.get(outline_key)
        if value in (None, "", [], {}):
            continue
        if _is_placeholder(value):
            continue
        fields[meta_key] = value
    return fields


def effective_chapter_meta(
    project_root: Path,
    chapter: int,
    state: Mapping[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return `(effective_meta, provenance)`.

    The effective value of every field the outline states comes from the outline; fields only
    present in `state.json` (e.g. `core_event`, which the Data Agent owns) are kept as a
    fallback. `provenance` records the authority, the outline digest, and any drift found in
    the stored copy so callers can surface it instead of silently trusting the cache.
    """
    directive = _load_outline_directive(project_root, chapter)
    stored = _stored_chapter_meta(state, chapter)
    outline_fields = outline_meta_fields(project_root, chapter)

    drift: Dict[str, Dict[str, Any]] = {}
    for field, outline_value in outline_fields.items():
        if field not in stored:
            continue
        if _normalized(stored.get(field)) != _normalized(outline_value):
            drift[field] = {"stored": stored.get(field), "outline": outline_value}

    effective: Dict[str, Any] = dict(stored)
    effective.update(outline_fields)
    for key in OUTLINE_NARRATIVE_KEYS:
        value = directive.get(key)
        if value in (None, "", [], {}) or _is_placeholder(value):
            continue
        effective[key] = value

    provenance = {
        "schema_version": SCHEMA_VERSION,
        "authority": "chapter_outline",
        "derived_store": "state.json:chapter_meta",
        "outline_digest": outline_intent_digest(project_root, chapter),
        "stored_source_digest": str((stored.get("_source") or {}).get("outline_digest") or ""),
        "drift": drift,
        "drift_fields": sorted(drift),
    }
    return effective, provenance


def detect_drift(
    project_root: Path,
    chapter: int,
    state: Mapping[str, Any],
) -> Dict[str, Any]:
    _effective, provenance = effective_chapter_meta(project_root, chapter, state)
    return provenance


def chapter_is_accepted(project_root: Path, chapter: int) -> bool:
    """True when the chapter already has a validated durable commit (immutable history)."""
    try:
        from .durable_projection import discover_validated_chapter_commits
    except ImportError:  # pragma: no cover
        from data_modules.durable_projection import discover_validated_chapter_commits

    try:
        for commit in discover_validated_chapter_commits(Path(project_root)):
            if not isinstance(commit, dict):
                continue
            if int(commit.get("chapter") or 0) == int(chapter):
                return True
    except Exception:
        pass
    commits_dir = Path(project_root) / ".story-system" / "commits"
    if commits_dir.is_dir():
        padded = f"{chapter:03d}"
        if (commits_dir / f"chapter_{padded}.commit.json").is_file():
            return True
    return False


def sync_chapter_meta(
    project_root: Path,
    chapter: int,
    state: Dict[str, Any],
    *,
    allow_accepted: bool = False,
) -> Dict[str, Any]:
    """Refresh `state["chapter_meta"][chapter]` from the outline. Idempotent.

    Refuses on accepted chapters unless `allow_accepted=True`: an accepted chapter's planning
    fields belong to history and may only be corrected through the Canon correction path.
    """
    if chapter_is_accepted(project_root, chapter) and not allow_accepted:
        return {
            "ok": False,
            "reason": "chapter_accepted",
            "chapter": chapter,
            "message": (
                f"第 {chapter} 章已被正式接受，章节规划属于历史事实，"
                "不能用普通 intent 同步覆盖；请走 Canon Correction 流程。"
            ),
        }

    outline_fields = outline_meta_fields(project_root, chapter)
    digest = outline_intent_digest(project_root, chapter)
    meta_root = state.setdefault("chapter_meta", {})
    if not isinstance(meta_root, dict):
        meta_root = {}
        state["chapter_meta"] = meta_root

    key = None
    for candidate in (f"{chapter:04d}", str(chapter)):
        if candidate in meta_root:
            key = candidate
            break
    if key is None:
        key = str(chapter)

    entry = meta_root.get(key)
    entry = dict(entry) if isinstance(entry, Mapping) else {}

    changed: Dict[str, Dict[str, Any]] = {}
    for field, value in outline_fields.items():
        if _normalized(entry.get(field)) != _normalized(value):
            changed[field] = {"before": entry.get(field), "after": value}
            entry[field] = value

    previous = entry.get("_source") if isinstance(entry.get("_source"), dict) else {}
    source_changed = str(previous.get("outline_digest") or "") != digest
    entry["_source"] = {
        "authority": "chapter_outline",
        "outline_digest": digest,
        "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    meta_root[key] = entry

    return {
        "ok": True,
        "chapter": chapter,
        "key": key,
        "changed_fields": changed,
        "changed": bool(changed) or source_changed,
        "outline_digest": digest,
        "field_count": len(outline_fields),
    }


def build_report(project_root: Path, chapter: int, state: Mapping[str, Any]) -> Dict[str, Any]:
    """Read-only drift report for the CLI."""
    _effective, provenance = effective_chapter_meta(project_root, chapter, state)
    return {
        "schema_version": SCHEMA_VERSION,
        "chapter": chapter,
        "accepted": chapter_is_accepted(project_root, chapter),
        "authority": provenance["authority"],
        "outline_digest": provenance["outline_digest"],
        "stored_source_digest": provenance["stored_source_digest"],
        "drift": provenance["drift"],
        "drift_count": len(provenance["drift"]),
    }


def format_report_text(report: Mapping[str, Any]) -> str:
    lines = [
        f"chapter_intent chapter={report.get('chapter')} authority={report.get('authority')}",
        f"  accepted={report.get('accepted')} drift={report.get('drift_count')}",
        f"  outline_digest={str(report.get('outline_digest') or '')[:16]}",
        f"  stored_digest ={str(report.get('stored_source_digest') or '')[:16]}",
    ]
    for field, values in (report.get("drift") or {}).items():
        lines.append(f"  DRIFT {field}: stored={values.get('stored')!r} outline={values.get('outline')!r}")
    return "\n".join(lines)


def load_state(project_root: Path) -> Dict[str, Any]:
    state_path = Path(project_root) / ".webnovel" / "state.json"
    if not state_path.is_file():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


__all__ = [
    "OUTLINE_TO_META",
    "build_report",
    "chapter_is_accepted",
    "detect_drift",
    "effective_chapter_meta",
    "format_report_text",
    "load_state",
    "outline_intent_digest",
    "outline_meta_fields",
    "sync_chapter_meta",
]
