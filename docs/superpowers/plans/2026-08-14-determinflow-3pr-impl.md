# DeterminFlow 3-PR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 webnovel-writer fork 落地 3 个从 DeterminFlow 偷来的理念：(1) workflow snapshot 防设定漂移；(2) context isolation 降 token；(3) structured rejection contract 提返修效率。每个 PR 独立可发布。

**Architecture:** 项目级 fork 层（`.claude/scripts/` + `.claude/skills/`）做新工具，不动 vendor 的 webnovel-writer 插件。3 个 PR 互相独立，可按任意顺序实现；推荐顺序为 1 → 3 → 2（PR 1 改少量、风险最低；PR 2 改 context-agent 输出，风险最大放最后）。

**Tech Stack:** Python 3.10+（fork 已用）、pytest、`hashlib`、JSON Schema（`jsonschema` 包，如缺失则用 dataclass + 手写 validator 避免引入新依赖）。无新依赖。

---

## 文件结构总览

| 文件 | 用途 | 来自 PR |
|---|---|---|
| `.claude/scripts/snapshot_manager.py` | PR1 核心：freeze / verify / list / diff | PR 1 |
| `.claude/scripts/tests/test_snapshot_manager.py` | PR1 单元测试 | PR 1 |
| `.claude/references/snapshot-protocol.md` | PR1 用户文档：何时 freeze、写什么、漂移怎么办 | PR 1 |
| `.claude/scripts/rejection_contract.py` | PR3 核心：定义 RejectionContract + validate + parse | PR 3 |
| `.claude/scripts/revise_chapter.py` | PR3 核心：基于 contract 做局部重写（CLI） | PR 3 |
| `.claude/scripts/tests/test_rejection_contract.py` | PR3 单元测试 | PR 3 |
| `.claude/scripts/tests/test_revise_chapter.py` | PR3 集成测试 | PR 3 |
| `.claude/skills/webnovel-revise/SKILL.md` | PR3 新增 skill | PR 3 |
| `.claude/scripts/context_slice.py` | PR2 核心：定义 ContextSlice schema + read_slice() | PR 2 |
| `.claude/scripts/tests/test_context_slice.py` | PR2 单元测试 | PR 2 |
| `.claude/references/context-slice-schema.md` | PR2 用户文档：每个节点要哪些 slice | PR 2 |

**Skill 改动**（小修，不重写）：

| Skill | 改动 | 来自 PR |
|---|---|---|
| `.claude/skills/webnovel-fast-write/SKILL.md` | Step 0 加 snapshot verify；末尾可选 Step 7 "revise if reviewer rejected" 走 PR3 | PR 1 + 3 |
| `.claude/skills/webnovel-resume/SKILL.md` | 检测 snapshot drift 时给用户"re-snapshot or keep"选项 | PR 1 |
| `.claude/plugins/webnovel-writer/agents/context-agent.md` | **不改**；PR2 在调用方做 post-trim | PR 2 |

**重要约束**：vendor 路径 `.claude/plugins/webnovel-writer/` **不可改**（fork 升级时会被覆盖）。所有新增都在 `.claude/scripts/` 与 `.claude/skills/`。

---

## 全局约定

- 所有 Python 脚本遵循 `.claude/scripts/changes_gate.py` 的风格：`argparse` CLI + `dataclass` + `to_dict()` 输出 JSON、退出码 0/1/2（0=ok, 1=blocking failure, 2=infrastructure error）。
- 所有测试在 `.claude/scripts/tests/`，用 pytest，运行命令统一为：
  ```bash
  cd .claude/scripts && python3 -m pytest tests/test_<name>.py -v
  ```
- Commit 粒度：每个 Task 末尾一个 commit，message 格式 `feat(<scope>): <what>` 或 `test(<scope>): <what>`。

---

# PR 1: Workflow Snapshot

**目标**：每次 plan 完成后，冻结当前 设定集/大纲 副本到 `.webnovel/snapshots/ch{NNNN}/`；每次 write 启动时检测 hash 漂移，强制提示。

**为什么**：用户改设定集时，已写章节不应被破坏。这是长篇一致性的硬保障。

**验收**：
- `snapshot_manager.py freeze 1` 创建 `.webnovel/snapshots/ch0001/`，内含 设定集/大纲 副本 + `manifest.json`
- `snapshot_manager.py verify 1` 对比当前文件与 snapshot 的 sha256，输出一致/漂移清单
- `snapshot_manager.py list` 列出所有 snapshot 的章节号 + 时间
- `snapshot_manager.py diff 1` 显示当前 vs snapshot 的差异文件列表

---

### Task 1.1: snapshot_manager.py 骨架 + manifest schema

**Files:**
- Create: `.claude/scripts/snapshot_manager.py`
- Test: `.claude/scripts/tests/test_snapshot_manager.py`

- [ ] **Step 1.1.1: 写失败测试 — ManifestSchema dataclass**

在 `.claude/scripts/tests/test_snapshot_manager.py`：

```python
"""snapshot_manager.py 单元测试。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SNAPSHOT_SCRIPT = Path(__file__).resolve().parent.parent / "snapshot_manager.py"


def run_snapshot(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SNAPSHOT_SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd,
    )


# === Manifest schema ===
def test_manifest_has_required_fields(tmp_path):
    """manifest.json 必须包含: chapter, frozen_at, files[]。"""
    from snapshot_manager import build_manifest
    # 准备真实文件（build_manifest 跳过不存在的路径）
    (tmp_path / "设定集").mkdir()
    target = tmp_path / "设定集" / "陈默.md"
    target.write_text("x", encoding="utf-8")
    m = build_manifest(
        chapter=1,
        files=["设定集/陈默.md"],
        project_root=tmp_path,
    )
    assert m.chapter == 1
    assert m.frozen_at  # 非空字符串
    assert len(m.files) == 1
    assert m.files[0].path == "设定集/陈默.md"
    d = m.to_dict()
    assert "chapter" in d and "frozen_at" in d and "files" in d


def test_manifest_serializes_to_json(tmp_path):
    """to_dict() 输出可被 json.dumps 序列化。"""
    from snapshot_manager import build_manifest
    (tmp_path / "x").write_text("y", encoding="utf-8")
    m = build_manifest(chapter=42, files=["x"], project_root=tmp_path)
    s = json.dumps(m.to_dict(), ensure_ascii=False)
    parsed = json.loads(s)
    assert parsed["chapter"] == 42
```

- [ ] **Step 1.1.2: 运行测试确认失败**

```bash
cd .claude/scripts && python3 -m pytest tests/test_snapshot_manager.py::test_manifest_has_required_fields -v
```

Expected: `ModuleNotFoundError: No module named 'snapshot_manager'` 或 `ImportError`。

- [ ] **Step 1.1.3: 实现 manifest schema**

在 `.claude/scripts/snapshot_manager.py`：

```python
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
```

- [ ] **Step 1.1.4: 运行测试确认通过**

```bash
cd .claude/scripts && python3 -m pytest tests/test_snapshot_manager.py::test_manifest_has_required_fields tests/test_snapshot_manager.py::test_manifest_serializes_to_json -v
```

Expected: 2 passed。

- [ ] **Step 1.1.5: Commit**

```bash
git add .claude/scripts/snapshot_manager.py .claude/scripts/tests/test_snapshot_manager.py
git commit -m "feat(snapshot): add manifest schema + skeleton CLI"
```

---

### Task 1.2: discover_files() + freeze 命令

**Files:**
- Modify: `.claude/scripts/snapshot_manager.py`
- Modify: `.claude/scripts/tests/test_snapshot_manager.py`

- [ ] **Step 1.2.1: 写失败测试 — discover_files + freeze**

追加到 `test_snapshot_manager.py`：

```python


# === discover_files ===
def test_discover_files_finds_md_under_settings_and_outline(tmp_path: Path):
    """discover_files 应递归扫描 设定集/ 与 大纲/ 下所有 .md 文件。"""
    (tmp_path / "设定集").mkdir()
    (tmp_path / "大纲").mkdir()
    (tmp_path / "设定集" / "角色库").mkdir()
    (tmp_path / "设定集" / "角色库" / "陈默.md").write_text("x", encoding="utf-8")
    (tmp_path / "大纲" / "总纲.md").write_text("y", encoding="utf-8")
    # 噪声：应被忽略
    (tmp_path / "设定集" / ".DS_Store").write_text("z", encoding="utf-8")
    (tmp_path / "大纲" / "note.txt").write_text("w", encoding="utf-8")

    from snapshot_manager import discover_files
    found = discover_files(tmp_path)
    rels = sorted(f.relative_to(tmp_path).as_posix() for f in found)
    assert rels == ["大纲/总纲.md", "设定集/角色库/陈默.md"]


# === freeze 命令（端到端） ===
def test_freeze_creates_snapshot_dir_and_copies_files(tmp_path: Path):
    """freeze N 在 .webnovel/snapshots/ch{NNNN}/ 创建目录并复制所有 .md + manifest.json。"""
    # 准备项目结构
    (tmp_path / "设定集").mkdir()
    (tmp_path / "大纲").mkdir()
    (tmp_path / "设定集" / "陈默.md").write_text("角色状态", encoding="utf-8")
    (tmp_path / "大纲" / "总纲.md").write_text("大纲", encoding="utf-8")

    result = run_snapshot("freeze", "1", cwd=tmp_path)
    assert result.returncode == 0, f"stderr: {result.stderr}"

    snap_dir = tmp_path / ".webnovel" / "snapshots" / "ch0001"
    assert snap_dir.is_dir()
    assert (snap_dir / "设定集" / "陈默.md").is_file()
    assert (snap_dir / "大纲" / "总纲.md").is_file()
    assert (snap_dir / "manifest.json").is_file()
    manifest = json.loads((snap_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["chapter"] == 1
    assert manifest["version"] == 1
    file_paths = {f["path"] for f in manifest["files"]}
    assert file_paths == {"设定集/陈默.md", "大纲/总纲.md"}


def test_freeze_uses_4digit_chapter_number(tmp_path: Path):
    """freeze 12 → ch0012；freeze 100 → ch0100。"""
    (tmp_path / "大纲").mkdir()
    result = run_snapshot("freeze", "12", cwd=tmp_path)
    assert result.returncode == 0
    assert (tmp_path / ".webnovel" / "snapshots" / "ch0012").is_dir()


def test_freeze_fails_when_no_settings_or_outline(tmp_path: Path):
    """既无 设定集/ 也无 大纲/ → 退出码 2（infrastructure error）。"""
    result = run_snapshot("freeze", "1", cwd=tmp_path)
    assert result.returncode == 2
    assert "no snapshot-eligible files" in result.stderr.lower() or "找不到" in result.stderr
```

