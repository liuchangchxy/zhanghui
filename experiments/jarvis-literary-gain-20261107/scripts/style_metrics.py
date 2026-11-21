#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Descriptive text metrics for A vs B. Not a quality score."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CHAPTERS, input_path, output_path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MARKERS = ["听懂了", "明白了", "意识到", "这说明", "这意味着", "看得出来",
           "不是怕", "不是", "心里", "脑子里", "他知道", "她觉得", "他觉得"]


def metrics(text: str) -> dict:
    body = re.sub(r"\s", "", text)
    sentences = [s for s in re.split(r"[。！？!?…]+", text) if s.strip()]
    paras = [p for p in text.split("\n\n") if p.strip()]
    dialogue = sum(len(m) for m in re.findall(r"[“\"]([^”\"]{2,})[”\"]", text))
    return {
        "body_chars": len(body),
        "paragraphs": len(paras),
        "sentences": len(sentences),
        "avg_sentence_chars": round(len(body) / max(1, len(sentences)), 2),
        "dialogue_chars": dialogue,
        "dialogue_ratio": round(dialogue / max(1, len(body)), 4),
        "marker_counts": {m: text.count(m) for m in MARKERS},
        "marker_total": sum(text.count(m) for m in MARKERS),
        "marker_per_1000": round(sum(text.count(m) for m in MARKERS) / max(1, len(body)) * 1000, 3),
    }


def main() -> None:
    out = {}
    for ch, meta in CHAPTERS.items():
        a = metrics(input_path(ch).read_text(encoding="utf-8"))
        b = metrics(output_path(ch).read_text(encoding="utf-8"))
        out[meta["key"]] = {"A": a, "B": b}
    (ROOT / "outputs/STYLE_METRICS.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for ch, d in out.items():
        print(ch, "chars", d["A"]["body_chars"], "->", d["B"]["body_chars"],
              "| marker/1000", d["A"]["marker_per_1000"], "->", d["B"]["marker_per_1000"],
              "| dialogue", d["A"]["dialogue_ratio"], "->", d["B"]["dialogue_ratio"],
              "| avg sent", d["A"]["avg_sentence_chars"], "->", d["B"]["avg_sentence_chars"])


if __name__ == "__main__":
    main()
