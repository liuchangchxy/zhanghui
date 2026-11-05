#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Measure the round-3 sealed prompts (one-sentence skill delivery)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def ns(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def section(prompt: str, heading: str, ends: list[str]) -> str:
    start = prompt.find(heading)
    if start < 0:
        return ""
    end = len(prompt)
    for nxt in ends:
        idx = prompt.find(nxt, start + len(heading))
        if 0 <= idx < end:
            end = idx
    return prompt[start:end].strip()


def measure(arm: str, chapter: int, prompt_path: Path, sel_path: Path | None) -> dict:
    prompt = prompt_path.read_text(encoding="utf-8")
    skill_heading = "## 本章可用技巧" if arm == "B" else "## 本章创作方法"
    skills = section(prompt, skill_heading, ["## 交付要求", "## 6. 正文交付协议"])
    facts = section(prompt, "## 本章必须写对", ["## 当前人物状态与前文事实", "## 2. 治理事实"])
    brief = ""
    if arm == "B":
        brief = section(prompt, "## 创作方向", ["## 工艺与边界", "## 4. 调性"])
    guidance = []
    if sel_path and sel_path.is_file():
        sel = json.loads(sel_path.read_text(encoding="utf-8"))
        guidance = [len(i.get("chapter_guidance", "")) for i in sel.get("selected_skills", [])]
    return {
        "arm": arm,
        "chapter": chapter,
        "prompt_chars": ns(prompt),
        "brief_chars": ns(brief),
        "skill_section_chars": ns(skills),
        "hard_facts_chars": ns(facts),
        "guidance": guidance,
        "direction_low": "低了将近一米" in facts if chapter == 7 else None,
        "gap_year": ("年份连续性" in facts) if chapter == 10 else None,
    }


def main() -> None:
    out = []
    for ch in (6, 7, 10):
        out.append(measure("A", ch, ROOT / f"ch{ch}" / "prompt_A.txt", ROOT / f"ch{ch}" / "sel_A.json"))
        out.append(measure("B", ch, ROOT / f"ch{ch}" / "prompt_B.txt", ROOT / f"ch{ch}" / "sel_B.json"))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