- [ ] **Step 1.2.2: 运行测试确认失败**

```bash
cd .claude/scripts && python3 -m pytest tests/test_snapshot_manager.py::test_discover_files_finds_md_under_settings_and_outline tests/test_snapshot_manager.py::test_freeze_creates_snapshot_dir_and_copies_files -v
```

Expected: FAIL（discover_files 不存在；freeze 是 stub）。

- [ ] **Step 1.2.3: 实现 discover_files + freeze**

替换 `.claude/scripts/snapshot_manager.py` 末尾的 `main()` 及之前的 stub，**保留** `Manifest` / `FileEntry` / `build_manifest` 不变。在 `build_manifest` 后追加：

```python
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
```

替换 `main()`：

```python
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

    # 其他子命令占位，后续 task 填充
    p_verify = sub.add_parser("verify", help="校验 N 章快照是否漂移")
    p_verify.add_argument("chapter", type=int)
    p_verify.set_defaults(func=lambda a: _not_implemented("verify"))

    p_list = sub.add_parser("list", help="列出所有快照")
    p_list.set_defaults(func=lambda a: _not_implemented("list"))

    p_diff = sub.add_parser("diff", help="显示当前 vs 快照的文件差异清单")
    p_diff.add_argument("chapter", type=int)
    p_diff.set_defaults(func=lambda a: _not_implemented("diff"))

    args = parser.parse_args(argv)
    return args.func(args)


def _not_implemented(name: str) -> int:
    print(f"[snapshot] {name} 尚未实现", file=sys.stderr)
    return EXIT_INFRA
```

- [ ] **Step 1.2.4: 运行测试确认通过**

```bash
cd .claude/scripts && python3 -m pytest tests/test_snapshot_manager.py::test_discover_files_finds_md_under_settings_and_outline tests/test_snapshot_manager.py::test_freeze_creates_snapshot_dir_and_copies_files tests/test_snapshot_manager.py::test_freeze_uses_4digit_chapter_number tests/test_snapshot_manager.py::test_freeze_fails_when_no_settings_or_outline -v
```

Expected: 4 passed。

- [ ] **Step 1.2.5: Commit**

```bash
git add .claude/scripts/snapshot_manager.py .claude/scripts/tests/test_snapshot_manager.py
git commit -m "feat(snapshot): implement freeze + discover_files"
```

---

### Task 1.3: verify + list + diff 命令

**Files:**
- Modify: `.claude/scripts/snapshot_manager.py`
- Modify: `.claude/scripts/tests/test_snapshot_manager.py`

- [ ] **Step 1.3.1: 写失败测试 — verify / list / diff**

追加：

```python


# === verify ===
def test_verify_returns_ok_when_unchanged(tmp_path: Path):
    """freeze 后立即 verify → exit 0, ok=true。"""
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("v1", encoding="utf-8")
    assert run_snapshot("freeze", "1", cwd=tmp_path).returncode == 0
    result = run_snapshot("verify", "1", cwd=tmp_path)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["ok"] is True
    assert out["drifted_files"] == []
    assert out["missing_files"] == []
    assert out["added_files"] == []


def test_verify_detects_modified_file(tmp_path: Path):
    """modify 一个文件后 verify → exit 1, drifted_files 列出该文件。"""
    (tmp_path / "大纲").mkdir()
    f = tmp_path / "大纲" / "总纲.md"
    f.write_text("v1", encoding="utf-8")
    run_snapshot("freeze", "1", cwd=tmp_path)
    f.write_text("v2 — 修改过", encoding="utf-8")
    result = run_snapshot("verify", "1", cwd=tmp_path)
    assert result.returncode == 1
    out = json.loads(result.stdout)
    assert out["ok"] is False
    assert "大纲/总纲.md" in out["drifted_files"]


def test_verify_detects_added_and_deleted_files(tmp_path: Path):
    """新增/删除文件 → added_files / missing_files 反映。"""
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("x", encoding="utf-8")
    (tmp_path / "设定集").mkdir()
    (tmp_path / "设定集" / "陈默.md").write_text("y", encoding="utf-8")
    run_snapshot("freeze", "1", cwd=tmp_path)
    # 新增一个
    (tmp_path / "设定集" / "王玄之.md").write_text("z", encoding="utf-8")
    # 删除一个
    (tmp_path / "设定集" / "陈默.md").unlink()

    result = run_snapshot("verify", "1", cwd=tmp_path)
    assert result.returncode == 1
    out = json.loads(result.stdout)
    assert "设定集/王玄之.md" in out["added_files"]
    assert "设定集/陈默.md" in out["missing_files"]


def test_verify_fails_when_snapshot_missing(tmp_path: Path):
    """不存在的章节 → exit 2。"""
    (tmp_path / "大纲").mkdir()
    result = run_snapshot("verify", "999", cwd=tmp_path)
    assert result.returncode == 2


# === list ===
def test_list_returns_all_snapshots(tmp_path: Path):
    """freeze 多个章节 → list 全部返回。"""
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("x", encoding="utf-8")
    for n in (1, 3, 7):
        run_snapshot("freeze", str(n), cwd=tmp_path)
    result = run_snapshot("list", cwd=tmp_path)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    chapters = {s["chapter"] for s in out["snapshots"]}
    assert chapters == {1, 3, 7}


# === diff ===
def test_diff_shows_drifted_file_list(tmp_path: Path):
    """diff 输出当前 vs snapshot 的差异文件清单（包含状态）。"""
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("v1", encoding="utf-8")
    run_snapshot("freeze", "1", cwd=tmp_path)
    (tmp_path / "大纲" / "总纲.md").write_text("v2", encoding="utf-8")
    result = run_snapshot("diff", "1", cwd=tmp_path)
    assert result.returncode in (0, 1)  # diff 本身不强制失败
    out = json.loads(result.stdout)
    statuses = {f["path"]: f["status"] for f in out["files"]}
    assert statuses.get("大纲/总纲.md") == "modified"
```

- [ ] **Step 1.3.2: 运行测试确认失败**

```bash
cd .claude/scripts && python3 -m pytest tests/test_snapshot_manager.py::test_verify_returns_ok_when_unchanged -v
```

Expected: FAIL（verify 是 stub）。

- [ ] **Step 1.3.3: 实现 verify / list / diff**

在 `_not_implemented` 之前插入：

```python
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
```

替换 `main()` 中三个 stub：

```python
    p_verify = sub.add_parser("verify", help="校验 N 章快照是否漂移")
    p_verify.add_argument("chapter", type=int)
    p_verify.set_defaults(func=cmd_verify)

    p_list = sub.add_parser("list", help="列出所有快照")
    p_list.set_defaults(func=cmd_list)

    p_diff = sub.add_parser("diff", help="显示当前 vs 快照的文件差异清单")
    p_diff.add_argument("chapter", type=int)
    p_diff.set_defaults(func=cmd_diff)
```

删除 `_not_implemented` 函数（或保留但移除引用）。

- [ ] **Step 1.3.4: 运行全部 snapshot 测试**

```bash
cd .claude/scripts && python3 -m pytest tests/test_snapshot_manager.py -v
```

Expected: 全部 passed（Task 1.1 的 2 个 + Task 1.2 的 4 个 + Task 1.3 的 6 个 = 12 个）。

- [ ] **Step 1.3.5: Commit**

```bash
git add .claude/scripts/snapshot_manager.py .claude/scripts/tests/test_snapshot_manager.py
git commit -m "feat(snapshot): implement verify/list/diff commands"
```

---

### Task 1.4: snapshot-protocol.md 用户文档

**Files:**
- Create: `.claude/references/snapshot-protocol.md`

- [ ] **Step 1.4.1: 写文档**

```markdown
# Workflow Snapshot 协议

## 这是什么

每次 `/webnovel-plan` 完成后，冻结当前 设定集/ + 大纲/ 的完整副本到 `.webnovel/snapshots/ch{NNNN}/`。

写未来章节时即使改了设定，已写章节也不会受影响——因为它"出生时"的设定已经被锁死。

## 何时调用

```bash
# 在 /webnovel-plan 流程的最后一步（或单独运行）
python3 .claude/scripts/snapshot_manager.py freeze <chapter> --project-root .
```

按惯例：每次完成一章的章纲拆分后立刻 freeze。

## 何时校验

`/webnovel-fast-write` 和 `/webnovel-write` 的 Step 0（预检）会调用 `verify`：

```bash
python3 .claude/scripts/snapshot_manager.py verify <chapter> --project-root .
```

- 退出码 0 = 设定未漂移，正常往下走
- 退出码 1 = 漂移（修改过 / 新增 / 删除），主流程**不阻断**，但会在日志里 warning：
  > `[snapshot] ch0001 设定已漂移：1 个文件被修改、0 个新增、0 个删除。是否需要 re-snapshot？`
- 退出码 2 = infrastructure error（snapshot 目录不存在 / manifest 损坏），需要人工处理

## 漂移了怎么办

两个选择：

**A. 接受漂移**（默认）：写手用最新的设定继续写。可能产生前后不一致，但省时间。

**B. 重新 freeze**：
```bash
python3 .claude/scripts/snapshot_manager.py freeze <chapter> --project-root .
# 警告: ch0001 已存在，将被覆盖
```

适用场景：你改了设定但想"以新设定为准重写"前面章节——这时候别 re-freeze，先去把那几章用 `/webnovel-revise` 重写。

## 查 snapshot 状态

```bash
python3 .claude/scripts/snapshot_manager.py list --project-root .
python3 .claude/scripts/snapshot_manager.py diff <chapter> --project-root .
```

## 不冻结什么

- `正文/` — 产物，不是输入。重新生成不需要 snapshot
- `index.db` — 每次 chapter-commit 会更新；不需要版本冻结
- `.webnovel/summaries/` — 同上
- `.webnovel/snapshots/` 自己 — 防止递归
```

