#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Writing Skills: discovery, validation and Writer-facing rendering.

A *writing skill* is a local Markdown file that states one craft method (scene-sequel,
dialogue subtext, information gap, ...). The directory is the registry: dropping a new
``<id>/SKILL.md`` in makes it available on the next scan, and there is no Python enum,
central list, or registration call to edit.

Two audiences, deliberately separated:

* the **router** (an AI step) sees the method — purpose, applicability, anti-patterns,
  guidance body — and decides which skills this chapter actually needs, then translates
  each into a chapter-specific instruction;
* the **Writer** sees only that translation ("本章创作方法"), never the theory, the skill
  id, the score, or why the skill was picked.

Discovery scans without a cache. Files are small and read once per chapter, so a stale
cache would only buy a hot-reload bug.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

# Bundled skills live at the plugin root (scripts/data_modules/ -> plugin root).
PLUGIN_SKILLS_DIR = Path(__file__).resolve().parents[2] / "writing-skills"
PROJECT_SKILLS_REL = Path(".webnovel") / "writing-skills"

DEFAULT_MAX_SKILLS = 5
DEFAULT_MIN_SKILLS = 2
MAX_GUIDANCE_CHARS = 600

REQUIRED_FIELDS = ("id", "name", "purpose", "applies_when", "avoid_when")

# Tokens that mean a "chapter guidance" is really theory leaking to the Writer.
# Kept narrow and explicit: ordinary craft words (悬念/冲突/场景) are fine.
THEORY_LEAK_TOKENS = (
    "skill",
    "理论",
    "swain",
    "scene-sequel",
    "scene_goal",
    "scene_conflict",
    "sequel_",
    "hook_type",
    "hook_strength",
    "reader-pull",
    "reading-power",
    "writing-skill",
)


class SkillFormatError(ValueError):
    """Raised when a SKILL.md cannot be parsed into a usable skill."""


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _split_inline_list(value: str) -> List[str]:
    inner = value.strip()
    if not (inner.startswith("[") and inner.endswith("]")):
        return []
    inner = inner[1:-1].strip()
    if not inner:
        return []
    return [_unquote(part) for part in inner.split(",") if part.strip()]


def parse_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    """Parse the small YAML subset skills use, without a YAML dependency.

    Supported: ``key: value``, quoted values, inline lists ``[a, b]`` and block lists
    (``key:`` followed by indented ``- item`` lines). Anything else is left as a string.
    """
    if not text.startswith("---"):
        raise SkillFormatError("missing YAML frontmatter (file must start with ---)")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillFormatError("missing YAML frontmatter (file must start with ---)")
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        raise SkillFormatError("unterminated YAML frontmatter")

    meta: Dict[str, Any] = {}
    current_key: Optional[str] = None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.strip()
        if stripped.startswith("- ") and current_key:
            bucket = meta.get(current_key)
            if not isinstance(bucket, list):
                bucket = []
                meta[current_key] = bucket
            bucket.append(_unquote(stripped[2:]))
            continue
        if ":" not in stripped:
            raise SkillFormatError(f"cannot parse frontmatter line: {raw!r}")
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise SkillFormatError(f"empty frontmatter key in: {raw!r}")
        current_key = key
        if not value:
            meta[key] = []
        elif value.startswith("[") and value.endswith("]"):
            meta[key] = _split_inline_list(value)
        elif value.lower() in ("true", "false"):
            meta[key] = value.lower() == "true"
        else:
            meta[key] = _unquote(value)

    body = "\n".join(lines[end + 1 :]).strip()
    return meta, body


def _extract_section(body: str, *headings: str) -> str:
    """Return the text under one of ``## heading``, or "" when absent."""
    wanted = {h.strip().lower() for h in headings}
    lines = body.splitlines()
    collecting = False
    out: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            title = stripped[3:].strip().lower()
            if title in wanted:
                collecting = True
                continue
            if collecting:
                break
        elif collecting:
            out.append(line)
    return "\n".join(out).strip()


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]


