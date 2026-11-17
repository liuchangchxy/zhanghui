#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Freeze A/B raws, anonymize as X/Y, and build the two position-reversed judge packets."""
from __future__ import annotations

import hashlib
import json
import pathlib
import random
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
A_RAW = HERE / "A_current_raw.md"
B_RAW = HERE / "B_jit_raw.md"
COMMON = HERE / "blind" / "judge_common.md"
BLIND = HERE / "blind"
JUDGE = HERE / "judge"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_prose(raw: str) -> str:
    prose = re.split(r"<chapter_changes>", raw, maxsplit=1)[0].strip()
    lines = prose.splitlines()
    if lines and re.match(r"^#{1,6}\s*第\s*0*4\s*章", lines[0]):
        lines = lines[1:]
    body = "\n".join(lines).strip()
    return "第4章 室友的邀请\n\n" + body


def cjk_count(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text))


def build_packet(common: str, first_label: str, first_text: str, second_label: str, second_text: str) -> str:
    return (
        common
        + "\n\n---\n\n"
        + f"# 稿 {first_label}（先读）\n\n"
        + first_text
        + "\n\n---\n\n"
        + f"# 稿 {second_label}（后读）\n\n"
        + second_text
        + "\n"
    )


def main() -> int:
    a_raw = A_RAW.read_text(encoding="utf-8")
    b_raw = B_RAW.read_text(encoding="utf-8")
    a_prose = split_prose(a_raw)
    b_prose = split_prose(b_raw)

    # Freeze hashes before any anonymization.
    freeze = {
        "A_current_raw_sha256": sha(a_raw),
        "B_jit_raw_sha256": sha(b_raw),
        "A_prose_sha256": sha(a_prose),
        "B_prose_sha256": sha(b_prose),
        "A_prose_cjk": cjk_count(a_prose),
        "B_prose_cjk": cjk_count(b_prose),
    }

    rng = random.SystemRandom()
    x_is_a = rng.choice([True, False])
    mapping = {"X": "A" if x_is_a else "B", "Y": "B" if x_is_a else "A"}
    texts = {"A": a_prose, "B": b_prose}
    blind_key = {"mapping": mapping, **freeze}
    (BLIND / "blind_key.json").write_text(
        json.dumps(blind_key, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (BLIND / "X.md").write_text(texts[mapping["X"]], encoding="utf-8")
    (BLIND / "Y.md").write_text(texts[mapping["Y"]], encoding="utf-8")

    common = COMMON.read_text(encoding="utf-8")
    xy = build_packet(common, "X", texts[mapping["X"]], "Y", texts[mapping["Y"]])
    yx = build_packet(common, "Y", texts[mapping["Y"]], "X", texts[mapping["X"]])
    (JUDGE / "packet_XY.md").write_text(xy, encoding="utf-8")
    (JUDGE / "packet_YX.md").write_text(yx, encoding="utf-8")

    print(json.dumps(blind_key, ensure_ascii=False, indent=2))
    print(f"packet_XY sha256 {sha(xy)}")
    print(f"packet_YX sha256 {sha(yx)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
