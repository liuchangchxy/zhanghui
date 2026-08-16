#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Build prompt-section injections for webnovel-write from reference_research/.

Implements 2026-08-16-p3-write-review-consume-reference-research-design §D1.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _primary_tree_path(project_root: Path, idea_bank_pointer: str | None,
                       valid_trees: list[Path] | None = None) -> Path | None:
    """Resolve the idea_bank pointer to a real reference_research tree.

    Resolution rules (in order):
      1. The pointer's last path segment after `reference_research` matches a
         tree directory name verbatim → use that tree.
      2. Otherwise, walk the trees and pick the one whose
         `_schema.json.source.reference_title` sanitizes to a substring of the
         pointer segment (so the pointer can store a friendly alias rather than
         the full pinyin slug).
    """
    if not idea_bank_pointer:
        return None
    parts = Path(idea_bank_pointer).parts
    if "reference_research" not in parts:
        return None
    idx = parts.index("reference_research")
    if idx + 1 >= len(parts):
        return None
    book_safe = parts[idx + 1].rstrip("/")
    if not book_safe:
        return None
    candidate = project_root / ".webnovel" / "reference_research" / book_safe
    if valid_trees is not None and candidate in valid_trees:
        return candidate

    # Fallback: scan for a tree whose slug is a substring of the pointer segment.
    try:
        from init_reference_tree import sanitize_book_title
    except ImportError:
        sanitize_book_title = None  # type: ignore[assignment]

    if valid_trees and sanitize_book_title is not None:
        for tree in valid_trees:
            schema = tree / "_schema.json"
            if not schema.is_file():
                continue
            try:
                data = json.loads(schema.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            ref_title = (data.get("source") or {}).get("reference_title") or tree.name
            try:
                slug = sanitize_book_title(ref_title)
            except ValueError:
                continue
            if slug and (book_safe in slug or slug in book_safe):
                return tree
    return candidate


def _load_idea_bank_pointer(project_root: Path) -> str | None:
    idea_bank = project_root / ".webnovel" / "idea_bank.json"
    if not idea_bank.is_file():
        return None
    try:
        data = json.loads(idea_bank.read_text(encoding="utf-8"))
        return data.get("reference_research_path")
    except (json.JSONDecodeError, OSError):
        return None


def _ordered_trees(project_root: Path) -> list[Path]:
    from data_modules.reference_research_scanner import scan_reference_research_trees
    trees = scan_reference_research_trees(project_root)
    primary = _primary_tree_path(
        project_root, _load_idea_bank_pointer(project_root), valid_trees=trees,
    )
    if primary and primary in trees:
        trees = [primary] + [t for t in trees if t != primary]
    return trees


def _read_json_field(tree: Path, field: str, default=None) -> Any:
    schema = tree / "_schema.json"
    if not schema.is_file():
        return default
    try:
        data = json.loads(schema.read_text(encoding="utf-8"))
        return data.get(field, default)
    except (json.JSONDecodeError, OSError):
        return default


def build_step1_summary(project_root: Path) -> str:
    """Build a compact "对标参考" summary string for Step 1 prompt injection.

    Output is hard-capped at 800 chars (~1200 CJK tokens), so it stays a
    small fraction of any L1 prompt. The previous docstring claimed a
    200-token cap that the implementation never honored — that claim
    has been removed; 800 chars is the actual contract.
    """
    trees = _ordered_trees(project_root)
    if not trees:
        return ""
    lines = ["## 对标参考（来自 reference_research/）"]
    for idx, tree in enumerate(trees):
        ref_title = _read_json_field(tree, "source", {}).get("reference_title", tree.name)
        narrative = _read_json_field(tree, "narrative_function", "") or "未标注"
        prefix = "主对标书" if idx == 0 else "对标书"
        lines.append(f"{prefix}：《{ref_title}》 题材：{narrative}")
        if idx == 0:
            borrowable = _read_json_field(tree, "borrowable_structures", [])[:2]
            do_not_copy = _read_json_field(tree, "do_not_copy", [])[:3]
            if borrowable:
                lines.append("可借鉴：" + "、".join(borrowable))
            if do_not_copy:
                lines.append("规避：" + "、".join(do_not_copy))
    summary = "\n".join(lines)
    if len(summary) > 800:
        summary = summary[:797] + "..."
    return summary


def build_step2a_prompt_section(project_root: Path) -> str:
    trees = _ordered_trees(project_root)
    if not trees:
        return ""
    primary = trees[0]
    ref_title = _read_json_field(primary, "source", {}).get("reference_title", primary.name)
    dnc = _read_json_field(primary, "do_not_copy", [])
    ccw = _read_json_field(primary, "canon_contamination_warnings", [])
    borrowable = _read_json_field(primary, "borrowable_structures", [])[:5]
    satisfaction = _read_json_field(primary, "satisfaction_point", [])[:2]
    lines = [
        "## 对标书红黑名单（必读）",
        "",
        f"> 参考书：《{ref_title}》",
        "",
    ]
    if dnc:
        lines.append("### 不可照搬（do_not_copy）")
        for item in dnc:
            lines.append(f"- {item}")
        lines.append("")
    if ccw:
        lines.append("### 必须规避的角色名/地名（canon_contamination_warnings）")
        for item in ccw:
            lines.append(f"- {item}")
        lines.append("")
    if borrowable:
        lines.append("### 可借鉴的结构（borrowable_structures，3-5条）")
        for item in borrowable:
            lines.append(f"- {item}")
        lines.append("")
    if satisfaction:
        lines.append("### 反转 hooks（satisfaction_point，1-2条）")
        for item in satisfaction:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


_CLASSIFIER_SUFFIXES = (
    "人设", "机制", "设定", "体系", "身份", "写法", "风格", "套路", "剧情",
    "结构", "模式", "设定集", "桥段", "风格基调", "氛围",
)


def _do_not_copy_match_tokens(item: str) -> list[str]:
    """Split a do_not_copy item into match tokens.

    Items typically look like:

    * ``"<name><classifier_suffix>"`` — e.g. ``"韩立人设"``, ``"神秘小瓶机制"``
    * ``"<category>: <name>"`` — e.g. ``"原作人物名: 韩立"``

    Rules:

    1. **Colon-prefix form** (``"原作人物名: 韩立"``): strip the prefix and use
       the value side (``"韩立"``) as the literal forbidden term — match it
       even if it is short (1-2 chars), because the user has explicitly named
       the value as forbidden.
    2. **Name+classifier form** (``"韩立人设"``): split on classifier suffixes
       to recover the name part(s), and drop tokens shorter than 3 chars so
       ``"韩立人设"`` does not split to the 2-char ``"韩立"`` (which would
       false-positive on innocent text like ``"韩立群"``).

    Returns a list of match tokens. Always yields at least one token when the
    item is non-empty and ≥ 2 chars, otherwise ``[]``.
    """
    # Rule 1: colon-prefix form → value side, no length filter (it's the
    # explicit forbidden name as stored by the user).
    if ":" in item:
        value = item.split(":", 1)[1].strip()
        if value:
            return [value]

    # Rule 2: name+classifier form → split on classifier suffixes; keep only
    # tokens ≥ 3 chars to avoid 2-char false positives like '韩立' on '韩立群'.
    pattern = "|".join(re.escape(s) for s in _CLASSIFIER_SUFFIXES)
    parts = re.split(f"({pattern})", item)
    tokens: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if not p:
            continue
        if re.fullmatch(pattern, p):
            continue
        if len(p) < 3:
            continue
        if p in seen:
            continue
        seen.add(p)
        tokens.append(p)

    # Fallback: keep the full item if it's ≥ 3 chars (and wasn't already added).
    if not tokens and len(item) >= 3 and item not in seen:
        tokens.append(item)
    return tokens


def build_do_not_copy_check_data(project_root: Path, chapter_text: str) -> list[dict]:
    trees = _ordered_trees(project_root)
    if not trees:
        return []
    violations = []
    lines = chapter_text.splitlines()
    for tree in trees:
        ref_title = _read_json_field(tree, "source", {}).get("reference_title", tree.name)
        for item in _read_json_field(tree, "do_not_copy", []):
            if len(item) < 2:
                continue
            tokens = _do_not_copy_match_tokens(item)
            for line_num, line in enumerate(lines, start=1):
                if any(tok in line for tok in tokens):
                    violations.append({
                        "item": item,
                        "source_book": ref_title,
                        "chapter_line": line_num,
                        "matched_text": line.strip()[:200],
                        "severity": "critical",
                        "category": "do_not_copy_violation",
                    })
    return violations


if __name__ == "__main__":
    import argparse
    import sys as _sys

    # When invoked as `python3 data_modules/reference_research_injector.py ...`,
    # `data_modules` is not on sys.path. Add the parent (scripts/) so the
    # `from data_modules.*` imports inside the helpers resolve.
    _HERE = Path(__file__).resolve().parent
    _PARENT = _HERE.parent
    if str(_PARENT) not in _sys.path:
        _sys.path.insert(0, str(_PARENT))

    parser = argparse.ArgumentParser(
        description="reference_research_injector — build prompt sections for write/review",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("build-step1-summary")
    p1.add_argument("--project-root", required=True)
    p1.set_defaults(fn=lambda a: print(build_step1_summary(Path(a.project_root))))

    p2 = sub.add_parser("build-step2a-section")
    p2.add_argument("--project-root", required=True)
    p2.set_defaults(fn=lambda a: print(build_step2a_prompt_section(Path(a.project_root))))

    p3 = sub.add_parser("build-do-not-copy-check-data")
    p3.add_argument("--project-root", required=True)
    p3.add_argument("--chapter-text", default="")
    p3.add_argument("--chapter-file", default=None,
                    help="Read chapter text from this file (alternative to --chapter-text)")
    p3.set_defaults(fn=lambda a: print(json.dumps(
        build_do_not_copy_check_data(
            Path(a.project_root),
            a.chapter_text if a.chapter_text
            else Path(a.chapter_file).read_text(encoding="utf-8") if a.chapter_file
            else "",
        ),
        ensure_ascii=False,
    )))

    args = parser.parse_args()
    args.fn(args)