def load_skill_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    missing = [key for key in REQUIRED_FIELDS if not meta.get(key)]
    if missing:
        raise SkillFormatError(f"{path}: missing required field(s): {', '.join(missing)}")

    skill_id = str(meta["id"]).strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", skill_id):
        raise SkillFormatError(f"{path}: id must be kebab-case ASCII, got {skill_id!r}")

    guidance = _extract_section(body, "方法", "guidance", "how") or body
    if not guidance.strip():
        raise SkillFormatError(f"{path}: empty guidance body")

    try:
        priority = int(meta.get("priority", 50))
    except (TypeError, ValueError):
        priority = 50

    return {
        "id": skill_id,
        "name": str(meta["name"]).strip(),
        "purpose": str(meta["purpose"]).strip(),
        "applies_when": _as_list(meta.get("applies_when")),
        "avoid_when": _as_list(meta.get("avoid_when")),
        "priority": priority,
        "guidance": guidance.strip(),
        "example": _extract_section(body, "正例", "example", "examples"),
        "anti_example": _extract_section(body, "反例", "anti-example", "anti_pattern", "anti-patterns"),
        "path": str(path),
    }


def default_skill_roots(project_root: Optional[Path | str] = None) -> List[Path]:
    """Registry roots, lowest precedence first (project overrides bundled)."""
    roots: List[Path] = [PLUGIN_SKILLS_DIR]
    if project_root:
        roots.append(Path(project_root) / PROJECT_SKILLS_REL)
    return roots


def discover_writing_skills(
    roots: Optional[Sequence[Path | str]] = None,
    *,
    project_root: Optional[Path | str] = None,
) -> List[Dict[str, Any]]:
    """Scan ``<root>/<id>/SKILL.md`` (one level deep) and return usable skills.

    Duplicate ids resolve to the later root, so a project skill can deliberately replace
    a bundled one without touching plugin code. Invalid files are skipped rather than
    breaking the chapter; the diagnostics are exposed by :func:`list_with_diagnostics`.
    """
    scan_roots = [Path(r) for r in (roots if roots is not None else default_skill_roots(project_root))]
    by_id: Dict[str, Dict[str, Any]] = {}
    for root in scan_roots:
        if not root.is_dir():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            try:
                skill = load_skill_file(skill_md)
            except (SkillFormatError, OSError, UnicodeDecodeError):
                continue
            by_id[skill["id"]] = skill
    return sorted(by_id.values(), key=lambda s: s["id"])


