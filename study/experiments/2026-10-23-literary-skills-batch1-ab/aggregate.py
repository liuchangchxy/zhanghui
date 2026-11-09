#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggregate the two blind judges' scores by arm, for one chapter.

Scores are transcribed from eval/judge_*.md. The key maps X/Y to draft_A/draft_B, so
this script only needs the per-dimension numbers; it never guesses the mapping.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DIMENSIONS = [
    "对话自然度", "潜台词", "人物声音", "POV稳定性", "作者直接解释", "描写具体有作用",
    "情绪由人物体验", "句段自然度", "AI味低", "阅读吸引力", "总体文学质量",
]
REVERSE = ["规则太多", "生硬执行技巧"]

# Per chapter: judge -> {arm: forward scores} and reverse scores.
DATA = {
    "ch3": {
        "judge_1_XY": {
            "forward": {"A": [7, 7, 7, 9, 6, 7, 7, 8, 6, 8, 8], "B": [9, 9, 9, 9, 7, 9, 9, 9, 7, 9, 9]},
            "reverse": {"A": [5, 6], "B": [4, 4]},
        },
        "judge_2_YX": {
            "forward": {"A": [8, 9, 7, 9, 9, 9, 9, 8, 7, 8, 9], "B": [7, 7, 8, 10, 8, 9, 7, 9, 6, 8, 8]},
            "reverse": {"A": [3, 3], "B": [6, 7]},
        },
    },
    "ch5": {
        "judge_1_XY": {
            "forward": {"A": [8, 8, 9, 9, 7, 9, 9, 7, 6, 8, 8], "B": [7, 7, 7, 9, 5, 8, 8, 8, 5, 7, 7]},
            "reverse": {"A": [5, 5], "B": [7, 7]},
        },
        "judge_2_YX": {
            "forward": {"A": [7.5, 7.0, 7.5, 9.0, 6.5, 8.0, 8.0, 8.0, 7.0, 8.0, 8.0], "B": [7.0, 8.5, 8.5, 9.0, 7.5, 9.0, 8.5, 7.5, 7.5, 7.5, 8.5]},
            "reverse": {"A": [7.0, 7.0], "B": [5.0, 5.5]},
        },
    },
}


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else float("nan")


def main() -> int:
    chapter = sys.argv[1] if len(sys.argv) > 1 else "ch3"
    rows = DATA[chapter]
    out = {"chapter": chapter, "dimensions": DIMENSIONS, "reverse": REVERSE, "judges": {}}
    for judge, scores in rows.items():
        entry = {}
        for arm in ("A", "B"):
            fwd = scores["forward"][arm]
            rev = scores["reverse"][arm]
            entry[arm] = {
                "forward_mean": mean(fwd),
                "reverse_mean": mean(rev),
                "by_dimension": dict(zip(DIMENSIONS, fwd)) if fwd else {},
            }
        out["judges"][judge] = entry
    for arm in ("A", "B"):
        fwd_all = [s for j in rows.values() for s in j["forward"][arm]]
        rev_all = [s for j in rows.values() for s in j["reverse"][arm]]
        out.setdefault("arms", {})[arm] = {
            "forward_mean": mean(fwd_all),
            "reverse_mean": mean(rev_all),
        }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
