#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic chapter-length contract.

Why this exists
---------------
The Skill documents a default target of 2000-2500 汉字 per chapter, but nothing in the
commit path ever checked it: `precommit` only asserted the chapter file existed and was
non-empty, and `prose_quality_gate`'s shrinkage rule compares a revision against the draft
it came from. A chapter 27 characters short of the documented floor could therefore be
accepted with a 100 defect score.

The fix is deliberately narrow. A default *target* is advice and stays advisory — turning
2000-2500 into an unwaivable gate would reject legitimate short chapters and make the
number unoverridable. Only an **explicitly declared hard contract** blocks, and it is
declared in one of two places, checked in this order:

1. the chapter contract — `chapter_directive.length_contract` in
   `.story-system/chapters/chapter_NNN.json` (or the same key under the chapter's entry in
   `.story-system/chapter_contracts.json`);
2. the project default — `project_info.chapter_length_contract` in `.webnovel/state.json`.

Both accept ``{"min_chars": int, "max_chars": int, "hard": bool}``. `min_chars`/`max_chars`
are counted in 汉字 (CJK ideographs), matching how the chapter length is reported elsewhere.
A contract without ``"hard": true`` is reported as a warning, never as a blocking error.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Default documented target. Advisory only — see the module docstring.
DEFAULT_TARGET_MIN = 2000
DEFAULT_TARGET_MAX = 2500

_CJK_RE = re.compile(r"[㐀-䶿一-鿿]")


def count_hanzi(text: str) -> int:
    """Count CJK ideographs, ignoring punctuation, whitespace and Latin text."""
    return len(_CJK_RE.findall(str(text or "")))


def _coerce_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _normalize_contract(raw: Any, source: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    min_chars = _coerce_int(raw.get("min_chars") or raw.get("min"))
    max_chars = _coerce_int(raw.get("max_chars") or raw.get("max"))
    if min_chars is None and max_chars is None:
        return None
    if min_chars is not None and max_chars is not None and min_chars > max_chars:
        min_chars, max_chars = max_chars, min_chars
    return {
        "min_chars": min_chars,
        "max_chars": max_chars,
        # Explicit opt-in only. A contract that merely states a range is advisory.
        "hard": raw.get("hard") is True,
        "source": source,
    }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def resolve_length_contract(project_root: Path, chapter: int) -> dict[str, Any]:
    """Return the length contract in force for a chapter.

    The result always has a `source`: `chapter_contract`, `project_default`, or `default`.
    `declared` is False for the built-in advisory default, so callers can tell "the author
    asked for this range" apart from "nobody said anything".
    """
    root = Path(project_root)

    chapter_path = root / ".story-system" / "chapters" / f"chapter_{int(chapter):03d}.json"
    chapter_payload = _read_json(chapter_path)
    if isinstance(chapter_payload, dict):
        directive = chapter_payload.get("chapter_directive")
        if isinstance(directive, dict):
            contract = _normalize_contract(
                directive.get("length_contract"), "chapter_contract"
            )
            if contract:
                contract["declared"] = True
                return contract

    contracts_path = root / ".story-system" / "chapter_contracts.json"
    contracts_payload = _read_json(contracts_path)
    if isinstance(contracts_payload, dict):
        entry = contracts_payload.get(str(int(chapter))) or contracts_payload.get(int(chapter))
        if isinstance(entry, dict):
            directive = entry.get("chapter_directive") if isinstance(entry.get("chapter_directive"), dict) else entry
            contract = _normalize_contract(
                directive.get("length_contract"), "chapter_contract"
            )
            if contract:
                contract["declared"] = True
                return contract

    state_payload = _read_json(root / ".webnovel" / "state.json")
    if isinstance(state_payload, dict):
        project_info = state_payload.get("project_info")
        if isinstance(project_info, dict):
            contract = _normalize_contract(
                project_info.get("chapter_length_contract"), "project_default"
            )
            if contract:
                contract["declared"] = True
                return contract

    return {
        "min_chars": DEFAULT_TARGET_MIN,
        "max_chars": DEFAULT_TARGET_MAX,
        "hard": False,
        "source": "default",
        "declared": False,
    }


def check_chapter_length(project_root: Path, chapter: int, prose: str) -> dict[str, Any]:
    """Compare the chapter's 汉字 count against the contract in force.

    Returns a report with `errors` (deterministic, only for a declared hard contract) and
    `warnings` (everything else). Never raises: a missing or unreadable chapter file is the
    precommit gate's problem, not this one's.
    """
    contract = resolve_length_contract(project_root, chapter)
    count = count_hanzi(prose)
    min_chars = contract.get("min_chars")
    max_chars = contract.get("max_chars")

    shortfall = count < min_chars if min_chars else False
    overage = count > max_chars if max_chars else False
    if not (shortfall or overage):
        return {"contract": contract, "count": count, "errors": [], "warnings": []}

    bound = "下限" if shortfall else "上限"
    limit = min_chars if shortfall else max_chars
    delta = abs(count - limit)
    ratio = (delta / limit * 100) if limit else 0.0
    message = (
        f"章节汉字数 {count} 低于篇幅合同下限 {min_chars}" if shortfall
        else f"章节汉字数 {count} 超过篇幅合同上限 {max_chars}"
    )

    if contract.get("hard"):
        return {
            "contract": contract,
            "count": count,
            "errors": [
                {
                    "type": "chapter_length_contract_violation",
                    "message": message,
                    "impact": (
                        f"本章声明了硬性篇幅合同（来源 {contract.get('source')}），"
                        f"当前距{bound} {delta} 字（{ratio:.2f}%）。"
                    ),
                    "repair": (
                        f"补写或精简正文使汉字数落在 "
                        f"{min_chars or '-'}-{max_chars or '-'} 区间；"
                        "确需豁免请修改章节合同的 length_contract（去掉 hard 或调整区间），"
                        "不要在正文之外绕过。"
                    ),
                    "details": {
                        "count": count,
                        "min_chars": min_chars,
                        "max_chars": max_chars,
                        "delta": delta,
                        "contract_source": contract.get("source"),
                    },
                }
            ],
            "warnings": [],
        }

    return {
        "contract": contract,
        "count": count,
        "errors": [],
        "warnings": [
            {
                "type": "chapter_length_off_target",
                "message": message,
                "severity": "warning",
                "impact": (
                    "这是建议目标（未声明 hard），不阻断提交；仅提示篇幅偏离。"
                    if contract.get("declared")
                    else "这是内置默认目标 2000-2500，未声明硬性合同，不阻断提交。"
                ),
                "details": {
                    "count": count,
                    "min_chars": min_chars,
                    "max_chars": max_chars,
                    "delta": delta,
                    "contract_source": contract.get("source"),
                },
            }
        ],
    }
