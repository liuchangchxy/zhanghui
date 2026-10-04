# Webnovel Foundation Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 zhanghui fork 上吸收 7 个跨卷一致性补丁（伏笔 DAG / 大纲 anchor / event matrix / pacing / state revision / reader contract / derived views），全部为硬门禁，把地基从 ⭐⭐⭐ 提到 ⭐⭐⭐⭐。

**Architecture:** 分层 — `scripts/consistency/core/` 提供 `Patch` 抽象 + `Runner` 调度；`scripts/consistency/patches/` 放 7 个具体补丁；`scripts/consistency/cli.py` 暴露 CLI；skill 端（plan/write/review）薄集成。

**Tech Stack:** Python 3.11+，pytest，pathlib，json，pyyaml（state.json 现有依赖），git。

**Spec:** `docs/superpowers/specs/2026-08-18-webnovel-foundation-hardening-design.md`

---

## Phase 0：基础层

### Task 1：创建目录结构

**Files:**
- Create: `scripts/consistency/__init__.py`
- Create: `scripts/consistency/core/__init__.py`
- Create: `scripts/consistency/patches/__init__.py`
- Create: `tests/unit/consistency/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/fixtures/cross_volume/__init__.py`

- [ ] **Step 1: 创建所有目录和 __init__.py**

```bash
mkdir -p scripts/consistency/core scripts/consistency/patches
mkdir -p tests/unit/consistency tests/integration tests/fixtures/cross_volume
touch scripts/consistency/__init__.py
touch scripts/consistency/core/__init__.py
touch scripts/consistency/patches/__init__.py
touch tests/unit/consistency/__init__.py
touch tests/integration/__init__.py
touch tests/fixtures/cross_volume/__init__.py
```

- [ ] **Step 2: 验证**

Run: `find scripts/consistency tests/unit/consistency tests/integration tests/fixtures/cross_volume -type d`
Expected: 7 directories listed

- [ ] **Step 3: Commit**

```bash
git add scripts/consistency tests
git commit -m "feat(consistency): scaffold directory structure"
```

---

### Task 2：核心抽象 `Patch` / `Blocker` / `Context`

**Files:**
- Create: `scripts/consistency/core/patch_base.py`
- Test: `tests/unit/consistency/test_patch_base.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/unit/consistency/test_patch_base.py
from scripts.consistency.core.patch_base import Patch, Blocker, CheckContext, ApplyContext
from pathlib import Path
import pytest

def test_blocker_construction():
    b = Blocker(patch="test", chapter=1, message="bad", fix_hint="fix it")
    assert b.patch == "test"
    assert b.chapter == 1
    assert b.message == "bad"
    assert b.fix_hint == "fix it"

def test_check_context_construction():
    ctx = CheckContext(
        project_root=Path("/tmp"),
        chapter_num=1,
        state={"foo": 1},
        chapter_outline=None,
        previous_chapters=[],
        chapter_text=None,
    )
    assert ctx.chapter_num == 1
    assert ctx.state == {"foo": 1}

def test_patch_abc_cannot_instantiate():
    with pytest.raises(TypeError):
        Patch()

def test_concrete_patch_implements_interface():
    class MyPatch(Patch):
        name = "my"
        description = "test"
        depends_on = ()
        def check(self, ctx): return []
        def apply(self, ctx): pass
    
    p = MyPatch()
    assert p.check(CheckContext(project_root=Path("/tmp"), chapter_num=1, state={}, chapter_outline=None, previous_chapters=[], chapter_text=None)) == []
```

- [ ] **Step 2: 运行测试，验证失败**

Run: `python -m pytest tests/unit/consistency/test_patch_base.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'scripts.consistency')

- [ ] **Step 3: 实现核心抽象**

```python
# scripts/consistency/core/patch_base.py
"""Core abstractions for consistency patches.

Source: 原創（設計參考 oh-story-claudecode 的 Patch 概念）
Path in references: N/A
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CheckContext:
    project_root: Path
    chapter_num: int
    state: dict
    chapter_outline: dict | None
    previous_chapters: list[dict]
    chapter_text: str | None


@dataclass
class ApplyContext:
    project_root: Path
    chapter_num: int
    state: dict


@dataclass
class Blocker:
    patch: str
    chapter: int
    message: str
    fix_hint: str


class Patch(ABC):
    name: str = ""
    description: str = ""
    depends_on: tuple[str, ...] = ()
    
    @abstractmethod
    def check(self, ctx: CheckContext) -> list[Blocker]: ...
    
    @abstractmethod
    def apply(self, ctx: ApplyContext) -> None: ...
```

- [ ] **Step 4: 运行测试，验证通过**

Run: `python -m pytest tests/unit/consistency/test_patch_base.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/consistency/core/patch_base.py tests/unit/consistency/test_patch_base.py
git commit -m "feat(consistency): core Patch / Blocker / Context abstractions"
```

---

### Task 3：Runner 调度器

**Files:**
- Create: `scripts/consistency/core/runner.py`
- Test: `tests/unit/consistency/test_runner.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/consistency/test_runner.py
from scripts.consistency.core.runner import ConsistencyRunner
from scripts.consistency.core.patch_base import Patch, CheckContext, ApplyContext, Blocker
from pathlib import Path


class CleanPatch(Patch):
    name = "clean"
    description = "always passes"
    depends_on = ()
    def check(self, ctx): return []
    def apply(self, ctx): pass


class FailingPatch(Patch):
    name = "failing"
    description = "always fails"
    depends_on = ()
    def check(self, ctx): return [Blocker(patch="failing", chapter=ctx.chapter_num, message="bad", fix_hint="fix")]
    def apply(self, ctx): pass


def test_runner_with_clean_patches():
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[CleanPatch()])
    assert runner.run_all(chapter=1) == []


def test_runner_with_failing_patch():
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[FailingPatch()])
    blockers = runner.run_all(chapter=1)
    assert len(blockers) == 1
    assert blockers[0].patch == "failing"


def test_runner_runs_all_patches():
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[CleanPatch(), FailingPatch(), CleanPatch()])
    blockers = runner.run_all(chapter=1)
    assert len(blockers) == 1


def test_runner_uses_default_patches_when_none_given():
    runner = ConsistencyRunner(project_root=Path("/tmp"))
    # Default patches not yet implemented - should raise NotImplementedError
    import pytest
    with pytest.raises(NotImplementedError):
        runner.run_all(chapter=1)
```

- [ ] **Step 2: 运行测试，验证失败**

Run: `python -m pytest tests/unit/consistency/test_runner.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 Runner**

```python
# scripts/consistency/core/runner.py
"""Consistency runner — orchestrates all 7 patches.

