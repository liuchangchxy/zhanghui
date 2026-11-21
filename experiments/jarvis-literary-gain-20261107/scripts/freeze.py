#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write the pre-registration record: sample selection + prompt + inputs."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CHAPTERS, input_path, outline_path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    files = [ROOT / "SAMPLE_SELECTION.md", ROOT / "prompts/editor_zh.md"]
    for ch, meta in CHAPTERS.items():
        files += [input_path(ch), outline_path(ch)]
    head = subprocess.run(["git", "-C", str(ROOT.parents[1]), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    record = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "git_head": head,
        "files": {str(p.relative_to(ROOT)): sha(p) for p in files},
        "chapters": [CHAPTERS[ch]["key"] for ch in sorted(CHAPTERS)],
        "note": "Written before any editor generation. See SAMPLE_SELECTION.md for rules.",
    }
    (ROOT / "FREEZE.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
