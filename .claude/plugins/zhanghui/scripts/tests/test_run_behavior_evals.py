#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[1]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_on_path()

from run_behavior_evals import run_behavior_evals  # noqa: E402


def test_run_behavior_evals_fast_suite_passes_for_current_package():
    root = Path(__file__).resolve().parents[2]

    report = run_behavior_evals(root, suite="fast")

    failures = [
        {"id": item.get("id"), "reason": item.get("reason"), "evidence": item.get("evidence")}
        for item in report.get("results") or []
        if not item.get("passed")
    ]
    # name the failing cases: "ok is False" alone gives no way to tell an environment gap
    # from a real contract drift when the suite runs on a machine you cannot poke at
    assert report["ok"] is True, f"behavior eval failures: {failures}"
    assert report["total"] >= 5
