#!/usr/bin/env python3
"""Create a prose-only Data Agent input and its separate ProposedChanges artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_modules.reconciliation import split_chapter_and_changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Split final chapter prose from its CHANGES declaration")
    parser.add_argument("--chapter-file", required=True)
    parser.add_argument("--prose-output", required=True)
    parser.add_argument("--changes-output", required=True)
    args = parser.parse_args()
    chapter_text = Path(args.chapter_file).read_text(encoding="utf-8")
    prose, proposed = split_chapter_and_changes(chapter_text)
    prose_path, changes_path = Path(args.prose_output), Path(args.changes_output)
    prose_path.parent.mkdir(parents=True, exist_ok=True)
    changes_path.parent.mkdir(parents=True, exist_ok=True)
    prose_path.write_text(prose, encoding="utf-8")
    changes_path.write_text(json.dumps(proposed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
