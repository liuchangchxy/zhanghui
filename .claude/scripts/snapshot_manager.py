#!/usr/bin/env python3
"""Workflow snapshot 管理器。

冻结 plan 时刻的 设定集/大纲 副本，防止未来修改污染已写章节。

子命令:
    freeze <chapter>    在 .webnovel/snapshots/ch{NNNN}/ 创建快照
    verify <chapter>    对比当前文件与快照的 sha256
    list                列出所有快照
    diff <chapter>      显示当前 vs 快照的文件差异清单
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 冻结范围：设定集 + 大纲。后续章节的正文/SQLite 不冻结（那是产物，不是输入）。
SNAPSHOT_PATHS = ("设定集", "大纲")

# manifest 版本号：格式变更时 +1
MANIFEST_VERSION = 1

# 验证时输出的退出码
EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_INFRA = 2


@dataclass
class FileEntry:
    """单个文件的快照记录。"""
    path: str  # 相对项目根的路径
    sha256: str
    bytes: int

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class Manifest:
    """snapshot 的元数据 + 文件清单。"""
    version: int
    chapter: int
    frozen_at: str  # ISO 8601, UTC
    project_root: str
    files: list[FileEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "version": self.version,
            "chapter": self.chapter,
            "frozen_at": self.frozen_at,
            "project_root": self.project_root,
            "files": [f.to_dict() for f in self.files],
        }
        return d


def build_manifest(chapter: int, files: list[str], project_root: Path) -> Manifest:
    """从当前文件状态构造 manifest（不写盘）。"""
    file_entries: list[FileEntry] = []
    for rel in files:
        full = project_root / rel
        if not full.is_file():
            continue
        h = hashlib.sha256()
        h.update(full.read_bytes())
        file_entries.append(FileEntry(
            path=rel,
            sha256=h.hexdigest(),
            bytes=full.stat().st_size,
        ))
    return Manifest(
        version=MANIFEST_VERSION,
        chapter=chapter,
        frozen_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        project_root=str(project_root),
        files=file_entries,
    )


# === CLI 占位（后续 task 填充） ===
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="workflow snapshot 管理器")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    sub.add_parser("verify")
    sub.add_parser("list")
    sub.add_parser("diff")
    args = parser.parse_args(argv)
    print(f"stub: {args.cmd}", file=sys.stderr)
    return EXIT_INFRA


if __name__ == "__main__":
    sys.exit(main())