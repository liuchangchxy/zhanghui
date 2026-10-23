#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Measure the sealed Writer prompts for the hard-facts/soft-craft round."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def non_space_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def section(prompt: str, heading: str, next_headings: list[str]) -> str:
    start = prompt.find(heading)
    if start < 0:
        return ""
    start += len(heading)
    end = len(prompt)
    for nxt in next_headings:
        idx = prompt.find(nxt, start)
        if 0 <= idx < end:
            end = idx
    return prompt[start:end].strip()


def measure(arm: str, chapter: int) -> dict:
    ch_dir = ROOT / f"ch{chapter}"
    prompt_path = ch_dir / f"prompt_{arm}.txt"
    prompt = prompt_path.read_text(encoding="utf-8")
    brief_path = ch_dir / f"brief_{arm}.txt"
    brief = brief_path.read_text(encoding="utf-8") if brief_path.is_file() else ""

    sel_path = ch_dir / f"sel_{arm}.json"
    sel = json.loads(sel_path.read_text(encoding="utf-8")) if sel_path.is_file() else {}
    guidance = [
        len(item.get("chapter_guidance", ""))
        for item in sel.get("selected_skills", [])
    ]

    skill_heading = "## 本章可用技巧" if arm == "B" else "## 本章创作方法"
    skill_text = section(
        prompt, skill_heading, ["## 交付要求", "## 6. 正文交付协议", "## 前情与线索", "## 5. 关联前情线索"]
    )
    facts = section(prompt, "## 本章必须写对", ["## 当前人物状态与前文事实", "## 2. "])

    result = {
        "arm": arm,
        "chapter": chapter,
        "brief_chars": non_space_len(brief),
        "prompt_chars": non_space_len(prompt),
        "prompt_bytes": len(prompt.encode("utf-8")),
        "guidance": guidance,
        "guidance_avg": round(sum(guidance) / len(guidance), 1) if guidance else 0,
        "skill_section_chars": non_space_len(skill_text),
        "hard_facts_present": bool(facts),
        "hard_facts_chars": non_space_len(facts),
    }
    if chapter == 7:
        result["direction_low"] = "比官方记录低了将近一米" in prompt or "低了将近一米" in prompt
        result["direction_high_in_facts"] = "高了将近一米" in facts
    if chapter == 10:
        result["gap_year"] = "年份连续性有缺口" in facts or "年份缺口" in facts
        result["gap_month_in_facts"] = "月份" in facts or "缺页" in facts
    return result


def main() -> int:
    rows = []
    for chapter in (6, 7, 10):
        for arm in ("A", "B"):
            p = ROOT / f"ch{chapter}" / f"prompt_{arm}.txt"
            if p.is_file():
                rows.append(measure(arm, chapter))
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
