#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Build and validate the .webnovel/reference_research/<book-safe>/ product tree.

Implements 2026-08-16-webnovel-init-deconstruction-wiring-design §D3/§D6.

Layout produced under a project root:

    .webnovel/reference_research/<book-safe>/
    ├── _schema.json                       # verbatim init_reference_research JSON
    ├── report.md                          # Jinja-rendered summary report
    ├── do_not_copy.md                     # field extract from schema.do_not_copy
    ├── canon_contamination_warnings.md    # field extract from schema.canon_contamination_warnings
    └── _progress.json                     # resumption state + version

The renderer flattens the nested fields expected by the template:
    source.reference_title, source.analysis_mode,
    quality.confidence, quality.coverage

It uses Jinja2 if available (preferred — required by the .j2 template's
{% for %} loops and {{ "%.2f" | format(...) }} filter). If Jinja2 is missing
the module raises a clear install-time error rather than a half-rendered
document — install jinja2 to enable this helper.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEMPLATE_DIR = Path(__file__).parent / "data_modules" / "templates"
MAX_BOOK_NAME = 64

# CJK fullwidth brackets that should be stripped alongside ASCII path-illegal chars.
_CJK_BRACKETS = "《》「」『』【】"


def _try_pinyin_slug(chars: str) -> str | None:
    """Best-effort Chinese-to-pinyin slug.

    Returns the pinyin-joined slug (using jieba word boundaries when available,
    otherwise per-character), or None if pinyin libs are unavailable / input
    contains no Chinese.
    """
    if not any("一" <= ch <= "鿿" for ch in chars):
        return None
    try:
        from pypinyin import lazy_pinyin
    except ImportError:
        return None

    pieces: list[str]
    try:
        import jieba
        words = [w for w in jieba.cut(chars) if w.strip()]
        pieces = []
        for w in words:
            for syllable in lazy_pinyin(w):
                pieces.append(syllable)
    except ImportError:
        pieces = list(lazy_pinyin(chars))

    return "-".join(pieces)


def sanitize_book_title(title: str) -> str:
    """Convert a reference title to a safe filesystem directory name.

    Rules:
      - Strip path-illegal characters (ASCII + CJK fullwidth brackets).
      - Transliterate Chinese characters to pinyin (if pypinyin/jieba
        are installed; otherwise leave the chars as-is and fall back
        to a safe ASCII transliteration).
      - Replace whitespace with `-`.
      - Lowercase.
      - Collapse multiple `-` to single.
      - Strip leading/trailing `-` and `.`.
      - If empty after sanitization, raise ValueError.
      - Truncate to MAX_BOOK_NAME chars.
    """
    if not title:
        raise ValueError("book title must not be empty")

    # Strip path-illegal chars (ASCII) + CJK fullwidth brackets.
    safe = re.sub(rf"[\\/:*?\"<>|{_CJK_BRACKETS}]", "", title)

    # Pull out any Chinese run and pinyin-transliterate it. We preserve
    # jieba word boundaries (凡人 / 修仙 / 传 → fanren / xiuxian / chuan)
    # by emitting a "-" between adjacent Chinese words. Syllables within
    # a single word are concatenated without separator.
    pinyin = _try_pinyin_slug(safe)
    if pinyin:
        try:
            import jieba
            words = [w for w in jieba.cut(safe) if w.strip()]
            pieces: list[str] = []
            for w in words:
                pinyin_words = _pinyin_for_segment(w)
                if pinyin_words is None:
                    pieces.append(w)
                else:
                    pieces.append("".join(pinyin_words))
            safe = "-".join(pieces)
        except ImportError:
            # Without jieba, fall back to the precomputed pinyin slug.
            safe = pinyin

    safe = re.sub(r"\s+", "-", safe)
    safe = re.sub(r"-+", "-", safe)
    safe = safe.strip("-.")
    safe = safe.lower()
    if not safe:
        raise ValueError(f"book title {title!r} sanitizes to empty string")
    return safe[:MAX_BOOK_NAME]


