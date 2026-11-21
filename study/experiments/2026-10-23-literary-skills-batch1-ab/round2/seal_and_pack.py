#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round-2 helpers: seal both arms' prompts and build blind packets.

Round 1's `make_blind.py` is reused unchanged; this script only wraps the calls so the
packet labels and the key live next to the drafts they describe.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
REPO = EXP.parents[2]
LIT = REPO / ".tmp" / "lit-ab"

ARM_CODE = {"A": LIT / "code_A", "B": LIT / "code_B"}
ARM_BOOK = {"A": LIT / "book_A", "B": LIT / "book_B"}


def seal(chapter: int, arm: str, brief: Path, skills: Path | None, out: Path) -> None:
    cmd = [
        sys.executable, "-X", "utf8",
        str(ARM_CODE[arm] / ".claude/plugins/zhanghui/scripts/webnovel.py"),
        "--project-root", str(ARM_BOOK[arm]),
        "runtime", "attach-creative-brief",
        "--chapter", str(chapter),
        "--brief-file", str(brief),
        "--scene-design", "--reader-pull", "--format", "prompt",
    ]
    if skills:
        cmd += ["--skills-file", str(skills)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"{arm} seal failed: {proc.stderr[-800:]}")
    out.write_text(proc.stdout, encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: seal_and_pack.py <round2/chN>", file=sys.stderr)
        return 2
    chap_dir = Path(sys.argv[1]).resolve()
    chapter = int(chap_dir.name.replace("ch", ""))
    brief = chap_dir / "creative_brief.txt"
    drafts = chap_dir / "drafts"

    for arm in ("A", "B"):
        skills = chap_dir / f"arm_{arm}_selection.json"
        if not skills.exists():
            skills = None
        seal(chapter, arm, brief, skills, chap_dir / f"prompt_{arm}.txt")

    diff = subprocess.run(
        ["diff", str(chap_dir / "prompt_A.txt"), str(chap_dir / "prompt_B.txt")],
        capture_output=True, text=True,
    )
    (chap_dir / "prompt_diff.txt").write_text(diff.stdout, encoding="utf-8")

    if drafts.is_dir():
        out = subprocess.run(
            [
                sys.executable, "-X", "utf8",
                str(EXP / "make_blind.py"),
                "--drafts", str(drafts),
                "--out", str(chap_dir),
                "--template", str(chap_dir / "judge_packet_template.md"),
            ],
            capture_output=True, text=True,
        )
        print("blind key:", out.stdout.strip(), out.stderr.strip(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