Source: 借鉴 oh-story-claudecode/skills/story-long-write/references/tracking-transaction.md 的事务模式
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/oh-story-claudecode/skills/story-import/references/tracking-transaction.md
"""
from pathlib import Path
from .patch_base import Patch, CheckContext, Blocker


class ConsistencyRunner:
    def __init__(self, project_root: Path, patches: list[Patch] | None = None):
        self.project_root = project_root
        self.patches = patches  # None means use defaults (set later)
    
    def _default_patches(self) -> list[Patch]:
        # Wired up in Phase 1+ once patches are implemented
        raise NotImplementedError("Default patches not yet wired; pass explicit list")
    
    def run_all(
        self,
        chapter: int,
        *,
        chapter_outline: dict | None = None,
        chapter_text: str | None = None,
        previous_chapters: list[dict] | None = None,
        state: dict | None = None,
    ) -> list[Blocker]:
        if self.patches is None:
            self.patches = self._default_patches()
        
        if state is None:
            state = self._load_state()
        if previous_chapters is None:
            previous_chapters = self._load_summaries(chapter)
        
        all_blockers: list[Blocker] = []
        for patch in self.patches:
            ctx = CheckContext(
                project_root=self.project_root,
                chapter_num=chapter,
                state=state,
                chapter_outline=chapter_outline,
                previous_chapters=previous_chapters,
                chapter_text=chapter_text,
            )
            all_blockers.extend(patch.check(ctx))
        return all_blockers
    
    def _load_state(self) -> dict:
        state_path = self.project_root / ".webnovel" / "state.json"
        if not state_path.exists():
            return {}
        import json
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)
    
    def _load_summaries(self, chapter: int) -> list[dict]:
        summaries_dir = self.project_root / ".webnovel" / "summaries"
        if not summaries_dir.exists():
            return []
        result = []
        for i in range(max(1, chapter - 5), chapter):
            p = summaries_dir / f"ch{i:04d}.md"
            if p.exists():
                result.append({"chapter": i, "path": str(p)})
        return result
```

- [ ] **Step 4: 运行测试，验证通过**

Run: `python -m pytest tests/unit/consistency/test_runner.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/consistency/core/runner.py tests/unit/consistency/test_runner.py
git commit -m "feat(consistency): Runner orchestrator"
```

---

### Task 4：CLI 入口

**Files:**
- Create: `scripts/consistency/cli.py`
- Test: `tests/unit/consistency/test_cli.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/consistency/test_cli.py
from scripts.consistency.cli import build_parser
import pytest


def test_parser_check_command():
    parser = build_parser()
    args = parser.parse_args(["check", "--project-root", "/tmp/proj", "--chapter", "5"])
    assert args.command == "check"
    assert args.project_root == "/tmp/proj"
    assert args.chapter == 5
    assert args.patch is None  # default: all


def test_parser_check_specific_patch():
    parser = build_parser()
    args = parser.parse_args(["check", "--project-root", "/tmp/proj", "--chapter", "5", "--patch", "foreshadow_dag"])
    assert args.patch == "foreshadow_dag"


def test_parser_list_command():
    parser = build_parser()
    args = parser.parse_args(["list", "--chapter", "5"])
    assert args.command == "list"


def test_parser_init_command():
    parser = build_parser()
    args = parser.parse_args(["init", "--volume", "1"])
    assert args.command == "init"
    assert args.volume == 1


def test_parser_override_command():
    parser = build_parser()
    args = parser.parse_args(["override", "--chapter", "5", "--reason", "user confirmed"])
    assert args.command == "override"
    assert args.reason == "user confirmed"
```

- [ ] **Step 2: 运行测试，验证失败**

Run: `python -m pytest tests/unit/consistency/test_cli.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 CLI**

```python
# scripts/consistency/cli.py
"""CLI for consistency runner.

