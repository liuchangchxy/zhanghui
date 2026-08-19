#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
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
    parser.add_argument(
        "--on-conflict",
        choices=["overwrite", "skip"],
        default="overwrite",
        help="已存在 chapter commit 时如何处理: overwrite/skip；默认 overwrite。"
        "append/ask 不支持 (chapter commit 是不可变的 point-in-time snapshot)。",
    )
    args = parser.parse_args()

    # CLI 层 default=overwrite：CLI 是用户显式动作；service 层 default=None 保持严格。
    # 内部 apply_projections 会再调一次 persist_commit 写 projection_status，
    # 所以此处必须显式传 flag，避免 service 层 default 触发误报。
    service = ChapterCommitService(Path(args.project_root))
    payload = service.build_commit(
        chapter=args.chapter,
        review_result=_read_json(args.review_result),
        fulfillment_result=_read_json(args.fulfillment_result),
        disambiguation_result=_read_json(args.disambiguation_result),
        extraction_result=_read_json(args.extraction_result),
    )
    service.persist_commit(payload, on_conflict=args.on_conflict)
    payload = service.apply_projections(payload, on_conflict=args.on_conflict)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
