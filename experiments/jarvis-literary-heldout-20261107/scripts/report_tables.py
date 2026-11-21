#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render the report tables from RUN_RECORDS / PRESERVATION / aggregate."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = []


def load(p: str):
    f = ROOT / p
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def main() -> None:
    global OUT
    OUT = []
    rec = load("outputs/RUN_RECORDS.json")
    pres = load("outputs/PRESERVATION.json")
    agg = load("blind/aggregate.json")

    OUT += ["## 生成状态", "",
            "| 章 | 状态 | A 正文字数 | B 正文字数 | 比例 | stop_reason | 尝试 |",
            "|---|---|---:|---:|---:|---|---:|"]
    for key in ["ch01", "ch02", "ch06", "ch07", "ch09", "ch10"]:
        r = rec.get(key, {})
        stops = ", ".join(str(a.get("stop_reason")) for a in r.get("attempts", []))
        OUT.append(f"| {key} | {r.get('status','MISSING')} | {r.get('source_body_chars','-')} | "
                   f"{r.get('output_body_chars','-')} | {r.get('length_ratio','-')} | "
                   f"{stops or '-'} | {len(r.get('attempts', []))} |")
    OUT.append("")

    if agg:
        OUT += ["## 盲评合计（A=原稿，B=编辑后）", "",
                "| 维度 | A | B | SPLIT | TIE |", "|---|---:|---:|---:|---:|"]
        for dim in agg["dims"]:
            s = agg["pooled"][dim]
            OUT.append(f"| {dim} | {s['A']} | {s['B']} | {s['SPLIT']} | {s['TIE']} |")
        OUT += ["", "## 章级 OVERALL", "",
                "| 章 | J1 | J2 | 严格偏 B | 偏向 B |", "|---|---|---|---|---|"]
        for ch in agg["evaluated_chapters"]:
            co = agg["chapter_overall"][ch]
            OUT.append(f"| {ch} | {co['judge_verdicts'][0]} | {co['judge_verdicts'][1]} | "
                       f"{co['strict_b']} | {co['leaning_b']} |")
        OUT.append("")

    OUT += ["## 确定性保全检查", "",
            "| 章 | 数字缺失 | 编号缺失 | 日期缺失 | 术语缺失 | 引语缺失 | 末段 8 字保留 | 末两段 8 字保留 |",
            "|---|---|---|---|---|---|---:|---:|"]
    for key in ["ch01", "ch02", "ch06", "ch07", "ch09", "ch10"]:
        p = pres.get(key, {})
        if p.get("status") != "ACCEPTED":
            OUT.append(f"| {key} | - | - | - | - | - | - | - |")
            continue
        OUT.append(
            f"| {key} | {p.get('numbers_missing')} | {p.get('codes_missing')} | "
            f"{p.get('dates_missing')} | {p.get('protected_terms_missing')} | "
            f"{len(p.get('quoted_segments_missing', []))} | "
            f"{p.get('last_paragraph_8char_retention')} | "
            f"{p.get('last_two_paragraphs_8char_retention')} |")
    OUT.append("")

    text = "# 实验表格（自动生成）\n\n" + "\n".join(OUT)
    (ROOT / "report/TABLES.md").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
