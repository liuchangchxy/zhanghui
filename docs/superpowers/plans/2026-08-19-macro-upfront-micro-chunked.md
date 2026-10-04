# Macro-Upfront + Micro-Chunked Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the spec `docs/superpowers/specs/2026-08-19-macro-upfront-micro-chunked-design.md` — let `/webnovel-plan --all-volumes`铺 N 卷蓝图 (每卷 15-beat + 章纲 + 时间线), while keeping default (无 flag) 行为完全兼容现状 + 引入跨卷伏笔账本 + chunked_write_policy (denova/oh-story 模式).

**Architecture:**
- **Layer 1 跨卷骨架**: `--all-volumes` 触发, 读 `volumes[]` confirmed 卷, 对每个卷产 `第N卷-详细大纲.md` / `第N卷-15节拍.md` / `第N卷-时间线.md` 三件套.
- **Layer 2 卷内蓝图**: 复用现有 plan 流程, 不变.
- **Layer 3 章节执行**: 1 章/call 不变; 加 chunked_write_policy 仅影响 UI 提交节奏.
- **跨卷伏笔账本**: 新加 `state.json.project_info.promise_ledger` + `cross_volume_beat_map`; overdue 触发 BLOCKER.
- **默认兼容**: `test_plan_v_plus_one_anchor` 不变, 新增 `--all-volumes` 分支.

**Tech Stack:** Python 3.10+ (dataclass, enum), pytest, Claude Code SKILL.md (markdown).

---

## 文件改动总览（先于 Task 1 一次读全）

| 路径 | 类型 | 行数参考 |
|---|---|---|
| `.claude/plugins/zhanghui/scripts/data_modules/volume_state.py` | 改 | 282 行（commit 580af18） |
| `.claude/plugins/zhanghui/scripts/data_modules/promise_ledger.py` | **新增** | ~120 行 |
| `.claude/plugins/zhanghui/scripts/data_modules/chunked_write.py` | **新增** | ~80 行 |
| `.claude/plugins/zhanghui/scripts/story_craft.py` | 改 | 382 行（line 315 `init_volume_beat` 硬限） |
| `.claude/plugins/zhanghui/scripts/update_master_outline.py` | 改 | 324 行（line 37 `_require_current_volume_artifacts`） |
| `.claude/plugins/zhanghui/scripts/init_project.py` | 改 | 1059 行（line 965 `main()` argparse） |
| `.claude/plugins/zhanghui/skills/webnovel-plan/SKILL.md` | 改 | 467 行（Step 9） |
| `.claude/plugins/zhanghui/skills/webnovel-write/SKILL.md` | 改 | 760 行（Step 0 pre-write gate） |
| `.claude/plugins/zhanghui/templates/output/大纲-总纲.md` | 改 | 模板（加跨卷伏笔账本 + 节拍映射表头） |
| `.claude/plugins/zhanghui/scripts/tests/unit/test_promise_ledger.py` | **新增** | TDD 红→绿 |
| `.claude/plugins/zhanghui/scripts/tests/unit/test_chunked_write.py` | **新增** | TDD 红→绿 |
| `.claude/plugins/zhanghui/scripts/tests/integration/test_plan_all_volumes.py` | **新增** | TDD 红→绿 |
| `.claude/plugins/zhanghui/scripts/tests/integration/test_e2e_macro_micro.py` | **新增** | 端到端 |
| `bin/deploy-plugin.sh` | 改 | 新文件加进 RUNTIME_FILES / TEST_FILES |
| `.claude/plugins/zhanghui/README.md` | 改 | 加 `--all-volumes` 文档 |

---

### Task 1: promise_ledger dataclass + ForeshadowEntry + ledger 状态机（不依赖 state.json）

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/promise_ledger.py`
- Test: `.claude/plugins/zhanghui/scripts/tests/unit/test_promise_ledger.py`

- [ ] **Step 1: 写失败测试 — ForeshadowEntry 必填字段**

```python
# .claude/plugins/zhanghui/scripts/tests/unit/test_promise_ledger.py
import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from data_modules.promise_ledger import (
    ForeshadowEntry,
    ForeshadowStatus,
    PromiseLedger,
)


def test_foreshadow_entry_required_fields():
    """ForeshadowEntry must carry planted_volume, expected_payoff_volume, expected_payoff_chapter."""
    now = datetime.now(timezone.utc).isoformat()
    e = ForeshadowEntry(
        id="fs_001",
        type="foreshadow",
        depth=3,
        planted_chapter=12,
        planted_volume=1,
        expected_payoff_chapter=145,
        expected_payoff_volume=3,
        status=ForeshadowStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    assert e.planted_volume == 1
    assert e.expected_payoff_volume == 3
    assert e.id == "fs_001"


def test_planted_must_precede_payoff():
    """planted_volume > expected_payoff_volume should raise."""
    now = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="planted_volume.*must precede.*expected_payoff_volume"):
        ForeshadowEntry(
            id="fs_bad",
            type="foreshadow", depth=1,
            planted_chapter=100, planted_volume=3,
            expected_payoff_chapter=50, expected_payoff_volume=1,  # backwards!
            status=ForeshadowStatus.PENDING,
            created_at=now, updated_at=now,
        )


def test_planted_eq_payoff_allowed_within_volume():
    """Same-volume plant and payoff is valid (same arc)."""
    now = datetime.now(timezone.utc).isoformat()
    e = ForeshadowEntry(
        id="fs_002",
        type="foreshadow", depth=2,
        planted_chapter=10, planted_volume=2,
        expected_payoff_chapter=50, expected_payoff_volume=2,  # same volume OK
        status=ForeshadowStatus.PENDING,
        created_at=now, updated_at=now,
    )
    assert e.planted_volume == e.expected_payoff_volume
```

- [ ] **Step 2: 跑测试确认红**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/unit/test_promise_ledger.py -v
```
Expected: `ModuleNotFoundError: No module named 'data_modules.promise_ledger'`.

- [ ] **Step 3: 写最小实现**

```python
# .claude/plugins/zhanghui/scripts/data_modules/promise_ledger.py
"""Promise ledger for cross-volume foreshadowing.

Spec: docs/superpowers/specs/2026-08-19-macro-upfront-micro-chunked-design.md §5.1.

Openwrite / neuro-book / QMAI 模式: 任意时刻状态推算 + 可审计.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum


class ForeshadowStatus(str, Enum):
    PENDING = "pending"
    ADVANCED = "advanced"
    PAID_OFF = "paid_off"
    OVERDUE = "overdue"


@dataclass
class ForeshadowEntry:
    id: str
    type: str  # 'foreshadow' | 'promise' | 'callback'
    depth: int
    planted_chapter: int
    planted_volume: int
    expected_payoff_chapter: int
    expected_payoff_volume: int
    status: ForeshadowStatus = ForeshadowStatus.PENDING
    created_at: str = ""
    updated_at: str = ""
    notes: str = ""

    def __post_init__(self):
        if self.planted_volume > self.expected_payoff_volume:
            raise ValueError(
                f"planted_volume ({self.planted_volume}) must precede "
                f"expected_payoff_volume ({self.expected_payoff_volume})"
            )
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class PromiseLedger:
    """List of ForeshadowEntry + helper methods.

    Owned state lives in state.json.project_info.promise_ledger (list[dict]).
    """
    entries: list[ForeshadowEntry] = field(default_factory=list)

    def to_list(self) -> list[dict]:
        return [e.to_dict() for e in self.entries]
```

