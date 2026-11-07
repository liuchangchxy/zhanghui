#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Held-out experiment configuration. Not imported by production code."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_RUN = Path(
    "/Users/chang/Desktop/Code/zhanghui-benchmark/runs/"
    "clean-e2e-jarvis-vs-zhanghui-2026-10-29"
)

# All six held-out chapters. Fixed before generation; no swaps allowed.
CHAPTERS = {
    1: {"key": "ch01", "title": "第一章"},
    2: {"key": "ch02", "title": "第二章 钥匙"},
    6: {"key": "ch06", "title": "第六章 那一夜"},
    7: {"key": "ch07", "title": "第7章 材质"},
    9: {"key": "ch09", "title": "第9章 切换盒"},
    10: {"key": "ch10", "title": "第10章 三通"},
}

HEADING = {
    1: "## 第一章",
    2: "## 第二章 钥匙",
    6: "## 第六章 那一夜",
    7: "## 第7章 材质",
    9: "## 第9章 切换盒",
    10: "## 第10章 三通",
}


def source_path(ch: int) -> Path:
    return BENCH_RUN / f"e2e/zhanghui/{CHAPTERS[ch]['key']}/published.md"


def any_source_path(n: int) -> Path:
    """Source for any benchmark chapter, including neighbours outside the held-out set."""
    return BENCH_RUN / f"e2e/zhanghui/ch{n:02d}/published.md"


def governed_context_path(ch: int) -> Path:
    return BENCH_RUN / f"e2e/zhanghui/{CHAPTERS[ch]['key']}/governed-context.json"


def input_path(ch: int) -> Path:
    return ROOT / f"inputs/{CHAPTERS[ch]['key']}_source.md"


def outline_path(ch: int) -> Path:
    return ROOT / f"inputs/context/{CHAPTERS[ch]['key']}_outline.md"


def constraints_path(ch: int) -> Path:
    return ROOT / f"inputs/context/{CHAPTERS[ch]['key']}_constraints.md"


def next_opening_path(ch: int) -> Path:
    return ROOT / f"inputs/context/{CHAPTERS[ch]['key']}_next_opening.md"


def output_path(ch: int) -> Path:
    return ROOT / f"outputs/{CHAPTERS[ch]['key']}_edited.md"


def rejected_path(ch: int) -> Path:
    return ROOT / f"outputs/rejected/{CHAPTERS[ch]['key']}_edited_rejected.md"


def prompt_path(ch: int) -> Path:
    return ROOT / f"outputs/{CHAPTERS[ch]['key']}_prompt.txt"
