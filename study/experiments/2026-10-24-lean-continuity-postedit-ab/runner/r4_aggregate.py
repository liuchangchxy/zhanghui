#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggregate the blind-judge scores for the hard-facts/soft-craft round.

Same rubric and parser as the previous round (study/experiments/2026-10-23-writer-freedom-ab),
so the two rounds' numbers are comparable. Reads chN/judge_XY.md and chN/judge_YX.md,
maps blind labels back to arms with chN/blind_key.json, prints per-chapter and overall means.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROUND = "r4"
CHAPTERS = ("ch6", "ch7", "ch10")

DIMS = [
    "对话自然度", "潜台词", "人物声音", "POV", "作者直接解释",
    "描写", "情绪", "句段自然度", "AI 味", "阅读吸引力",
    "总体文学质量", "规则太多", "生硬执行技巧",
]
NEGATIVE = {"规则太多", "生硬执行技巧"}


def _leading_number(cell: str) -> float | None:
    """Judges write "8.5 — reason"; take the score, ignore the commentary."""
    m = re.match(r"\s*\**\s*(\d+(?:\.\d+)?)", cell)
    return float(m.group(1)) if m else None


def _label_column(cells: list[str]) -> int | None:
    for idx, c in enumerate(cells):
        if c.replace(" ", "") in {"维度", "项目", "评分项"}:
            return idx
    return None


def _arm_columns(cells: list[str]) -> dict[str, int]:
    """Map "X"/"Y" to the column holding that arm's score (judges vary the order)."""
    found: dict[str, int] = {}
    for idx, raw in enumerate(cells):
        c = raw.replace(" ", "").replace("*", "")
        if c in {"X", "X分", "稿X", "稿X分"}:
            found["X"] = idx
        elif c in {"Y", "Y分", "稿Y", "稿Y分"}:
            found["Y"] = idx
    return found


def parse(path: Path) -> dict[str, dict[str, float]]:
    """Read the 13-dimension table, honouring whichever column order the judge used.

    Judges write the table in both orders ("| 项目 | 稿 X | 稿 Y |" and
    "| 项目 | 稿 Y | 稿 X |"), sometimes merge score and evidence into one cell,
    so the arm columns and the label column are both read from the header row and
    dimension names are matched against the label column only (evidence prose often
    names other dimensions).
    """
    text = path.read_text(encoding="utf-8")
    out: dict[str, dict[str, float]] = {"X": {}, "Y": {}}
    col = {"X": 1, "Y": 2}
    label_col = 1
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip().strip("*") for c in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if all(set(c) <= set("-: ") for c in cells if c):
            continue
        headers = _arm_columns(cells)
        label = _label_column(cells)
        if label is not None:
            label_col = label
            if headers:
                col = headers
            continue
        if "维度" in "".join(cells) or "项目" in "".join(cells):
            continue
        if label_col >= len(cells):
            continue
        name = cells[label_col].replace(" ", "")
        matched_key = next((key for key in DIMS if key.replace(" ", "") in name), None)
        if matched_key is None:
            continue
        xv = _leading_number(cells[col["X"]]) if col["X"] < len(cells) else None
        yv = _leading_number(cells[col["Y"]]) if col["Y"] < len(cells) else None
        if xv is None or yv is None:
            continue
        out["X"][matched_key] = xv
        out["Y"][matched_key] = yv
    return out


def verdict(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"哪一稿更好[^\n]*", text)
    if not m:
        return None
    # Judges put the verdict on the same line ("哪一稿更好：X") or the next
    # ("**哪一稿更好**\n\nX。"), so look at the heading line and the two lines after it.
    lines = text[m.start():].splitlines()[:3]
    body = "\n".join(lines)
    if "持平" in body or "一样好" in body:
        return "tie"
    # Prefer a standalone verdict token over letters inside the heading itself.
    after = "\n".join(lines[1:]).replace("*", "").strip()
    for source in (after, m.group(0).replace("*", "")):
        for token in re.findall(r"(?:^|[\s：:])([XY])(?=[。，、\s]|$)", source):
            return token
    return None


def map_arms(key: dict[str, str]) -> dict[str, str]:
    return {lab: ("A" if "draft_A" in f else "B") for lab, f in key.items()}


def mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def main() -> int:
    per_chapter: dict[str, dict[str, dict[str, list[float]]]] = {}
    overall = {"A": {k: [] for k in DIMS}, "B": {k: [] for k in DIMS}}
    picks = {"A": 0, "B": 0, "tie": 0}

    for ch in CHAPTERS:
        arm_of = map_arms(json.loads((BASE / ch / ROUND / "blind_key.json").read_text()))
        agg: dict[str, dict[str, list[float]]] = {
            "A": {k: [] for k in DIMS}, "B": {k: [] for k in DIMS},
        }
        for order in ("XY", "YX"):
            p = BASE / ch / ROUND / f"judge_{order}.md"
            if not p.is_file():
                continue
            for lab, dims in parse(p).items():
                arm = arm_of[lab]
                for k, v in dims.items():
                    agg[arm][k].append(v)
                    overall[arm][k].append(v)
            lab = verdict(p)
            if lab:
                arm = "tie" if lab == "tie" else arm_of[lab]
                picks[arm] += 1
        per_chapter[ch] = agg

    print("dimension          | ch6 A   B  | ch7 A   B  | ch10 A  B  | all A   B")
    for k in DIMS:
        row = [f"{k:<18}"]
        for ch in CHAPTERS:
            agg = per_chapter[ch]
            row.append(f"{str(mean(agg['A'][k])):>4} {str(mean(agg['B'][k])):>4}")
        row.append(f"{str(mean(overall['A'][k])):>4} {str(mean(overall['B'][k])):>4}")
        print(" | ".join(row))

    def total(side: str) -> float | None:
        vals = []
        for k in DIMS:
            m = mean(overall[side][k])
            if m is None:
                continue
            vals.append(10 - m if k in NEGATIVE else m)
        return round(sum(vals) / len(vals), 2) if vals else None

    print()
    print(f"adjusted mean (11 positive + 2 inverted): A {total('A')}  B {total('B')}")
    print(f"judge picks: {picks}")

    (BASE / "r4_judge_scores.json").write_text(
        json.dumps(
            {"per_chapter": per_chapter, "overall": overall, "picks": picks},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