- [ ] **Step 4: 跑测试确认绿**

Run: 同 Step 2.
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/zhanghui/scripts/data_modules/promise_ledger.py
git add .claude/plugins/zhanghui/scripts/tests/unit/test_promise_ledger.py
git commit -m "feat(promise-ledger): ForeshadowEntry dataclass with planted_volume/payoff invariant

Per spec 2026-08-19 §5.1 cross-volume foreshadowing schema.
Openwrite/neuro-book/QMAI promise ledger pattern: planted_volume must
precede expected_payoff_volume; same-volume plant/payoff allowed.
3 unit tests green."
```

---

### Task 2: PromiseLedger API — upsert / advance / payoff / overdue detection

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/promise_ledger.py`
- Modify: `.claude/plugins/zhanghui/scripts/tests/unit/test_promise_ledger.py`

- [ ] **Step 1: 写失败测试 — ledger CRUD + overdue detection**

```python
# Append to test_promise_ledger.py
def test_ledger_upsert_new_entry():
    ledger = PromiseLedger()
    e = ForeshadowEntry(
        id="fs_x", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    ledger.upsert(e)
    assert len(ledger.entries) == 1
    assert ledger.entries[0].id == "fs_x"


def test_ledger_upsert_existing_replaces():
    ledger = PromiseLedger()
    e1 = ForeshadowEntry(
        id="fs_x", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    e2 = ForeshadowEntry(
        id="fs_x", type="foreshadow", depth=2,  # depth changed
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.ADVANCED,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T01:00:00+00:00",
    )
    ledger.upsert(e1)
    ledger.upsert(e2)
    assert len(ledger.entries) == 1
    assert ledger.entries[0].depth == 2
    assert ledger.entries[0].status == ForeshadowStatus.ADVANCED


def test_advance_then_payoff():
    ledger = PromiseLedger()
    e = ForeshadowEntry(
        id="fs_y", type="foreshadow", depth=2,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    ledger.upsert(e)
    ledger.advance("fs_y", at_chapter=50)
    assert ledger.entries[0].status == ForeshadowStatus.ADVANCED
    ledger.payoff("fs_y", at_chapter=98)
    assert ledger.entries[0].status == ForeshadowStatus.PAID_OFF


def test_overdue_detection_by_chapter():
    ledger = PromiseLedger()
    # Expected payoff at ch 100, but current is 110 — overdue
    e = ForeshadowEntry(
        id="fs_over", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    ledger.upsert(e)
    overdue = ledger.list_overdue(current_chapter=110, current_volume=2)
    assert len(overdue) == 1
    assert overdue[0].id == "fs_over"


def test_no_overdue_when_paid_off():
    ledger = PromiseLedger()
    e = ForeshadowEntry(
        id="fs_z", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PAID_OFF,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    ledger.upsert(e)
    overdue = ledger.list_overdue(current_chapter=200, current_volume=3)
    assert overdue == []


def test_filter_by_volume():
    ledger = PromiseLedger()
    for vol in (1, 2, 3):
        ledger.upsert(ForeshadowEntry(
            id=f"fs_v{vol}", type="foreshadow", depth=1,
            planted_chapter=10, planted_volume=vol,
            expected_payoff_chapter=100, expected_payoff_volume=vol,
            status=ForeshadowStatus.PENDING,
            created_at="2026-08-19T00:00:00+00:00",
            updated_at="2026-08-19T00:00:00+00:00",
        ))
    in_vol_2 = ledger.list_for_volume(2)
    assert len(in_vol_2) == 1
    assert in_vol_2[0].id == "fs_v2"
```

- [ ] **Step 2: 跑测试确认红**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/unit/test_promise_ledger.py -v
```
Expected: 3 passed (Task 1) + 6 failed (新 API).

- [ ] **Step 3: 扩展实现**

修改 `PromiseLedger` 类, 添加方法:

```python
# Append to scripts/data_modules/promise_ledger.py
    def upsert(self, entry: ForeshadowEntry) -> None:
        for i, existing in enumerate(self.entries):
            if existing.id == entry.id:
                entry.updated_at = datetime.now(timezone.utc).isoformat()
                self.entries[i] = entry
                return
        self.entries.append(entry)

    def advance(self, entry_id: str, at_chapter: int) -> None:
        self._mutate(entry_id, ForeshadowStatus.ADVANCED, at_chapter)

    def payoff(self, entry_id: str, at_chapter: int) -> None:
        self._mutate(entry_id, ForeshadowStatus.PAID_OFF, at_chapter)

    def _mutate(self, entry_id: str, status: ForeshadowStatus, at_chapter: int) -> None:
        for e in self.entries:
            if e.id == entry_id:
                e.status = status
                e.updated_at = datetime.now(timezone.utc).isoformat()
                return
        raise KeyError(f"foreshadow not found: {entry_id}")

    def list_overdue(self, current_chapter: int, current_volume: int) -> list[ForeshadowEntry]:
        return [
            e for e in self.entries
            if e.status != ForeshadowStatus.PAID_OFF
            and (
                e.expected_payoff_volume < current_volume
                or (e.expected_payoff_volume == current_volume
                    and e.expected_payoff_chapter < current_chapter)
            )
        ]

    def list_for_volume(self, volume: int) -> list[ForeshadowEntry]:
        return [e for e in self.entries if e.planted_volume == volume
                or e.expected_payoff_volume == volume]
```

- [ ] **Step 4: 跑测试确认绿**

Run: 同 Step 2.
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/zhanghui/scripts/data_modules/promise_ledger.py
git add .claude/plugins/zhanghui/scripts/tests/unit/test_promise_ledger.py
git commit -m "feat(promise-ledger): upsert / advance / payoff / list_overdue / list_for_volume

6 new tests green. Spec 2026-08-19 §5.1 cross-volume ledger API.
Overdue detection: paid_off entries excluded; current_volume > payoff_volume
counts as overdue (whole-volume skip); same-volume payoffs check chapter."
```

---

### Task 3: VolumeStateManager 接入 promise_ledger（state.json 持久化）

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/volume_state.py`
- Modify: `.claude/plugins/zhanghui/scripts/tests/unit/test_volume_state.py`

- [ ] **Step 1: 写失败测试 — VolumeStateManager 读写 promise_ledger**

```python
# Append to test_volume_state.py
from data_modules.promise_ledger import ForeshadowEntry, ForeshadowStatus, PromiseLedger


