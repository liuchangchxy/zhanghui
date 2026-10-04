#!/usr/bin/env python3
"""Build a deterministic reconciliation artifact from final chapter artifacts."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from data_modules.chapter_commit_schema import ExtractionResult
from data_modules.reconciliation import reconcile_changes
from changes_gate import parse_changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile final CHANGES with Data Agent extraction")
    parser.add_argument("--chapter-file", required=True)
    parser.add_argument("--extraction-result", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--db", required=True, help="Story index DB passed to changes_gate")
    args = parser.parse_args()
    chapter_path = Path(args.chapter_file)
    output = Path(args.output)
    output.unlink(missing_ok=True)
    chapter_text = chapter_path.read_text(encoding="utf-8")
    gate = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("changes_gate.py")),
         "--chapter-file", str(chapter_path), "--db", args.db, "--json"],
        capture_output=True, text=True, check=False,
    )
    try:
        gate_result = json.loads(gate.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"changes_gate did not return valid JSON: {exc}") from exc
    if gate.returncode or not gate_result.get("passed"):
        raise SystemExit("changes_gate failed; reconciliation was not run")
    proposed, error = parse_changes(chapter_text)
    if error:
        raise SystemExit(f"CHANGES invalid: {error}")
    extraction = json.loads(Path(args.extraction_result).read_text(encoding="utf-8"))
    ExtractionResult.model_validate(extraction)
    result = reconcile_changes(proposed, extraction, chapter_text=chapter_text)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["status"] != "passed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
