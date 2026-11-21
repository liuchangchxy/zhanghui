#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Experiment-local configuration. Not imported by production code."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_RUN = Path(
    "/Users/chang/Desktop/Code/zhanghui-benchmark/runs/"
    "clean-e2e-jarvis-vs-zhanghui-2026-10-29"
)

CHAPTERS = {
    3: {"key": "ch03", "title": "旧城问路"},
    4: {"key": "ch04", "title": "潮汐站"},
    5: {"key": "ch05", "title": "同步"},
    8: {"key": "ch08", "title": "旧轨"},
}


def source_path(ch: int) -> Path:
    return BENCH_RUN / f"e2e/zhanghui/{CHAPTERS[ch]['key']}/published.md"


def governed_context_path(ch: int) -> Path:
    return BENCH_RUN / f"e2e/zhanghui/{CHAPTERS[ch]['key']}/governed-context.json"


def input_path(ch: int) -> Path:
    return ROOT / f"inputs/{CHAPTERS[ch]['key']}_source.md"


def outline_path(ch: int) -> Path:
    return ROOT / f"inputs/context/{CHAPTERS[ch]['key']}_outline.md"


def output_path(ch: int) -> Path:
    return ROOT / f"outputs/{CHAPTERS[ch]['key']}_edited.md"


def prompt_path(ch: int) -> Path:
    return ROOT / f"outputs/{CHAPTERS[ch]['key']}_prompt.txt"