Source: 原創（參考 webnovel.py 的 argparse 風格）
"""
import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="consistency", description="Cross-volume consistency checker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # check
    check = subparsers.add_parser("check", help="Run consistency checks on a chapter")
    check.add_argument("--project-root", type=Path, required=True)
    check.add_argument("--chapter", type=int, required=True)
    check.add_argument("--patch", type=str, default=None, help="Run only this patch")
    
    # list
    lst = subparsers.add_parser("list", help="List blockers for a chapter")
    lst.add_argument("--project-root", type=Path, required=True)
    lst.add_argument("--chapter", type=int, required=True)
    
    # init
    init = subparsers.add_parser("init", help="Initialize patch fields in state.json")
    init.add_argument("--project-root", type=Path, required=True)
    init.add_argument("--volume", type=int, required=True)
    
    # override
    override = subparsers.add_parser("override", help="Force-bypass blockers (emergency)")
    override.add_argument("--project-root", type=Path, required=True)
    override.add_argument("--chapter", type=int, required=True)
    override.add_argument("--reason", type=str, required=True)
    
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Wired in later tasks
    print(f"[stub] command={args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试，验证通过**

Run: `python -m pytest tests/unit/consistency/test_cli.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/consistency/cli.py tests/unit/consistency/test_cli.py
git commit -m "feat(consistency): CLI entry point"
```

---

### Task 5：Fixture 基线项目（干净）

**Files:**
- Create: `tests/fixtures/cross_volume/project_clean/.webnovel/state.json`
- Create: `tests/fixtures/cross_volume/project_clean/.webnovel/summaries/ch0001.md` 至 ch0005.md
- Create: `tests/fixtures/cross_volume/project_clean/README.md`

- [ ] **Step 1: 创建 fixture 目录和干净 state.json**

```bash
mkdir -p tests/fixtures/cross_volume/project_clean/.webnovel/summaries
mkdir -p tests/fixtures/cross_volume/project_clean/大纲 tests/fixtures/cross_volume/project_clean/设定集 tests/fixtures/cross_volume/project_clean/正文
```

写 state.json（含所有 7 个 patch 字段的合法 baseline）：
```json
{
  "project_info": {"name": "test-clean", "genre": "xianxia"},
  "state": {"_revision": 5, "_last_modified_by": "init", "_last_modified_at": "2026-08-18T00:00:00Z"},
  "story_craft": {
    "foreshadow_chain": {
      "version": 1,
      "dag": [
        {"id": "fs_001", "content": "神秘戒指", "level": "中层", "planted_chapter": 1, "paid_off_chapter": null, "status": "active", "depends_on": [], "introduced_by": "init"}
      ],
      "validated_at": null,
      "validation_history": []
    },
    "volume_anchors": {
      "version": 1,
      "anchors": [
        {"volume": 1, "volume_name": "测试卷", "core_conflict": "测试冲突", "volume_end_climax": "测试高潮", "must_not_reveal": [], "must_achieve": ["主角觉醒"], "foreshadows_to_plant": ["fs_001"], "total_chapters": 10, "current_chapter": 0}
      ]
    },
    "event_matrix_state": {
      "version": 1,
      "types": {
        "conflict_thrill": {"cooldown": 2, "last_used_chapter": 0},
        "bond_deepening": {"cooldown": 4, "last_used_chapter": 0},
        "faction_building": {"cooldown": 4, "last_used_chapter": 0},
        "world_painting": {"cooldown": 3, "last_used_chapter": 0},
        "tension_escalation": {"cooldown": 2, "last_used_chapter": 0}
      },
      "history": [],
      "gentle_window": 5,
      "max_consecutive_fast": 2
    },
    "pacing_history": {
      "version": 1,
      "history": [],
      "rules": {"max_consecutive_fast": 1, "slow_per_4_chapters_min": 1}
    },
    "reader_contract": {
      "version": 1,
      "expectation_debt": [],
      "causal_credits": {"protagonist_actions_used_without_setup": []},
      "endgame_reserves": [],
      "swap_debts": []
    }
  }
}
```

写 5 个空 summary：
```bash
for i in 1 2 3 4 5; do echo "# 第 $(printf %04d $i) 章摘要" > tests/fixtures/cross_volume/project_clean/.webnovel/summaries/ch$(printf %04d $i).md; done
```

写 README.md:
```markdown
# project_clean fixture

干净的 baseline。所有 7 个 patch 字段合法且无违规。
用于: 每个 patch 的"正例"测试 — 跑 consistency 应返回空。
```

- [ ] **Step 2: 验证 fixture 完整**

Run: `ls tests/fixtures/cross_volume/project_clean/.webnovel/summaries/ && cat tests/fixtures/cross_volume/project_clean/.webnovel/state.json | python -m json.tool > /dev/null && echo OK`
Expected: 5 .md files + OK

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/cross_volume/project_clean
git commit -m "test(consistency): clean fixture for baseline tests"
```

---

## Phase 1：补丁 1 — Foreshadow DAG

### Task 6：写 fixture（违规案例）

**Files:**
- Create: `tests/fixtures/cross_volume/project_dag_violation/.webnovel/state.json`
- Create: `tests/fixtures/cross_volume/project_dag_violation/README.md`

- [ ] **Step 1: 写 state.json（含 3 种违规：环 + 提前回收 + 超期）**

```json
{
  "project_info": {"name": "test-dag-bad", "genre": "xianxia"},
  "state": {"_revision": 1, "_last_modified_by": "init", "_last_modified_at": "2026-08-18T00:00:00Z"},
  "story_craft": {
    "foreshadow_chain": {
      "version": 1,
      "dag": [
        {"id": "fs_001", "content": "环A", "level": "中层", "planted_chapter": 1, "paid_off_chapter": 5, "status": "active", "depends_on": ["fs_002"], "introduced_by": "init"},
        {"id": "fs_002", "content": "环B", "level": "中层", "planted_chapter": 1, "paid_off_chapter": 5, "status": "active", "depends_on": ["fs_001"], "introduced_by": "init"},
        {"id": "fs_003", "content": "提前回收", "level": "表层", "planted_chapter": 5, "paid_off_chapter": 3, "status": "active", "depends_on": [], "introduced_by": "init"},
        {"id": "fs_004", "content": "超期未收", "level": "深层", "planted_chapter": 1, "paid_off_chapter": 5, "status": "active", "depends_on": [], "introduced_by": "init"}
      ],
      "validated_at": null,
      "validation_history": []
    }
  }
}
```

注：当前 chapter 在 10 章，fs_004 的 paid_off_chapter=5 已过但 status=active → 超期。

- [ ] **Step 2: 写 README**

```markdown
# project_dag_violation fixture

故意违反伏笔 DAG 规则：
- fs_001 ↔ fs_002 形成循环
- fs_003 planted_chapter > paid_off_chapter（提前回收）
- fs_004 paid_off_chapter < current_chapter 但 status=active（超期）

预期：foreshadow_dag patch 在 chapter=10 时至少报 3 个 BLOCKER。
```

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/cross_volume/project_dag_violation
git commit -m "test(consistency): dag violation fixture"
```

---

### Task 7：实现 Foreshadow DAG patch

**Files:**
- Create: `scripts/consistency/patches/p1_foreshadow_dag.py`
- Test: `tests/unit/consistency/test_p1_foreshadow_dag.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/consistency/test_p1_foreshadow_dag.py
from scripts.consistency.patches.p1_foreshadow_dag import P1ForeshadowDAG
from scripts.consistency.core.patch_base import CheckContext, ApplyContext
from pathlib import Path

CLEAN_STATE = {
    "story_craft": {
        "foreshadow_chain": {
            "version": 1,
            "dag": [
                {"id": "fs_001", "content": "ok", "level": "表层", "planted_chapter": 1, "paid_off_chapter": None, "status": "active", "depends_on": [], "introduced_by": "init"}
            ],
            "validated_at": None,
            "validation_history": []
        }
    }
}

VIOLATION_STATE = {
    "story_craft": {
        "foreshadow_chain": {
            "version": 1,
            "dag": [
                {"id": "fs_001", "content": "环A", "planted_chapter": 1, "paid_off_chapter": 5, "status": "active", "depends_on": ["fs_002"], "level": "中层", "introduced_by": "init"},
                {"id": "fs_002", "content": "环B", "planted_chapter": 1, "paid_off_chapter": 5, "status": "active", "depends_on": ["fs_001"], "level": "中层", "introduced_by": "init"},
                {"id": "fs_003", "content": "提前", "planted_chapter": 5, "paid_off_chapter": 3, "status": "active", "depends_on": [], "level": "表层", "introduced_by": "init"},
                {"id": "fs_004", "content": "超期", "planted_chapter": 1, "paid_off_chapter": 5, "status": "active", "depends_on": [], "level": "深层", "introduced_by": "init"}
            ],
            "validated_at": None,
            "validation_history": []
        }
    }
}


def _ctx(state, chapter=10):
    return CheckContext(project_root=Path("/tmp"), chapter_num=chapter, state=state, chapter_outline=None, previous_chapters=[], chapter_text=None)


def test_clean_dag_passes():
    p = P1ForeshadowDAG()
    blockers = p.check(_ctx(CLEAN_STATE, chapter=5))
    assert blockers == []


def test_dag_with_cycle_fails():
    p = P1ForeshadowDAG()
    blockers = p.check(_ctx(VIOLATION_STATE, chapter=5))
    assert any("循环" in b.message for b in blockers)


def test_dag_with_early_payoff_fails():
    p = P1ForeshadowDAG()
    blockers = p.check(_ctx(VIOLATION_STATE, chapter=5))
    assert any("提前" in b.message or "planted" in b.message for b in blockers)


def test_dag_with_overdue_fails():
    p = P1ForeshadowDAG()
    blockers = p.check(_ctx(VIOLATION_STATE, chapter=10))
    assert any("超期" in b.message or "fs_004" in b.message for b in blockers)


def test_missing_foreshadow_chain_fails():
    p = P1ForeshadowDAG()
    blockers = p.check(_ctx({}, chapter=5))
    assert any("未初始化" in b.message or "foreshadow_chain" in b.message for b in blockers)
```

- [ ] **Step 2: 运行测试，验证失败**

Run: `python -m pytest tests/unit/consistency/test_p1_foreshadow_dag.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 patch**

```python
# scripts/consistency/patches/p1_foreshadow_dag.py
"""Patch 1: Foreshadow DAG validation.

