#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic preservation checks + diff for accepted A/B pairs.

These checks are guards, not a quality score. Manual review remains authoritative.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CHAPTERS, input_path, output_path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

TERMS = [
    "林越", "梅叔", "乔宁", "韩策", "临汐城", "白塔", "白塔事故", "白塔能源站",
    "档案屋", "黄铜钥匙", "皮面笔记本", "第三册", "第四册", "铁皮柜",
    "旧维护轨道", "三号泵房", "七号泵房", "切换盒", "封存门", "临时医疗单",
    "医疗单", "值班确认单", "移交单", "交接班登记簿", "铅封", "封条", "巡防",
    "雨衣", "通行卡", "废品站", "旧图柜", "报废箱", "齿口", "锁芯", "硫酸纸",
    "防潮油纸", "纤维", "样本", "借条", "签到表", "维保", "调度井", "地下通道",
]

TERM_REPLACEMENT_GUARD = {
    "高潮": "高值",
    "低潮": "低值",
    "潮位": "水位值",
}


def body(text: str) -> str:
    return re.sub(r"\s", "", text)


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
    return {compact[i:i + n] for i in range(max(0, len(compact) - n + 1))}


def tail_retention(a: str, b: str) -> dict:
    paras = [p.strip() for p in a.split("\n\n") if p.strip()]
    b_paras = {p.strip() for p in b.split("\n\n") if p.strip()}
    last = paras[-1] if paras else ""
    last2 = "\n".join(paras[-2:]) if len(paras) >= 2 else last
    sb = shingles(b, 8)

    def ratio(src: str) -> float:
        # A one- or two-character ending ("明天。") has no 8-char shingle.
        # Treat it as retained only if that exact paragraph survives as a paragraph.
        if len(body(src)) < 8:
            return 1.0 if src.strip() in b_paras else 0.0
        s = shingles(src, 8)
        return round(len(s & sb) / max(1, len(s)), 4)

    return {"last_paragraph_8char_retention": ratio(last),
            "last_two_paragraphs_8char_retention": ratio(last2)}


def main() -> None:
    report = {}
    diff_lines = ["# A → B diff（原文 → 编辑后）", ""]
    for ch, meta in CHAPTERS.items():
        a = input_path(ch).read_text(encoding="utf-8")
        p = output_path(ch)
        if not p.exists():
            report[meta["key"]] = {"status": "REJECTED_OR_MISSING"}
            continue
        b = p.read_text(encoding="utf-8")
        na, nb = nums(a), nums(b)
        ca, cb = codes(a), codes(b)
        da, db = dates(a), dates(b)
        guarded = [t for t in TERMS if t in a]
        qa, qb = quoted(a), quoted(b)
        qb_set = set(qb)
        missing_quotes = [q for q in qa if len(q) >= 6 and q not in qb_set]
        report[meta["key"]] = {
            "status": "ACCEPTED",
            "source_body_chars": len(body(a)),
            "output_body_chars": len(body(b)),
            "length_ratio": round(len(body(b)) / max(1, len(body(a))), 4),
            "numbers_missing": {k: na[k] - nb.get(k, 0) for k in sorted(na) if na[k] > nb.get(k, 0)},
            "numbers_added": {k: nb[k] - na.get(k, 0) for k in sorted(nb) if nb[k] > na.get(k, 0)},
            "codes_missing": {k: ca[k] - cb.get(k, 0) for k in sorted(ca) if ca[k] > cb.get(k, 0)},
            "codes_added": {k: cb[k] - ca.get(k, 0) for k in sorted(cb) if cb[k] > ca.get(k, 0)},
            "dates_missing": {k: da[k] - db.get(k, 0) for k in sorted(da) if da[k] > db.get(k, 0)},
            "dates_added": {k: db[k] - da.get(k, 0) for k in sorted(db) if db[k] > da.get(k, 0)},
            "protected_terms_missing": [t for t in guarded if t not in b],
            "term_replacement_guard": {k: (k in a, v in b) for k, v in TERM_REPLACEMENT_GUARD.items() if k in a},
            "quoted_segments_source": len(qa),
            "quoted_segments_output": len(qb),
            "quoted_segments_missing": missing_quotes,
            "paragraphs_source": len([x for x in a.split("\n\n") if x.strip()]),
            "paragraphs_output": len([x for x in b.split("\n\n") if x.strip()]),
            **tail_retention(a, b),
        }
        a_lines = [x.strip() for x in a.split("\n") if x.strip()]
        b_lines = [x.strip() for x in b.split("\n") if x.strip()]
        diff = list(difflib.unified_diff(a_lines, b_lines, fromfile=f"{meta['key']} A",
                                         tofile=f"{meta['key']} B", lineterm="", n=1))
        diff_lines += [f"## {meta['key']}", "", "```diff", *diff, "```", ""]
    (ROOT / "outputs/PRESERVATION.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "outputs/DIFF.md").write_text("\n".join(diff_lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
