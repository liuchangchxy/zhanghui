#!/usr/bin/env python3
"""Explicit, read-only measurement of existing CHANGES artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from data_modules.changes_shadow_report import aggregate_reports, analyze_phase2_files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    chapter = sub.add_parser("chapter", help="analyze existing Phase 2 source artifacts")
    chapter.add_argument("--chapter-file", required=True, type=Path)
    chapter.add_argument("--extraction-result", required=True, type=Path)
    chapter.add_argument("--reconciliation", required=True, type=Path)
    chapter.add_argument("--project-id", required=True)
    chapter.add_argument("--project-mode", choices=("story_system", "legacy"), required=True)
    chapter.add_argument("--extractor-failed", action="store_true")
    corpus = sub.add_parser("corpus", help="aggregate previously generated JSON reports")
    corpus.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args(argv)
    if args.command == "chapter":
        report = analyze_phase2_files(args.chapter_file, args.extraction_result, args.reconciliation,
                                      project_id=args.project_id, project_mode=args.project_mode,
                                      extractor_failed=args.extractor_failed)
    else:
        report = aggregate_reports([json.loads(path.read_text(encoding="utf-8")) for path in args.reports])
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