Source: 移植自 Openwrite-main/skills/foreshadowing-system（伏笔状态机+DAG 验证）
Path in references: references/02-Openwrite/upstream/skills/foreshadowing-system/
Original algorithm: 无环（DFS）+ 有向（planted<paid_off）+ 可达（路径存在）+ 超期（active && paid_off_chapter < current_chapter）
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker


class P1ForeshadowDAG(Patch):
    name = "foreshadow_dag"
    description = "伏笔 DAG 验证：无环 / 有向 / 可达 / 超期"
    depends_on = ()
    
    OVERDUE_TOLERANCE = 50  # 超期容忍窗口（章）
    
    def check(self, ctx: CheckContext) -> list[Blocker]:
        chain = ctx.state.get("story_craft", {}).get("foreshadow_chain")
        if chain is None:
            return [Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message="state.json 缺少 foreshadow_chain 字段",
                fix_hint="运行 `python webnovel.py consistency init --volume <current_volume>`"
            )]
        
        dag = chain.get("dag", [])
        blockers: list[Blocker] = []
        
        # 1. 无环检测（DFS）
        if self._has_cycle(dag):
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message="伏笔 DAG 存在循环引用",
                fix_hint="检查伏笔的 depends_on 是否形成回环"
            ))
        
        # 2. 有向：planted < paid_off
        for fs in dag:
            planted = fs.get("planted_chapter")
            paid_off = fs.get("paid_off_chapter")
            if planted is not None and paid_off is not None and planted >= paid_off:
                blockers.append(Blocker(
                    patch=self.name,
                    chapter=ctx.chapter_num,
                    message=f"伏笔 {fs.get('id')} planted_chapter({planted}) >= paid_off_chapter({paid_off})，提前回收",
                    fix_hint="调整 paid_off_chapter 到 planted_chapter 之后"
                ))
        
        # 3. 超期：active 状态且 paid_off_chapter + tolerance < current_chapter
        for fs in dag:
            if fs.get("status") != "active":
                continue
            paid_off = fs.get("paid_off_chapter")
            if paid_off is None:
                continue
            if ctx.chapter_num > paid_off + self.OVERDUE_TOLERANCE:
                blockers.append(Blocker(
                    patch=self.name,
                    chapter=ctx.chapter_num,
                    message=f"伏笔 {fs.get('id')} 应在第 {paid_off} 章回收但仍未回收（已过 {ctx.chapter_num - paid_off} 章）",
                    fix_hint=f"在本章或前 {self.OVERDUE_TOLERANCE} 章内回收 fs {fs.get('id')}，或更新 paid_off_chapter"
                ))
        
        return blockers
    
    def apply(self, ctx: ApplyContext) -> None:
        # No-op: dag 字段由 plan 阶段的 init 写入
        # 这里只记录 validated_at 时间戳
        chain = ctx.state.setdefault("story_craft", {}).setdefault("foreshadow_chain", {"version": 1, "dag": [], "validated_at": None, "validation_history": []})
        chain["validated_at"] = ctx.state.get("_last_modified_at")
    
    def _has_cycle(self, dag: list[dict]) -> bool:
        """DFS 检测环"""
        # Build adjacency
        graph: dict[str, list[str]] = {fs["id"]: fs.get("depends_on", []) for fs in dag}
        visited: set[str] = set()
        path: set[str] = set()
        
        def dfs(node: str) -> bool:
            if node in path:
                return True
            if node in visited:
                return False
            visited.add(node)
            path.add(node)
            for nxt in graph.get(node, []):
                if dfs(nxt):
                    return True
            path.remove(node)
            return False
        
        return any(dfs(fs["id"]) for fs in dag if fs["id"] not in visited)
