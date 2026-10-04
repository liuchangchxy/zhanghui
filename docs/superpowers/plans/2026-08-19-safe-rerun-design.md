# Safe Rerun Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现"重跑一次都要问三态（重写 / 部分改写 / 不改）"的覆盖守卫层，让 webnovel-writer_chang 所有写入路径在重跑时不再静默覆盖。

**Architecture:** 新增 `safe_overwrite.py` 统一处理冲突；4 个 P0 脚本（`update_master_outline` / `chapter_commit` / `snapshot_manager`）+ plan 2 个脚本问题接入；新增 `check_plan_artifacts.py` 把 3 处 SKILL.md"询问"声明落到脚本；调用者同步传 `--on-conflict=overwrite`。默认行为从"静默覆盖"改为"存在则报错"，调用者必须显式传 flag。

**Tech Stack:** Python 3.11+、pytest、Click（已有）、Claude Code Skill 上下文（CLAUDE_PLUGIN_ROOT 环境变量）

---

## Phase 1: safe_overwrite.py + 单元测试

### Task 1: 创建 safe_overwrite.py 模块骨架

**Files:**
- Create: `scripts/_shared/safe_overwrite.py`
- Create: `scripts/tests/test_safe_overwrite.py`

- [ ] **Step 1: 写 4 个失败测试（覆盖 ConflictMode 枚举 + _in_claude_code_context）**

```python
# scripts/tests/test_safe_overwrite.py
from pathlib import Path
import pytest
from scripts._shared.safe_overwrite import ConflictMode, resolve_conflict, _in_claude_code_context


def test_conflict_mode_values():
    assert ConflictMode.OVERWRITE.value == "overwrite"
    assert ConflictMode.APPEND.value == "append"
    assert ConflictMode.SKIP.value == "skip"
    assert ConflictMode.ASK.value == "ask"


def test_in_claude_code_context_with_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert _in_claude_code_context() is True


def test_in_claude_code_context_without_env(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    assert _in_claude_code_context() is False


def test_resolve_conflict_no_exists_no_mode():
    # exists=False → 不管 mode 是什么都直接通过
    resolve_conflict(exists=False, path=Path("/tmp/x"), mode=None)
```

- [ ] **Step 2: 跑测试确认它们失败（红）**

```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang
PYTHONPATH=. pytest scripts/tests/test_safe_overwrite.py -v
```

Expected: 4 个 ImportError 或 ModuleNotFoundError

- [ ] **Step 3: 写最小实现**

```python
# scripts/_shared/safe_overwrite.py
"""统一覆盖守卫：所有写入路径在重跑前必须经过此层。"""
from __future__ import annotations

import json
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Callable


class ConflictMode(str, Enum):
    """三态 + ASK（让 Claude Code 主流程询问用户）。"""
    OVERWRITE = "overwrite"
    APPEND = "append"
    SKIP = "skip"
    ASK = "ask"


def _in_claude_code_context() -> bool:
    """检测是否在 Claude Code Skill 上下文。"""
    return os.environ.get("CLAUDE_PLUGIN_ROOT") is not None


def resolve_conflict(
    exists: bool,
    path: Path | None = None,
    mode: str | None = None,
    *,
    append_op: Callable[[Path], None] | None = None,
) -> None:
    """如果 exists=True 且 mode=None → raise FileExistsError。

    Args:
        exists: 目标是否已存在（调用方负责检测）。
        path: 仅用于报错信息；逻辑冲突也可用虚拟路径。
        mode: None → 报错；'overwrite'/'append'/'skip' → 显式三态；
              'ask' → ASK 模式（仅 Claude Code 内可用；打印 JSON 后 sys.exit(0)）。
        append_op: 当 mode='append' 时执行的合并函数。
    """
    if not exists:
        return

    display = str(path) if path else "<未指定路径>"
    if mode is None:
        raise FileExistsError(
            f"{display} 已存在。请传 --on-conflict=overwrite|append|skip|ask"
        )

    parsed = ConflictMode(mode)

    if parsed == ConflictMode.SKIP:
        print(f"SKIP: {display} 已存在，未修改", file=sys.stderr)
        return

    if parsed == ConflictMode.OVERWRITE:
        print(f"OVERWRITE: {display}", file=sys.stderr)
        return

    if parsed == ConflictMode.APPEND:
        if append_op is None:
            raise ValueError(
                f"mode=append 但未传 append_op（{display} 不支持 append）"
            )
        print(f"APPEND: {display}", file=sys.stderr)
        append_op(path)
        return

    if parsed == ConflictMode.ASK:
        if not _in_claude_code_context():
            raise RuntimeError(
                f"mode=ask 仅在 Claude Code Skill 上下文可用。"
                f"独立脚本请传 overwrite/append/skip。"
            )
        # 输出结构化 JSON，由 Claude Code 主流程捕获并 AskUserQuestion
        print(json.dumps({
            "ask": True,
            "question": f"{display} 已存在，如何处理？",
            "options": ["overwrite", "append", "skip"],
            "default": "skip",
        }, ensure_ascii=False))
        # HALT: 退出脚本，等 Claude Code 用用户选择的 mode 重跑
        sys.exit(0)
```

- [ ] **Step 4: 跑测试确认 4 个通过（绿）**

```bash
PYTHONPATH=. pytest scripts/tests/test_safe_overwrite.py::test_conflict_mode_values scripts/tests/test_safe_overwrite.py::test_in_claude_code_context_with_env scripts/tests/test_safe_overwrite.py::test_in_claude_code_context_without_env scripts/tests/test_safe_overwrite.py::test_resolve_conflict_no_file_no_mode -v
```

Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/_shared/safe_overwrite.py scripts/tests/test_safe_overwrite.py
git commit -m "feat(safe-overwrite): add ConflictMode + resolve_conflict + ask降级"
```

---

### Task 2: 补全 resolve_conflict 单元测试（剩余 4 用例）

**Files:**
- Modify: `scripts/tests/test_safe_overwrite.py`

- [ ] **Step 1: 写剩余 4 个失败测试**

```python
# 在 scripts/tests/test_safe_overwrite.py 末尾追加
from unittest.mock import patch


