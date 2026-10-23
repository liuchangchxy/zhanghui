#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic side-metrics for the literary-skills A/B.

These are diagnostics, not judges: they only report counts a reviewer can check by hand.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
REPO = EXP.parents[1]
SCRIPTS = Path("/Users/chang/Desktop/Code/zhanghui/.claude/plugins/zhanghui/scripts/webnovel.py")

# Emotion named outright by the narrator (not in dialogue).
EMOTION_WORDS = ["恐惧", "害怕", "愤怒", "悲伤", "痛苦", "绝望", "紧张", "不安", "震惊", "慌乱", "羞愧", "欣慰"]
# Template body reactions the brief warns about.
BODY_TEMPLATES = ["指节发白", "指节泛白", "心跳加速", "呼吸一滞", "呼吸急促", "倒吸一口凉气", "咬住下唇", "咬唇"]
# Author stepping in to explain.
EXPLAIN_MARKERS = ["他终于明白", "他明白了", "这意味着", "这说明", "他意识到", "他知道，", "原来", "不禁"]
# POV leaks: another character's interior.
OTHER_MIND = ["老周心里", "老周想", "老周知道", "科长心里", "梁沐心里", "他心里其实", "心里一沉"]


def count_words(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text))


def dialogue_ratio(text: str) -> float:
    quoted = re.findall(r"[“\"]([^”\"]*)[”\"]", text)
    q = sum(count_words(x) for x in quoted)
    total = count_words(text) or 1
    return round(q / total, 3)


def hits(text: str, words: list[str]) -> dict[str, int]:
    out = {}
    for w in words:
        n = text.count(w)
        if n:
            out[w] = n
    return out


def diagnose(path: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPTS), "prose", "diagnose", "--file", str(path), "--format", "json"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return {"error": proc.stderr[-500:]}
    data = json.loads(proc.stdout)
    return {
        "total_chars": data.get("total_chars"),
        "issue_counts_by_type": data.get("issue_counts_by_type", {}),
        "issue_total": len(data.get("issues", [])),
    }


def main() -> int:
    # `--chapter ch5` reads ch5/drafts/ and writes ch5/metrics.json.
    base = EXP / sys.argv[1] if len(sys.argv) > 1 else EXP
    report = {}
    for arm in ("A", "B"):
        path = base / "drafts" / f"draft_{arm}.md"
        text = path.read_text(encoding="utf-8")
        report[arm] = {
            "hanzi": count_words(text),
            "paragraphs": len([p for p in text.split("\n\n") if p.strip()]),
            "dialogue_ratio": dialogue_ratio(text),
            "emotion_words": hits(text, EMOTION_WORDS),
            "body_templates": hits(text, BODY_TEMPLATES),
            "explain_markers": hits(text, EXPLAIN_MARKERS),
            "other_mind": hits(text, OTHER_MIND),
            "diagnose": diagnose(path),
        }
    out = base / "metrics.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