```

- [ ] **Step 4: 运行测试，验证通过**

Run: `python -m pytest tests/unit/consistency/test_p1_foreshadow_dag.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 用 fixture 跑端到端**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from scripts.consistency.core.runner import ConsistencyRunner
from scripts.consistency.patches.p1_foreshadow_dag import P1ForeshadowDAG
from pathlib import Path

# clean
r = ConsistencyRunner(Path('tests/fixtures/cross_volume/project_clean'), patches=[P1ForeshadowDAG()])
print('clean chapter=5:', len(r.run_all(chapter=5)))

# violation
r2 = ConsistencyRunner(Path('tests/fixtures/cross_volume/project_dag_violation'), patches=[P1ForeshadowDAG()])
print('violation chapter=5:', [b.message for b in r2.run_all(chapter=5)])
print('violation chapter=10:', [b.message for b in r2.run_all(chapter=10)])
"
```
Expected: clean=0, violation chapter=5=[循环, 提前...], chapter=10=[循环, 提前, 超期]

- [ ] **Step 6: Commit**

```bash
git add scripts/consistency/patches/p1_foreshadow_dag.py tests/unit/consistency/test_p1_foreshadow_dag.py
git commit -m "feat(consistency): patch 1 — foreshadow DAG validation"
```

---

> **Pattern for Phase 2-7:** 后续 6 个补丁（anchor / event_matrix / pacing / state_revision / reader_contract / derived_views）每个遵循同一循环：
> 1. 写违规 fixture（Task X.1）
> 2. 写测试（Task X.2）
> 3. 实现 patch（Task X.3）
> 4. 跑通 + commit（Task X.4）
>
> 完整代码因篇幅省略。实现时严格按 spec §2.2-2.7 的数据模型和算法移植/设计。

---

## Phase 2：补丁 2 — Volume Anchor（任务 8-10）

### Task 8：fixture `project_anchor_overrun`

**Files:** Create `tests/fixtures/cross_volume/project_anchor_overrun/.webnovel/state.json`（anchor.current_chapter > total_chapters × 1.15）

### Task 9：实现 P2 + 测试

**Files:**
- Create: `scripts/consistency/patches/p2_volume_anchor.py`（移植自 novel-creator/outline_anchor_manager.py）
- Create: `tests/unit/consistency/test_p2_volume_anchor.py`

实现 check() 检测：
- 进度偏离预期 > 15%
- 正文违反 must_not_reveal（关键词扫描）
- must_achieve 在 current_chapter 未推进

参考代码骨架：
```python
class P2VolumeAnchor(Patch):
    name = "volume_anchor"
    description = "大纲 anchor 配额门禁"
    depends_on = ()
    
    def check(self, ctx: CheckContext) -> list[Blocker]:
        anchors = ctx.state.get("story_craft", {}).get("volume_anchors", {}).get("anchors", [])
        blockers = []
        for anchor in anchors:
            total = anchor.get("total_chapters", 0)
            current = anchor.get("current_chapter", 0)
            if total == 0:
                continue
            # 进度检查
            progress = current / total
            expected = ctx.chapter_num / total  # 简化：用当前章 / 总章
            if abs(progress - expected) > 0.15:
                blockers.append(Blocker(
                    patch=self.name,
                    chapter=ctx.chapter_num,
                    message=f"第{anchor['volume']}卷进度偏离预期 {progress:.0%} vs 期望 {expected:.0%}",
                    fix_hint="加快/放缓节奏，或调整剩余章纲"
                ))
            # must_not_reveal 检查
            if ctx.chapter_text:
                for forbidden in anchor.get("must_not_reveal", []):
                    if forbidden in ctx.chapter_text:
                        blockers.append(Blocker(
                            patch=self.name,
                            chapter=ctx.chapter_num,
                            message=f"正文泄露 anchor.must_not_reveal: '{forbidden}'",
                            fix_hint=f"删除 '{forbidden}' 相关内容，或调整 must_not_reveal 列表"
                        ))
        return blockers
    
    def apply(self, ctx: ApplyContext) -> None:
        anchors = ctx.state.setdefault("story_craft", {}).setdefault("volume_anchors", {"version": 1, "anchors": []})["anchors"]
        for anchor in anchors:
            if anchor.get("current_chapter", 0) < ctx.chapter_num:
                anchor["current_chapter"] = ctx.chapter_num