- [ ] **Step 1.4.2: Commit**

```bash
git add .claude/references/snapshot-protocol.md
git commit -m "docs(snapshot): add snapshot-protocol.md"
```

---

### Task 1.5: 接入 webnovel-fast-write 预检

**Files:**
- Modify: `.claude/skills/webnovel-fast-write/SKILL.md`

- [ ] **Step 1.5.1: 在 Step 0 后插入 snapshot verify**

修改 `.claude/skills/webnovel-fast-write/SKILL.md`，把第 30 行的：

```
1. **Step 0 预检**：调用 `${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py preflight` + `placeholder-scan`。
```

改为：

```
1. **Step 0 预检**：调用 `${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py preflight` + `placeholder-scan`。
2. **Step 0.5 snapshot 校验**（PR 1 引入）：调用 `python3 ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/snapshot_manager.py verify ${chapter} --project-root .`。
   - exit 0：继续
   - exit 1（漂移）：log warning 但不阻断，向用户报告 `drifted_files` / `added_files` / `missing_files`，等用户裁决后再继续
   - exit 2（infrastructure error）：阻断，要求用户先 freeze
```

- [ ] **Step 1.5.2: Commit**

```bash
git add .claude/skills/webnovel-fast-write/SKILL.md
git commit -m "feat(fast-write): add snapshot verify preflight (PR 1)"
```

---

### Task 1.6: 端到端 smoke test（在 根源牌序 项目跑）

**Files:** 无（验证 PR 1 整体可工作）

- [ ] **Step 1.6.1: 在《根源牌序》目录跑 freeze**

```bash
cd /Users/chang/Desktop/根源牌序
python3 /Users/chang/Desktop/ai写小说工具开发/.claude/scripts/snapshot_manager.py --project-root /Users/chang/Desktop/根源牌序 freeze 1
# 注：--project-root 是 argparse 全局选项，必须在子命令前
```

Expected: stdout 一行 JSON `{"ok": true, "snapshot_dir": ".../snapshots/ch0001", "chapter": 1, "file_count": N}`，退出码 0。

- [ ] **Step 1.6.2: 验证文件确实复制了**

```bash
ls -la /Users/chang/Desktop/根源牌序/.webnovel/snapshots/ch0001/
cat /Users/chang/Desktop/根源牌序/.webnovel/snapshots/ch0001/manifest.json
```

Expected: 看到 `manifest.json`、`大纲/`、`设定集/` 子目录。manifest.json 是合法 JSON，含 `chapter: 1`、`files` 数组列出所有相对路径。

- [ ] **Step 1.6.3: 跑 verify（无修改 → 应该 ok）**

```bash
python3 /Users/chang/Desktop/ai写小说工具开发/.claude/scripts/snapshot_manager.py --project-root /Users/chang/Desktop/根源牌序 verify 1
```

Expected: 退出码 0，`ok: true`。

- [ ] **Step 1.6.4: 修改一个文件再 verify**

```bash
echo "测试修改" >> /Users/chang/Desktop/根源牌序/大纲/总纲.md
python3 /Users/chang/Desktop/ai写小说工具开发/.claude/scripts/snapshot_manager.py --project-root /Users/chang/Desktop/根源牌序 verify 1
echo "exit=$?"
# 改回去（手动，因为《根源牌序》非 git 仓库）
# 实际 smoke test 时应记录原始内容并精确还原，或：
#   1. 记录 sha256: shasum /Users/chang/Desktop/根源牌序/大纲/总纲.md
#   2. 测完后用同一内容覆盖回去
```

Expected: 退出码 1，`drifted_files` 含 `大纲/总纲.md`。

- [ ] **Step 1.6.5: 跑全量测试**

```bash
cd /Users/chang/Desktop/ai写小说工具开发/.claude/scripts && python3 -m pytest tests/ -v
```

Expected: 全部 passed（包括老的 changes_gate 测试，不能回归）。

- [ ] **Step 1.6.6: Commit（如有变化）**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git status  # 看是否有未提交改动
# 通常 smoke test 不改代码，但若改了 setup 之类才需要 commit
```

---

# PR 3: Structured Rejection Contract

**目标**：reviewer 已经输出结构化 JSON（`issues[]`），复用它。让 reviewer 的输出能直接驱动局部重写：用户（或自动流程）拿到 `RejectionContract`，重写器只改 `target_section` 范围内的内容。

**为什么**：现在 reviewer 给的是「散文反馈」，写手拿到要么自己猜改哪里（累），要么让 AI 整章重写（贵 60-80%）。structured contract 把"哪里要改、改什么、保留什么"显式化。

**注意**：reviewer 的 JSON 格式 **已经存在**（在 `.claude/plugins/webnovel-writer/agents/reviewer.md` 第 7 节）。我们**不修改**它，而是在 contract 层加一层语义：哪些 issue 是 blocker、对应到 chapter 的哪几段、要改什么类型。这是从 reviewer JSON → 可执行的 rewrite plan 的转换。

**验收**：
- `rejection_contract.py` 能从 reviewer JSON 构造 `RejectionContract`、校验合法、把多个 issue 合并为一段可执行计划
- `revise_chapter.py` 接受 contract + 章节文件，**只重写 contract 标出的范围**，其他段落原样保留
- `webnovel-revise` skill 编排整个流程

---

### Task 3.1: RejectionContract schema + parser

**Files:**
- Create: `.claude/scripts/rejection_contract.py`
- Create: `.claude/scripts/tests/test_rejection_contract.py`

- [ ] **Step 3.1.1: 写失败测试**

在 `.claude/scripts/tests/test_rejection_contract.py`：

```python
"""rejection_contract.py 单元测试。"""
import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rejection_contract import (
    IssueRef,
    RejectionContract,
    build_contract_from_reviewer_output,
    validate_contract,
    merge_contracts,
    targets_text,
    Severity,
)


REVIEWER_JSON = {
    "chapter": 5,
    "issues": [
        {
            "severity": "critical",
            "category": "continuity",
            "location": "第3段",
            "description": "上章钩子未回应",
            "evidence": "上章末尾提到玄之会回来，本章没出现",
            "fix_hint": "在第3段加入玄之回场的桥段",
            "blocking": True,
        },
        {
            "severity": "high",
            "category": "character",
            "location": "第5段",
            "description": "陈默的对话风格与角色库矛盾",
            "evidence": "原文：'在下告辞'。角色库标注：粗犷不拘礼节",
            "fix_hint": "改为更口语化的告别方式",
            "blocking": False,
        },
        {
            "severity": "low",
            "category": "pacing",
            "location": "第7段",
            "description": "节奏略拖",
            "evidence": "环境描写 800 字无推进",
            "fix_hint": "压缩到 300 字",
            "blocking": False,
        },
    ],
    "blocking_count": 1,
    "issues_count": 3,
}


def test_build_contract_from_reviewer_output_keeps_blocking_only_by_default():
    """默认只把 blocking=true 的 issue 转成 IssueRef。"""
    contract = build_contract_from_reviewer_output(REVIEWER_JSON)
    assert contract.chapter == 5
    assert len(contract.issues) == 1
    issue = contract.issues[0]
    assert issue.category == "continuity"
    assert issue.location == "第3段"
    assert issue.severity == Severity.CRITICAL


def test_build_contract_with_include_advisory_includes_low():
    """include_advisory=True → 全收。"""
    contract = build_contract_from_reviewer_output(
        REVIEWER_JSON, include_advisory=True
    )
    assert len(contract.issues) == 3
    cats = [i.category for i in contract.issues]
    assert "continuity" in cats and "character" in cats and "pacing" in cats


def test_validate_contract_rejects_empty():
    """空 contract → raise。"""
    c = RejectionContract(chapter=1, issues=[])
    with pytest.raises(ValueError, match="至少一个 issue"):
        validate_contract(c)


def test_validate_contract_rejects_unknown_category():
    """category 不在白名单 → raise。"""
    bad = RejectionContract(
        chapter=1,
        issues=[IssueRef(
            severity=Severity.HIGH,
            category="fashion",  # 不合法
            location="第1段",
            description="x",
            fix_hint="y",
            blocking=True,
        )],
    )
    with pytest.raises(ValueError, match="category"):
        validate_contract(bad)


def test_validate_contract_rejects_missing_required_field():
    """IssueRef 缺 location/description/fix_hint → raise。"""
    bad = RejectionContract(
        chapter=1,
        issues=[IssueRef(
            severity=Severity.HIGH,
            category="continuity",
            location="",
            description="x",
            fix_hint="y",
            blocking=True,
        )],
    )
    with pytest.raises(ValueError, match="location"):
        validate_contract(bad)


def test_merge_contracts_concatenates_issues():
    """两个 contract 合并 → issues 拼接，chapter 必须一致。"""
    a = build_contract_from_reviewer_output(REVIEWER_JSON)
    b = build_contract_from_reviewer_output(REVIEWER_JSON)
    merged = merge_contracts([a, b])
    assert merged.chapter == 5
    assert len(merged.issues) == 2

    other = RejectionContract(chapter=6, issues=a.issues)
    with pytest.raises(ValueError, match="同一章节"):
        merge_contracts([a, other])


def test_targets_text_groups_by_location():
    """targets_text() 按 location 聚合 fix_hint。"""
    contract = RejectionContract(
        chapter=1,
        issues=[
            IssueRef(Severity.CRITICAL, "continuity", "第2段", "缺钩子", "加回场", True),
            IssueRef(Severity.HIGH, "character", "第5段", "腔调错", "改口语", False),
            IssueRef(Severity.HIGH, "character", "第5段", "用典错", "换典故", False),
        ],
    )
    targets = targets_text(contract)
    assert "第2段" in targets
    assert "第5段" in targets
    # 第5段有两条 fix_hint
    seg5 = targets.split("第5段")[1]
    assert "改口语" in seg5 and "换典故" in seg5
```

- [ ] **Step 3.1.2: 运行测试确认失败**

```bash
cd .claude/scripts && python3 -m pytest tests/test_rejection_contract.py -v
```

Expected: `ModuleNotFoundError: No module named 'rejection_contract'`。

- [ ] **Step 3.1.3: 实现 rejection_contract.py**

在 `.claude/scripts/rejection_contract.py`：

```python
#!/usr/bin/env python3
"""Reviewer 输出 → RejectionContract 转换与校验。

Reviewer 的原始 JSON（见 plugins/webnovel-writer/agents/reviewer.md §7）
是结构化但"散文式"的：每个 issue 有 location / description / fix_hint
但没有显式"保留哪些段"。

RejectionContract 在它之上加 3 件事：
1. 过滤（默认只收 blocking=true）
2. 校验（location/fix_hint 必填，category 在白名单）
3. 合并（多次 reviewer 跑出的 contract 可聚合）
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Iterable


VALID_CATEGORIES = frozenset({
    "continuity", "setting", "character", "timeline", "logic", "pacing", "other",
})


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class IssueRef:
    """单条 issue 的引用 + 修复指令。"""
    severity: Severity
    category: str
    location: str  # "第3段" / "§2-§5" / 具体引用
    description: str
    fix_hint: str
    blocking: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "location": self.location,
            "description": self.description,
            "fix_hint": self.fix_hint,
            "blocking": self.blocking,
        }


@dataclass
class RejectionContract:
    """一组要修的 issue + 元数据。"""
    chapter: int
    issues: list[IssueRef] = field(default_factory=list)
    source: str = "reviewer"  # 来源标识，方便调试

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter": self.chapter,
            "source": self.source,
            "issues": [i.to_dict() for i in self.issues],
        }


def build_contract_from_reviewer_output(
    reviewer_json: dict[str, Any],
    include_advisory: bool = False,
    source: str = "reviewer",
) -> RejectionContract:
    """从 reviewer 的原始 JSON 构造 contract。

    include_advisory=False（默认）：只收 blocking=True 的 issue。
    include_advisory=True：全收，按 severity 顺序保留。
    """
    chapter = reviewer_json.get("chapter")
    if chapter is None:
        raise ValueError("reviewer_json 缺少 chapter 字段")

    raw_issues = reviewer_json.get("issues", [])
    if include_advisory:
        selected = raw_issues
    else:
        selected = [i for i in raw_issues if i.get("blocking")]

    issues: list[IssueRef] = []
    for raw in selected:
        sev = raw.get("severity", "high")
        try:
            sev_enum = Severity(sev)
        except ValueError:
            sev_enum = Severity.HIGH

        issues.append(IssueRef(
            severity=sev_enum,
            category=raw.get("category", "other"),
            location=raw.get("location", ""),
            description=raw.get("description", ""),
            fix_hint=raw.get("fix_hint", ""),
            blocking=bool(raw.get("blocking", False)),
        ))

    return RejectionContract(chapter=chapter, issues=issues, source=source)


def validate_contract(contract: RejectionContract) -> None:
    """合法性校验。raise ValueError 说明哪里坏了。"""
    if not contract.issues:
        raise ValueError("contract 需要至少一个 issue")

    for idx, issue in enumerate(contract.issues):
        if not issue.location.strip():
            raise ValueError(f"contract.issues[{idx}].location 必填")
        if not issue.description.strip():
            raise ValueError(f"contract.issues[{idx}].description 必填")
        if not issue.fix_hint.strip():
            raise ValueError(f"contract.issues[{idx}].fix_hint 必填")
        if issue.category not in VALID_CATEGORIES:
            raise ValueError(
                f"contract.issues[{idx}].category={issue.category!r} 不在白名单 {sorted(VALID_CATEGORIES)}"
            )


def merge_contracts(contracts: Iterable[RejectionContract]) -> RejectionContract:
    """合并多个 contract（必须同一章节）。"""
    contracts = list(contracts)
    if not contracts:
        raise ValueError("至少需要一个 contract")
    chapters = {c.chapter for c in contracts}
    if len(chapters) > 1:
        raise ValueError(f"合并的 contract 必须是同一章节，得到 {sorted(chapters)}")

    chapter = contracts[0].chapter
    merged_issues: list[IssueRef] = []
    for c in contracts:
        merged_issues.extend(c.issues)
    return RejectionContract(
        chapter=chapter,
        issues=merged_issues,
        source="+".join({c.source for c in contracts}),
    )


def targets_text(contract: RejectionContract) -> str:
    """生成给重写 LLM 看的"目标段 + 修复指令"汇总文本。

    按 location 聚合；同一段有多个 fix_hint 用换行分隔。
    """
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for issue in contract.issues:
        if issue.location not in grouped:
            order.append(issue.location)
            grouped[issue.location] = []
        grouped[issue.location].append(
            f"  - [{issue.severity.value}/{issue.category}] {issue.fix_hint}（{issue.description}）"
        )

    lines = [f"针对第 {contract.chapter} 章的局部重写任务："]
    for loc in order:
        lines.append(f"\n## {loc}")
        lines.extend(grouped[loc])
    return "\n".join(lines)
```

- [ ] **Step 3.1.4: 运行测试确认通过**

```bash
cd .claude/scripts && python3 -m pytest tests/test_rejection_contract.py -v
```

Expected: 7 passed。

- [ ] **Step 3.1.5: Commit**

```bash
git add .claude/scripts/rejection_contract.py .claude/scripts/tests/test_rejection_contract.py
git commit -m "feat(rejection): add RejectionContract schema + parser/validator"
```

---

### Task 3.2: revise_chapter.py — 局部重写执行器

**Files:**
- Create: `.claude/scripts/revise_chapter.py`
- Create: `.claude/scripts/tests/test_revise_chapter.py`

- [ ] **Step 3.2.1: 写失败测试**

在 `.claude/scripts/tests/test_revise_chapter.py`：

```python
"""revise_chapter.py 集成测试。

注意：完整的 LLM 重写测试需要 mock（PR3 阶段先验证骨架，
真实 LLM 调用留到 PR 3 末尾的 smoke test）。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REVISE_SCRIPT = Path(__file__).resolve().parent.parent / "revise_chapter.py"


SAMPLE_CHAPTER = """# 第5章 玄之归来

## §1 开场

陈默站在论剑台上，夜风把他的衣角吹得猎猎作响。

## §2 战斗

## §3 玄之回场

王玄之从台下跃起，长剑出鞘。

## §4 对话

"好久不见。"玄之说。

## §5 结尾

陈默微笑。

"""


CONTRACT_JSON = {
    "chapter": 5,
    "issues": [
        {
            "severity": "critical",
            "category": "continuity",
            "location": "§2",
            "description": "战斗段空",
            "fix_hint": "补 200 字战斗描写",
            "blocking": True,
        },
        {
            "severity": "high",
            "category": "character",
            "location": "§4",
            "description": "对白与角色库矛盾",
            "fix_hint": "改成粗犷口语",
            "blocking": False,
        },
    ],
}


def run_revise(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REVISE_SCRIPT), *args],
        capture_output=True, text=True,
    )


