#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mechanical cleanup: remove duplicated leading title/paragraph added by the model.

This does not rewrite prose. It only removes an exact duplicate prefix so that
A/B difference is not contaminated by a formatting artifact.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CHAPTERS, input_path, output_path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def body(t: str) -> int:
    return len(re.sub(r"\s", "", t))


def main() -> None:
    notes = []
    rec_path = ROOT / "outputs/RUN_RECORDS.json"
    records = json.loads(rec_path.read_text(encoding="utf-8")) if rec_path.exists() else {}
    for ch, meta in CHAPTERS.items():
        p = output_path(ch)
        text = p.read_text(encoding="utf-8")
        before = hashlib.sha256(text.encode()).hexdigest()
        paras = [x.strip() for x in text.split("\n\n") if x.strip()]
        changed = False
        # Find the first paragraph that repeats later within the first 4 paragraphs.
        for i in range(min(3, len(paras) - 1)):
            if paras[i] and paras[i] in paras[i + 1:i + 4]:
                dup_at = paras.index(paras[i], i + 1)
                paras = paras[dup_at:]
                changed = True
                break
        if changed:
            cleaned = "\n\n".join(paras).strip() + "\n"
            p.write_text(cleaned, encoding="utf-8")
            after = hashlib.sha256(cleaned.encode()).hexdigest()
            src = input_path(ch).read_text(encoding="utf-8")
            if meta["key"] in records:
                records[meta["key"]]["output_sha256"] = after
                records[meta["key"]]["output_chars"] = body(cleaned)
                records[meta["key"]]["length_ratio"] = round(body(cleaned) / max(1, body(src)), 4)
                records[meta["key"]]["cleanup"] = {
                    "reason": "duplicated leading paragraph",
                    "before_sha256": before,
                    "after_sha256": after,
                }
            notes.append(f"- {meta['key']}: removed duplicated leading paragraph; {before[:12]} -> {after[:12]}")
            print(meta["key"], "cleaned", body(src), "->", body(cleaned))
    rec_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "outputs/CLEANUP_NOTES.md").write_text(
        "# Mechanical cleanup notes\n\n" + ("\n".join(notes) if notes else "- none") + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
