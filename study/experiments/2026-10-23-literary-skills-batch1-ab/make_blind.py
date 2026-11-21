#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the two blind judge packets from the A/B drafts.

The mapping is decided by a fixed key written to blind_key.json before any judge runs.
Each packet labels its own drafts: the template carries no draft heading, so the two
reading orders cannot silently end up with the wrong label.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent

# Chapter 5 runs from a copy of this script under ch5/, sharing the rubric template.
import argparse


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", default="drafts")
    ap.add_argument("--out", default=".")
    ap.add_argument("--template", default=str(EXP / "judge_packet_template.md"))
    ap.add_argument("--seed", type=int, default=20261023)
    args = ap.parse_args()

    template = Path(args.template).read_text(encoding="utf-8").rstrip()

    base = Path(args.drafts)
    if not base.is_absolute():
        base = Path.cwd() / base
    out = Path(args.out)
    if not out.is_absolute():
        # Relative to the caller's cwd, not to this script: ch5 reuses this builder.
        out = Path.cwd() / out
    out.mkdir(parents=True, exist_ok=True)
    draft_a = (base / "draft_A.md").read_text(encoding="utf-8")
    draft_b = (base / "draft_B.md").read_text(encoding="utf-8")

    key_path = out / "blind_key.json"
    if key_path.exists():
        key = json.loads(key_path.read_text(encoding="utf-8"))
    else:
        # Fixed seed so the key is reproducible rather than ad hoc.
        flip = random.Random(args.seed).random() < 0.5
        key = {"X": "draft_B.md", "Y": "draft_A.md"} if flip else {"X": "draft_A.md", "Y": "draft_B.md"}
        key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")

    texts = {"draft_A.md": draft_a, "draft_B.md": draft_b}
    x_text, y_text = texts[key["X"]], texts[key["Y"]]

    def packet(first_label: str, first_text: str, second_label: str, second_text: str) -> str:
        return (
            f"{template}\n\n---\n\n# 稿 {first_label}\n\n{first_text.strip()}\n\n"
            f"---\n\n# 稿 {second_label}\n\n{second_text.strip()}\n"
        )

    # Opposite reading orders, identical rubric.
    (out / "judge_packet_XY.md").write_text(packet("X", x_text, "Y", y_text), encoding="utf-8")
    (out / "judge_packet_YX.md").write_text(packet("Y", y_text, "X", x_text), encoding="utf-8")
    print(json.dumps(key, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