def list_with_diagnostics(
    roots: Optional[Sequence[Path | str]] = None,
    *,
    project_root: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Like :func:`discover_writing_skills`, but also report skipped files."""
    scan_roots = [Path(r) for r in (roots if roots is not None else default_skill_roots(project_root))]
    by_id: Dict[str, Dict[str, Any]] = {}
    skipped: List[Dict[str, str]] = []
    for root in scan_roots:
        if not root.is_dir():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            try:
                skill = load_skill_file(skill_md)
            except Exception as exc:  # noqa: BLE001 - diagnostics must never break a run
                skipped.append({"path": str(skill_md), "error": str(exc)})
                continue
            by_id[skill["id"]] = skill
    skills = sorted(by_id.values(), key=lambda s: s["id"])
    return {
        "skills": skills,
        "count": len(skills),
        "skipped": skipped,
        "roots": [str(r) for r in scan_roots],
    }


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _usable_plan_value(value: Any) -> str:
    """Drop dangling pointers and next-chapter hand-offs from the routing material.

    The same rule already applies to the Writer's Scene block: a field that only says
    "see story_craft chapter N" or "→ next chapter's goal" carries no material, and a
    router must not translate it into invented guidance.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower().replace(" ", "").replace("`", "")
    if "见story_craft" in lowered or "story_craft第" in lowered:
        return ""
    if "下章目标" in text or "→下章" in text or "->下章" in lowered:
        return ""
    return text


def build_router_catalog(skills: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Compact metadata the router needs to judge applicability."""
    catalog: List[Dict[str, Any]] = []
    for skill in skills:
        entry = {
            "id": skill["id"],
            "name": skill["name"],
            "purpose": _clip(skill.get("purpose", ""), 200),
            "applies_when": _as_list(skill.get("applies_when")),
            "avoid_when": _as_list(skill.get("avoid_when")),
            "priority": int(skill.get("priority", 50)),
            "guidance": _clip(skill.get("guidance", ""), 500),
        }
        example = str(skill.get("example") or "").strip()
        anti = str(skill.get("anti_example") or "").strip()
        if example:
            entry["example"] = _clip(example, 240)
        if anti:
            entry["anti_example"] = _clip(anti, 240)
        catalog.append(entry)
    return catalog


def _normalize_selection_raw(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, Mapping):
        raw = raw.get("selected_skills") or raw.get("skills") or []
    if not isinstance(raw, (list, tuple)):
        raise ValueError("selection must be a JSON object with selected_skills[] or a list")
    normalized: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            normalized.append({"id": item.strip(), "chapter_guidance": ""})
            continue
        if not isinstance(item, Mapping):
            normalized.append({"id": "", "chapter_guidance": ""})
            continue
        skill_id = str(item.get("id") or item.get("skill") or "").strip()
        guidance = (
            item.get("chapter_guidance")
            or item.get("guidance")
            or item.get("instruction")
            or ""
        )
        normalized.append(
            {
                "id": skill_id,
                "chapter_guidance": str(guidance).strip(),
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    return normalized


def validate_selection(
    raw: Any,
    catalog: Sequence[Mapping[str, Any]],
    *,
    max_skills: int = DEFAULT_MAX_SKILLS,
    min_skills: int = 0,
) -> Dict[str, Any]:
    """Validate the router's output before it can reach the Writer.

    Returns ``{"ok", "selected_skills", "errors", "warnings"}``. Order is preserved:
    the router's ordering is its statement of which method matters most this chapter.
    """
    catalog_ids = {str(s["id"]) for s in catalog}
    errors: List[str] = []
    warnings: List[str] = []
    selected: List[Dict[str, Any]] = []
    seen: set[str] = set()

    try:
        items = _normalize_selection_raw(raw)
    except ValueError as exc:
        return {"ok": False, "selected_skills": [], "errors": [str(exc)], "warnings": []}

    for item in items:
        skill_id = item["id"]
        if not skill_id:
            errors.append("selection entry has no id")
            continue
        if skill_id not in catalog_ids:
            errors.append(f"unknown skill id: {skill_id}")
            continue
        if skill_id in seen:
            warnings.append(f"duplicate skill id ignored: {skill_id}")
            continue
        guidance = item["chapter_guidance"]
        if not guidance:
            errors.append(f"{skill_id}: chapter_guidance is required (theory alone must not reach the Writer)")
            continue
        leak = next((tok for tok in THEORY_LEAK_TOKENS if tok in guidance.lower()), None)
        if leak:
            errors.append(
                f"{skill_id}: chapter_guidance leaks meta/theory token {leak!r}; "
                "translate it into what to write, not which method is being used"
            )
            continue
        if len(guidance) > MAX_GUIDANCE_CHARS:
            warnings.append(f"{skill_id}: chapter_guidance truncated to {MAX_GUIDANCE_CHARS} chars")
            guidance = guidance[:MAX_GUIDANCE_CHARS].rstrip()
        seen.add(skill_id)
        selected.append(
            {
                "id": skill_id,
                "chapter_guidance": guidance,
                "reason": item.get("reason", ""),
            }
        )

    if len(selected) > max_skills:
        warnings.append(
            f"{len(selected)} skills selected; keeping the first {max_skills} (default budget)"
        )
        selected = selected[:max_skills]
    if min_skills and len(selected) < min_skills:
        warnings.append(
            f"only {len(selected)} skill(s) selected; {min_skills} is the usual minimum, "
            "but a chapter may legitimately need fewer"
        )

    return {
        "ok": not errors,
        "selected_skills": selected,
        "errors": errors,
        "warnings": warnings,
    }


def selection_fingerprint(selection: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        {"id": item.get("id", ""), "guidance": item.get("chapter_guidance", "")}
        for item in selection
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def render_writer_skills(selection: Sequence[Mapping[str, Any]]) -> List[str]:
    """Render only the chapter-specific instructions, never the skill identity."""
    guidance = [
        str(item.get("chapter_guidance") or "").strip()
        for item in selection
        if isinstance(item, Mapping) and str(item.get("chapter_guidance") or "").strip()
    ]
    if not guidance:
        return []
    lines = [
        "",
        "## 本章创作方法",
        "（以下方法只在本章素材允许的范围内执行；与 Canon、作者意图、本章禁区冲突时，一律以后者为准。）",
    ]
    for idx, text in enumerate(guidance, start=1):
        lines.append(f"{idx}. {text}")
    return lines


def build_router_input(
    *,
    chapter: int,
    story_identity: Mapping[str, Any] | None,
    current_intent: Mapping[str, Any] | None,
    governed_canon: Mapping[str, Any] | None,
    creative_brief: str,
    catalog: Sequence[Mapping[str, Any]],
    writer_context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Assemble the compact routing input (no full Canon dump, no theory dump)."""
    story = dict(story_identity or {})
    intent = dict(current_intent or {})
    directive = intent.get("directive") or {}
    canon = dict(governed_canon or {})

    characters: List[Dict[str, str]] = []
    for row in (canon.get("appearing_characters") or [])[:8]:
        if not isinstance(row, Mapping):
            continue
        c_type = str(row.get("type") or "").strip()
        if c_type and c_type not in ("角色", "人物", "character"):
            continue
        name = str(row.get("name") or row.get("entity_id") or "").strip()
        if not name:
            continue
        states = [
            f"{s.get('field')}：{s.get('value')}"
            for s in (row.get("state") or [])
            if isinstance(s, Mapping) and str(s.get("value") or "").strip()
        ]
        characters.append({"name": name, "state": "；".join(states[:3])})

    scene = {
        key: _usable_plan_value(directive.get(key))
        for key in (
            "scene_goal",
            "scene_conflict",
            "scene_setback",
            "scene_resolution",
            "sequel_reaction",
            "sequel_dilemma",
            "sequel_decision",
            "beat_position",
            "chapter_type",
        )
        if _usable_plan_value(directive.get(key))
    }

    book = {
        "title": story.get("title", ""),
        "genre": story.get("genre", ""),
        "target_readers": story.get("target_readers", ""),
        "volume": story.get("current_volume", 1),
    }
    chapter_intent = {
        "goal": directive.get("goal", ""),
        "conflict": directive.get("conflict", ""),
        "obstacles": directive.get("obstacles", ""),
        "cost": directive.get("cost", ""),
        "chapter_change": directive.get("chapter_change", ""),
        "ending_question": directive.get("ending_question")
        or directive.get("chapter_end_open_question", ""),
        "must_cover_nodes": list(directive.get("must_cover_nodes") or [])[:8],
        "forbidden_zones": list(directive.get("forbidden_zones") or [])[:8],
    }
    return {
        "schema_version": "writing-skill-router/v1",
        "chapter": chapter,
        "book": book,
        "chapter_intent": chapter_intent,
        "scene": scene,
        "characters": characters,
        "voice_target": _compact_voice_target(writer_context),
        "creative_brief": str(creative_brief or "").strip(),
        "available_skills": list(catalog),
        "rules": {
            "select_count": f"{DEFAULT_MIN_SKILLS}-{DEFAULT_MAX_SKILLS}",
            "only_if": "the skill changes how this chapter is actually written",
            "never_override": ["canon", "author_intent", "chapter_forbidden_zones"],
            "writer_already_receives": [
                "场景四问（目标/阻力/被迫选择/场景后变化）",
                "追读三问（期待/当章回报/新期待）",
                "章纲结构与人物状态",
            ],
            "do_not_restate": "若选择 scene-sequel 或 reader-pull，不要复述四问/三问；把它们翻译成本章的具体写法。",
            "output": {"selected_skills": [{"id": "...", "reason": "...", "chapter_guidance": "..."}]},
        },
    }


def _compact_voice_target(writer_context: Mapping[str, Any] | None) -> Dict[str, Any]:
    """Positive style anchor the router can translate into one chapter instruction.

    `prose_voice_target.VoiceTarget` never emitted a `target_voice` key, so the old
    Writer-prompt line was dead. The router consumes the real fields instead of
    changing that unrelated renderer here.
    """
    ctx = dict(writer_context or {})
    target = ctx.get("voice_target") or {}
    if not isinstance(target, Mapping):
        return {}
    picked: Dict[str, Any] = {}
    for key in ("genre", "narrative_pov", "core_rules", "sentence_rhythm", "dialogue_policy", "positive_guidance"):
        value = target.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple)):
            picked[key] = [str(v) for v in value][:6]
        else:
            picked[key] = _clip(str(value), 300)
    return picked
