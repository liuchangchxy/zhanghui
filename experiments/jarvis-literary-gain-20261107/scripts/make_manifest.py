#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hash every experiment artifact for the PR."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"__pycache__", ".DS_Store", "MANIFEST.json"}


def main() -> None:
    rows = {}
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or any(part in SKIP for part in p.parts):
            continue
        rel = str(p.relative_to(ROOT))
        rows[rel] = {
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
    (ROOT / "MANIFEST.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(len(rows), "files hashed")


if __name__ == "__main__":
    main()