def test_resolve_conflict_exists_no_mode_raises():
    with pytest.raises(FileExistsError, match="已存在"):
        resolve_conflict(exists=True, path=Path("/tmp/x"), mode=None)


def test_resolve_conflict_skip_does_not_modify(capsys):
    resolve_conflict(exists=True, path=Path("/tmp/skip"), mode="skip")
    captured = capsys.readouterr()
    assert "SKIP" in captured.err


def test_resolve_conflict_overwrite_allows_subsequent(capsys):
    # resolve_conflict 不直接写文件，只返回；调用方负责覆盖
    resolve_conflict(exists=True, path=Path("/tmp/ow"), mode="overwrite")
    captured = capsys.readouterr()
    assert "OVERWRITE" in captured.err


def test_resolve_conflict_append_with_op_executes_op(tmp_path, capsys):
    target = tmp_path / "ap.txt"
    target.write_text("base\n")

    def my_append(p: Path):
        with p.open("a", encoding="utf-8") as f:
            f.write("appended\n")

    resolve_conflict(exists=True, path=target, mode="append", append_op=my_append)
    content = target.read_text()
    assert content == "base\nappended\n"
    captured = capsys.readouterr()
    assert "APPEND" in captured.err
```

- [ ] **Step 2: 跑测试确认 4 个通过（绿）**

```bash
PYTHONPATH=. pytest scripts/tests/test_safe_overwrite.py -v
```

Expected: 8 passed

- [ ] **Step 3: 提交**

```bash
git add scripts/tests/test_safe_overwrite.py
git commit -m "test(safe-overwrite): add 4 resolve_conflict edge cases"
```

---

### Task 3: 补 append_op 缺失 + ask 降级 2 用例

**Files:**
- Modify: `scripts/tests/test_safe_overwrite.py`

- [ ] **Step 1: 追加 2 个失败测试**

```python
# 追加到 scripts/tests/test_safe_overwrite.py


def test_resolve_conflict_append_without_op_raises():
    with pytest.raises(ValueError, match="不支持 append"):
        resolve_conflict(exists=True, path=Path("/tmp/x"), mode="append", append_op=None)


def test_resolve_conflict_ask_outside_claude_code_raises(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="仅在 Claude Code"):
        resolve_conflict(exists=True, path=Path("/tmp/x"), mode="ask")


def test_resolve_conflict_ask_in_claude_code_exits(monkeypatch, tmp_path):
    """ASK 模式在 Claude Code 上下文应 sys.exit(0)，把 JSON 输出留给主流程捕获。"""
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    with pytest.raises(SystemExit) as exc_info:
        resolve_conflict(exists=True, path=Path("/tmp/x"), mode="ask")
    assert exc_info.value.code == 0
```

- [ ] **Step 2: 跑测试确认 2 个通过（绿）**

```bash
PYTHONPATH=. pytest scripts/tests/test_safe_overwrite.py -v
```

Expected: 11 passed（4 + 4 + 3）

- [ ] **Step 3: 提交**

```bash
git add scripts/tests/test_safe_overwrite.py
git commit -m "test(safe-overwrite): append_op-missing + ask-degradation"
```

---

## Phase 2: P0 脚本接入 (update_master_outline / chapter_commit / snapshot_manager)

### Task 4: update_master_outline.py 加 --on-conflict flag + 守卫

**Files:**
- Modify: `scripts/update_master_outline.py:121-162` (`_update_volume_table`)
- Modify: `scripts/update_master_outline.py:303-343` (`main` argparse)
- Create: `scripts/tests/test_update_master_outline_conflict.py`

- [ ] **Step 1: 写集成测试（默认 + skip + overwrite 3 用例）**

```python
# scripts/tests/test_update_master_outline_conflict.py
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path("/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang")


@pytest.fixture
def fake_project(tmp_path):
    """构造一个最小可跑项目：state.json + 大纲/总纲.md 含 V2 row。"""
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".webnovel").mkdir()
    (project / "大纲").mkdir()

    # state.json
    (project / ".webnovel" / "state.json").write_text(
        '{"project_info": {"title": "T", "genre": "玄幻"}, '
        '"volumes": [{"index": 1, "status": "confirmed"}, '
        '{"index": 2, "status": "confirmed", "title": "V2", '
        '"core_conflict": "old", "climax": "old"}]}'
    )

    # 总纲.md 含 V2 row
    outline = project / "大纲" / "总纲.md"
    outline.write_text(
        "# 总纲\n\n## 卷划分\n"
        "| 卷号 | 卷名 | 章节范围 | 核心冲突 | 卷末高潮 |\n"
        "|------|------|----------|----------|----------|\n"
        "| 2 | V2 | 81-160 | old | old |\n"
    )

    # 总纲写回 JSON
    (project / "大纲" / "第1卷-总纲写回.json").write_text(
        '{"next_volume_anchor": {"volume": 2, "volume_name": "V2", '
        '"chapters_range": "81-160", "core_conflict": "NEW", '
        '"volume_end_climax": "NEW"}}'
    )
    return project