def _pinyin_for_segment(segment: str) -> list[str] | None:
    """Return pinyin syllables for a Chinese segment, or None if segment has no Chinese."""
    if not any("一" <= ch <= "鿿" for ch in segment):
        return None
    try:
        from pypinyin import lazy_pinyin
    except ImportError:
        return None
    return list(lazy_pinyin(segment))


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def _flatten_schema_for_template(schema: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested source.* / quality.* / boundary_reason fields.

    The Jinja template expects top-level variables
    (reference_title, analysis_mode, confidence, coverage, ...),
    but the agent schema nests them under source.* and quality.*.
    """
    source = schema.get("source", {}) or {}
    quality = schema.get("quality", {}) or {}
    boundary = schema.get("boundary_reason") or {}
    init_candidates = schema.get("init_candidates") or {}

    return {
        "reference_title": source.get("reference_title") or source.get("title", ""),
        "analysis_mode": source.get("analysis_mode", "quick"),
        "confidence": quality.get("confidence", 0.0),
        "coverage": quality.get("coverage", 0.0),
        "reader_promise": schema.get("reader_promise", ""),
        "opening_hook_patterns": schema.get("opening_hook_patterns", []),
        "cool_point_loops": schema.get("cool_point_loops", []),
        "protagonist_patterns": schema.get("protagonist_patterns", ""),
        "antagonist_pressure_patterns": schema.get("antagonist_pressure_patterns", ""),
        "pacing_notes": schema.get("pacing_notes", ""),
        "narrative_function": schema.get("narrative_function", ""),
        "boundary_reason": boundary,
        "protagonist_action_chain": schema.get("protagonist_action_chain", []),
        "emotion_curve": schema.get("emotion_curve", []),
        "satisfaction_point": schema.get("satisfaction_point", []),
        "foreshadowing": schema.get("foreshadowing", []),
        "gains_costs": schema.get("gains_costs", []),
        "character_changes": schema.get("character_changes", []),
        "borrowable_structures": schema.get("borrowable_structures", []),
        "differentiation_requirements": schema.get("differentiation_requirements", ""),
        "init_candidates": init_candidates,
    }


def _render_report(schema: dict[str, Any]) -> str:
    """Render report.md from schema using the Jinja template."""
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError as exc:
        raise RuntimeError(
            "jinja2 is not installed. Install with: "
            "pip install jinja2 --break-system-packages. "
            "The reference_report.md.j2 template requires Jinja2 features "
            "(loops and filters)."
        ) from exc

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=("md",)),
        keep_trailing_newline=True,
    )
    template = env.get_template("reference_report.md.j2")
    return template.render(**_flatten_schema_for_template(schema))


def _render_field_extract(field_name: str, items: list[Any]) -> str:
    """Render a single-field extract file (do_not_copy.md / canon_contamination_warnings.md)."""
    lines = [
        f"# {field_name}\n",
        f"> 自动从 deconstruction-agent 抽取的 `{field_name}` 字段。\n",
        "",
    ]
    for item in items:
        if isinstance(item, dict):
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Tree builder + validator
# ---------------------------------------------------------------------------


def build_reference_tree(
    project_path: Path,
    schema: dict[str, Any],
    reference_title: str,
    *,
    overwrite: bool = False,
) -> Path:
    """Build the multi-file product tree under project_path/reference_research/<book-safe>/."""
    safe = sanitize_book_title(reference_title)
    webnovel = project_path / ".webnovel"
    tree = webnovel / "reference_research" / safe

    if tree.exists():
        if not overwrite:
            raise FileExistsError(
                f"reference_research tree already exists at {tree}. "
                f"Pass overwrite=True or use --reference-overwrite flag."
            )
        existing_schema = tree / "_schema.json"
        if existing_schema.exists():
            backup = tree / f"_schema.json.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            existing_schema.rename(backup)

    tree.mkdir(parents=True, exist_ok=True)

    # 1. _schema.json (verbatim dump)
    (tree / "_schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # 2. report.md (Jinja-rendered)
    (tree / "report.md").write_text(_render_report(schema), encoding="utf-8")

    # 3. do_not_copy.md (field extract)
    dnc = schema.get("do_not_copy", []) or []
    (tree / "do_not_copy.md").write_text(
        _render_field_extract("do_not_copy", dnc), encoding="utf-8",
    )

    # 4. canon_contamination_warnings.md (field extract)
    ccw = schema.get("canon_contamination_warnings", []) or []
    (tree / "canon_contamination_warnings.md").write_text(
        _render_field_extract("canon_contamination_warnings", ccw), encoding="utf-8",
    )

    # 5. _progress.json (resumption state)
    now = datetime.now(timezone.utc).isoformat()
    progress = {
        "schema_version": 1,
        "reference_title": reference_title,
        "created_at": now,
        "last_updated": now,
        "superseded_versions": [],
        "quality_flags": schema.get(
            "quality", {"passed": False, "confidence": 0.0, "coverage": 0.0},
        ),
    }
    (tree / "_progress.json").write_text(
        json.dumps(progress, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return tree


def validate_reference_tree(tree: Path) -> bool:
    """Return True iff tree has all required files."""
    required = (
        "_schema.json",
        "report.md",
        "do_not_copy.md",
        "canon_contamination_warnings.md",
        "_progress.json",
    )
    return all((tree / name).is_file() for name in required)