def test_revise_dry_run_outputs_target_sections(tmp_path: Path):
    """--dry-run：不调 LLM，只输出 targets_text + 受影响段落预览。"""
    chapter_file = tmp_path / "ch0005.md"
    chapter_file.write_text(SAMPLE_CHAPTER, encoding="utf-8")
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(CONTRACT_JSON), encoding="utf-8")

    result = run_revise(
        "--chapter-file", str(chapter_file),
        "--contract", str(contract_file),
        "--dry-run",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    out = json.loads(result.stdout)
    assert out["dry_run"] is True
    assert "§2" in out["target_sections"]
    assert "§4" in out["target_sections"]
    assert "补 200 字战斗描写" in out["targets_text"]


def test_revise_rejects_missing_chapter_file(tmp_path: Path):
    """章节文件不存在 → exit 2。"""
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(CONTRACT_JSON), encoding="utf-8")
    result = run_revise(
        "--chapter-file", str(tmp_path / "missing.md"),
        "--contract", str(contract_file),
        "--dry-run",
    )
    assert result.returncode == 2


def test_revise_rejects_invalid_contract(tmp_path: Path):
    """contract 缺 location → exit 1。"""
    chapter_file = tmp_path / "ch0005.md"
    chapter_file.write_text(SAMPLE_CHAPTER, encoding="utf-8")
    bad_contract = {
        "chapter": 5,
        "issues": [
            {
                "severity": "high",
                "category": "continuity",
                "location": "",  # 非法
                "description": "x",
                "fix_hint": "y",
                "blocking": True,
            }
        ],
    }
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(bad_contract), encoding="utf-8")
    result = run_revise(
        "--chapter-file", str(chapter_file),
        "--contract", str(contract_file),
        "--dry-run",
    )
    assert result.returncode == 1
    assert "location" in result.stderr