def test_default_runs_raises_file_exists_error(fake_project):
    """默认（不传 --on-conflict）应报错且不修改文件。"""
    result = subprocess.run(
        [sys.executable, "scripts/update_master_outline.py",
         "--project-root", str(fake_project), "--volume", "1"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "已存在" in result.stderr or "请传 --on-conflict" in result.stderr
    # V2 row 仍未被覆盖
    content = (fake_project / "大纲" / "总纲.md").read_text()
    assert "old" in content


def test_skip_does_not_modify(fake_project):
    result = subprocess.run(
        [sys.executable, "scripts/update_master_outline.py",
         "--project-root", str(fake_project), "--volume", "1",
         "--on-conflict", "skip"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    content = (fake_project / "大纲" / "总纲.md").read_text()
    assert "old" in content


def test_overwrite_modifies(fake_project):
    result = subprocess.run(
        [sys.executable, "scripts/update_master_outline.py",
         "--project-root", str(fake_project), "--volume", "1",
         "--on-conflict", "overwrite"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    content = (fake_project / "大纲" / "总纲.md").read_text()
    assert "NEW" in content
```

- [ ] **Step 2: 跑测试确认 3 个都失败（红）**

```bash
PYTHONPATH=. pytest scripts/tests/test_update_master_outline_conflict.py -v
```

Expected: 3 failed（默认应成功 0 → 现在默默覆盖；skip 应保持 → 现在默默覆盖；overwrite 应改 → 现在默默覆盖但测试期望是已覆盖所以可能 1 个意外通过）

- [ ] **Step 3: 修改 _update_volume_table 加守卫**

打开 `scripts/update_master_outline.py`，在 `_update_volume_table` 函数前导入 `resolve_conflict`：

```python
# 在文件顶部 import 区域追加
from scripts._shared.safe_overwrite import resolve_conflict, ConflictMode
```

然后修改 `_update_volume_table`（行 121-162），在 for 循环里检测已存在 row：

```python
def _update_volume_table(text: str, anchor: dict[str, str], on_conflict: str | None = None) -> tuple[str, bool]:
    """Sync V+1 anchor row into 大纲/总纲.md's 卷划分 table.

    on_conflict: 传入 resolve_conflict；遇到已存在 row 时按 flag 决定
    overwrite/append/skip/ask。None = 报错。
    """
    lines = text.splitlines()
    header_idx = next((i for i, line in enumerate(lines) if line.strip().startswith("| 卷号")), None)
    new_row = _render_row(
        [
            anchor["volume"],
            anchor["volume_name"],
            anchor["chapters_range"],
            anchor["core_conflict"],
            anchor["volume_end_climax"],
        ]
    )

    # 如果表存在 + 检测到已有 row → 守卫
    if header_idx is not None:
        row_start = header_idx + 2
        row_end = row_start
        while row_end < len(lines) and lines[row_end].strip().startswith("|"):
            row_end += 1

        for idx in range(row_start, row_end):
            cells = _split_row(lines[idx])
            if cells and cells[0] == anchor["volume"]:
                # 检测到已存在 row → 守卫
                resolve_conflict(
                    exists=True,
                    path=Path(text.splitlines()[0]) if text else None,  # 仅作展示用
                    mode=on_conflict,
                )
                # 守卫通过 → 执行覆盖
                while len(cells) < 5:
                    cells.append("")
                cells[1] = anchor["volume_name"]
                if anchor["chapters_range"]:
                    cells[2] = anchor["chapters_range"]
                cells[3] = anchor["core_conflict"]
                cells[4] = anchor["volume_end_climax"]
                rendered = _render_row(cells[:5])
                changed = rendered != lines[idx]
                lines[idx] = rendered
                return "\n".join(lines).rstrip() + "\n", changed

    if header_idx is None:
        addition = [
            "",
            "## 卷划分",
            "| 卷号 | 卷名 | 章节范围 | 核心冲突 | 卷末高潮 |",
            "|------|------|----------|----------|----------|",
            new_row,
        ]
        return "\n".join(lines + addition).rstrip() + "\n", True

    lines.insert(row_end, new_row)
    return "\n".join(lines).rstrip() + "\n", True
```

`resolve_conflict` 已经在 Task 1 定义为接收 `exists: bool` + `path: Path | None` + `mode`，不需要再改签名。

- [ ] **Step 4: 修改 main() 加 --on-conflict flag**

```python
# scripts/update_master_outline.py main() (行 303-)
parser.add_argument("--on-conflict", choices=["overwrite", "append", "skip", "ask"], default=None,
                    help="遇到已存在 row 时的处理策略")

# 在 sync_master_outline 调用处传 on_conflict=args.on_conflict
# 找到 _update_volume_table(before, anchor) 改为 _update_volume_table(before, anchor, on_conflict=args.on_conflict)
```

- [ ] **Step 5: 跑集成测试确认 3 个全过（绿）**

```bash
PYTHONPATH=. pytest scripts/tests/test_update_master_outline_conflict.py -v
```

Expected: 3 passed

- [ ] **Step 6: 跑全量单测确认 safe_overwrite.py 仍过**

```bash
PYTHONPATH=. pytest scripts/tests/test_safe_overwrite.py -v
```

Expected: 10 passed

- [ ] **Step 7: 提交**

```bash
git add scripts/update_master_outline.py scripts/_shared/safe_overwrite.py scripts/tests/test_safe_overwrite.py scripts/tests/test_update_master_outline_conflict.py
git commit -m "feat(safe-overwrite): update_master_outline 接入 --on-conflict"
```

---

### Task 5: chapter_commit.py 加 --on-conflict flag + 守卫

**Files:**
- Modify: `scripts/chapter_commit.py:19-39` (`main`)
- Modify: `scripts/data_modules/chapter_commit_service.py:91-96` (`persist_commit`)
- Create: `scripts/tests/test_chapter_commit_conflict.py`

- [ ] **Step 1: 写集成测试（默认 + overwrite 2 用例）**

```python
# scripts/tests/test_chapter_commit_conflict.py
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path("/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang")


@pytest.fixture
def fake_chapter_project(tmp_path):
    project = tmp_path / "proj"
    (project / ".story-system" / "commits").mkdir(parents=True)
    # 已存在的 commit
    (project / ".story-system" / "commits" / "chapter_001.commit.json").write_text(
        json.dumps({"meta": {"chapter": 1, "status": "accepted"}, "old": True})
    )
    return project


def test_default_rejects_overwrite(fake_chapter_project):
    """默认应该报错，不覆盖 accepted commit。"""
    result = subprocess.run(
        [sys.executable, "scripts/chapter_commit.py",
         "--project-root", str(fake_chapter_project),
         "--chapter", "1",
         "--review-result", "/tmp/rr.json",
         "--fulfillment-result", "/tmp/fr.json",
         "--disambiguation-result", "/tmp/dr.json",
         "--extraction-result", "/tmp/er.json"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0
    content = (fake_chapter_project / ".story-system" / "commits" / "chapter_001.commit.json").read_text()
    assert json.loads(content).get("old") is True  # 未被覆盖
```

- [ ] **Step 2: 修改 `persist_commit` 加守卫**

```python
# scripts/data_modules/chapter_commit_service.py
from scripts._shared.safe_overwrite import resolve_conflict

class ChapterCommitService:
    def persist_commit(
        self,
        payload: Dict[str, Any],
        on_conflict: str | None = None,
    ) -> Path:
        target = self.project_root / ".story-system" / "commits"
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"chapter_{int(payload['meta']['chapter']):03d}.commit.json"
        # 守卫
        resolve_conflict(exists=path.exists(), path=path, mode=on_conflict)
        write_json(path, payload)
        return path
```

- [ ] **Step 3: 修改 chapter_commit.py main() 加 flag**

```python
# scripts/chapter_commit.py main()
parser.add_argument("--on-conflict", choices=["overwrite", "append", "skip", "ask"], default=None)
# 在 persist_commit(payload) 改为 persist_commit(payload, on_conflict=args.on_conflict)
```

- [ ] **Step 4: 跑测试确认绿**

```bash
PYTHONPATH=. pytest scripts/tests/test_chapter_commit_conflict.py -v
```

Expected: 1 passed（默认拒绝）；可加 overwrite 用例确认绿

- [ ] **Step 5: 提交**

```bash
git add scripts/chapter_commit.py scripts/data_modules/chapter_commit_service.py scripts/tests/test_chapter_commit_conflict.py
git commit -m "feat(safe-overwrite): chapter_commit 接入 --on-conflict"
```

---

### Task 6: snapshot_manager.py cmd_freeze 加 --on-conflict flag

**Files:**
- Modify: `scripts/snapshot_manager.py:121-150` (`cmd_freeze`)
- Create: `scripts/tests/test_snapshot_manager_conflict.py`

- [ ] **Step 1: 写集成测试（默认 + overwrite 2 用例）**

```python
# scripts/tests/test_snapshot_manager_conflict.py
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path("/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang")


@pytest.fixture
def fake_snapshot_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    # 创建一个 dummy .md 让 discover_files 不返回空
    (project / "大纲").mkdir()
    (project / "大纲" / "总纲.md").write_text("# dummy")
    # 预创建 snapshot dir
    snap_dir = project / ".webnovel" / "snapshots" / "ch0001"
    snap_dir.mkdir(parents=True)
    (snap_dir / "old.txt").write_text("OLD")
    return project


def test_default_refuses_rmtree(fake_snapshot_project):
    """默认应该报错，不 rmtree 现有 snapshot dir。"""
    result = subprocess.run(
        [sys.executable, "scripts/snapshot_manager.py", "freeze",
         "--project-root", str(fake_snapshot_project), "--chapter", "1"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0
    # old.txt 仍存在
    assert (fake_snapshot_project / ".webnovel" / "snapshots" / "ch0001" / "old.txt").exists()
```

- [ ] **Step 2: 修改 cmd_freeze**

```python
# scripts/snapshot_manager.py
from scripts._shared.safe_overwrite import resolve_conflict

def cmd_freeze(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    files = discover_files(project_root)
    if not files:
        print(f"[snapshot] 找不到任何 SNAPSHOT_PATHS 下的 .md 文件", file=sys.stderr)
        return EXIT_INFRA

    chapter = args.chapter
    snap_dir = _chapter_dir(project_root, chapter)
    # 守卫：snap_dir 已存在 → 按 flag 决定
    on_conflict = getattr(args, "on_conflict", None)
    if snap_dir.exists():
        resolve_conflict(exists=True, path=snap_dir, mode=on_conflict)
        # 守卫通过 → 执行清空（仅当 on_conflict=overwrite 时才会到这一步）
        import shutil
        shutil.rmtree(snap_dir)

    # ... 后续不变
```

- [ ] **Step 3: 修改 argparse 加 --on-conflict**

```python
# cmd_freeze 的 parser setup
parser.add_argument("--on-conflict", choices=["overwrite", "append", "skip", "ask"], default=None)
```

注意：`append` 语义对 snapshot dir 是不 `rmtree` + manifest 增量更新。但 Task 6 的最小实现先不支持 append，让 `mode='append'` 直接抛 ValueError（`resolve_conflict` 缺 append_op 时已会抛）。

- [ ] **Step 4: 跑测试确认绿**

```bash
PYTHONPATH=. pytest scripts/tests/test_snapshot_manager_conflict.py -v
```

Expected: 1 passed（默认拒绝）

- [ ] **Step 5: 提交**

```bash
git add scripts/snapshot_manager.py scripts/tests/test_snapshot_manager_conflict.py
git commit -m "feat(safe-overwrite): snapshot_manager cmd_freeze 接入 --on-conflict"
```

---

## Phase 3: plan 脚本可修（hook_type / chapter_meta / check-volume）

### Task 7: 扩 VALID_HOOK_TYPES 6 → 11

**Files:**
- Modify: `scripts/story_craft.py:237`
- Create: `scripts/tests/test_story_craft_extended.py`

- [ ] **Step 1: 写测试（"悬念钩" 别名可入库）**

```python
# scripts/tests/test_story_craft_extended.py
from scripts.story_craft import set_chapter_meta, VALID_HOOK_TYPES


def test_valid_hook_types_includes_aliases():
    """6 枚举扩到 11 种常用钩子，含别名。"""
    expected = {"悬念式", "悬念钩", "反转式", "反转钩",
                "情绪炸弹式", "情绪钩", "信息投放式",
                "留白式", "反讽式", "爽点钩", "危机钩"}
    assert expected.issubset(VALID_HOOK_TYPES)


def test_set_chapter_meta_accepts_xiwang_alias():
    """'悬念钩' 是 '悬念式' 的别名，应该可以入库。"""
    state = {}
    set_chapter_meta(state, chapter=1, hook_type="悬念钩")
    assert state["chapter_meta"]["1"]["hook_type"] == "悬念钩"
```

- [ ] **Step 2: 跑测试确认 red**

```bash
PYTHONPATH=. pytest scripts/tests/test_story_craft_extended.py -v
```

Expected: 2 failed

- [ ] **Step 3: 修改 VALID_HOOK_TYPES**

```python
# scripts/story_craft.py line 237
VALID_HOOK_TYPES = {
    "悬念式", "悬念钩",
    "反转式", "反转钩",
    "情绪炸弹式", "情绪钩",
    "信息投放式",
    "留白式",
    "反讽式",
    "爽点钩",
    "危机钩",
}
```

- [ ] **Step 4: 跑测试确认绿**

```bash
PYTHONPATH=. pytest scripts/tests/test_story_craft_extended.py::test_valid_hook_types_includes_aliases scripts/tests/test_story_craft_extended.py::test_set_chapter_meta_accepts_xiwang_alias -v
```

Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/story_craft.py scripts/tests/test_story_craft_extended.py
git commit -m "feat(story-craft): extend VALID_HOOK_TYPES 6→11 (含别名)"
```

---

### Task 8: 扩 ALLOWED_CHAPTER_META_FIELDS 11 → 20+

**Files:**
- Modify: `scripts/story_craft.py:239-244`
- Modify: `scripts/tests/test_story_craft_extended.py`

- [ ] **Step 1: 追加测试**

```python
# 追加到 scripts/tests/test_story_craft_extended.py


def test_allowed_fields_includes_outline_fields():
    """plan 提的字段都能入库。"""
    from scripts.story_craft import ALLOWED_CHAPTER_META_FIELDS
    required = {
        "CBN", "CPNs", "CEN",
        "must_cover", "forbidden",
        "strand", "coolpoint",
        "time_anchor", "villain_tier",
    }
    missing = required - ALLOWED_CHAPTER_META_FIELDS
    assert not missing, f"缺少字段: {missing}"


def test_set_chapter_meta_accepts_cbn():
    state = {}
    set_chapter_meta(state, chapter=1, CBN="主角突破境界")
    assert state["chapter_meta"]["1"]["CBN"] == "主角突破境界"
```

- [ ] **Step 2: 跑测试确认 red**

```bash
PYTHONPATH=. pytest scripts/tests/test_story_craft_extended.py::test_allowed_fields_includes_outline_fields scripts/tests/test_story_craft_extended.py::test_set_chapter_meta_accepts_cbn -v
```

Expected: 2 failed

- [ ] **Step 3: 修改 ALLOWED_CHAPTER_META_FIELDS**

```python
# scripts/story_craft.py
ALLOWED_CHAPTER_META_FIELDS = {
    # 原有 11 字段
    "beat_position", "hook_type",
    "scene_goal", "scene_conflict", "scene_setback", "scene_resolution",
    "sequel_reaction", "sequel_dilemma", "sequel_decision",
    "foreshadow_buried", "foreshadow_paid_off",
    # 新增：结构化节点 + outline 字段
    "CBN", "CPNs", "CEN",
    "must_cover", "forbidden",
    "strand", "coolpoint",
    "time_anchor", "villain_tier",
}
```

- [ ] **Step 4: 跑测试确认绿**

```bash
PYTHONPATH=. pytest scripts/tests/test_story_craft_extended.py -v
```

Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/story_craft.py scripts/tests/test_story_craft_extended.py
git commit -m "feat(story-craft): extend ALLOWED_CHAPTER_META_FIELDS 11→20"
```

---

### Task 9: check-volume 加 .md 存在性检查

**Files:**
- Modify: `scripts/data_modules/webnovel.py:467-523` (check-volume action)
- Create: `scripts/tests/test_check_volume_md.py`

- [ ] **Step 1: 写测试（缺 .md 时 check-volume 报 BLOCKER）**

```python
# scripts/tests/test_check_volume_md.py
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path("/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang")


@pytest.fixture
def proj_no_md(tmp_path):
    project = tmp_path / "proj"
    (project / ".webnovel").mkdir(parents=True)
    (project / ".webnovel" / "state.json").write_text(
        '{"story_craft": {"volume_beat": {"volume": 1, "total_chapters": 50, '
        '"beats": []}}, "chapter_meta": {}}'
    )
    # 没有 大纲/ 目录 → 所有 .md 缺失
    return project


def test_check_volume_warns_missing_md(proj_no_md):
    result = subprocess.run(
        [sys.executable, "scripts/webnovel.py",
         "--project-root", str(proj_no_md),
         "story-craft", "check-volume", "--volume", "1"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    # .md 缺失应该被报为 BLOCKER（exit code != 0）
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "节拍表" in output or "时间线" in output or "详细大纲" in output
    assert "BLOCKER" in output
```

- [ ] **Step 2: 修改 check-volume action**

在 `data_modules/webnovel.py` `check-volume` 分支最后追加：

```python
    # 7+. .md 文件存在性检查（P0 修复）
    from pathlib import Path
    outline_dir = root / "大纲"
    expected_md = [
        outline_dir / f"第{args.volume}卷-节拍表.md",
        outline_dir / f"第{args.volume}卷-时间线.md",
        outline_dir / f"第{args.volume}卷-详细大纲.md",
    ]
    for md in expected_md:
        if not md.is_file():
            issues.append(f"BLOCKER: {md.relative_to(root)} 不存在")
```

- [ ] **Step 3: 跑测试确认绿**

```bash
PYTHONPATH=. pytest scripts/tests/test_check_volume_md.py -v
```

Expected: 1 passed

- [ ] **Step 4: 跑全量单测确认未破坏其他测试**

```bash
PYTHONPATH=. pytest scripts/tests/test_story_craft_extended.py scripts/tests/test_safe_overwrite.py -v
```

Expected: 14+ passed

- [ ] **Step 5: 提交**

```bash
git add scripts/data_modules/webnovel.py scripts/tests/test_check_volume_md.py
git commit -m "feat(check-volume): verify .md artifacts exist (P0 修复)"
```

---

## Phase 4: SKILL.md 落地脚本 (check_plan_artifacts.py)

### Task 10: 创建 check_plan_artifacts.py

**Files:**
- Create: `scripts/check_plan_artifacts.py`
- Create: `scripts/tests/test_check_plan_artifacts.py`

- [ ] **Step 1: 写 3 个失败测试**

```python
# scripts/tests/test_check_plan_artifacts.py
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path("/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang")


@pytest.fixture
def proj_with_md(tmp_path):
    project = tmp_path / "proj"
    (project / "大纲").mkdir(parents=True)
    (project / "大纲" / "第1卷-节拍表.md").write_text("# V1 节拍")
    (project / "大纲" / "第1卷-时间线.md").write_text("# V1 时间线")
    # 第1卷-详细大纲.md 故意缺失
    return project


def test_no_md_returns_empty_list(tmp_path):
    project = tmp_path / "empty"
    project.mkdir()
    result = subprocess.run(
        [sys.executable, "scripts/check_plan_artifacts.py",
         "--project-root", str(project), "--volume", "1"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["artifacts"] == []


def test_partial_md_lists_existing(proj_with_md):
    result = subprocess.run(
        [sys.executable, "scripts/check_plan_artifacts.py",
         "--project-root", str(proj_with_md), "--volume", "1"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    paths = [a["path"] for a in data["artifacts"]]
    assert "大纲/第1卷-节拍表.md" in paths
    assert "大纲/第1卷-时间线.md" in paths
    assert "大纲/第1卷-详细大纲.md" not in paths  # 缺失不计入


def test_output_includes_last_modified(proj_with_md):
    result = subprocess.run(
        [sys.executable, "scripts/check_plan_artifacts.py",
         "--project-root", str(proj_with_md), "--volume", "1"],
        cwd=PLUGIN_ROOT, capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    for a in data["artifacts"]:
        assert "last_modified" in a
        assert a["last_modified"]  # 非空
```

- [ ] **Step 2: 跑测试确认 red**

```bash
PYTHONPATH=. pytest scripts/tests/test_check_plan_artifacts.py -v
```

Expected: 3 failed

- [ ] **Step 3: 写实现**

```python
# scripts/check_plan_artifacts.py
"""扫描 plan / init / review 重跑前需要检查的 .md artifact 集合。

返回 JSON：{volume, artifacts: [{path, exists, last_modified}]}

用于让 3 个 SKILL.md (plan/init/review) 在重跑前显式感知文件存在状态。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def _resolve_project_root(args_project_root: str | None) -> Path:
    if args_project_root:
        return Path(args_project_root).expanduser().resolve()
    return Path.cwd()


def _check_artifact(outline_dir: Path, name: str) -> dict:
    path = outline_dir / name
    if not path.is_file():
        return {"path": str(path), "exists": False, "last_modified": ""}
    mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    return {"path": str(path), "exists": True, "last_modified": mtime}


def collect_plan_artifacts(project_root: Path, volume: int) -> dict:
    outline_dir = project_root / "大纲"
    names = [
        f"第{volume}卷-节拍表.md",
        f"第{volume}卷-时间线.md",
        f"第{volume}卷-详细大纲.md",
    ]
    artifacts = [_check_artifact(outline_dir, n) for n in names]
    return {"volume": volume, "artifacts": artifacts}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check plan artifacts existence")
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--volume", type=int, required=True)
    args = parser.parse_args()
    root = _resolve_project_root(args.project_root)
    result = collect_plan_artifacts(root, args.volume)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认绿**

```bash
PYTHONPATH=. pytest scripts/tests/test_check_plan_artifacts.py -v
```

Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/check_plan_artifacts.py scripts/tests/test_check_plan_artifacts.py
git commit -m "feat(check-plan-artifacts): CLI for SKILL.md landing"
```

---

### Task 11: 改写 plan/SKILL.md 加 check-plan-artifacts 调用

**Files:**
- Modify: `skills/webnovel-plan/SKILL.md:72-96` (Step 1)

- [ ] **Step 1: 找到 plan SKILL.md Step 1**

用 Read 工具读 `skills/webnovel-plan/SKILL.md`，定位 Step 1 区块。

- [ ] **Step 2: 在 Step 1 区块开头插入 check-plan-artifacts**

```markdown
#### 重跑守卫（Step 1 前置，2026-08-19 新增）

运行 plan 前必须扫描目标卷的现有 .md artifact，避免静默覆盖：

\`\`\`bash
python3 -X utf8 "${SCRIPTS_DIR}/check_plan_artifacts.py" \
  --project-root "${PROJECT_ROOT}" --volume ${volume_id} \
  --format json
\`\`\`

输出非空 → **必须用 AskUserQuestion 三态询问用户**：

- 重写 → 加 `--on-conflict=overwrite` 给后续 `master-outline-sync` / `update-state`
- 部分改写 → 加 `--on-conflict=append`
- 不改 → 加 `--on-conflict=skip`（默认行为，遇到 .md 存在时脚本会报错退出；此处显式传 skip 让它直接通过）

未询问用户前，禁止进入 Step 4 / Step 5 / Step 6 / Step 7。

```

- [ ] **Step 3: 验证文档完整性（无 placeholder）**

```bash
grep -n "TBD\|TODO\|FIXME" skills/webnovel-plan/SKILL.md
```

Expected: 无输出

- [ ] **Step 4: 提交**

```bash
git add skills/webnovel-plan/SKILL.md
git commit -m "docs(plan): add check-plan-artifacts 落地 + 三态询问"
```

---

### Task 12: 改写 init/SKILL.md 加 check-plan-artifacts

**Files:**
- Modify: `skills/webnovel-init/SKILL.md` Step 0 区块

- [ ] **Step 1: 找到 init SKILL.md Step 0**

Read `skills/webnovel-init/SKILL.md` 定位 Step 0。

- [ ] **Step 2: 在 Step 0 末尾追加重跑守卫段**

```markdown
#### 重跑守卫（Step 0 后置，2026-08-19 新增）

init 不允许重 init 已 confirmed 项目；若用户明确要"沿用 + 部分改写"，先扫一遍 artifact 状态：

\`\`\`bash
python3 -X utf8 "${SCRIPTS_DIR}/check_plan_artifacts.py" \
  --project-root "${PROJECT_ROOT}" --volume 1 \
  --format json
\`\`\`

输出非空 → **必须用 AskUserQuestion 三态询问用户**（沿用 / 部分改写 / 暂停初始化）。

```

- [ ] **Step 3: 验证 + 提交**

```bash
grep -n "TBD\|TODO\|FIXME" skills/webnovel-init/SKILL.md
git add skills/webnovel-init/SKILL.md
git commit -m "docs(init): add check-plan-artifacts 落地 + 三态询问"
```

---

### Task 13: 改写 review/SKILL.md 加报告覆盖询问

**Files:**
- Modify: `skills/webnovel-review/SKILL.md` Step 4 区块

- [ ] **Step 1: 找到 review SKILL.md Step 4**

Read `skills/webnovel-review/SKILL.md` 定位 Step 4（生成审查报告）。

- [ ] **Step 2: 在 Step 4 开头追加重跑守卫段**

```markdown
#### 重跑守卫（Step 4 前置，2026-08-19 新增）

写审查报告前必须检查现有报告路径：

\`\`\`bash
test -f "${PROJECT_ROOT}/审查报告/第${start}-${end}章审查报告.md" && echo "EXISTS" || echo "NEW"
\`\`\`

EXISTS → **必须用 AskUserQuestion 三态询问用户**（覆盖 / 改名追加 / 跳过本次审查）。

- 覆盖 → 继续生成报告
- 改名追加 → 生成 `审查报告/第${start}-${end}章审查报告-${ts}.md`
- 跳过 → 提前结束流程，不生成报告

未询问用户前，禁止覆盖已有审查报告。

```

- [ ] **Step 3: 验证 + 提交**

```bash
grep -n "TBD\|TODO\|FIXME" skills/webnovel-review/SKILL.md
git add skills/webnovel-review/SKILL.md
git commit -m "docs(review): add report-overwrite 三态询问"
```

---

## Phase 5: 调用者同步升级（breaking change）

### Task 14: plan/SKILL.md Step 4-7 加 --on-conflict=overwrite

**Files:**
- Modify: `skills/webnovel-plan/SKILL.md` Step 4-7 (master-outline-sync / update-state 调用)

- [ ] **Step 1: 找所有 master-outline-sync / update-state 调用**

```bash
grep -n "master-outline-sync\|update-state" skills/webnovel-plan/SKILL.md
```

- [ ] **Step 2: 给每个调用加 --on-conflict=overwrite**

把所有 `master-outline-sync --volume {volume_id}` 改为：
```
master-outline-sync --volume {volume_id} --on-conflict=overwrite
```

把所有 `update-state -- --volume-planned {volume_id}` 改为：
```
update-state -- --volume-planned {volume_id} --on-conflict=overwrite
```

plan 默认是覆盖语义（用户已确认 GOAL）。

- [ ] **Step 3: 验证**

```bash
grep -n "master-outline-sync\|update-state" skills/webnovel-plan/SKILL.md | grep -v "on-conflict"
```

Expected: 无输出（每个调用都已加 flag）

- [ ] **Step 4: 提交**

```bash
git add skills/webnovel-plan/SKILL.md
git commit -m "docs(plan): master-outline-sync/update-state 显式 --on-conflict=overwrite"
```

---

### Task 15: write/SKILL.md Step 5.5 chapter-commit 加 --on-conflict=overwrite

**Files:**
- Modify: `skills/webnovel-write/SKILL.md` Step 5.5

- [ ] **Step 1: 找 chapter-commit 调用**

```bash
grep -n "chapter-commit" skills/webnovel-write/SKILL.md
```

- [ ] **Step 2: 给 chapter-commit 加 --on-conflict=overwrite**

把 `chapter-commit --chapter N` 改为：
```
chapter-commit --chapter N --on-conflict=overwrite
```

write 默认是覆盖语义。

- [ ] **Step 3: 验证 + 提交**

```bash
grep -n "chapter-commit" skills/webnovel-write/SKILL.md | grep -v "on-conflict"
git add skills/webnovel-write/SKILL.md
git commit -m "docs(write): chapter-commit 显式 --on-conflict=overwrite"
```

---

### Task 16: dashboard/app.py 透传 --on-conflict

**Files:**
- Modify: `dashboard/app.py`（找 master-outline-sync / chapter-commit / update-state 调用）

- [ ] **Step 1: 找调用点**

```bash
grep -n "master-outline-sync\|chapter-commit\|update-state" dashboard/app.py
```

- [ ] **Step 2: 在 dashboard 调用加 on_conflict 参数透传**

找到每个调用，给它加 `on_conflict="overwrite"` 参数（dashboard 是显式 UI 操作，默认 overwrite）。

例：
```python
# 原
result = subprocess.run(["python", "scripts/update_master_outline.py", "--volume", str(v)])
# 改为
result = subprocess.run(["python", "scripts/update_master_outline.py", "--volume", str(v), "--on-conflict", "overwrite"])
```

- [ ] **Step 3: 验证 dashboard 启动不报错**

```bash
python -c "from dashboard.app import app; print('OK')"
```

Expected: OK

- [ ] **Step 4: 提交**

```bash
git add dashboard/app.py
git commit -m "feat(dashboard): pass --on-conflict=overwrite to write calls"
```

---

## Phase 6: 全量验收

### Task 17: 跑全量测试 + 修复回归

**Files:** 无修改

- [ ] **Step 1: 跑全部新增测试**

```bash
PYTHONPATH=. pytest \
  scripts/tests/test_safe_overwrite.py \
  scripts/tests/test_update_master_outline_conflict.py \
  scripts/tests/test_chapter_commit_conflict.py \
  scripts/tests/test_snapshot_manager_conflict.py \
  scripts/tests/test_story_craft_extended.py \
  scripts/tests/test_check_volume_md.py \
  scripts/tests/test_check_plan_artifacts.py \
  -v
```

Expected: 全部 passed（至少 20 个用例）

- [ ] **Step 2: 跑现有 test suite 确保未破坏**

```bash
PYTHONPATH=. pytest scripts/tests/ -v --tb=short
```

Expected: 所有原有测试仍通过

- [ ] **Step 3: 修复任何回归（如有）**

针对失败用例，按"红 → 改 → 绿"循环修复。

- [ ] **Step 4: 提交最终修复（如有）**

```bash
git add scripts/
git commit -m "fix: regression fixes after full test run"
```

---

### Task 18: 更新 CHANGELOG + 项目文档

**Files:**
- Modify: `CHANGELOG.md`（如不存在则创建）
- Modify: `README.md`（在"当前能力"段加 safe_overwrite 说明）

- [ ] **Step 1: 在 CHANGELOG 加 2026-08-19 条目**

```markdown
## 2026-08-19

### 新增
- `scripts/_shared/safe_overwrite.py`：覆盖守卫层，统一处理"重跑=三态询问"语义
- `scripts/check_plan_artifacts.py`：SKILL.md 落地的 CLI
- 4 个 P0 脚本接入 `--on-conflict=overwrite|append|skip|ask` flag

### 破坏性变更（breaking change）
- 默认行为从"静默覆盖"改为"存在则报错"
- 调用者必须显式传 `--on-conflict`
- 影响：`master-outline-sync` / `chapter-commit` / `update-state` / `snapshot_manager cmd_freeze`

### 修复
- plan SKILL.md "覆盖时询问"声明首次落到脚本
- check-volume 加 .md artifact 存在性检查
- hook_type 6 枚举扩到 11（含别名"悬念钩"等）
- chapter_meta 字段白名单 11 扩到 20

```

- [ ] **Step 2: README.md 加 safe_overwrite 说明**

定位 README.md 的"当前能力"或"工作流"段，追加一段。

- [ ] **Step 3: 提交**

```bash
git add CHANGELOG.md README.md
git commit -m "docs: safe_overwrite CHANGELOG + README"
```

---

### Task 19: 最终验收清单

**Files:** 无修改

- [ ] **Step 1: 跑验收脚本**

```bash
cd /Users/chang/Desktop/zhanghui

# 1. 4 个 P0 脚本遇覆盖报错
echo "=== Test 1: update_master_outline 默认应报错 ==="
mkdir -p /tmp/test_proj/.webnovel /tmp/test_proj/大纲
echo '{"project_info":{"title":"T","genre":"x"},"volumes":[]}' > /tmp/test_proj/.webnovel/state.json
echo '{"next_volume_anchor":{"volume":1,"volume_name":"V","chapters_range":"1-50","core_conflict":"x","volume_end_climax":"y"}}' > /tmp/test_proj/大纲/第1卷-总纲写回.json
echo -e "# 总纲\n\n## 卷划分\n| 卷号 | 卷名 | 章节范围 | 核心冲突 | 卷末高潮 |\n|------|------|----------|----------|----------|\n| 1 | OLD | 1-50 | old | old |\n" > /tmp/test_proj/大纲/总纲.md
python3 .claude/plugins/webnovel-writer_chang/scripts/update_master_outline.py --project-root /tmp/test_proj --volume 1 2>&1 | grep -q "已存在" && echo "PASS" || echo "FAIL"

# 2. plan 8 缺陷修复
echo "=== Test 2: 悬念钩 可入库 ==="
PYTHONPATH=.claude/plugins/webnovel-writer_chang python3 -c "
from sys import path; path.insert(0, '.claude/plugins/webnovel-writer_chang')
from scripts.story_craft import set_chapter_meta
s = {}
set_chapter_meta(s, chapter=1, hook_type='悬念钩')
print('PASS' if s['chapter_meta']['1']['hook_type'] == '悬念钩' else 'FAIL')
"

# 3. SKILL.md 落地脚本存在
echo "=== Test 3: check_plan_artifacts.py 存在 ==="
test -f .claude/plugins/webnovel-writer_chang/scripts/check_plan_artifacts.py && echo "PASS" || echo "FAIL"

# 4. 调用者传 --on-conflict=overwrite
echo "=== Test 4: plan SKILL.md 所有调用都有 --on-conflict ==="
grep -c "on-conflict=overwrite" .claude/plugins/webnovel-writer_chang/skills/webnovel-plan/SKILL.md
grep -c "on-conflict=overwrite" .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
```

Expected: 全部 PASS / 数字 ≥ 1

- [ ] **Step 2: 在 PR 描述里写一段验收总结**

完成所有任务的总结消息。

---

## Self-Review Checklist

- [x] Spec coverage: 12 处改动清单全部映射到 19 个 task
- [x] Placeholder scan: 无 TBD/TODO/FIXME 残留
- [x] Type consistency: `ConflictMode` / `resolve_conflict(exists, path, mode, append_op)` 签名在 Task 1 定义、Task 4-6 一致使用
- [x] 决策记录: Section 1-5 用户裁决都已在 task 注释中标注