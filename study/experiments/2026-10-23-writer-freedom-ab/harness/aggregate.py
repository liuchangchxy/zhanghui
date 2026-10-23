#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggregate the blind-judge scores for the writer-freedom A/B.

Reads chN/judge_XY.md and chN/judge_YX.md, pulls the 13-dimension table, maps the
blind labels back to arms with chN/blind_key.json, and prints per-chapter and
overall means. Judges are independent; a dimension the judge did not score is None.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

DIMS = [
    "对话自然度", "潜台词", "人物声音", "POV", "作者直接解释",
    "描写", "情绪", "句段自然度", "AI 味", "阅读吸引力",
    "总体文学质量", "规则太多", "生硬执行技巧",
]
NEGATIVE = {"规则太多", "生硬执行技巧"}


def parse(path: Path) -> dict[str, dict[str, int]]:
    """Return {'X': {dim_key: score}, 'Y': {...}} for one judge packet review."""
    text = path.read_text(encoding="utf-8")
    out: dict[str, dict[str, int]] = {"X": {}, "Y": {}}
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        label = cells[0]
        for key in DIMS:
            if key in label:
                try:
                    xv = float(cells[1])
                    yv = float(cells[2])
                except ValueError:
                    break
                out["X"][key] = xv
                out["Y"][key] = yv
                break
    return out


def verdict(path: Path) -> str | None:
    """Pull the judge's final 'which draft is better' call (X / Y / 持平)."""
    text = path.read_text(encoding="utf-8")
    m = re.search(r"哪一稿更好[^\n]*\n+\s*\**[XYX／/、 ]+", text)
    if not m:
        return None
    tail = text[m.start():m.start() + 400]
    # Only look at the verdict paragraph, not the whole following section where
    # "X" / "Y" appear again as per-draft problem headings.
    body = tail.split("哪一稿更好", 1)[1].split("##", 1)[0]
    for lab in ("持平", "一样", "相当"):
        if lab in body:
            return "tie"
    for token in re.findall(r"\b([XY])\b|稿\s*([XY])", body):
        lab = token[0] or token[1]
        if lab:
            return lab
    return None


def map_arms(key: dict[str, str]) -> dict[str, str]:
    return {lab: ("A" if "draft_A" in f else "B") for lab, f in key.items()}


def main() -> int:
    per_chapter: dict[str, dict[str, dict[str, list[int]]]] = {}
    for ch in ("ch6", "ch7", "ch10"):
        arm_of = map_arms(json.loads((BASE / ch / "blind_key.json").read_text()))
        agg: dict[str, dict[str, list[int]]] = {
            "A": {k: [] for k in DIMS}, "B": {k: [] for k in DIMS},
        }
        for order in ("XY", "YX"):
            p = BASE / ch / f"judge_{order}.md"
            if not p.exists():
                continue
            scores = parse(p)
            for lab, dims in scores.items():
                arm = arm_of[lab]
                for k, v in dims.items():
                    agg[arm][k].append(v)
        per_chapter[ch] = agg

    def mean(xs: list[int]) -> float | None:
        return round(sum(xs) / len(xs), 2) if xs else None

    print("dimension          | ch6 A  B | ch7 A  B | ch10 A  B | all A  B")
    overall = {"A": {k: [] for k in DIMS}, "B": {k: [] for k in DIMS}}
    for k in DIMS:
        row = [f"{k:<18}"]
        for ch in ("ch6", "ch7", "ch10"):
            agg = per_chapter[ch]
            row.append(
                f"{mean(agg['A'][k])!s:>4} {mean(agg['B'][k])!s:>4}"
            )
            overall["A"][k] += agg["A"][k]
            overall["B"][k] += agg["B"][k]
        row.append(f"{mean(overall['A'][k])!s:>4} {mean(overall['B'][k])!s:>4}")
        print(" | ".join(row))

    def total(side: str) -> float:
        vals = []
        for k in DIMS:
            xs = overall[side][k]
            if not xs:
                continue
            m = sum(xs) / len(xs)
            vals.append(10 - m if k in NEGATIVE else m)
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    print()
    print("adjusted mean over 11 positive dims + 2 inverted dims")
    print("  A:", total("A"))
    print("  B:", total("B"))

    print()
    print("judge picks (X/Y mapped back to arms):")
    picks = {"A": 0, "B": 0, "tie": 0}
    for ch in ("ch6", "ch7", "ch10"):
        arm_of = map_arms(json.loads((BASE / ch / "blind_key.json").read_text()))
        for order in ("XY", "YX"):
            p = BASE / ch / f"judge_{order}.md"
            if not p.exists():
                continue
            lab = verdict(p)
            if lab is None:
                continue
            arm = "tie" if lab == "tie" else arm_of[lab]
            picks[arm] += 1
            print(f"  {ch} judge_{order}: {lab} -> arm {arm}")
    print("  tally:", picks)

    dump = {"per_chapter": per_chapter, "overall": overall, "picks": picks}
    (BASE / "judge_scores.json").write_text(
        json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
