#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic preservation checks + human-readable diff for A vs B."""
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

PROTECTED = {
    "ch03": ["19", "7", "67", "68", "69", "白塔", "乔宁", "韩策", "梅叔", "安全阀",
             "值班确认单", "移交单", "关帝庙", "宏昌号", "铁皮柜", "黄铜钥匙", "鱼胶"],
    "ch04": ["19", "7", "1999.10", "七号泵房", "十九号旁通阀", "C区", "乔宁", "韩策",
             "封存门", "临时医疗单", "安全阀", "签认单", "维护通道"],
    "ch05": ["1999", "八月八日", "八月十五日", "七号泵房", "填料微漏", "值班说先记着",
             "交接班登记簿", "乔宁", "梅叔", "三十天", "东区综合站", "纸质档案",
             "同步", "公示屏", "版本日志"],
    "ch08": ["K-7", "M-84-07", "DN300", "DN150", "八九年", "十一月十四日", "黄铜钥匙",
             "旧维护轨道", "切换盒", "光谱", "百分之三十八", "雨衣", "通行卡",
             "废品站", "十点", "乔宁", "韩策", "梅叔"],
}

TERM_REPLACEMENT_GUARD = {
    "高潮": "高值",
    "低潮": "低值",
    "潮位": "水位值",
    "铅封": "铅封条",
}


def body(text: str) -> str:
    return re.sub(r"\s", "", text)


def nums(text: str) -> Counter:
    return Counter(re.findall(r"\d+(?:\.\d+)?", text))


def quoted(text: str) -> list[str]:
    return re.findall(r"[“\"]([^”\"]{2,})[”\"]", text)


def main() -> None:
    report = {}
    diff_lines = ["# A → B diff（原文 → 编辑后）", ""]
    for ch, meta in CHAPTERS.items():
        a = input_path(ch).read_text(encoding="utf-8")
        b = output_path(ch).read_text(encoding="utf-8")
        na, nb = nums(a), nums(b)
        # Only terms that actually occur in A can be "lost"; the list is a guard,
        # not a claim about which plot facts exist in this book's chapter.
        guarded = [t for t in PROTECTED[meta["key"]] if t in a]
        missing_terms = [t for t in guarded if t not in b]
        term_hits = {k: (k in a, v in b) for k, v in TERM_REPLACEMENT_GUARD.items() if k in a}
        qa, qb = quoted(a), quoted(b)
        report[meta["key"]] = {
            "source_body_chars": len(body(a)),
            "output_body_chars": len(body(b)),
            "length_ratio": round(len(body(b)) / max(1, len(body(a))), 4),
            "numbers_missing": {k: na[k] - nb.get(k, 0) for k in sorted(na) if na[k] > nb.get(k, 0)},
            "numbers_added": {k: nb[k] - na.get(k, 0) for k in sorted(nb) if nb[k] > na.get(k, 0)},
            "protected_terms_missing": missing_terms,
            "term_replacement_guard": term_hits,
            "quoted_segments_source": len(qa),
            "quoted_segments_output": len(qb),
            "paragraphs_source": len([p for p in a.split("\n\n") if p.strip()]),
            "paragraphs_output": len([p for p in b.split("\n\n") if p.strip()]),
        }
        a_lines = [p.strip() for p in a.split("\n") if p.strip()]
        b_lines = [p.strip() for p in b.split("\n") if p.strip()]
        diff = list(difflib.unified_diff(a_lines, b_lines, fromfile=f"{meta['key']} A",
                                         tofile=f"{meta['key']} B", lineterm="", n=1))
        diff_lines += [f"## {meta['key']}", "", "```diff", *diff, "```", ""]
    (ROOT / "outputs/PRESERVATION.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "outputs/DIFF.md").write_text("\n".join(diff_lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
