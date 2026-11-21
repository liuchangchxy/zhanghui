#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render a compact evidence table from blind/aggregate.json."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
agg = json.loads((ROOT / "blind/aggregate.json").read_text(encoding="utf-8"))
lines = ["# Judge evidence (held-out)", ""]
for ch in agg["evaluated_chapters"]:
    lines += [f"## {ch}", ""]
    for judge in agg["judges"]:
        lines += [f"### {judge}", ""]
        for dim in agg["dims"]:
            r = agg["raw_pass"][f"{ch}_{judge}_{dim}"]
            ev = r["p1_evidence"] if r["verdict"] == "B" else r["p2_evidence"]
            if r["verdict"] == "SPLIT":
                ev = f"P1={r['p1_evidence']} / P2={r['p2_evidence']}"
            lines.append(f"- **{dim}: {r['verdict']}** — {ev}")
        lines.append("")
(ROOT / "blind/EVIDENCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines[:40]))