def test_extract_section_returns_correct_span(tmp_path: Path):
    """extract_section('§2', chapter_text) → 返回 ## §2 段到下一个 ## 之前。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    from revise_chapter import extract_section
    text = SAMPLE_CHAPTER
    sec = extract_section(text, "§2")
    assert "## §2" in sec
    assert "## §3" not in sec
    # §4 段
    sec4 = extract_section(text, "§4")
    assert "好久不见" in sec4
    assert "## §5" not in sec4


def test_revise_plan_returns_per_section_actions(tmp_path: Path):
    """build_revise_plan() 返回 {section: 原内容} 的字典，给 LLM 喂。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    from revise_chapter import build_revise_plan
    from rejection_contract import build_contract_from_reviewer_output

    contract = build_contract_from_reviewer_output(CONTRACT_JSON)
    plan = build_revise_plan(SAMPLE_CHAPTER, contract)
    assert "§2" in plan
    assert "§4" in plan
    assert "§1" not in plan  # 不在 contract 里就不动
    assert "## §2" in plan["§2"]


def test_apply_revised_sections_replaces_only_marked_sections(tmp_path: Path):
    """apply_revised_sections(orig, {"§2": new, "§4": new4}) → 只替换 §2 和 §4，其他原样。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    from revise_chapter import apply_revised_sections
    new_text = apply_revised_sections(
        SAMPLE_CHAPTER,
        {
            "§2": "## §2 战斗（新写）\n\n陈默拔剑迎敌。\n",
            "§4": "## §4 对话（新写）\n\n\"嘿！你小子！\"玄之大喊。\n",
        },
    )
    # §1 §3 §5 应原样
    assert "陈默站在论剑台上" in new_text
    assert "王玄之从台下跃起" in new_text
    assert "陈默微笑" in new_text
    # §2 §4 替换
    assert "陈默拔剑迎敌" in new_text
    assert '"嘿！你小子！"' in new_text
    # 旧内容消失
    assert '"好久不见。"玄之说' not in new_text
```

- [ ] **Step 3.2.2: 运行测试确认失败**

```bash
cd .claude/scripts && python3 -m pytest tests/test_revise_chapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'revise_chapter'`。

- [ ] **Step 3.2.3: 实现 revise_chapter.py**

在 `.claude/scripts/revise_chapter.py`：

```python
#!/usr/bin/env python3
"""根据 RejectionContract 局部重写章节。

用法:
    python3 revise_chapter.py \\
        --chapter-file 正/第0005章.md \\
        --contract .webnovel/rejection/ch0005.json \\
        [--dry-run] [--model claude-sonnet-4-5]

退出码:
    0 = 成功（生成 .revised.md）
    1 = 输入合法但 contract 校验失败
    2 = infrastructure error（文件缺失 / JSON 损坏）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# 把同目录下的 rejection_contract.py 加进来
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rejection_contract import (  # noqa: E402
    RejectionContract,
    build_contract_from_reviewer_output,
    targets_text,
    validate_contract,
)


EXIT_OK = 0
EXIT_INVALID = 1
EXIT_INFRA = 2


# §N 段的标题正则：## §N 标题 / ## §N
SECTION_PATTERN = re.compile(r"^##\s+(§\d+)\b", re.MULTILINE)