def test_volume_state_owns_promise_ledger(fresh_state):
    """VolumeStateManager must read/write promise_ledger via project_info."""
    from data_modules.volume_state import VolumeStateManager
    mgr = VolumeStateManager(fresh_state)
    e = ForeshadowEntry(
        id="fs_001", type="foreshadow", depth=3,
        planted_chapter=12, planted_volume=1,
        expected_payoff_chapter=145, expected_payoff_volume=3,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    mgr.upsert_promise_entry(e)
    # Persisted to state.json
    assert "promise_ledger" in fresh_state["project_info"]
    assert fresh_state["project_info"]["promise_ledger"][0]["id"] == "fs_001"
    # Round-trip: new manager reads from same state
    mgr2 = VolumeStateManager(fresh_state)
    ledger = mgr2.get_promise_ledger()
    assert len(ledger.entries) == 1
    assert ledger.entries[0].id == "fs_001"


def test_volume_state_list_overdue_foreshadows(fresh_state):
    """VolumeStateManager.list_overdue_foreshadows uses current chapter/volume."""
    from data_modules.volume_state import VolumeStateManager
    mgr = VolumeStateManager(fresh_state)
    # Plant in V1, expected payoff V2 ch100
    e = ForeshadowEntry(
        id="fs_over", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    )
    mgr.upsert_promise_entry(e)
    # No overdue at V1 ch50
    assert mgr.list_overdue_foreshadows(current_chapter=50, current_volume=1) == []
    # Overdue at V2 ch50 (we've already moved past V2's start, payoff not done)
    overdue = mgr.list_overdue_foreshadows(current_chapter=50, current_volume=2)
    assert len(overdue) == 1
    assert overdue[0].id == "fs_over"


def test_volume_state_payoff_writes_back(fresh_state):
    """mgr.payoff_foreshadow must persist status=paid_off to state.json."""
    from data_modules.volume_state import VolumeStateManager
    mgr = VolumeStateManager(fresh_state)
    mgr.upsert_promise_entry(ForeshadowEntry(
        id="fs_p", type="foreshadow", depth=1,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    mgr.payoff_foreshadow("fs_p", at_chapter=98)
    assert fresh_state["project_info"]["promise_ledger"][0]["status"] == "paid_off"
```

- [ ] **Step 2: 跑测试确认红**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/unit/test_volume_state.py::test_volume_state_owns_promise_ledger -v
```
Expected: AttributeError / ImportError related to upsert_promise_entry.

- [ ] **Step 3: 实现 VolumeStateManager 新方法**

修改 `.claude/plugins/zhanghui/scripts/data_modules/volume_state.py`:

```python
# Append to imports at top
from data_modules.promise_ledger import ForeshadowEntry, PromiseLedger  # noqa: E402

# Append to VolumeStateManager class (after list_volumes):
    # ----- promise ledger -----

    def get_promise_ledger(self) -> PromiseLedger:
        """Read promise_ledger from state.json.project_info."""
        raw = self.state.get("project_info", {}).get("promise_ledger", [])
        entries: list[ForeshadowEntry] = []
        for d in raw:
            entries.append(ForeshadowEntry(
                id=d["id"], type=d["type"], depth=d["depth"],
                planted_chapter=d["planted_chapter"],
                planted_volume=d["planted_volume"],
                expected_payoff_chapter=d["expected_payoff_chapter"],
                expected_payoff_volume=d["expected_payoff_volume"],
                status=ForeshadowStatus(d["status"]),
                created_at=d.get("created_at", ""),
                updated_at=d.get("updated_at", ""),
                notes=d.get("notes", ""),
            ))
        return PromiseLedger(entries=entries)

    def _write_promise_ledger(self, ledger: PromiseLedger) -> None:
        self.state.setdefault("project_info", {})["promise_ledger"] = ledger.to_list()

    def upsert_promise_entry(self, entry: ForeshadowEntry) -> None:
        ledger = self.get_promise_ledger()
        ledger.upsert(entry)
        self._write_promise_ledger(ledger)

    def advance_foreshadow(self, entry_id: str, at_chapter: int) -> None:
        ledger = self.get_promise_ledger()
        ledger.advance(entry_id, at_chapter)
        self._write_promise_ledger(ledger)

    def payoff_foreshadow(self, entry_id: str, at_chapter: int) -> None:
        ledger = self.get_promise_ledger()
        ledger.payoff(entry_id, at_chapter)
        self._write_promise_ledger(ledger)

    def list_overdue_foreshadows(self, current_chapter: int, current_volume: int) -> list[ForeshadowEntry]:
        return self.get_promise_ledger().list_overdue(current_chapter, current_volume)
```

并在 imports 加 `ForeshadowStatus`:

```python
from data_modules.promise_ledger import ForeshadowEntry, ForeshadowStatus, PromiseLedger  # noqa: E402
```

- [ ] **Step 4: 跑测试确认绿**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/unit/test_volume_state.py -v
```
Expected: 全部通过 (含 Task 3 新增 3 个 + 原 16 个).

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/zhanghui/scripts/data_modules/volume_state.py
git add .claude/plugins/zhanghui/scripts/tests/unit/test_volume_state.py
git commit -m "feat(volume-state): promise_ledger persistence + overdue query API

VolumeStateManager now owns state.json.project_info.promise_ledger.
New: upsert_promise_entry / advance_foreshadow / payoff_foreshadow /
list_overdue_foreshadows. 3 new tests green; existing 16 tests
unaffected (round-trip safety verified)."
```

---

### Task 4: story_craft.py — `init_volume_beat` 跨卷扩展（去硬限）

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/story_craft.py`
- Modify: `.claude/plugins/zhanghui/scripts/tests/unit/` （新文件 test_story_craft_multivolume.py）

- [ ] **Step 1: 写失败测试 — 跨卷初始化 V1+V2 都成功**

```python
# .claude/plugins/zhanghui/scripts/tests/unit/test_story_craft_multivolume.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from story_craft import init_volume_beat, check_volume_beat


def test_init_volume_beat_v1_then_v2():
    """Spec §6.2: multi-volume supported. V1 + V2 must coexist."""
    state: dict = {}
    init_volume_beat(state, volume=1, total_chapters=80)
    init_volume_beat(state, volume=2, total_chapters=80)
    vb = state["story_craft"]["volume_beat"]
    # New schema: dict[vol, beat_sheet]
    assert isinstance(vb, dict)
    assert vb["1"]["volume"] == 1
    assert vb["2"]["volume"] == 2


def test_check_volume_beat_for_v2_after_v1_initialized():
    """check_volume_beat must work for V2 even if V1 was already initialized."""
    state: dict = {}
    init_volume_beat(state, volume=1, total_chapters=80)
    init_volume_beat(state, volume=2, total_chapters=80)
    issues = check_volume_beat(state, volume=2, current_chapter=20)
    # Should return issues for V2's Midpoint/All Is Lost, NOT raise
    assert isinstance(issues, list)


def test_init_volume_beat_idempotent_per_volume():
    """Calling init_volume_beat(1) twice must not clobber existing data."""
    state: dict = {}
    init_volume_beat(state, volume=1, total_chapters=80)
    # Fill a beat
    state["story_craft"]["volume_beat"]["1"]["beats"][10]["filled"] = True
    # Re-init
    init_volume_beat(state, volume=1, total_chapters=80)
    # Filled state preserved (no-op)
    assert state["story_craft"]["volume_beat"]["1"]["beats"][10]["filled"] is True
```

- [ ] **Step 2: 跑测试确认红**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/unit/test_story_craft_multivolume.py -v
```
Expected: FAIL with `multi-volume not yet supported (requested volume 2)`.

- [ ] **Step 3: 修改 `init_volume_beat` schema — 改成 dict[vol, beat_sheet]**

修改 `.claude/plugins/zhanghui/scripts/story_craft.py:308-330`:

```python
# Replace init_volume_beat body (lines 308-330) with:
    percentages = [0.01, 0.05, 0.10, 0.10, 0.20, 0.20, 0.22, 0.50, 0.50, 0.75, 0.75, 0.80, 0.80, 0.99, 1.00]
    if len(percentages) != 15:
        raise ValueError("internal: percentages must match 15 beats")
    sc = state.setdefault("story_craft", {})
    # New schema: dict[volume_id, beat_sheet]. Migrate from legacy single-volume.
    vb = sc.get("volume_beat")
    if vb is None:
        vb = {}
        sc["volume_beat"] = vb
    elif isinstance(vb, dict) and "volume" in vb:
        # Legacy schema: single volume_beat dict. Migrate to multi-volume.
        legacy_vol = str(vb["volume"])
        vb = {legacy_vol: vb}
        sc["volume_beat"] = vb
    if str(volume) in vb:
        # Same volume already initialized — no-op (idempotent).
        return state
    beats = []
    for name, pct in zip(VALID_BEATS, percentages):
        ch = max(1, round(pct * total_chapters))
        beats.append({"name": name, "chapter": ch, "filled": False, "notes": None})
    vb[str(volume)] = {
        "volume": volume,
        "total_chapters": total_chapters,
        "beats": beats,
    }
    return state
```

并修改 `check_volume_beat` (lines 346-383) schema 读取:

```python
# Replace lines 361-368 with:
    vb_raw = state.get("story_craft", {}).get("volume_beat")
    if vb_raw is None:
        return [f"BLOCKER: story_craft.volume_beat not initialized for volume {volume} — run init-volume-beat first"]
    # New schema: dict[vol, beat_sheet]
    if isinstance(vb_raw, dict) and "volume" in vb_raw:
        # Legacy single-volume schema
        if vb_raw.get("volume") != volume:
            raise ValueError(
                f"volume_beat initialized for volume {vb_raw.get('volume')}; "
                f"multi-volume not yet supported (requested volume {volume})"
            )
        vb = vb_raw
    else:
        # Multi-volume dict schema
        vb = vb_raw.get(str(volume))
        if vb is None:
            return [f"BLOCKER: story_craft.volume_beat not initialized for volume {volume} — run init-volume-beat first"]
```

并修改 `fill_beat` (lines 333-343):

```python
# Replace fill_beat body:
def fill_beat(state: dict, volume: int, beat_name: str, chapter: int, notes: str) -> dict:
    sc = state.get("story_craft", {})
    vb_raw = sc.get("volume_beat")
    if vb_raw is None:
        raise ValueError(f"volume {volume} not initialized; run init-volume-beat first")
    if isinstance(vb_raw, dict) and "volume" in vb_raw:
        # Legacy schema — fill against the single volume's beats
        if vb_raw.get("volume") != volume:
            raise ValueError(f"volume {volume} not initialized; run init-volume-beat first")
        beats = vb_raw["beats"]
    else:
        vb = vb_raw.get(str(volume))
        if vb is None:
            raise ValueError(f"volume {volume} not initialized; run init-volume-beat first")
        beats = vb["beats"]
    for beat in beats:
        if beat["name"] == beat_name:
            beat["filled"] = True
            beat["chapter"] = chapter
            beat["notes"] = notes
            return state
    raise ValueError(f"beat {beat_name} not found")
```

- [ ] **Step 4: 跑测试确认绿**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/unit/test_story_craft_multivolume.py tests/unit/ -v --ignore=tests/unit/test_promise_ledger.py
```
Expected: 全部通过. (注意其他 test 可能依赖 volume_beat 的 legacy schema, 但因为我们做了迁移兼容, 应都过.)

如果其他测试失败:
- `test_volume_state.py`: 与本任务无关, 应保持绿
- 跑全量:
```bash
python3 -m pytest tests/ -v 2>&1 | tail -50
```

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/zhanghui/scripts/story_craft.py
git add .claude/plugins/zhanghui/scripts/tests/unit/test_story_craft_multivolume.py
git commit -m "feat(story-craft): multi-volume beat sheet (dict[vol, beat_sheet])

Per spec 2026-08-19 §6.1: remove 'multi-volume not yet supported' hard
limit on init_volume_beat. New schema: story_craft.volume_beat is
dict[volume_id, beat_sheet]. Legacy single-volume schema auto-migrated
on first multi-volume init. fill_beat / check_volume_beat / init_volume_beat
all updated. 3 new tests green; full test suite must stay green."
```

---

### Task 5: `chunked_write.py` — ChunkedWritePolicy + evaluate_pre_write_gates

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/chunked_write.py`
- Test: `.claude/plugins/zhanghui/scripts/tests/unit/test_chunked_write.py`

- [ ] **Step 1: 写失败测试**

```python
# .claude/plugins/zhanghui/scripts/tests/unit/test_chunked_write.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_modules.chunked_write import (
    ChunkedWritePolicy,
    should_take_snapshot,
    evaluate_pre_write_gates,
)


def test_should_snapshot_every_3_chapters():
    assert should_take_snapshot(3, snapshot_every=3) is True
    assert should_take_snapshot(6, snapshot_every=3) is True
    assert should_take_snapshot(2, snapshot_every=3) is False
    assert should_take_snapshot(7, snapshot_every=3) is False


def test_policy_default():
    p = ChunkedWritePolicy()
    assert p.chunk_size == 5
    assert p.snapshot_every == 3
    assert p.fore_check_threshold == 50


def test_evaluate_pre_write_gates_no_overdue():
    """Empty overdue list → no blockers."""
    issues = evaluate_pre_write_gates(
        chapter=10, current_volume=1,
        overdue_foreshadows=[],
    )
    assert issues == []


def test_evaluate_pre_write_gates_with_overdue_returns_blocker():
    """Any overdue foreshadow → BLOCKER list."""
    # Mock entry-like object with .id attribute
    class FakeEntry:
        id = "fs_over_1"
    issues = evaluate_pre_write_gates(
        chapter=110, current_volume=2,
        overdue_foreshadows=[FakeEntry()],
    )
    assert len(issues) == 1
    assert "BLOCKER" in issues[0]
    assert "fs_over_1" in issues[0]
```

- [ ] **Step 2: 跑测试确认红**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/unit/test_chunked_write.py -v
```
Expected: `ModuleNotFoundError: No module named 'data_modules.chunked_write'`.

- [ ] **Step 3: 写实现**

```python
# .claude/plugins/zhanghui/scripts/data_modules/chunked_write.py
"""Chunked write policy + pre-write gate evaluator.

Spec: docs/superpowers/specs/2026-08-19-macro-upfront-micro-chunked-design.md §6.4.

denova chapter-group mode + oh-story 中途快照模式.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChunkedWritePolicy:
    chunk_size: int = 5            # denova default 3-8 章/批
    snapshot_every: int = 3        # oh-story 每 3 章检查点
    fore_check_threshold: int = 50 # 距离伏笔回收 N 章 BLOCKER 警告阈值


def should_take_snapshot(chapter: int, snapshot_every: int = 3) -> bool:
    """oh-story pattern: 每 N 章强制 snapshot."""
    if snapshot_every <= 0:
        return False
    return chapter % snapshot_every == 0 and chapter > 0


def evaluate_pre_write_gates(
    chapter: int,
    current_volume: int,
    overdue_foreshadows: list,
) -> list[str]:
    """tianming 六道门禁模式: 写前检查跨卷伏笔 overdue.

    Returns a list of issue strings. BLOCKER if any overdue foreshadow
    exists. Empty list means gates passed.
    """
    issues: list[str] = []
    for entry in overdue_foreshadows:
        issues.append(
            f"BLOCKER: foreshadow {entry.id} overdue — must be paid off before "
            f"writing chapter {chapter} (volume {current_volume})"
        )
    return issues
```

- [ ] **Step 4: 跑测试确认绿**

Run: 同 Step 2.
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/zhanghui/scripts/data_modules/chunked_write.py
git add .claude/plugins/zhanghui/scripts/tests/unit/test_chunked_write.py
git commit -m "feat(chunked-write): ChunkedWritePolicy + evaluate_pre_write_gates

Spec 2026-08-19 §6.4: denova chapter-group policy (chunk_size=5 default)
+ oh-story snapshot_every=3 + tianming-style overdue BLOCKER gate.
4 unit tests green."
```

---

### Task 6: `update_master_outline.py` — `all_volumes_mode` 旁路

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/update_master_outline.py`
- Modify: `.claude/plugins/zhanghui/scripts/tests/integration/test_update_master_outline_volumes.py`

- [ ] **Step 1: 读现有测试断言**

```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
grep -n "_require_current_volume_artifacts\|all_volumes_mode" tests/integration/test_update_master_outline_volumes.py | head -20
```

记下当前测试如何调用 `_require_current_volume_artifacts`. 如果没有直接调用, 走的是 `main()` 入口.

- [ ] **Step 2: 写失败测试 — `all_volumes_mode=True` 跳过前置门**

```python
# Append to test_update_master_outline_volumes.py
from update_master_outline import _require_current_volume_artifacts, MasterOutlineSyncError


def test_require_current_volume_artifacts_all_volumes_mode_skips(tmp_path):
    """Spec §6.3: in --all-volumes mode, missing V1 artifacts must NOT raise."""
    # No artifacts created
    (tmp_path / "大纲").mkdir()
    # Should NOT raise — all_volumes_mode=True short-circuits
    result = _require_current_volume_artifacts(tmp_path, volume=1, all_volumes_mode=True)
    assert result == []


def test_require_current_volume_artifacts_default_still_enforces(tmp_path):
    """Default behavior unchanged: missing artifacts raise MasterOutlineSyncError."""
    (tmp_path / "大纲").mkdir()
    with pytest.raises(MasterOutlineSyncError, match="planning artifacts are incomplete"):
        _require_current_volume_artifacts(tmp_path, volume=1)
```

并在文件顶部 imports 加:
```python
import pytest
```

- [ ] **Step 3: 跑测试确认红**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/integration/test_update_master_outline_volumes.py -v
```
Expected: 2 failed (新断言).

- [ ] **Step 4: 修改 `_require_current_volume_artifacts` 接受 `all_volumes_mode`**

修改 `.claude/plugins/zhanghui/scripts/update_master_outline.py:37-48`:

```python
# Replace _require_current_volume_artifacts with:
def _require_current_volume_artifacts(
    project_root: Path,
    volume: int,
    all_volumes_mode: bool = False,
) -> list[str]:
    """在 --all-volumes 模式下, 不需要当前卷已写过."""
    if all_volumes_mode:
        return []
    missing: list[str] = []
    outline_dir = project_root / "大纲"
    for pattern in REQUIRED_VOLUME_ARTIFACTS:
        path = outline_dir / pattern.format(volume=volume)
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            missing.append(path.relative_to(project_root).as_posix())
    if missing:
        raise MasterOutlineSyncError(
            "current volume planning artifacts are incomplete: " + ", ".join(missing)
        )
    return [f.format(volume=volume) for f in REQUIRED_VOLUME_ARTIFACTS]
```

- [ ] **Step 5: 跑测试确认绿**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/integration/test_update_master_outline_volumes.py -v
```
Expected: 全部通过 (新增 2 + 原 N).

- [ ] **Step 6: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/zhanghui/scripts/update_master_outline.py
git add .claude/plugins/zhanghui/scripts/tests/integration/test_update_master_outline_volumes.py
git commit -m "feat(update-master-outline): all_volumes_mode bypass for plan stage

Spec 2026-08-19 §6.3: --all-volumes mode lets plan stage generate N
volume blueprints without requiring current volume to be written first.
Default behavior unchanged. 2 new tests green."
```

---

### Task 7: `init_project.py` — `--all-volumes` CLI 入口 + generate_blueprint() 函数

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/init_project.py`
- Test: `.claude/plugins/zhanghui/scripts/tests/integration/test_plan_all_volumes.py`

- [ ] **Step 1: 写失败测试 — `--all-volumes` 一次性铺 V1-V3 蓝图**

```python
# .claude/plugins/zhanghui/scripts/tests/integration/test_plan_all_volumes.py
"""Spec 2026-08-19 §6.2: --all-volumes mode generates N volume blueprint triplets."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from init_project import init_project, generate_volume_blueprints


def _init_project_with_3_vols(tmp_path):
    init_project(
        project_dir=str(tmp_path),
        title="All Volumes Test",
        genre="玄幻",
        target_chapters=240,
        target_words=720000,
        volume_skeleton=[
            {"index": 1, "title": "V1", "chapter_range": [1, 80],
             "core_conflict": "A", "climax": "B",
             "status": "confirmed", "source": "human"},
            {"index": 2, "title": "V2", "chapter_range": [81, 160],
             "core_conflict": "C", "climax": "D",
             "status": "confirmed", "source": "human"},
            {"index": 3, "title": "V3", "chapter_range": [161, 240],
             "core_conflict": "E", "climax": "F",
             "status": "confirmed", "source": "human"},
        ],
    )


def test_generate_volume_blueprints_creates_3_triplets(tmp_path):
    """--all-volumes mode: 3 confirmed volumes → 3 blueprint triplets."""
    _init_project_with_3_vols(tmp_path)
    written = generate_volume_blueprints(tmp_path, all_volumes=True)
    assert written == 3
    # Each volume gets 详细大纲 + 15节拍 + 时间线
    for vol in (1, 2, 3):
        assert (tmp_path / "大纲" / f"第{vol}卷-详细大纲.md").is_file()
        assert (tmp_path / "大纲" / f"第{vol}卷-15节拍.md").is_file()
        assert (tmp_path / "大纲" / f"第{vol}卷-时间线.md").is_file()


def test_generate_volume_blueprints_default_no_op(tmp_path):
    """Default (all_volumes=False) must NOT create any per-volume blueprints (regression)."""
    _init_project_with_3_vols(tmp_path)
    written = generate_volume_blueprints(tmp_path, all_volumes=False)
    assert written == 0
    for vol in (1, 2, 3):
        assert not (tmp_path / "大纲" / f"第{vol}卷-详细大纲.md").exists()


def test_generate_volume_blueprints_skips_deferred(tmp_path):
    """Only confirmed volumes get blueprints; deferred ones are skipped."""
    init_project(
        project_dir=str(tmp_path),
        title="Deferred Test", genre="玄幻",
        target_chapters=160, target_words=480000,
        volume_skeleton=[
            {"index": 1, "title": "V1", "chapter_range": [1, 80],
             "core_conflict": "A", "climax": "B",
             "status": "confirmed", "source": "human"},
            {"index": 2, "title": "V2-deferred", "chapter_range": [81, 160],
             "core_conflict": "C", "climax": "D",
             "status": "deferred", "source": "human"},
        ],
    )
    written = generate_volume_blueprints(tmp_path, all_volumes=True)
    # Only V1 confirmed → only V1 blueprint triplet
    assert written == 1
    assert (tmp_path / "大纲" / "第1卷-详细大纲.md").is_file()
    assert not (tmp_path / "大纲" / "第2卷-详细大纲.md").is_file()
```

- [ ] **Step 2: 跑测试确认红**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/integration/test_plan_all_volumes.py -v
```
Expected: ImportError / AttributeError on `generate_volume_blueprints`.

- [ ] **Step 3: 实现 `generate_volume_blueprints()`**

修改 `.claude/plugins/zhanghui/scripts/init_project.py`. 在 `init_project()` 之后追加:

```python
def _render_volume_blueprint(volume: dict, total_project_chapters: int) -> tuple[str, str, str]:
    """Render 详细大纲 / 15节拍 / 时间线 三件套 for one volume."""
    idx = volume["index"]
    title = volume.get("title", f"V{idx}")
    ch_range = volume.get("chapter_range") or [0, 0]
    core_conflict = volume.get("core_conflict", "")
    climax = volume.get("climax", "")
    vol_chapters = max(1, ch_range[1] - ch_range[0] + 1)

    # 第N卷-详细大纲.md
    detailed = (
        f"# 第{idx}卷 详细大纲 — {title}\n\n"
        f"**章节范围**: {ch_range[0]}-{ch_range[1]} ({vol_chapters} 章)\n"
        f"**核心冲突**: {core_conflict}\n"
        f"**卷末高潮**: {climax}\n\n"
        f"## 章节蓝图\n\n"
        f"（plan 流程 Step 7 填充 chapter list；本骨架由 --all-volumes 自动生成）\n"
    )

    # 第N卷-15节拍.md (Save the Cat)
    beats = [
        "Opening Image", "Theme Stated", "Setup", "Catalyst",
        "Debate", "Break Into Two", "B Story", "Fun and Games",
        "Midpoint", "Bad Guys Close In", "All Is Lost",
        "Dark Night of the Soul", "Break Into Three", "Finale", "Final Image",
    ]
    percentages = [0.01, 0.05, 0.10, 0.10, 0.20, 0.20, 0.22, 0.50, 0.50, 0.75, 0.75, 0.80, 0.80, 0.99, 1.00]
    beat_lines = []
    for name, pct in zip(beats, percentages):
        ch = max(1, round(pct * vol_chapters))
        beat_lines.append(f"- **{name}** — ch {ch}")
    beat_sheet = (
        f"# 第{idx}卷 15-节拍表 — {title}\n\n"
        f"**节拍分布算法**: 比例法 (vol_chapters={vol_chapters})\n\n"
        + "\n".join(beat_lines) + "\n"
    )

    # 第N卷-时间线.md
    timeline = (
        f"# 第{idx}卷 时间线 — {title}\n\n"
        f"**章节范围**: ch {ch_range[0]} - ch {ch_range[1]}\n"
        f"**项目总章节**: {total_project_chapters}\n\n"
        f"（事件时间线由 plan 流程 Step 6.5 填充；本骨架由 --all-volumes 自动生成）\n"
    )
    return detailed, beat_sheet, timeline


def generate_volume_blueprints(project_root, all_volumes: bool = False) -> int:
    """按 confirmed volumes[] 生成 N 卷蓝图三件套.

    Args:
        project_root: 项目根目录.
        all_volumes: True 一次性铺全部 confirmed 卷; False 不铺.

    Returns:
        实际写入的卷数.
    """
    if not all_volumes:
        return 0
    state_path = Path(project_root) / ".webnovel" / "state.json"
    if not state_path.is_file():
        return 0
    import json
    state = json.loads(state_path.read_text(encoding="utf-8"))
    volumes = state.get("volumes", [])
    confirmed = [v for v in volumes if v.get("status") == "confirmed"]
    if not confirmed:
        return 0
    total_project_chapters = state.get("project_info", {}).get("target_chapters", 600)
    outline_dir = Path(project_root) / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for vol in confirmed:
        idx = vol["index"]
        detailed, beat_sheet, timeline = _render_volume_blueprint(vol, total_project_chapters)
        (outline_dir / f"第{idx}卷-详细大纲.md").write_text(detailed, encoding="utf-8")
        (outline_dir / f"第{idx}卷-15节拍.md").write_text(beat_sheet, encoding="utf-8")
        (outline_dir / f"第{idx}卷-时间线.md").write_text(timeline, encoding="utf-8")
        written += 1
    return written
```

并在 `main()` argparse (line 965+) 新增 `--all-volumes` 选项:

```python
    # Append to main() argparse:
    parser.add_argument(
        "--all-volumes", action="store_true",
        help="一次性铺 N 卷蓝图 (覆盖所有 confirmed volumes). 默认关闭保持现状兼容."
    )
```

并在 `main()` 调用 `init_project()` 之后插入:

```python
    # After init_project call in main(), append:
    if getattr(args, 'all_volumes', False):
        from init_project import generate_volume_blueprints
        written = generate_volume_blueprints(args.project_dir, all_volumes=True)
        print(f"--all-volumes: wrote {written} volume blueprint(s)")
```

- [ ] **Step 4: 跑测试确认绿**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/integration/test_plan_all_volumes.py tests/integration/test_plan_v_plus_one_anchor.py -v
```
Expected: 全部通过 (新 3 + 原 3 regression 不破).

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/zhanghui/scripts/init_project.py
git add .claude/plugins/zhanghui/scripts/tests/integration/test_plan_all_volumes.py
git commit -m "feat(init-project): --all-volumes mode generates N volume blueprint triplets

Spec 2026-08-19 §6.2: new --all-volumes CLI flag + generate_volume_blueprints()
helper. Per confirmed volume, writes {详细大纲,15节拍,时间线}.md.
Default (flag off) is no-op for backward compatibility. 3 new integration
tests green; test_plan_v_plus_one_anchor regression preserved."
```

---

### Task 8: `templates/output/大纲-总纲.md` 加跨卷伏笔账本 + 节拍映射表头

**Files:**
- Modify: `.claude/plugins/zhanghui/templates/output/大纲-总纲.md`

- [ ] **Step 1: 读现有模板**

```bash
cat /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/templates/output/大纲-总纲.md
```

- [ ] **Step 2: 在卷划分表后追加新表头**

在 `## 卷划分` (或类似) 节末尾追加:

```markdown

## 跨卷伏笔账本（Promise Ledger）

| ID | 类型 | 深度 | 埋设卷/章 | 预期回收卷/章 | 状态 | 备注 |
|---|---|---|---|---|---|---|
| (示例) fs_001 | foreshadow | 3 | V1 ch12 | V3 ch145 | pending | 长老作弊伏笔 |

## 跨卷节拍映射（Cross-Volume Beat Map）

| 起卷 | 终卷 | 节拍ID | 描述 |
|---|---|---|---|
| (示例) V1 | V3 | fs_001_payoff | 长老作弊揭露 → 第三卷回收 |
```

- [ ] **Step 3: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/zhanghui/templates/output/大纲-总纲.md
git commit -m "docs(template): add cross-volume promise ledger + beat map headers

Spec 2026-08-19 §5.1: 总纲 now has empty tables for promise_ledger
and cross_volume_beat_map. Filled by --all-volumes mode (Task 7) or
manually by user during plan stage."
```

---

### Task 9: `webnovel-plan` SKILL.md Step 9 接入 `--all-volumes`

**Files:**
- Modify: `.claude/plugins/zhanghui/skills/webnovel-plan/SKILL.md`

- [ ] **Step 1: 读现有 Step 9**

```bash
grep -n "Step 9\|9\\." /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/skills/webnovel-plan/SKILL.md | head -10
```

定位 Step 9 当前段落.

- [ ] **Step 2: 在 Step 9 段落末尾追加 `--all-volumes` 分支**

找到当前 Step 9 段落 (如 line 336 那段), 追加:

```markdown

**`--all-volumes` 模式（可选）**:

如果用户传 `--all-volumes`（或 `python3 scripts/init_project.py ... --all-volumes`），则一次性铺 N 卷蓝图：
1. 读 `state.json` 的 `volumes[]`（包含 `expected_total_volumes` 与 confirmed 卷）
2. 对每个 **confirmed** 卷（不限于 V+1）：
   - 产 `第N卷-详细大纲.md` (15-beat + 章纲蓝图)
   - 产 `第N卷-15节拍.md` (Save the Cat beat sheet)
   - 产 `第N卷-时间线.md` (卷内时间线)
3. 写跨卷伏笔账本 + 节拍映射到 `大纲-总纲.md`（见模板新增表头）
4. 校验 index continuity + cross_volume_beat_map 无环路

**默认（无 `--all-volumes`）行为完全不变**：只更新 V+1 锚点，不生成 V+2+ 详细蓝图（与 `test_plan_v_plus_one_anchor` 一致）。

**调度命令**：
```bash
python3 scripts/init_project.py <project_dir> <title> \
    --genre <genre> --target-chapters <N> --target-words <W> \
    --all-volumes
```
```

- [ ] **Step 3: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/zhanghui/skills/webnovel-plan/SKILL.md
git commit -m "docs(skill-plan): Step 9 documents --all-volumes mode

Spec 2026-08-19 §6.2: --all-volumes is opt-in. Default behavior
unchanged (preserves test_plan_v_plus_one_anchor regression)."
```

---

### Task 10: `webnovel-write` SKILL.md 注入 pre-write gate 钩子

**Files:**
- Modify: `.claude/plugins/zhanghui/skills/webnovel-write/SKILL.md`

- [ ] **Step 1: 读现有 Step 0**

```bash
grep -n "^### Step 0\|^## Step 0" /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/skills/webnovel-write/SKILL.md | head -5
```

如果不存在 Step 0, 找最早的 Step (Step 1 / 准备).

- [ ] **Step 2: 在最前 Step 之前插入新 Step 0**

在 SKILL.md 顶部（Step 1 之前）追加:

```markdown

### Step 0: Pre-Write Gate Check（oh-story 模式）

每次写章前, 跑 `evaluate_pre_write_gates`：

```python
from data_modules.chunked_write import evaluate_pre_write_gates
from data_modules.volume_state import VolumeStateManager

state = json.loads(open(".webnovel/state.json").read())
mgr = VolumeStateManager(state)
overdue = mgr.list_overdue_foreshadows(
    current_chapter=<next_chapter>,
    current_volume=<current_volume>,
)
issues = evaluate_pre_write_gates(
    chapter=<next_chapter>,
    current_volume=<current_volume>,
    overdue_foreshadows=overdue,
)
if issues:
    print("\n".join(issues))
    raise SystemExit(1)  # BLOCKER: 不允许写
```

**BLOCKER 时**：要求用户先在 plan 阶段调整伏笔账本或回收 overdue 伏笔，方可继续。

**逃生口**：`WEBNOVEL_DISABLE_CHUNKED_GATE=1` 临时跳过本检查。
```

- [ ] **Step 3: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/zhanghui/skills/webnovel-write/SKILL.md
git commit -m "docs(skill-write): Step 0 pre-write gate (oh-story + tianming pattern)

Spec 2026-08-19 §6.4: write stage evaluates overdue foreshadows before
each chapter; BLOCKER on overdue. Escape hatch: WEBNOVEL_DISABLE_CHUNKED_GATE=1."
```

---

### Task 11: 端到端测试 — `test_e2e_macro_micro.py`

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/tests/integration/test_e2e_macro_micro.py`

- [ ] **Step 1: 写端到端测试**

```python
"""End-to-end: init → --all-volumes plan → pre-write gate check."""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from init_project import init_project, generate_volume_blueprints
from data_modules.volume_state import VolumeStateManager
from data_modules.promise_ledger import ForeshadowEntry, ForeshadowStatus
from data_modules.chunked_write import evaluate_pre_write_gates


def test_e2e_full_flow(tmp_path):
    """Init 3-volume project → --all-volumes → upsert overdue foreshadow → BLOCKER."""
    # Init
    init_project(
        project_dir=str(tmp_path),
        title="E2E Macro-Micro", genre="玄幻",
        target_chapters=240, target_words=720000,
        volume_skeleton=[
            {"index": 1, "title": "V1", "chapter_range": [1, 80],
             "core_conflict": "A", "climax": "B",
             "status": "confirmed", "source": "human"},
            {"index": 2, "title": "V2", "chapter_range": [81, 160],
             "core_conflict": "C", "climax": "D",
             "status": "confirmed", "source": "human"},
            {"index": 3, "title": "V3", "chapter_range": [161, 240],
             "core_conflict": "E", "climax": "F",
             "status": "confirmed", "source": "human"},
        ],
    )

    # --all-volumes plan stage
    written = generate_volume_blueprints(tmp_path, all_volumes=True)
    assert written == 3
    for vol in (1, 2, 3):
        assert (tmp_path / "大纲" / f"第{vol}卷-详细大纲.md").is_file()
        assert (tmp_path / "大纲" / f"第{vol}卷-15节拍.md").is_file()
        assert (tmp_path / "大纲" / f"第{vol}卷-时间线.md").is_file()

    # Upsert overdue foreshadow: planted V1, expected payoff V2 ch100
    state_path = tmp_path / ".webnovel" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    mgr = VolumeStateManager(state)
    mgr.upsert_promise_entry(ForeshadowEntry(
        id="fs_e2e", type="foreshadow", depth=2,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # Pre-write gate at V2 ch110: BLOCKER expected (payoff missed)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    mgr = VolumeStateManager(state)
    overdue = mgr.list_overdue_foreshadows(current_chapter=110, current_volume=2)
    issues = evaluate_pre_write_gates(
        chapter=110, current_volume=2,
        overdue_foreshadows=overdue,
    )
    assert len(issues) == 1
    assert "fs_e2e" in issues[0]
    assert "BLOCKER" in issues[0]

    # Payoff → re-evaluate → no blocker
    mgr.payoff_foreshadow("fs_e2e", at_chapter=112)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    mgr = VolumeStateManager(state)
    overdue = mgr.list_overdue_foreshadows(current_chapter=112, current_volume=2)
    issues = evaluate_pre_write_gates(
        chapter=112, current_volume=2,
        overdue_foreshadows=overdue,
    )
    assert issues == []
```

- [ ] **Step 2: 跑测试确认绿**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/integration/test_e2e_macro_micro.py -v
```
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/zhanghui/scripts/tests/integration/test_e2e_macro_micro.py
git commit -m "test(e2e): macro-upfront + micro-chunked end-to-end flow

Verifies: init 3-volume project → --all-volumes plan writes 3 triplets
→ upsert overdue foreshadow → BLOCKER on pre-write gate → payoff clears
blocker. Covers full spec 2026-08-19 flow."
```

---

### Task 12: 部署 — `bin/deploy-plugin.sh` + README + 全量测试回归

**Files:**
- Modify: `.claude/plugins/zhanghui/bin/deploy-plugin.sh`
- Modify: `.claude/plugins/zhanghui/README.md`
- Verify: 全部测试绿 + marketplace sync 完成

- [ ] **Step 1: `bin/deploy-plugin.sh` 加新文件**

修改 `bin/deploy-plugin.sh` 的 `RUNTIME_FILES` 和 `TEST_FILES` 数组:

```bash
RUNTIME_FILES=(
    "scripts/data_modules/volume_state.py"
    "scripts/data_modules/ai_volume_drafter.py"
    "scripts/data_modules/promise_ledger.py"     # NEW
    "scripts/data_modules/chunked_write.py"      # NEW
    "scripts/init_project.py"
    "scripts/story_craft.py"
    "scripts/update_master_outline.py"
    "skills/webnovel-init/SKILL.md"
    "skills/webnovel-init/references/multi-volume-ux.md"
    "skills/webnovel-plan/SKILL.md"
    "skills/webnovel-write/SKILL.md"             # NEW
    "templates/output/大纲-总纲.md"
    "README.md"
    "bin/deploy-plugin.sh"
)

TEST_FILES=(
    "scripts/tests/unit/test_volume_state.py"
    "scripts/tests/unit/test_ai_volume_drafter.py"
    "scripts/tests/unit/test_promise_ledger.py"           # NEW
    "scripts/tests/unit/test_chunked_write.py"            # NEW
    "scripts/tests/unit/test_story_craft_multivolume.py"  # NEW
    "scripts/tests/integration/test_init_multi_volume.py"
    "scripts/tests/integration/test_plan_v_plus_one_anchor.py"
    "scripts/tests/integration/test_plan_all_volumes.py"  # NEW
    "scripts/tests/integration/test_e2e_macro_micro.py"   # NEW
    "scripts/tests/integration/test_e2e_multi_volume_init.py"
    "scripts/tests/integration/test_update_master_outline_volumes.py"
)
```

- [ ] **Step 2: README.md 加 `--all-volumes` 文档**

在 README.md 的 "## 三个 skill 的功能" 节后追加:

```markdown

## `--all-volumes` 模式（macro upfront + micro chunked）

`init_project.py` 新增 `--all-volumes` CLI 选项：

```bash
python3 scripts/init_project.py <project_dir> <title> \
    --genre <genre> --target-chapters <N> --target-words <W> \
    --all-volumes
```

**效果**：一次性铺 N 卷蓝图（每卷产 `详细大纲.md` / `15节拍.md` / `时间线.md` 三件套）。

**默认行为不变**（无 `--all-volumes`）：只更新 V+1 锚点，与旧版本兼容。

详见 `docs/superpowers/specs/2026-08-19-macro-upfront-micro-chunked-design.md`。
```

- [ ] **Step 3: 跑全量测试**

```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/scripts
python3 -m pytest tests/ -v 2>&1 | tail -30
```

Expected: 全部通过. If any fail, fix before continuing.

- [ ] **Step 4: 部署到 marketplace**

```bash
cd /Users/chang/Desktop/zhanghui
./bin/deploy-plugin.sh
```

Expected: 14 runtime + 11 test files synced.

- [ ] **Step 5: 验证 marketplace 副本一致**

```bash
diff -q .claude/plugins/zhanghui/scripts/data_modules/promise_ledger.py \
       /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/zhanghui/scripts/data_modules/promise_ledger.py
diff -q .claude/plugins/zhanghui/scripts/data_modules/chunked_write.py \
       /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/zhanghui/scripts/data_modules/chunked_write.py
```

Expected: no diff.

- [ ] **Step 6: Commit + push**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/zhanghui/bin/deploy-plugin.sh
git add .claude/plugins/zhanghui/README.md
git commit -m "chore(deploy): sync new files to marketplace; document --all-volumes

Adds promise_ledger.py + chunked_write.py to RUNTIME_FILES.
Adds 4 new test files to TEST_FILES. README documents --all-volumes mode.
Full test suite green; marketplace copies verified identical."
```

---

## 自检清单（实施前）

- [ ] 所有 12 个 Task 的代码片段完整（无 TODO / placeholder）
- [ ] 文件路径准确（基于实际目录 layout）
- [ ] 测试命令具体（带 cd + pytest 路径）
- [ ] Commit message 明确（conventional commits）
- [ ] 默认行为兼容（test_plan_v_plus_one_anchor 不破）
- [ ] spec §6 各组件全覆盖

---

## 引用来源

- 内部 spec: `docs/superpowers/specs/2026-08-19-macro-upfront-micro-chunked-design.md` (commit 1079342)
- 上一版 spec: `docs/superpowers/specs/2026-08-18-multi-volume-init-design.md`
- 上一版 plan: `docs/superpowers/plans/2026-08-18-multi-volume-init.md`（参考 path bug 修复经验）
- VolumeStateManager 现状: `.claude/plugins/zhanghui/scripts/data_modules/volume_state.py` (commit 580af18)
- 现有测试 regression baseline: `scripts/tests/integration/test_plan_v_plus_one_anchor.py`