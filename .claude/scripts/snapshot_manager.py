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


def discover_files(project_root: Path) -> list[Path]:
    """递归扫描 SNAPSHOT_PATHS 下所有 .md 文件。

    过滤规则：
    - 只扫 SNAPSHOT_PATHS 列出的根（默认 设定集/ + 大纲/）
    - 只收 .md
    - 忽略隐藏文件（以 . 开头）
    """
    found: list[Path] = []
    for sub in SNAPSHOT_PATHS:
        root = project_root / sub
        if not root.is_dir():
            continue
        for p in root.rglob("*.md"):
            if any(part.startswith(".") for part in p.relative_to(root).parts):
                continue
            found.append(p)
    return sorted(found)


def _chapter_dir(project_root: Path, chapter: int) -> Path:
    return project_root / ".webnovel" / "snapshots" / f"ch{chapter:04d}"


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def cmd_freeze(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    files = discover_files(project_root)
    if not files:
        print(
            f"[snapshot] 找不到任何 SNAPSHOT_PATHS 下的 .md 文件 "
            f"(尝试过: {', '.join(SNAPSHOT_PATHS)})",
            file=sys.stderr,
        )
        return EXIT_INFRA

    chapter = args.chapter
    snap_dir = _chapter_dir(project_root, chapter)
    if snap_dir.exists():
        print(
            f"[snapshot] 警告: {snap_dir} 已存在，将被覆盖",
            file=sys.stderr,
        )

    rels = [p.relative_to(project_root).as_posix() for p in files]
    manifest = build_manifest(chapter, rels, project_root)

    # 复制文件 + 写 manifest
    for src in files:
        dst = snap_dir / src.relative_to(project_root)
        _copy_file(src, dst)
    (snap_dir / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "ok": True,
                "snapshot_dir": str(snap_dir),
                "chapter": chapter,
                "file_count": len(rels),
            },
            ensure_ascii=False,
        )
    )
    return EXIT_OK


def _not_implemented(name: str) -> int:
    print(f"[snapshot] {name} 尚未实现", file=sys.stderr)
    return EXIT_INFRA


def _load_manifest(project_root: Path, chapter: int) -> Manifest | None:
    snap_dir = _chapter_dir(project_root, chapter)
    p = snap_dir / "manifest.json"
    if not p.is_file():
        return None
    raw = json.loads(p.read_text(encoding="utf-8"))
    return Manifest(
        version=raw["version"],
        chapter=raw["chapter"],
        frozen_at=raw["frozen_at"],
        project_root=raw["project_root"],
        files=[FileEntry(**f) for f in raw["files"]],
    )


def cmd_verify(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    manifest = _load_manifest(project_root, args.chapter)
    if manifest is None:
        print(f"[snapshot] 找不到 ch{args.chapter:04d} 的 manifest", file=sys.stderr)
        return EXIT_INFRA

    current_files = discover_files(project_root)
    current_rels = {p.relative_to(project_root).as_posix(): p for p in current_files}

    snap_paths = {f.path for f in manifest.files}
    cur_paths = set(current_rels.keys())

    drifted: list[str] = []
    for f in manifest.files:
        cur = current_rels.get(f.path)
        if cur is None:
            continue  # 在 missing 里
        h = hashlib.sha256()
        h.update(cur.read_bytes())
        if h.hexdigest() != f.sha256:
            drifted.append(f.path)

    missing = sorted(snap_paths - cur_paths)
    added = sorted(cur_paths - snap_paths)

    ok = not (drifted or missing or added)
    print(json.dumps({
        "ok": ok,
        "chapter": args.chapter,
        "drifted_files": sorted(drifted),
        "missing_files": missing,
        "added_files": added,
    }, ensure_ascii=False))
    return EXIT_OK if ok else EXIT_DRIFT


def cmd_list(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    snap_root = project_root / ".webnovel" / "snapshots"
    snapshots: list[dict[str, Any]] = []
    if snap_root.is_dir():
        for d in sorted(snap_root.iterdir()):
            if not d.is_dir():
                continue
            m = _load_manifest(project_root, int(d.name[2:]))
            if m is None:
                continue
            snapshots.append({
                "chapter": m.chapter,
                "frozen_at": m.frozen_at,
                "file_count": len(m.files),
                "path": str(d.relative_to(project_root)),
            })
    print(json.dumps({"snapshots": snapshots}, ensure_ascii=False))
    return EXIT_OK


def cmd_diff(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    manifest = _load_manifest(project_root, args.chapter)
    if manifest is None:
        print(f"[snapshot] 找不到 ch{args.chapter:04d} 的 manifest", file=sys.stderr)
        return EXIT_INFRA

    current_files = discover_files(project_root)
    current_rels = {p.relative_to(project_root).as_posix(): p for p in current_files}

    rows: list[dict[str, Any]] = []
    snap_paths = {f.path for f in manifest.files}
    cur_paths = set(current_rels.keys())

    for f in manifest.files:
        cur = current_rels.get(f.path)
        if cur is None:
            rows.append({"path": f.path, "status": "deleted"})
            continue
        h = hashlib.sha256()
        h.update(cur.read_bytes())
        if h.hexdigest() != f.sha256:
            rows.append({"path": f.path, "status": "modified"})
        else:
            rows.append({"path": f.path, "status": "unchanged"})

    for p in sorted(cur_paths - snap_paths):
        rows.append({"path": p, "status": "added"})

    print(json.dumps({
        "chapter": args.chapter,
        "files": rows,
    }, ensure_ascii=False))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="workflow snapshot 管理器")
    parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="项目根目录（默认 CWD）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_freeze = sub.add_parser("freeze", help="冻结 N 章的 设定集+大纲")
    p_freeze.add_argument("chapter", type=int, help="章节号")
    p_freeze.set_defaults(func=cmd_freeze)

    p_verify = sub.add_parser("verify", help="校验 N 章快照是否漂移")
    p_verify.add_argument("chapter", type=int)
    p_verify.set_defaults(func=cmd_verify)

    p_list = sub.add_parser("list", help="列出所有快照")
    p_list.set_defaults(func=cmd_list)

    p_diff = sub.add_parser("diff", help="显示当前 vs 快照的文件差异清单")
    p_diff.add_argument("chapter", type=int)
    p_diff.set_defaults(func=cmd_diff)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())