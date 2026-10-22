#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggregate one round-2 chapter's blind scores by arm.

Same convention as the round-1 script: X/Y -> draft_A/draft_B comes from blind_key.json,
so this only transcribes the per-dimension numbers a judge wrote down.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DIMENSIONS = [
    "对话自然度", "潜台词", "人物声音", "POV稳定性", "作者直接解释", "描写具体有作用",
    "情绪由人物体验", "句段自然度", "AI味低", "阅读吸引力", "总体文学质量",
]

DATA: dict[str, dict[str, dict[str, list[float]]]] = {
    "ch4": {
        "judge_1_XY": {
            "forward": {"A": [9, 9, 8.5, 9, 7, 9, 9, 8, 8, 9, 8.5], "B": [7, 7, 8, 8, 6, 9, 9, 7.5, 7, 8, 7.5]},
            "reverse": {"A": [3, 3], "B": [4, 5]},
        },
        "judge_2_YX": {
            "forward": {"A": [8, 6, 6, 7, 7, 8, 7, 8, 7, 7.5, 7.5], "B": [9, 9, 8, 9, 8, 9, 9, 9, 8, 8, 8.5]},
            "reverse": {"A": [6, 6], "B": [3, 3]},
        },
    },
    "ch9": {
        "judge_1_XY": {
            "forward": {"A": [8, 8.5, 8, 9, 8, 9, 8.5, 7.5, 9, 7.5, 8.5], "B": [8.5, 7.5, 7.5, 9, 7, 8.5, 8, 8.5, 8, 8.5, 8]},
            "reverse": {"A": [5, 5], "B": [5.5, 6]},
        },
        "judge_2_YX": {
            "forward": {"A": [7.5, 7.5, 7, 9, 6, 9, 7.5, 8, 6, 8, 7.5], "B": [8.5, 9, 8, 9.5, 8, 9, 9, 7.5, 7, 7.5, 8.5]},
            "reverse": {"A": [6, 6.5], "B": [3, 4]},
        },
    },
}


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else float("nan")


def main() -> int:
    chapter = sys.argv[1] if len(sys.argv) > 1 else "ch4"
    rows = DATA[chapter]
    out = {"chapter": chapter, "judges": {}, "arms": {}}
    for judge, scores in rows.items():
        entry = {}
        for arm in ("A", "B"):
            fwd = scores["forward"][arm]
            rev = scores["reverse"][arm]
            entry[arm] = {"forward_mean": mean(fwd), "reverse_mean": mean(rev),
                          "by_dimension": dict(zip(DIMENSIONS, fwd)) if fwd else {}}
        out["judges"][judge] = entry
    for arm in ("A", "B"):
        fwd_all = [s for j in rows.values() for s in j["forward"][arm]]
        rev_all = [s for j in rows.values() for s in j["reverse"][arm]]
        out["arms"][arm] = {"forward_mean": mean(fwd_all), "reverse_mean": mean(rev_all)}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