```

### Task 10：跑通 + commit

```bash
python -m pytest tests/unit/consistency/test_p2_volume_anchor.py -v
git add scripts/consistency/patches/p2_volume_anchor.py tests/unit/consistency/test_p2_volume_anchor.py tests/fixtures/cross_volume/project_anchor_overrun
git commit -m "feat(consistency): patch 2 — volume anchor quota gate"
```

---

## Phase 3：补丁 3 — Event Matrix（任务 11-13）

### Task 11：fixture `project_event_pattern_break`

故意连续 5 章都选 `conflict_thrill`（违反 max_consecutive_fast=2）。

### Task 12：实现 P3 + 测试

```python
# scripts/consistency/patches/p3_event_matrix.py
"""Patch 3: Event matrix — anti-pattern cooldown.

Source: 移植自 novel-creator-skill/scripts/event_matrix_scheduler.py
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/novel-creator-skill/scripts/event_matrix_scheduler.py
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker


EVENT_TYPES = ["conflict_thrill", "tension_escalation", "bond_deepening", "faction_building", "world_painting"]
FAST_TYPES = {"conflict_thrill", "tension_escalation"}
SOFT_TYPES = {"bond_deepening", "faction_building", "world_painting"}


class P3EventMatrix(Patch):
    name = "event_matrix"
    description = "事件矩阵防模式化：冷却 / 连续 / gentle 配额"
    depends_on = ("foreshadow_dag",)  # 用 foreshadow 索引
    
    def check(self, ctx: CheckContext) -> list[Blocker]:
        ems = ctx.state.get("story_craft", {}).get("event_matrix_state")
        if ems is None:
            return [Blocker(patch=self.name, chapter=ctx.chapter_num, message="event_matrix_state 未初始化", fix_hint="运行 consistency init")]
        
        history = ems.get("history", [])
        if not history:
            return []  # 没历史不报警
        
        # 检查最近 N 章是否违反规则
        # 取最近 max(gentle_window, max_consecutive_fast + 1) 章
        window_size = max(ems.get("gentle_window", 5), ems.get("max_consecutive_fast", 2) + 1)
        recent = history[-window_size:]
        
        blockers = []
        
        # 1. 连续快档上限
        consecutive_fast = 0
        for entry in reversed(recent):
            primary = entry.get("primary", "")
            if primary in FAST_TYPES:
                consecutive_fast += 1
            else:
                break
        max_allowed = ems.get("max_consecutive_fast", 2)
        if consecutive_fast > max_allowed:
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"连续 {consecutive_fast} 章使用快档事件类型（上限 {max_allowed}）",
                fix_hint="本章选 bond_deepening / world_painting / faction_building 中的一种"
            ))
        
        # 2. gentle 配额：每 N 章至少 1 个 soft
        gentle_window = ems.get("gentle_window", 5)
        recent_window = history[-gentle_window:] if len(history) >= gentle_window else history
        has_soft = any(entry.get("primary") in SOFT_TYPES for entry in recent_window)
        if not has_soft and len(recent_window) == gentle_window:
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"最近 {gentle_window} 章没有 soft 类型事件",
                fix_hint="本章选 bond_deepening / world_painting / faction_building"
            ))
        
        return blockers
    
    def apply(self, ctx: ApplyContext) -> None:
        # 调用方需传入当前章 primary event 类型，存储到 ctx.state 临时字段
        # 简化：apply 只更新 last_used_chapter
        ems = ctx.state.setdefault("story_craft", {}).setdefault("event_matrix_state", {"version": 1, "types": {}, "history": [], "gentle_window": 5, "max_consecutive_fast": 2})
        history = ems.setdefault("history", [])
        # 当前章 primary 从 chapter_outline 读（apply 上下文不带 outline，简化为 NoOp）
        # 真实场景在 skill 端 commit 时显式调用 patch.apply_with_primary()
        pass
```

### Task 13：跑通 + commit

```bash
python -m pytest tests/unit/consistency/test_p3_event_matrix.py -v
git commit -am "feat(consistency): patch 3 — event matrix anti-pattern"
```

---

## Phase 4：补丁 4 — Pacing Tracker（任务 14-16）

### Task 14：fixture `project_pacing_drift`

连续 3 章 tier=fast（违反 max_consecutive_fast=1）。

### Task 15：实现 P4

```python
# scripts/consistency/patches/p4_pacing_tracker.py
"""Patch 4: Pacing 3-tier tracker.

Source: 移植自 novel-creator-skill/scripts/pacing_tracker.py
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker


TIERS = {"fast", "medium", "slow"}


class P4PacingTracker(Patch):
    name = "pacing_tracker"
    description = "节奏 3 档追踪：连续快档上限 + 慢档配额"
    depends_on = ()
    
    def check(self, ctx: CheckContext) -> list[Blocker]:
        ph = ctx.state.get("story_craft", {}).get("pacing_history")
        if ph is None:
            return [Blocker(patch=self.name, chapter=ctx.chapter_num, message="pacing_history 未初始化", fix_hint="运行 consistency init")]
        
        history = ph.get("history", [])
        rules = ph.get("rules", {"max_consecutive_fast": 1, "slow_per_4_chapters_min": 1})
        
        blockers = []
        # 1. 连续快档
        consecutive_fast = 0
        for entry in reversed(history):
            if entry.get("tier") == "fast":
                consecutive_fast += 1
            else:
                break
        if consecutive_fast >= rules.get("max_consecutive_fast", 1):
            # 当前章也要 fast 才会触发（由 skill 在 commit 时设）
            # 这里只报警历史趋势
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"已连续 {consecutive_fast} 章快档（上限 {rules['max_consecutive_fast']}）",
                fix_hint="本章建议选 medium 或 slow"
            ))
        
        # 2. 每 4 章至少 1 慢档
        recent_4 = history[-4:]
        slow_count = sum(1 for e in recent_4 if e.get("tier") == "slow")
        if len(recent_4) == 4 and slow_count < rules.get("slow_per_4_chapters_min", 1):
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"最近 4 章只有 {slow_count} 章慢档（要求至少 {rules['slow_per_4_chapters_min']}）",
                fix_hint="本章或下一章选 slow"
            ))
        
        return blockers
    
    def apply(self, ctx: ApplyContext) -> None:
        # skill 在 commit 时显式调 apply_with_tier
        pass
