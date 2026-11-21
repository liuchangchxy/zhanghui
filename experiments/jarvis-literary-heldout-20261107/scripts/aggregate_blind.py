#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggregate blind A/B results with mandatory position reversal."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLIND = ROOT / "blind"
DIMENSIONS = [
    "OVERALL_PREFERENCE",
    "READING_APPEAL",
    "LOW_AUTHOR_EXPLANATION",
    "SENTENCE_NATURALNESS",
    "SCENE_IMMERSION",
    "SUBTEXT",
]
ALL_CHAPTERS = ["ch01", "ch02", "ch06", "ch07", "ch09", "ch10"]
JUDGES = ["j1", "j2"]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CHAPTERS  # noqa: E402


def arm_of(winner: str, left_arm: str) -> str:
    if winner == "TIE":
        return "TIE"
    return left_arm if winner == "LEFT" else ("B" if left_arm == "A" else "A")


def accepted_keys() -> list[str]:
    p = ROOT / "outputs/RUN_RECORDS.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    return [CHAPTERS[ch]["key"] for ch in sorted(CHAPTERS)
            if rec.get(CHAPTERS[ch]["key"], {}).get("status") == "ACCEPTED"]


def main() -> None:
    key = json.loads((BLIND / "blind_key.json").read_text(encoding="utf-8"))
    chapters = accepted_keys()
    verdicts = {}
    raw_pass = {}
    for ch in chapters:
        verdicts[ch] = {}
        for judge in JUDGES:
            ck = f"{ch}_{judge}"
            first_left = key[ck]["pass1_left"]
            p1 = json.loads((BLIND / f"{ch}_{judge}_pass1/judgement.json").read_text(encoding="utf-8"))
            p2 = json.loads((BLIND / f"{ch}_{judge}_pass2/judgement.json").read_text(encoding="utf-8"))
            for dim in DIMENSIONS:
                w1 = p1["dimensions"][dim]["winner"]
                w2 = p2["dimensions"][dim]["winner"]
                a1 = arm_of(w1, first_left)
                a2 = arm_of(w2, "B" if first_left == "A" else "A")
                if a1 == a2:
                    v = a1
                else:
                    v = "SPLIT"
                verdicts[ch].setdefault(judge, {})[dim] = v
                raw_pass[f"{ch}_{judge}_{dim}"] = {
                    "pass1": a1, "pass2": a2, "verdict": v,
                    "p1_evidence": p1["dimensions"][dim].get("evidence", ""),
                    "p2_evidence": p2["dimensions"][dim].get("evidence", ""),
                    "p1_conf": p1["dimensions"][dim].get("confidence"),
                    "p2_conf": p2["dimensions"][dim].get("confidence"),
                }

    summary = {}
    for judge in JUDGES:
        summary[judge] = {}
        for dim in DIMENSIONS:
            c = Counter(verdicts[ch][judge][dim] for ch in chapters)
            summary[judge][dim] = {k: c.get(k, 0) for k in ("A", "B", "SPLIT", "TIE")}

    pooled = {}
    for dim in DIMENSIONS:
        c = Counter(verdicts[ch][j][dim] for ch in chapters for j in JUDGES)
        pooled[dim] = {k: c.get(k, 0) for k in ("A", "B", "SPLIT", "TIE")}

    chapter_overall = {}
    for ch in chapters:
        votes = [verdicts[ch][j]["OVERALL_PREFERENCE"] for j in JUDGES]
        strict_b = all(v == "B" for v in votes)
        leaning_b = ("B" in votes) and ("A" not in votes)
        chapter_overall[ch] = {
            "judge_verdicts": votes,
            "strict_b": strict_b,
            "leaning_b": leaning_b,
        }

    out = {
        "all_chapters": ALL_CHAPTERS,
        "evaluated_chapters": chapters,
        "rejected_or_missing": [c for c in ALL_CHAPTERS if c not in chapters],
        "judges": JUDGES,
        "dims": DIMENSIONS,
        "verdicts": verdicts,
        "summary_by_judge": summary,
        "pooled": pooled,
        "chapter_overall": chapter_overall,
        "strict_overall_b_count": sum(1 for v in chapter_overall.values() if v["strict_b"]),
        "leaning_overall_b_count": sum(1 for v in chapter_overall.values() if v["leaning_b"]),
        "raw_pass": raw_pass,
    }
    (BLIND / "aggregate.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# Blind A/B aggregate (held-out)", "",
             f"Evaluated: {', '.join(chapters) or 'none'}",
             f"Rejected/missing: {', '.join(out['rejected_or_missing']) or 'none'}",
             f"Strict chapter-level OVERALL B: {out['strict_overall_b_count']}/{len(ALL_CHAPTERS)}",
             f"Leaning chapter-level OVERALL B: {out['leaning_overall_b_count']}/{len(ALL_CHAPTERS)}",
             ""]
    for judge in JUDGES:
        lines += [f"## {judge}", "", "| dim | A original | B edited | SPLIT | TIE |", "|---|---:|---:|---:|---:|"]
        for dim in DIMENSIONS:
            s = summary[judge][dim]
            lines.append(f"| {dim} | {s['A']} | {s['B']} | {s['SPLIT']} | {s['TIE']} |")
        lines.append("")
    lines += ["## pooled (both judges)", "", "| dim | A | B | SPLIT | TIE |", "|---|---:|---:|---:|---:|"]
    for dim in DIMENSIONS:
        s = pooled[dim]
        lines.append(f"| {dim} | {s['A']} | {s['B']} | {s['SPLIT']} | {s['TIE']} |")
    lines += ["", "## per chapter (J1 / J2 / strict-B)", ""]
    for ch in chapters:
        lines.append(f"### {ch}")
        lines.append("")
        lines.append("| dim | J1 | J2 |")
        lines.append("|---|---|---|")
        for dim in DIMENSIONS:
            lines.append(f"| {dim} | {verdicts[ch]['j1'][dim]} | {verdicts[ch]['j2'][dim]} |")
        lines.append("")
        lines.append(f"strict OVERALL B: **{chapter_overall[ch]['strict_b']}** "
                     f"(leaning: {chapter_overall[ch]['leaning_b']})")
        lines.append("")
    (BLIND / "aggregate.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
