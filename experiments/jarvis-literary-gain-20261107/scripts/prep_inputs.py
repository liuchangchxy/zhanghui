#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Freeze the A-arm inputs and the per-chapter outline from the 2026-10-29 run.

Only removes the packaging fingerprint line; no prose is edited.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CHAPTERS, governed_context_path, input_path, outline_path, source_path  # noqa: E402


def strip_packaging(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"(?m)^\s*\*\*封包验证指纹[^\n]*\n?", "", text)
    text = re.sub(r"(?m)^\s*[0-9a-f]{64}\s*$\n?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def main() -> None:
    manifest = {}
    for ch, meta in CHAPTERS.items():
        src = source_path(ch)
        raw = src.read_text(encoding="utf-8")
        frozen = strip_packaging(raw)
        out = input_path(ch)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(frozen, encoding="utf-8")

        ctx = json.loads(governed_context_path(ch).read_text(encoding="utf-8"))
        outline = ctx["current_intent"]["outline"].strip() + "\n"
        op = outline_path(ch)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(outline, encoding="utf-8")

        manifest[meta["key"]] = {
            "source": str(src),
            "source_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "frozen_input": str(out.relative_to(Path(__file__).resolve().parents[1])),
            "frozen_sha256": hashlib.sha256(frozen.encode()).hexdigest(),
            "outline": str(op.relative_to(Path(__file__).resolve().parents[1])),
            "outline_sha256": hashlib.sha256(outline.encode()).hexdigest(),
            "chars": len(frozen),
        }
        print(meta["key"], manifest[meta["key"]]["chars"], manifest[meta["key"]]["frozen_sha256"][:16])

    p = Path(__file__).resolve().parents[1] / "inputs/PROVENANCE.json"
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