```

### Task 16：跑通 + commit

```bash
python -m pytest tests/unit/consistency/test_p4_pacing_tracker.py -v
git commit -am "feat(consistency): patch 4 — pacing tracker"
```

---

## Phase 5：补丁 5 — State Revision（任务 17-19）

### Task 17：fixture `project_state_revision_stale`

ctx 传入的 revision=10，但 state._revision=15（stale）。

### Task 18：实现 P5

```python
# scripts/consistency/patches/p5_state_revision.py
"""Patch 5: expected_state_revision — prevent stale commits.

Source: 借鉴 oh-story-claudecode/skills/story-import/references/state-tracking.md 的 state_revision 防 stale 机制
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker


class P5StateRevision(Patch):
    name = "state_revision"
    description = "state_revision 防 stale：提交时验证 revision 匹配"
    depends_on = ()
    
    def check(self, ctx: CheckContext) -> list[Blocker]:
        current_rev = ctx.state.get("state", {}).get("_revision", 0)
        # 调用方传 expected_revision 到 ctx.state（hack：临时字段）
        expected_rev = ctx.state.get("_expected_revision")
        if expected_rev is None:
            return []  # 没传 expected = 跳过
        if expected_rev != current_rev:
            return [Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"state_revision 不匹配：期望 {expected_rev}，实际 {current_rev}",
                fix_hint="重新读取 state.json 后重试"
            )]
        return []
    
    def apply(self, ctx: ApplyContext) -> None:
        # +1 revision
        state_meta = ctx.state.setdefault("state", {})
        state_meta["_revision"] = state_meta.get("_revision", 0) + 1
        state_meta["_last_modified_by"] = f"webnovel-write/ch{ctx.chapter_num}"
        # _last_modified_at 用 wall-clock；写盘前注入
```

### Task 19：跑通 + commit

```bash
python -m pytest tests/unit/consistency/test_p5_state_revision.py -v
git commit -am "feat(consistency): patch 5 — state revision"
```

---

## Phase 6：补丁 6 — Reader Contract（任务 20-22）

### Task 20：fixture `project_reader_contract_breach`

expectation_debt 中有 5 项未偿还，且当前章未新增任何期待债。

### Task 21：实现 P6

```python
# scripts/consistency/patches/p6_reader_contract.py
"""Patch 6: Reader contract 5 dimensions.

Source: 借鉴 oh-story-claudecode/skills/story-long-write/references/reader-contract-and-progression.md
Dimensions: 因果权 / 期待债 / 终局储备 / 换书债 / 履约爽文
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker


class P6ReaderContract(Patch):
    name = "reader_contract"
    description = "读者契约 5 维度：因果权 + 期待债 + 终局储备 + 换书债 + 履约爽文"
    depends_on = ("foreshadow_dag", "pacing_tracker")
    
    DEBT_LIMIT = 10  # 未偿期待债上限
    ENDGAME_RESERVE_USED_LIMIT = 1  # 单卷最多用 1 个终局底牌
    
    def check(self, ctx: CheckContext) -> list[Blocker]:
        rc = ctx.state.get("story_craft", {}).get("reader_contract")
        if rc is None:
            return [Blocker(patch=self.name, chapter=ctx.chapter_num, message="reader_contract 未初始化", fix_hint="运行 consistency init")]
        
        blockers = []
        
        # 1. 期待债堆积
        debts = [d for d in rc.get("expectation_debt", []) if d.get("satisfied_chapter") is None]
        if len(debts) > self.DEBT_LIMIT:
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"未偿期待债 {len(debts)} 项，超过上限 {self.DEBT_LIMIT}",
                fix_hint="本章偿还至少 1 项期待债，或减少新增"
            ))
        
        # 2. 因果权：主角用了未铺垫的能力（关键词扫描，正文里出现 setup_chapter 为空的"觉醒"等）
        if ctx.chapter_text:
            setup_needed = rc.get("causal_credits", {}).get("protagonist_actions_used_without_setup", [])
            for action in setup_needed:
                if action in ctx.chapter_text:
                    blockers.append(Blocker(
                        patch=self.name,
                        chapter=ctx.chapter_num,
                        message=f"主角使用未铺垫的能力/事件：'{action}'",
                        fix_hint=f"在前文铺垫 '{action}' 或在本章加入解释"
                    ))
        
        # 3. 终局底牌超用
        endgame_used = sum(1 for r in rc.get("endgame_reserves", []) if r.get("used_chapter") is not None and r["used_chapter"] <= ctx.chapter_num)
        if endgame_used > self.ENDGAME_RESERVE_USED_LIMIT:
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"终局底牌已用 {endgame_used} 个（单卷上限 {self.ENDGAME_RESERVE_USED_LIMIT}）",
                fix_hint="推迟使用剩余底牌，留到高潮"
            ))
        
        return blockers
    
    def apply(self, ctx: ApplyContext) -> None:
        rc = ctx.state.setdefault("story_craft", {}).setdefault("reader_contract", {"version": 1, "expectation_debt": [], "causal_credits": {"protagonist_actions_used_without_setup": []}, "endgame_reserves": [], "swap_debts": []})
        # 默认 NoOp；skill 端通过 helper 函数更新字段
