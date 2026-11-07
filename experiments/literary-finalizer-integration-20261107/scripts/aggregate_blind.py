#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggregate the short E2E blind A/B results with mandatory position reversal."""
from __future__ import annotations

import json
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
JUDGES = ["j1", "j2"]


def arm_of(winner: str, left_arm: str) -> str:
    if winner == "TIE":
        return "TIE"
    return left_arm if winner == "LEFT" else ("B" if left_arm == "A" else "A")


def main() -> None:
    records = json.loads((ROOT / "results" / "run_records.json").read_text(encoding="utf-8"))
    all_keys = sorted(records)
    key = json.loads((BLIND / "blind_key.json").read_text(encoding="utf-8"))
    accepted = [k for k, rec in records.items() if rec.get("status") == "ACCEPTED"]
    chapters = sorted(
        k
        for k in all_keys
        if all((BLIND / f"{k}_{j}_pass{p}" / "judgement.json").exists()
               for j in JUDGES for p in (1, 2))
    )
    if not chapters:
        raise SystemExit("no evaluated chapters")
    diagnostic = not accepted
    verdicts: dict[str, dict[str, dict[str, str]]] = {}
    raw_pass = {}
    for ch in chapters:
        verdicts[ch] = {}
        for judge in JUDGES:
            ck = f"{ch}_{judge}"
            first_left = key[ck]["pass1_left"]
            p1 = json.loads(
                (BLIND / f"{ch}_{judge}_pass1" / "judgement.json").read_text(encoding="utf-8")
            )
            p2 = json.loads(
                (BLIND / f"{ch}_{judge}_pass2" / "judgement.json").read_text(encoding="utf-8")
            )
            for dim in DIMENSIONS:
                w1 = p1["dimensions"][dim]["winner"]
                w2 = p2["dimensions"][dim]["winner"]
                a1 = arm_of(w1, first_left)
                a2 = arm_of(w2, "B" if first_left == "A" else "A")
                v = a1 if a1 == a2 else "SPLIT"
                verdicts[ch].setdefault(judge, {})[dim] = v
                raw_pass[f"{ch}_{judge}_{dim}"] = {
                    "pass1": a1,
                    "pass2": a2,
                    "verdict": v,
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
        chapter_overall[ch] = {
            "judge_verdicts": votes,
            "strict_b": all(v == "B" for v in votes),
            "leaning_b": ("B" in votes) and ("A" not in votes),
        }

    out = {
        "diagnostic": diagnostic,
        "b_arm": "finalizer_candidate_rejected" if diagnostic else "finalizer",
        "accepted_chapters": accepted,
        "all_chapters": all_keys,
        "evaluated_chapters": chapters,
        "fallback_or_missing": [c for c in all_keys if c not in chapters],
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
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Blind A/B aggregate — Writer raw (A) vs finalizer (B)",
        "",
        f"Evaluated: {', '.join(chapters) or 'none'}",
        f"Arm B: {out['b_arm']}"
        + (" — DIAGNOSTIC: candidates were rejected by the semantic gate and are not final prose"
           if diagnostic else ""),
        f"Accepted (formal final): {', '.join(accepted) or 'none'}",
        f"Fallback/not evaluated: {', '.join(out['fallback_or_missing']) or 'none'}",
        f"Strict chapter-level OVERALL B: {out['strict_overall_b_count']}/{len(chapters)}",
        f"Leaning chapter-level OVERALL B: {out['leaning_overall_b_count']}/{len(chapters)}",
        "",
    ]
    for judge in JUDGES:
        lines += [
            f"## {judge}",
            "",
            "| dim | A raw | B final | SPLIT | TIE |",
            "|---|---:|---:|---:|---:|",
        ]
        for dim in DIMENSIONS:
            s = summary[judge][dim]
            lines.append(f"| {dim} | {s['A']} | {s['B']} | {s['SPLIT']} | {s['TIE']} |")
        lines.append("")
    lines += ["## pooled (both judges)", "", "| dim | A | B | SPLIT | TIE |", "|---|---:|---:|---:|---:|"]
    for dim in DIMENSIONS:
        s = pooled[dim]
        lines.append(f"| {dim} | {s['A']} | {s['B']} | {s['SPLIT']} | {s['TIE']} |")
    lines += ["", "## per chapter", ""]
    for ch in chapters:
        lines += [f"### {ch}", "", "| dim | J1 | J2 |", "|---|---|---|"]
        for dim in DIMENSIONS:
            lines.append(f"| {dim} | {verdicts[ch]['j1'][dim]} | {verdicts[ch]['j2'][dim]} |")
        lines += [
            "",
            f"strict OVERALL B: **{chapter_overall[ch]['strict_b']}** "
            f"(leaning: {chapter_overall[ch]['leaning_b']})",
            "",
        ]
    (BLIND / "aggregate.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
