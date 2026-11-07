#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic content-preservation screen for the short E2E.

This is evidence, not a verdict. The manual check in analysis/CONTENT_CHECK.md
remains authoritative for propulsion information, inference links, chapter-end
hooks, subtext and sensory carrying.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUFFIX = ("_" + sys.argv[1]) if len(sys.argv) > 1 else ""
OUT_SUFFIX = "_V2" if SUFFIX else ""


def clean(text: str) -> str:
    text = re.sub(r"(?m)^\s*\*{0,2}封包验证指纹[^\n]*\n?", "", text)
    text = re.sub(r"(?m)^\s*[0-9a-f]{64}\s*$\n?", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def body(text: str) -> str:
    return re.sub(r"\s", "", clean(text))


def nums(text: str) -> Counter:
    return Counter(re.findall(r"\d+(?:\.\d+)?", text))


def codes(text: str) -> Counter:
    return Counter(re.findall(r"\b[A-Za-z]{1,5}[-–]?\d+[A-Za-z0-9-]*\b", text))


def dates(text: str) -> Counter:
    pats = [
        r"\d{4}\s*[年./-]\s*\d{1,2}(?:\s*[月./-]\s*\d{1,2}\s*日?)?",
        r"[一二三四五六七八九十]{1,3}\s*月\s*[一二三四五六七八九十]{1,3}\s*日",
        r"\d{1,2}\s*/\s*\d{1,2}",
    ]
    found = []
    for p in pats:
        found += re.findall(p, text)
    return Counter(found)


def quoted(text: str) -> list[str]:
    return re.findall(r"[“\"]([^”\"]{2,})[”\"]", text)


def shingles(text: str, n: int = 8) -> set[str]:
    compact = body(text)
    return {compact[i : i + n] for i in range(max(0, len(compact) - n + 1))}


def tail_retention(a: str, b: str) -> dict:
    paras = [p.strip() for p in a.split("\n\n") if p.strip()]
    b_paras = {p.strip() for p in b.split("\n\n") if p.strip()}
    last = paras[-1] if paras else ""
    last2 = "\n".join(paras[-2:]) if len(paras) >= 2 else last
    sb = shingles(b, 8)

    def ratio(src: str) -> float:
        if len(body(src)) < 8:
            return 1.0 if src.strip() in b_paras else 0.0
        s = shingles(src, 8)
        return round(len(s & sb) / max(1, len(s)), 4)

    return {
        "last_paragraph_8char_retention": ratio(last),
        "last_two_paragraphs_8char_retention": ratio(last2),
    }


def main() -> None:
    records = json.loads(
        (ROOT / "results" / f"run_records{SUFFIX}.json").read_text(encoding="utf-8")
    )
    report = {}
    diff_lines = ["# Writer raw → finalizer diff", ""]
    for key in sorted(records):
        rec = records[key]
        accepted = rec.get("status") == "ACCEPTED"
        arm = "final" if accepted else "candidate_rejected"
        artifact = (
            ROOT / "outputs" / f"{key}_final{SUFFIX}.md"
            if accepted
            else ROOT / "outputs" / f"{key}_candidate.md"
        )
        if not artifact.exists():
            report[key] = {"status": rec.get("status"), "reasons": rec.get("reasons", [])}
            continue
        a = clean((ROOT / "inputs" / f"{key}_raw.md").read_text(encoding="utf-8"))
        b = clean(artifact.read_text(encoding="utf-8"))
        na, nb = nums(a), nums(b)
        ca, cb = codes(a), codes(b)
        da, db = dates(a), dates(b)
        qa, qb = quoted(a), quoted(b)
        qb_set = set(qb)
        report[key] = {
            "status": rec.get("status"),
            "evaluated_arm": arm,
            "gate_reasons": rec.get("reasons", []),
            "source_body_chars": len(body(a)),
            "output_body_chars": len(body(b)),
            "length_ratio": round(len(body(b)) / max(1, len(body(a))), 4),
            "numbers_missing": {k: na[k] - nb.get(k, 0) for k in sorted(na) if na[k] > nb.get(k, 0)},
            "numbers_added": {k: nb[k] - na.get(k, 0) for k in sorted(nb) if nb[k] > na.get(k, 0)},
            "codes_missing": {k: ca[k] - cb.get(k, 0) for k in sorted(ca) if ca[k] > cb.get(k, 0)},
            "codes_added": {k: cb[k] - ca.get(k, 0) for k in sorted(cb) if cb[k] > ca.get(k, 0)},
            "dates_missing": {k: da[k] - db.get(k, 0) for k in sorted(da) if da[k] > db.get(k, 0)},
            "dates_added": {k: db[k] - da.get(k, 0) for k in sorted(db) if db[k] > da.get(k, 0)},
            "quoted_segments_source": len(qa),
            "quoted_segments_output": len(qb),
            "quoted_segments_missing": [
                q for q in qa if len(q) >= 6 and q not in qb_set
            ],
            "paragraphs_source": len([x for x in a.split("\n\n") if x.strip()]),
            "paragraphs_output": len([x for x in b.split("\n\n") if x.strip()]),
            **tail_retention(a, b),
        }
        a_lines = [x.strip() for x in a.split("\n") if x.strip()]
        b_lines = [x.strip() for x in b.split("\n") if x.strip()]
        diff = list(
            difflib.unified_diff(
                a_lines, b_lines, fromfile=f"{key} raw", tofile=f"{key} {arm}", lineterm="", n=1
            )
        )
        diff_lines += [f"## {key} ({arm})", "", "```diff", *diff, "```", ""]
    (ROOT / "analysis" / f"CONTENT_CHECK{OUT_SUFFIX}_AUTO.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "analysis" / f"DIFFS{OUT_SUFFIX}.md").write_text(
        "\n".join(diff_lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