```

### Task 22：跑通 + commit

```bash
python -m pytest tests/unit/consistency/test_p6_reader_contract.py -v
git commit -am "feat(consistency): patch 6 — reader contract"
```

---

## Phase 7：补丁 7 — Derived Views（任务 23-25）

### Task 23：fixture `project_derived_view_mismatch`

state 中 foreshadow_chain.dag 含 fs_005，但 .webnovel/views/foreshadow_table.md 不含 fs_005（派生视图过期）。

### Task 24：实现 P7

```python
# scripts/consistency/patches/p7_derived_views.py
"""Patch 7: Derived views — generated from state, must stay in sync.

Source: 借鉴 oh-story-claudecode tracking_commit.py 的"派生视图由工具生成"模式
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker
from pathlib import Path
import hashlib


DERIVED_VIEWS = {
    "foreshadow_table": ".webnovel/views/foreshadow_table.md",
    "pacing_chart": ".webnovel/views/pacing_chart.md",
    "summary": ".webnovel/summaries/{chapter:04d}.md",
}


class P7DerivedViews(Patch):
    name = "derived_views"
    description = "派生视图与 state 一致性"
    depends_on = ("state_revision",)
    
    def check(self, ctx: CheckContext) -> list[Blocker]:
        views_dir = ctx.project_root / ".webnovel" / "views"
        if not views_dir.exists():
            return []  # 派生视图未启用，跳过
        
        blockers = []
        # 检查 foreshadow_table 是否含 state 中所有 fs
        fs_table = views_dir / "foreshadow_table.md"
        if fs_table.exists():
            content = fs_table.read_text(encoding="utf-8")
            dag = ctx.state.get("story_craft", {}).get("foreshadow_chain", {}).get("dag", [])
            for fs in dag:
                if fs.get("id") not in content:
                    blockers.append(Blocker(
                        patch=self.name,
                        chapter=ctx.chapter_num,
                        message=f"派生视图 foreshadow_table.md 缺少伏笔 {fs.get('id')}",
                        fix_hint=f"运行 consistency apply 重新生成 views/"
                    ))
        
        return blockers
    
    def apply(self, ctx: ApplyContext) -> None:
        views_dir = ctx.project_root / ".webnovel" / "views"
        views_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成 foreshadow_table.md
        dag = ctx.state.get("story_craft", {}).get("foreshadow_chain", {}).get("dag", [])
        lines = ["# 伏笔表", "", "| ID | 内容 | 层级 | 埋设章 | 回收章 | 状态 |", "|---|---|---|---|---|---|"]
        for fs in dag:
            lines.append(f"| {fs.get('id', '')} | {fs.get('content', '')} | {fs.get('level', '')} | {fs.get('planted_chapter', '')} | {fs.get('paid_off_chapter') or '未回收'} | {fs.get('status', '')} |")
        (views_dir / "foreshadow_table.md").write_text("\n".join(lines), encoding="utf-8")
```

### Task 25：跑通 + commit

```bash
python -m pytest tests/unit/consistency/test_p7_derived_views.py -v
git commit -am "feat(consistency): patch 7 — derived views"
```

---

## Phase 8：集成

### Task 26：把 7 个 patch 注册到 Runner 默认列表

**Files:** Modify `scripts/consistency/core/runner.py`

替换 `_default_patches`：

```python
def _default_patches(self) -> list[Patch]:
    from ..patches.p1_foreshadow_dag import P1ForeshadowDAG
    from ..patches.p2_volume_anchor import P2VolumeAnchor
    from ..patches.p3_event_matrix import P3EventMatrix
    from ..patches.p4_pacing_tracker import P4PacingTracker
    from ..patches.p5_state_revision import P5StateRevision
    from ..patches.p6_reader_contract import P6ReaderContract
    from ..patches.p7_derived_views import P7DerivedViews
    return [
        P1ForeshadowDAG(),
        P2VolumeAnchor(),
        P3EventMatrix(),
        P4PacingTracker(),
        P5StateRevision(),
        P6ReaderContract(),
        P7DerivedViews(),
    ]
```

### Task 27：E2E 集成测试

**Files:** Create `tests/integration/test_runner_e2e.py`

```python
import pytest
from pathlib import Path
from scripts.consistency.core.runner import ConsistencyRunner


FIXTURES = Path(__file__).parent.parent / "fixtures" / "cross_volume"


@pytest.mark.parametrize("fixture_name,chapter,expected_patch,expected_keyword", [
    ("project_clean", 5, None, None),
    ("project_dag_violation", 5, "foreshadow_dag", "循环"),
    ("project_dag_violation", 10, "foreshadow_dag", "超期"),
])
def test_runner_with_fixture(fixture_name, chapter, expected_patch, expected_keyword):
    runner = ConsistencyRunner(FIXTURES / fixture_name)
    blockers = runner.run_all(chapter=chapter)
    if expected_patch is None:
        assert blockers == []
    else:
        matching = [b for b in blockers if b.patch == expected_patch]
        assert any(expected_keyword in b.message for b in matching), \
            f"Expected '{expected_keyword}' in {expected_patch} blockers, got: {[b.message for b in matching]}"
```

```bash
python -m pytest tests/integration/test_runner_e2e.py -v
```

### Task 28：CLI 接线 main()

**Files:** Modify `scripts/consistency/cli.py`

把 stub `main()` 替换为真实现（read state.json → 调 runner → 输出 blocker JSON）。

### Task 29：webnovel-plan 集成

**Files:** Modify `.claude/plugins/zhanghui/skills/webnovel-plan/SKILL.md`

在 Step 7 拆章完成后追加：

```markdown
### 一致性检查（plan 阶段）

拆完章后，对每个新章调用：
```bash
python webnovel.py consistency check --project-root "$PROJECT_ROOT" --chapter {chapter_num}
```
如有 BLOCKER：用户改章纲后再跑，直到通过。
```

### Task 30：webnovel-write 集成

**Files:** Modify `.claude/plugins/zhanghui/skills/webnovel-write/SKILL.md`

Step 2A 写前：
```bash
python webnovel.py consistency check --project-root "$PROJECT_ROOT" --chapter {chapter_num}
```
Step 5 写后 commit：
```bash
python webnovel.py consistency apply --project-root "$PROJECT_ROOT" --chapter {chapter_num}
```

### Task 31：webnovel-review 集成

**Files:** Modify `.claude/plugins/zhanghui/skills/webnovel-review/SKILL.md`

在 reviewer 输出追加"consistency 维度"：列出所有 BLOCKER。

### Task 32：最终验收

```bash
# 全部测试
python -m pytest tests/ -v

# 全部 fixture 端到端
for fix in tests/fixtures/cross_volume/project_*/; do
  for ch in 5 10; do
    echo "=== $fix chapter=$ch ==="
    python webnovel.py consistency check --project-root "$fix" --chapter $ch
  done
done

# Commit
git commit --allow-empty -m "feat(consistency): 7 patches complete + integrated"
```

---

## 完成定义（DoD）

- [ ] 7 个 patch 单元测试全过
- [ ] 7 个 fixture 故意违规场景正确触发
- [ ] Runner e2e 集成测试过
- [ ] CLI 4 个子命令（check/list/init/override）能用
- [ ] webnovel-plan / webnovel-write / webnovel-review SKILL.md 已集成
- [ ] 现有 changes_gate.py / reviewer.py 不被破坏
- [ ] 不破坏现有项目（init 命令向后兼容）