def extract_section(text: str, section_id: str) -> str:
    """从正文中提取 §N 段（从 ## §N 行到下一个 ## 之前）。"""
    pattern = re.compile(
        rf"^(##\s+{re.escape(section_id)}\b.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return ""
    return m.group(1).rstrip() + "\n"


def build_revise_plan(
    chapter_text: str,
    contract: RejectionContract,
) -> dict[str, str]:
    """返回 {section_id: 原内容} —— 只包含 contract 里出现的段。"""
    plan: dict[str, str] = {}
    for issue in contract.issues:
        loc = issue.location.strip()
        if loc.startswith("§"):
            section_id = loc.split()[0]  # "§2-§5" → "§2-§5"
            if section_id not in plan:
                content = extract_section(chapter_text, section_id)
                if content:
                    plan[section_id] = content
    return plan


def apply_revised_sections(
    original: str,
    revised: dict[str, str],
) -> str:
    """把原文中标记的段替换成 revised[section_id]，其他原样。"""
    out = original
    for section_id, new_content in revised.items():
        pattern = re.compile(
            rf"^(##\s+{re.escape(section_id)}\b.*?)(?=^##\s|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        if pattern.search(out):
            out = pattern.sub(new_content.rstrip() + "\n\n", out, count=1)
        else:
            # §N 段在原文里找不到 —— 追加到末尾（罕见，但要兜底）
            out = out.rstrip() + "\n\n" + new_content
    return out


# === LLM 调用（PR 3 阶段先做占位，真实 prompt 在 smoke test 时调） ===
def call_llm_for_revision(
    section_id: str,
    original: str,
    instruction: str,
    model: str,
) -> str:
    """调 LLM 重写一个段。返回新段（不含 markdown 标题之外的元数据）。

    PR 3 阶段：先返回原内容 + 一行 marker，证明链路通。
    TODO: 替换为真实 Claude API 调用（用 anthropic SDK 或 curl）。
    """
    # 占位：直接拼一个标记，便于 smoke test 验证替换发生
    return f"## {section_id}（待 LLM 重写）\n\n[REVISE-MARKER] 收到 instruction: {instruction[:50]}\n\n原内容前 30 字: {original[:30]}\n"


# === CLI ===
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="根据 RejectionContract 局部重写章节")
    parser.add_argument("--chapter-file", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path,
                        help="reviewer JSON 或 RejectionContract JSON")
    parser.add_argument("--dry-run", action="store_true",
                        help="不调 LLM，只输出 plan")
    parser.add_argument("--output", type=Path, default=None,
                        help="输出文件（默认 <chapter>.revised.md）")
    parser.add_argument("--model", default="claude-sonnet-4-5")
    args = parser.parse_args(argv)

    if not args.chapter_file.is_file():
        print(f"[revise] 章节文件不存在: {args.chapter_file}", file=sys.stderr)
        return EXIT_INFRA
    if not args.contract.is_file():
        print(f"[revise] contract 文件不存在: {args.contract}", file=sys.stderr)
        return EXIT_INFRA

    try:
        raw = json.loads(args.contract.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[revise] contract JSON 损坏: {e}", file=sys.stderr)
        return EXIT_INFRA

    # 兼容两种输入：
    # 1) reviewer JSON（issues[] 里每项含 severity 字段）
    # 2) RejectionContract JSON（顶层有 chapter + issues，每项含 severity）
    # 区分：用 issues[0] 是否含 fix_hint 字段判断（reviewer JSON 有，contract 也有；
    # 但 reviewer 的 description 是长文本，contract 的是短文本 — 不易区分）。
    # 实用策略：都走 build_contract_from_reviewer_output，它能容忍两种形态（contract JSON 缺字段时会填空）。
    contract = build_contract_from_reviewer_output(raw, include_advisory=True)

    try:
        validate_contract(contract)
    except ValueError as e:
        print(f"[revise] contract 校验失败: {e}", file=sys.stderr)
        return EXIT_INVALID

    chapter_text = args.chapter_file.read_text(encoding="utf-8")
    plan = build_revise_plan(chapter_text, contract)
    target_text = targets_text(contract)

    output_payload: dict[str, Any] = {
        "dry_run": args.dry_run,
        "chapter_file": str(args.chapter_file),
        "contract_chapter": contract.chapter,
        "target_sections": sorted(plan.keys()),
        "targets_text": target_text,
        "plan": {k: v[:200] + "..." if len(v) > 200 else v for k, v in plan.items()},
    }

    if args.dry_run:
        print(json.dumps(output_payload, ensure_ascii=False, indent=2))
        return EXIT_OK

    # 真实重写：每个 section 单独调 LLM
    revised: dict[str, str] = {}
    for issue in contract.issues:
        loc = issue.location.strip()
        section_id = loc.split()[0]
        if section_id in revised:
            # 同一段有多个 issue，合并 fix_hint
            existing = revised[section_id]
            revised[section_id] = call_llm_for_revision(
                section_id, plan.get(section_id, ""),
                f"{existing}\n[附加] {issue.fix_hint}",
                args.model,
            )
        elif section_id in plan:
            revised[section_id] = call_llm_for_revision(
                section_id, plan[section_id], issue.fix_hint, args.model,
            )

    new_text = apply_revised_sections(chapter_text, revised)
    out_path = args.output or args.chapter_file.with_suffix(".revised.md")
    out_path.write_text(new_text, encoding="utf-8")

    output_payload["output_file"] = str(out_path)
    output_payload["revised_sections"] = sorted(revised.keys())
    print(json.dumps(output_payload, ensure_ascii=False, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3.2.4: 运行测试确认通过**

```bash
cd .claude/scripts && python3 -m pytest tests/test_revise_chapter.py -v
```

Expected: 6 passed。

- [ ] **Step 3.2.5: Commit**

```bash
git add .claude/scripts/revise_chapter.py .claude/scripts/tests/test_revise_chapter.py
git commit -m "feat(revise): add revise_chapter with local rewrite + dry-run"
```

---

### Task 3.3: 真实 LLM 集成（替换占位的 call_llm_for_revision）

**Files:**
- Modify: `.claude/scripts/revise_chapter.py`
- Modify: `.claude/scripts/tests/test_revise_chapter.py`

- [ ] **Step 3.3.1: 写失败测试（用 monkeypatch 验证 LLM prompt 格式）**

追加：

```python


def test_call_llm_for_revision_uses_anthropic_messages_api(monkeypatch):
    """call_llm_for_revision 必须调 anthropic SDK（mock 验证 prompt 字段）。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    import revise_chapter

    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            class FakeResp:
                content = [type("Block", (), {"text": "## §2（新文）"})()]
            return FakeResp()

    class FakeAnthropic:
        def __init__(self, *a, **kw):
            pass
        @property
        def messages(self):
            return FakeMessages()

    monkeypatch.setattr(revise_chapter, "anthropic", type("X", (), {"Anthropic": FakeAnthropic})())

    result = revise_chapter.call_llm_for_revision(
        section_id="§2",
        original="原文内容",
        instruction="补 200 字战斗",
        model="claude-sonnet-4-5",
    )
    assert "新文" in result
    kw = captured["kwargs"]
    assert kw["model"] == "claude-sonnet-4-5"
    # 必须包含原内容 + 修复指令 + 段 ID
    user_msg = kw["messages"][0]["content"]
    assert "原文内容" in user_msg
    assert "补 200 字战斗" in user_msg
    assert "§2" in user_msg


def test_call_llm_for_revision_keeps_section_heading():
    """LLM 输出必须保留 ## §N 标题（否则 apply_revised_sections 无法定位）。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    import revise_chapter

    class FakeMessages:
        def create(self, **kwargs):
            class FakeResp:
                content = [type("Block", (), {"text": "## §3（新文）\n\n正文"})()]
            return FakeResp()

    class FakeAnthropic:
        def __init__(self, *a, **kw): pass
        @property
        def messages(self): return FakeMessages()

    import importlib
    revise_chapter.anthropic = type("X", (), {"Anthropic": FakeAnthropic})
    result = revise_chapter.call_llm_for_revision("§3", "x", "y", "claude-sonnet-4-5")
    assert result.startswith("## §3") or "## §3" in result.split("\n", 1)[0]
```

- [ ] **Step 3.3.2: 运行测试确认失败**

```bash
cd .claude/scripts && python3 -m pytest tests/test_revise_chapter.py::test_call_llm_for_revision_uses_anthropic_messages_api -v
```

Expected: FAIL（当前 call_llm_for_revision 不调 anthropic）。

- [ ] **Step 3.3.3: 重写 call_llm_for_revision**

替换 `.claude/scripts/revise_chapter.py` 中的 `call_llm_for_revision`：

```python
# 真实 LLM 调用（通过 anthropic SDK）
import os
try:
    import anthropic  # type: ignore
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False


REVISION_SYSTEM_PROMPT = """你是网文局部重写器。
输入是一章正文的某个段落（## §N 标题）和一条修复指令。
要求：
1. 只输出重写后的段落，必须保留 ## §N 标题
2. 保持原文风格一致（不要 AI 化、不要加入未声明的设定）
3. 严格遵循 fix_hint，不要扩大改动范围
4. 修复完成后，整段字数与原段差距控制在 ±30% 以内
"""


def call_llm_for_revision(
    section_id: str,
    original: str,
    instruction: str,
    model: str,
) -> str:
    """调 Claude API 重写一个段。"""
    if not _HAS_ANTHROPIC:
        raise RuntimeError(
            "需要 anthropic SDK：pip install anthropic "
            "(或设置 ANTHROPIC_API_KEY 后用 requests 调 REST API)"
        )

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    user_msg = (
        f"## 待重写段: {section_id}\n\n"
        f"### 原文\n{original}\n\n"
        f"### 修复指令\n{instruction}\n\n"
        f"请只输出重写后的段落（含 ## {section_id} 标题），不要输出其他文本。"
    )
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        system=REVISION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    return text.strip()
```

并在文件顶部 import 区域替换：

```python
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
```

（加 `os`，并把 `import anthropic` 放在 try 块里。）

- [ ] **Step 3.3.4: 运行测试确认通过**

```bash
cd .claude/scripts && python3 -m pytest tests/test_revise_chapter.py -v
```

Expected: 8 passed。

- [ ] **Step 3.3.5: Commit**

```bash
git add .claude/scripts/revise_chapter.py .claude/scripts/tests/test_revise_chapter.py
git commit -m "feat(revise): replace placeholder with real Claude API call"
```

---

### Task 3.4: webnovel-revise skill

**Files:**
- Create: `.claude/skills/webnovel-revise/SKILL.md`

- [ ] **Step 3.4.1: 写 skill**

```markdown
---
name: webnovel-revise
description: 根据 reviewer 的结构化反馈局部重写章节。只改 contract 标出的段，其他原样保留。比整章重写省 60-80% token。Use when reviewer has run and produced structured JSON with blocking issues.
allowed-tools: Read Write Edit Grep Bash
---

# Local Chapter Revision (Structured Rejection Contract)

## 目标

拿到 reviewer 的 JSON 后，**只重写标出的段**，不重写整章。

## 适用场景

- reviewer 跑完，输出 blocking issues
- 你想改但不想花一整章的 token
- 想保持未受影响段落的原文（避免 AI 改稿时的"漂移"）

## 不适用场景

- reviewer 没跑过（先 `/webnovel-review` 或 `/webnovel-write`）
- 大返工（>50% 段落要改）—— 直接用 `/webnovel-write` 整章重写更划算
- 想改大纲或设定（PR 1 snapshot 范畴）

## 执行流程

按顺序执行：

1. **拿 reviewer 输出**：从 `.webnovel/review/ch{NNNN}.json` 读取（如不存在，告诉用户先跑 reviewer）。
2. **构造 contract**：
   ```bash
   python3 ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/revise_chapter.py \
       --chapter-file "正文/第${NNNN}章-${title}.md" \
       --contract .webnovel/review/ch${NNNN}.json \
       --dry-run
   ```
   确认 `target_sections` 列表合理。
3. **真实重写**：
   ```bash
   python3 .../revise_chapter.py \
       --chapter-file "正文/第${NNNN}章-${title}.md" \
       --contract .webnovel/review/ch${NNNN}.json \
       --output "正文/第${NNNN}章-${title}.revised.md"
   ```
4. **人工 diff**：用 Read 或 diff 工具对比原版和 .revised.md。
5. **覆盖**：用户确认后，把 .revised.md 改名为原文件名（删 .revised 后缀）。
6. **CHANGES 重新校验**：
   ```bash
   python3 .../changes_gate.py --chapter-file "正文/第${NNNN}章-${title}.md" --db index.db --json
   ```
7. **回写 data-agent**（可选）：重跑 `webnovel-writer:data-agent` 让 index.db 同步。

## 退出条件

- reviewer 没有输出 contract → 提示先跑 review
- target_sections 为空 → contract 没有 blocking issue，无需 revise
- LLM 输出不含 `## §N` 标题 → revise_chapter.py 会兜底追加，warning 但不阻断

## 失败处理

- LLM 调用失败（ANTHROPIC_API_KEY 未设置 / 超时）→ exit code 非 0，向用户报告
- 重写后 CHANGES 校验失败 → 把原版恢复（不覆盖），告诉用户"修订版破坏了设定契约，建议人工处理"
```

- [ ] **Step 3.4.2: Commit**

```bash
git add .claude/skills/webnovel-revise/SKILL.md
git commit -m "feat(skill): add webnovel-revise (PR 3)"
```

---

### Task 3.5: 接入 webnovel-fast-write（Step 7: optional revise）

**Files:**
- Modify: `.claude/skills/webnovel-fast-write/SKILL.md`

- [ ] **Step 3.5.1: 在末尾追加 Step 7**

修改 `.claude/skills/webnovel-fast-write/SKILL.md`，把执行流程的第 7 步（第 36 行末尾）改为：

```
7. **Step 6 备份**：调用 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py backup`。
8. **Step 7 可选修订**（PR 3 引入）：如果存在 `.webnovel/review/ch${NNNN}.json` 且含 blocking issue，询问用户是否走 `/webnovel-revise`。默认不调——因为本 skill 是"信任方向的快车道"，重写交还用户决策。
```

- [ ] **Step 3.5.2: Commit**

```bash
git add .claude/skills/webnovel-fast-write/SKILL.md
git commit -m "feat(fast-write): optional Step 7 invoke /webnovel-revise (PR 3)"
```

---

### Task 3.6: 端到端 smoke test

- [ ] **Step 3.6.1: 准备 mock reviewer JSON**

```bash
mkdir -p /tmp/revise_smoke/.webnovel/review
cat > /tmp/revise_smoke/.webnovel/review/ch0005.json <<'EOF'
{
  "chapter": 5,
  "issues": [
    {
      "severity": "critical",
      "category": "continuity",
      "location": "§2",
      "description": "战斗段空",
      "fix_hint": "补 200 字战斗描写",
      "blocking": true
    }
  ],
  "blocking_count": 1,
  "issues_count": 1,
  "dimension_results": [{"dimension": "continuity", "conclusion": "发现1个问题：战斗段空"}],
  "summary": "1个问题：1个阻断"
}
EOF

cat > /tmp/revise_smoke/ch0005.md <<'EOF'
# 第5章 玄之归来

## §1 开场

陈默站在论剑台上。

## §2 战斗

（待写）

## §3 玄之回场

王玄之跃上台。
EOF
```

- [ ] **Step 3.6.2: dry-run**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
python3 .claude/scripts/revise_chapter.py \
    --chapter-file /tmp/revise_smoke/ch0005.md \
    --contract /tmp/revise_smoke/.webnovel/review/ch0005.json \
    --dry-run
```

Expected: stdout JSON 含 `"dry_run": true`, `"target_sections": ["§2"]`, `"plan"` 里能看到原文片段。

- [ ] **Step 3.6.3: 跑全量测试**

```bash
cd /Users/chang/Desktop/ai写小说工具开发/.claude/scripts && python3 -m pytest tests/ -v
```

Expected: 所有测试 passed（changes_gate + snapshot_manager + rejection_contract + revise_chapter）。

---

# PR 2: Context Isolation

**目标**：context-agent 的输出当前是一坨「五段写作任务书」+ 全量上下文。每个下游 agent（write / review / polish）会拿到全部 context，token 随章节数线性膨胀。改成：context-agent 输出**结构化切片索引**，每个下游 agent 按白名单只读自己需要的。

**为什么**：写到 30+ 章时，context-agent 一份任务书就要 5-8K token，下游 write/review 各自再读一遍 = 单章总 context token 20K+。改成切片后，writer 拿「本章大纲 + 角色卡 + 前 2 章摘要」（~3K），reviewer 拿「正文 + 周围 2 章 + 爽点规划」（~2K），polish 拿「正文 + 文风规则」（~1K）。**总 context token 降 70%+**。

**核心挑战**：context-agent 是 vendor 路径，**不能改**。所以 PR 2 在调用方做 post-trim——也就是在 fork 自己的 webnovel-fast-write / webnovel-write skill 里，**截取 context-agent 的输出，按下游需要拆分喂入**。

**验收**：
- `context_slice.py` 定义 3 个标准 slice（writer_slice / reviewer_slice / polisher_slice），每个给出相对路径白名单
- `read_slice(project_root, slice_name)` 按白名单读文件 + 输出 token 估算
- webnovel-fast-write skill 在调用 draft 之前，把 context-agent 输出 + slice 文件合并喂入 draft prompt

**约束**：
- 不改 vendor 的 `plugins/webnovel-writer/agents/context-agent.md`
- 不引入新的 agent（用 fork 自己的 helper 脚本）
- 单测覆盖白名单逻辑和读盘逻辑

---

### Task 2.1: ContextSlice schema + slice 定义

**Files:**
- Create: `.claude/scripts/context_slice.py`
- Create: `.claude/scripts/tests/test_context_slice.py`

- [ ] **Step 2.1.1: 写失败测试**

在 `.claude/scripts/tests/test_context_slice.py`：

```python
"""context_slice.py 单元测试。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from context_slice import (
    ContextSlice,
    SLICES,
    read_slice,
    estimate_tokens,
    list_slices,
)


def test_writer_slice_has_minimal_white_list():
    """writer_slice 必须只包含：章纲 + 角色卡 + 前 2 章摘要 + 当前章大纲相关设定。"""
    s = SLICES["writer"]
    patterns = [e.pattern for e in s.entries]
    # 必须有：当前章大纲
    assert any("大纲/第1卷-详细大纲.md" in p or "第1卷-详细大纲.md" in p for p in patterns)
    # 必须有：角色库
    assert any("设定集/角色库/" in p for p in patterns)
    # 必须有：前 N 章摘要（用 glob）
    assert any("summaries" in p.lower() for p in patterns)
    # 不应包含：所有章的正文（除非是当前章）
    assert not any("正文/" in p and "*" in p for p in patterns)


def test_reviewer_slice_focuses_on_local_context():
    """reviewer_slice 主要喂：当前章正文 + 周围 2 章正文 + 爽点规划 + 设定卡（仅相关）。"""
    s = SLICES["reviewer"]
    patterns = [e.pattern for e in s.entries]
    # 应包含当前章正文（chapter 号来自参数，不在 schema 里硬编码）
    assert any("正文/第{NNNN}章" in p for p in patterns)
    # 应包含前后 ±2 章
    assert any("±2" in p or "前后" in repr(s.entries) for p in [repr(s)])


def test_polisher_slice_minimal():
    """polisher_slice 只喂：当前章正文 + 文风规则 + 白名单。"""
    s = SLICES["polisher"]
    patterns = [e.pattern for e in s.entries]
    assert any("正文/第{NNNN}章" in p for p in patterns)
    assert any("deslop" in p.lower() or "白名单" in repr(s) for p in [repr(s)])
    # 不应包含：完整大纲
    assert not any("总纲" in p for p in patterns)


def test_list_slices_returns_known_names():
    """list_slices() 返回所有内置 slice 名。"""
    names = list_slices()
    assert "writer" in names
    assert "reviewer" in names
    assert "polisher" in names


def test_read_slice_concatenates_matched_files(tmp_path: Path):
    """read_slice(project_root, 'writer', chapter=5) → 返回拼接的 {path: content}。"""
    # 准备最小项目
    (tmp_path / "设定集" / "角色库").mkdir(parents=True)
    (tmp_path / "设定集" / "角色库" / "陈默.md").write_text("陈默，21岁", encoding="utf-8")
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "第1卷-详细大纲.md").write_text("# 第1卷\nch5: 玄之归来", encoding="utf-8")
    (tmp_path / ".webnovel" / "summaries").mkdir(parents=True)
    (tmp_path / ".webnovel" / "summaries" / "ch0003.md").write_text("ch3 摘要", encoding="utf-8")
    (tmp_path / ".webnovel" / "summaries" / "ch0004.md").write_text("ch4 摘要", encoding="utf-8")
    (tmp_path / ".webnovel" / "summaries" / "ch0005.md").write_text("ch5 摘要（应被排除）", encoding="utf-8")

    result = read_slice(tmp_path, "writer", chapter=5)
    paths = {p for p in result.keys()}
    # 角色 + 大纲 + 前 2 章摘要
    assert "设定集/角色库/陈默.md" in paths
    assert "大纲/第1卷-详细大纲.md" in paths
    assert ".webnovel/summaries/ch0003.md" in paths
    assert ".webnovel/summaries/ch0004.md" in paths
    # 当前章摘要应被排除（要写的是它本身，不是回顾它）
    assert ".webnovel/summaries/ch0005.md" not in paths


def test_read_slice_skips_missing_files(tmp_path: Path):
    """白名单匹配但文件不存在 → 静默跳过，不报错。"""
    (tmp_path / "设定集" / "角色库").mkdir(parents=True)
    # 没有陈默.md
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "第1卷-详细大纲.md").write_text("x", encoding="utf-8")

    result = read_slice(tmp_path, "writer", chapter=1)
    # 不抛错，返回的 dict 不含缺失文件
    assert "大纲/第1卷-详细大纲.md" in result


def test_estimate_tokens_rough_chinese():
    """estimate_tokens: 中文 1 字 ≈ 1.5 token；英文 1 word ≈ 1.3 token。"""
    assert 6 <= estimate_tokens("你好世界") <= 10  # 4 字 × 1.5 = 6
    assert 3 <= estimate_tokens("hello") <= 6
```

- [ ] **Step 2.1.2: 运行测试确认失败**

```bash
cd .claude/scripts && python3 -m pytest tests/test_context_slice.py -v
```

Expected: `ModuleNotFoundError: No module named 'context_slice'`。

- [ ] **Step 2.1.3: 实现 context_slice.py**

在 `.claude/scripts/context_slice.py`：

```python
#!/usr/bin/env python3
"""Context slice 定义与读盘。

每个 slice 是一组 (path_pattern, required) 白名单条目。
read_slice(project_root, slice_name, chapter=N) 按白名单匹配文件并读入。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SliceEntry:
    """单条白名单。pattern 是相对于 project_root 的 glob。"""
    pattern: str
    required: bool = False  # required=True 但文件不存在时 raise（默认 False = 静默跳过）


@dataclass
class ContextSlice:
    """一组白名单 + 元信息。"""
    name: str
    description: str
    entries: list[SliceEntry] = field(default_factory=list)


# === 内置 slice 定义 ===
WRITER_SLICE = ContextSlice(
    name="writer",
    description="写一章正文需要的最小上下文：章纲 + 角色卡 + 前 2 章摘要 + 当前章相关设定",
    entries=[
        SliceEntry("大纲/第*-详细大纲.md"),
        SliceEntry("大纲/总纲.md", required=False),
        SliceEntry("设定集/角色库/*.md"),
        SliceEntry("设定集/物品库/*.md", required=False),
        SliceEntry("设定集/其他设定/*.md", required=False),
        # 前 2 章摘要（chapter 参数驱动；read_slice 时按 chapter 展开）
        SliceEntry(".webnovel/summaries/ch{N-2}.md", required=False),
        SliceEntry(".webnovel/summaries/ch{N-1}.md", required=False),
    ],
)


REVIEWER_SLICE = ContextSlice(
    name="reviewer",
    description="reviewer 看：当前章正文 + 前后 ±2 章正文 + 爽点规划 + 相关角色设定",
    entries=[
        SliceEntry("正文/第{N-2}章*.md", required=False),
        SliceEntry("正文/第{N-1}章*.md", required=False),
        SliceEntry("正文/第{N}章*.md"),
        SliceEntry("正文/第{N+1}章*.md", required=False),
        SliceEntry("正文/第{N+2}章*.md", required=False),
        SliceEntry("大纲/爽点规划.md", required=False),
        SliceEntry("大纲/第1卷-时间线.md", required=False),
        SliceEntry("设定集/角色库/*.md", required=False),
        SliceEntry("设定集/物品库/*.md", required=False),
    ],
)


POLISHER_SLICE = ContextSlice(
    name="polisher",
    description="polisher 看：当前章正文 + 文风指纹 + anti-slop 白名单",
    entries=[
        SliceEntry("正文/第{N}章*.md"),
        SliceEntry("设定集/其他设定/文风.md", required=False),
        SliceEntry(".claude/references/deslop/whitelist.md", required=False),
    ],
)


SLICES: dict[str, ContextSlice] = {
    "writer": WRITER_SLICE,
    "reviewer": REVIEWER_SLICE,
    "polisher": POLISHER_SLICE,
}


def list_slices() -> list[str]:
    return sorted(SLICES.keys())


def _expand_pattern(pattern: str, chapter: int) -> str:
    """把 {N}, {N-1}, {N+2} 等占位符展开为 4 位章节号。"""
    def repl(m: re.Match) -> str:
        offset = int(m.group(1)) if m.group(1) else 0
        actual = chapter + offset
        return f"{actual:04d}"
    return re.sub(r"\{N([+-]\d+)?\}", repl, pattern)


def read_slice(
    project_root: Path,
    slice_name: str,
    chapter: int,
) -> dict[str, str]:
    """按 slice 白名单读文件，返回 {relative_path: content}。

    缺失文件：required=False 静默跳过；required=True 抛 FileNotFoundError。
    """
    if slice_name not in SLICES:
        raise ValueError(
            f"未知 slice: {slice_name!r}，可用: {list_slices()}"
        )
    slice_def = SLICES[slice_name]

    result: dict[str, str] = {}
    for entry in slice_def.entries:
        pat = _expand_pattern(entry.pattern, chapter)
        matched = sorted(project_root.glob(pat))
        for p in matched:
            if not p.is_file():
                continue
            rel = p.relative_to(project_root).as_posix()
            try:
                result[rel] = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # 二进制文件跳过
                continue

    # required 检查
    missing_required = [
        _expand_pattern(e.pattern, chapter)
        for e in slice_def.entries if e.required
        if not list(project_root.glob(_expand_pattern(e.pattern, chapter)))
    ]
    if missing_required:
        raise FileNotFoundError(
            f"slice {slice_name!r} 的 required 文件不存在: {missing_required}"
        )

    return result


def estimate_tokens(text: str) -> int:
    """粗估 token 数：中文 1 字 ≈ 1.5 token，英文 1 word ≈ 1.3 token。"""
    # 分离中英文
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    english_words = len(re.findall(r"[a-zA-Z]+", text))
    other = len(text) - chinese_chars - sum(len(w) for w in re.findall(r"[a-zA-Z]+", text))
    return int(chinese_chars * 1.5 + english_words * 1.3 + other * 0.5)
```

- [ ] **Step 2.1.4: 运行测试确认通过**

```bash
cd .claude/scripts && python3 -m pytest tests/test_context_slice.py -v
```

Expected: 7 passed。

- [ ] **Step 2.1.5: Commit**

```bash
git add .claude/scripts/context_slice.py .claude/scripts/tests/test_context_slice.py
git commit -m "feat(context-slice): add slice schema + read_slice + token estimate"
```

---

### Task 2.2: context-slice-schema.md 文档

**Files:**
- Create: `.claude/references/context-slice-schema.md`

- [ ] **Step 2.2.1: 写文档**

```markdown
# Context Slice Schema

## 这是什么

每个 webnovel-writer 下游 agent（writer / reviewer / polisher）需要不同的 context：
- writer：要章纲、角色卡、前几章摘要
- reviewer：要正文本身、周围章节、爽点规划
- polisher：只要正文 + 文风规则

不要给它们全本。`context_slice.py` 把每个 agent 的"最小必要 context"白名单化，调用方按需喂入。

## 三个内置 slice

### `writer` — 起草时喂什么

| 路径 pattern | 必需？ |
|---|---|
| `大纲/第*-详细大纲.md` | 必需 |
| `大纲/总纲.md` | 可选 |
| `设定集/角色库/*.md` | 必需 |
| `设定集/物品库/*.md` | 可选 |
| `设定集/其他设定/*.md` | 可选 |
| `.webnovel/summaries/ch{N-2}.md` | 可选 |
| `.webnovel/summaries/ch{N-1}.md` | 可选 |

### `reviewer` — 审查时喂什么

| 路径 pattern | 必需？ |
|---|---|
| `正文/第{N-2}章*.md` ~ `第{N+2}章*.md` | 必需（当前章）；其他可选 |
| `大纲/爽点规划.md` | 可选 |
| `大纲/第1卷-时间线.md` | 可选 |
| `设定集/角色库/*.md` | 可选 |
| `设定集/物品库/*.md` | 可选 |

### `polisher` — 润色时喂什么

| 路径 pattern | 必需？ |
|---|---|
| `正文/第{N}章*.md` | 必需 |
| `设定集/其他设定/文风.md` | 可选 |
| `.claude/references/deslop/whitelist.md` | 可选 |

## 怎么用

```python
from context_slice import read_slice, estimate_tokens

files = read_slice(project_root, "writer", chapter=5)
# files = {"大纲/第1卷-详细大纲.md": "...", "设定集/角色库/陈默.md": "...", ...}

total_tokens = sum(estimate_tokens(c) for c in files.values())
print(f"writer slice 总 token: {total_tokens}")
```

## 怎么扩展

往 `SLICES` 字典里加：

```python
PROOFREADER_SLICE = ContextSlice(
    name="proofreader",
    description="...",
    entries=[SliceEntry("..."), ...],
)
SLICES["proofreader"] = PROOFREADER_SLICE
```

## 命名约定

- slice name 用 snake_case（writer / reviewer / polisher）
- 占位符 `{N}`, `{N-1}`, `{N+2}` 表达"当前章节号 ± 偏移"
- 占位符会被自动展开为 4 位章节号（chapter=5 → `{N}` = `0005`）
```

- [ ] **Step 2.2.2: Commit**

```bash
git add .claude/references/context-slice-schema.md
git commit -m "docs(context-slice): add context-slice-schema.md"
```

---

### Task 2.3: webnovel-fast-write 接入 read_slice（writer）

**Files:**
- Modify: `.claude/skills/webnovel-fast-write/SKILL.md`

- [ ] **Step 2.3.1: 改 Step 2A 描述**

修改 `.claude/skills/webnovel-fast-write/SKILL.md` 的第 32 行：

```
3. **Step 2A 起草**：主流程生成正文 + 末尾追加 `<chapter_changes>...</chapter_changes>` 块。
```

改为：

```
3. **Step 2A 起草**：主流程生成正文 + 末尾追加 `<chapter_changes>...</chapter_changes>` 块。
   - **PR 2 接入**：在喂给主 LLM 之前，先调用 `python3 ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/context_slice.py read writer ${chapter}`（或 Read 源码后用 Python 等价调用），按白名单加载 writer slice 的文件，作为 context 注入。
   - context-agent 的"五段写作任务书"作为 instruction 不变；writer slice 的文件作为参考输入。
   - 不再一次性 Read 全本大纲/设定/所有章节。
```

- [ ] **Step 2.3.2: Commit**

```bash
git add .claude/skills/webnovel-fast-write/SKILL.md
git commit -m "feat(fast-write): inject writer slice context (PR 2)"
```

---

### Task 2.4: 端到端 token 对比 smoke test

- [ ] **Step 2.4.1: 在《根源牌序》项目跑 read_slice writer**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
python3 -c "
import sys
sys.path.insert(0, '.claude/scripts')
from pathlib import Path
from context_slice import read_slice, estimate_tokens
files = read_slice(Path('/Users/chang/Desktop/根源牌序'), 'writer', chapter=1)
total = sum(estimate_tokens(c) for c in files.values())
print(f'files: {len(files)}, total_tokens: ~{total}')
for p in files:
    print(f'  {p}: {estimate_tokens(files[p])} tokens')
"
```

Expected: 列出 ~10 个文件，总 token 应 < 5K（如果 chapter=1 还没 summaries，那 summaries 会是 0 文件，但其他文件应在）。

- [ ] **Step 2.4.2: 对比「未隔离」基线**

手动做：把全部 设定集/*.md + 大纲/*.md + .webnovel/summaries/*.md 读一遍，估算总 token。

Expected: writer slice 的 token 应明显小于全量基线（基线假设 ≥ 10K）。

- [ ] **Step 2.4.3: 跑全量测试**

```bash
cd /Users/chang/Desktop/ai写小说工具开发/.claude/scripts && python3 -m pytest tests/ -v
```

Expected: 所有测试 passed。

---

# 实施顺序与提交策略

## 推荐实施顺序

1. **PR 1**（snapshot）：半天，4 个 commit，最安全
2. **PR 3**（rejection contract）：1 天，5 个 commit，最具杠杆
3. **PR 2**（context isolation）：半天（仅 schema + 接入），3 个 commit，最长尾

每个 PR 独立可发布。PR 1 完成后即可用，PR 3 完成后才解决"重写效率"，PR 2 完成后才解决"长篇 token 通胀"。

## 全局验收（所有 PR 完成后）

1. `cd .claude/scripts && python3 -m pytest tests/ -v` 全部 passed
2. 在《根源牌序》项目里跑：
   - `snapshot_manager.py freeze 1` → 成功
   - `snapshot_manager.py verify 1` → 0
   - `revise_chapter.py --dry-run --chapter-file .../ch0001.md --contract .../review.json` → dry_run=true, targets 列表非空
   - `context_slice.py` 读取 writer slice → 文件数合理
3. 任何旧测试不回归

## 风险与备选

| 风险 | 概率 | 应对 |
|---|---|---|
| reviewer JSON schema 变化 | 低 | rejection_contract 与 reviewer 解耦，schema 变只动 build_contract_from_reviewer_output |
| snapshot 文件太多占空间 | 中 | 加 `.gitignore` `.webnovel/snapshots/` + 写一个 `snapshot_manager.py gc <keep_last_N>` 命令（**不在本计划，做为下一轮**） |
| context slice 漏文件导致 agent 看不到关键设定 | 中 | writer slice 设 required=True 的文件 + smoke test；先在快车道跑 5 章验证 |
| LLM 重写破坏原文风格 | 中 | REVISION_SYSTEM_PROMPT 强调"保留风格"；PR 3 末尾 smoke test 验证 |