#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio

from data_modules.chapter_commit_service import ChapterCommitService


def _read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Chapter commit CLI")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--review-result", required=True)
    parser.add_argument("--fulfillment-result", required=True)
    parser.add_argument("--disambiguation-result", required=True)
    parser.add_argument("--extraction-result", required=True)
    parser.add_argument("--reconciliation-result", required=True)
    parser.add_argument("--chapter-file", required=True, help="Final chapter file bound to reconciliation")
    parser.add_argument(
        "--on-conflict",
        choices=["overwrite", "skip"],
        default=None,
        help="已有 canonical chapter commit 时拒绝 overwrite；skip 只从磁盘上的既有 commit 重试投影。"
        "append/ask 不支持 (chapter commit 是不可变的 point-in-time snapshot)。",
    )
    args = parser.parse_args()

    # The durable chapter transaction is stored before any projection writer runs.
    service = ChapterCommitService(Path(args.project_root))
    from data_modules.reconciliation import split_chapter_and_changes
    reconciliation_result = _read_json(args.reconciliation_result)
    chapter_text = Path(args.chapter_file).read_text(encoding="utf-8")
    gate = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("changes_gate.py")),
         "--chapter-file", args.chapter_file, "--db", str(Path(args.project_root) / ".webnovel" / "index.db"), "--json"],
        capture_output=True, text=True, check=False,
    )
    try:
        gate_result = json.loads(gate.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"changes_gate did not return valid JSON: {exc}") from exc
    if gate.returncode or not gate_result.get("passed"):
        raise ValueError("changes_gate failed; chapter commit is blocked")
    _, proposed_changes = split_chapter_and_changes(chapter_text)
    payload = service.build_commit(
        chapter=args.chapter,
        review_result=_read_json(args.review_result),
        fulfillment_result=_read_json(args.fulfillment_result),
        disambiguation_result=_read_json(args.disambiguation_result),
        extraction_result=_read_json(args.extraction_result),
        chapter_text=chapter_text,
        proposed_changes=proposed_changes,
        reconciliation_result=reconciliation_result,
    )
    payload = service.apply_projections(payload, on_conflict=args.on_conflict)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
