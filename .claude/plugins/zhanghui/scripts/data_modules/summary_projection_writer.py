#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

try:
    from security_utils import atomic_write_text
except ImportError:  # pragma: no cover
    from scripts.security_utils import atomic_write_text

from .commit_artifacts import extraction_text
from .durable_projection import require_durable_commit_match


def append_summary_projection(project_root: Path, commit_payload: dict) -> dict:
    require_durable_commit_match(project_root, commit_payload)
    chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
    summary_text = extraction_text(commit_payload, "summary_text")
    if chapter <= 0 or not summary_text:
        return {"applied": False, "writer": "summary", "reason": "missing_summary"}

    target = Path(project_root) / ".webnovel" / "summaries" / f"ch{chapter:04d}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    if "## 剧情摘要" not in summary_text:
        summary_text = f"## 剧情摘要\n{summary_text}\n"
    # 原子写入：写入中途崩溃不会留下半截摘要（M-H17）
    atomic_write_text(target, summary_text, use_lock=False, backup=False)
    return {"applied": True, "writer": "summary", "path": str(target)}


class SummaryProjectionWriter:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def apply(self, commit_payload: dict) -> dict:
        require_durable_commit_match(self.project_root, commit_payload)
        if commit_payload["meta"]["status"] != "accepted":
            return {"applied": False, "writer": "summary", "reason": "commit_rejected"}
        return append_summary_projection(self.project_root, commit_payload)
