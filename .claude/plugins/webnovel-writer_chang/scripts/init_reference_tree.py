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

# I4 fix: broader CJK punctuation ranges — U+3000-U+303F (CJK Symbols & Punctuation,
# including ！ 。 ？ ， ： 、 ；) and U+FF00-U+FFEF (Halfwidth and Fullwidth Forms,
# including fullwidth （ ）). Without these, CJK titles like "凡人修仙传！" leak the
# punctuation into the filesystem slug.
_CJK_PUNCTUATION_PATTERN = re.compile(
    r"["
    r"　-〿"
    r"＀-￯"
    r"]"
)


def _is_cjk(ch: str) -> bool:
    """Return True if char is in CJK Unified Ideographs BMP range (U+4E00-U+9FFF)."""
    return "一" <= ch <= "鿿"


def _pinyin_slug_with_jieba(text: str) -> str | None:
    """Word-segmented pinyin slug: '凡人修仙传' -> 'fanren-xiuxian-chuan'.

    Uses jieba for word boundaries. Non-CJK segments (punctuation, ASCII)
    are passed through unchanged. Returns None if jieba or pypinyin missing.
    """
    try:
        import jieba
        from pypinyin import lazy_pinyin
    except ImportError:
        return None
    words = [w for w in jieba.cut(text) if w.strip()]
    pieces: list[str] = []
    for w in words:
        if all((not _is_cjk(c)) for c in w):
            pieces.append(w.lower())
            continue
        pinyin_chars = lazy_pinyin(w)
        pieces.append("".join(pinyin_chars))
    return "-".join(pieces)


def _pinyin_slug_fallback(text: str) -> str | None:
    """Per-char pinyin slug without word segmentation: '凡人修仙传' -> 'fanrenxiuxianchuan'.

    Used when jieba is unavailable. Returns None if pypinyin missing.
    Non-CJK chars are appended unchanged (lowercased).

    Note: This produces a different shape than the jieba path (no word
    boundaries), so the same input may yield different slugs depending on
    whether jieba is installed. Documented in sanitize_book_title's docstring.
    """
    try:
        from pypinyin import lazy_pinyin
    except ImportError:
        return None
    pieces: list[str] = []
    for c in text:
        if _is_cjk(c):
            py = lazy_pinyin(c)
            pieces.append("".join(py))
        else:
            pieces.append(c.lower())
    return "".join(pieces)


def sanitize_book_title(title: str) -> str:
    """Convert a reference title to a safe filesystem directory name.

    Rules:
      - Strip path-illegal characters (ASCII + CJK fullwidth brackets).
      - Replace whitespace with `-`.
      - Lowercase.
      - Collapse multiple `-` to single.
      - Strip leading/trailing `-` and `.`.
      - If empty after sanitization, raise ValueError.
      - Truncate to MAX_BOOK_NAME chars.
      - Transliterate CJK characters to pinyin:
        * If `jieba` + `pypinyin` available: word-segmented pinyin
          (e.g. "凡人修仙传" -> "fanren-xiuxian-chuan")
        * If only `pypinyin` available: per-char concatenated pinyin
          (e.g. "凡人修仙传" -> "fanrenxiuxianchuan")
        * If neither available: CJK characters preserved as-is

    Note: The test `test_sanitize_book_title_basic` asserts the jieba
    shape ("fanren-xiuxian-chuan"). On a CI env without jieba, the
    fallback shape ("fanrenxiuxianchuan") will NOT match.
    """
    if not title:
        raise ValueError("book title must not be empty")

    # Strip path-illegal chars (ASCII) + CJK fullwidth brackets.
    safe = re.sub(rf"[\\/:*?\"<>|{_CJK_BRACKETS}]", "", title)
    # I4 fix: strip broader CJK punctuation (U+3000-U+303F, U+FF00-U+FFEF)
    # before pinyin transliteration so they don't leak as pinyin fragments.
    safe = _CJK_PUNCTUATION_PATTERN.sub("", safe)

    # Transliterate CJK runs to pinyin. Try jieba path first (word
    # boundaries), then fallback (per-char concatenated). If neither lib
    # is available, keep ASCII-safe chars as-is.
    slug = _pinyin_slug_with_jieba(safe)
    if slug is None:
        slug = _pinyin_slug_fallback(safe)
    if slug is not None:
        safe = slug

    safe = re.sub(r"\s+", "-", safe)
    safe = re.sub(r"-+", "-", safe)
    safe = safe.strip("-.")
    safe = safe.lower()
    if not safe:
        raise ValueError(f"book title {title!r} sanitizes to empty string")
    return safe[:MAX_BOOK_NAME]


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

    # C3 fix: refuse to write through a symlink (could be attacker-controlled target).
    if tree.is_symlink():
        raise SystemExit(
            f"refusing to write through symlink: {tree}. "
            f"Remove the symlink first or choose a different <book-safe> name."
        )

    if tree.exists():
        if not overwrite:
            raise FileExistsError(
                f"reference_research tree already exists at {tree}. "
                f"Pass overwrite=True or use --reference-overwrite flag."
            )
        existing_schema = tree / "_schema.json"
        if existing_schema.exists():
            backup = tree / f"_schema.json.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')}"
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
