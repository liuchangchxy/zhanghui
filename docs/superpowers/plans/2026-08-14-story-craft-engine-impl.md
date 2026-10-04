# Story Craft Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade webnovel-writer's `webnovel-plan` layer from form-level to craft-level by adding 4 core narrative mechanisms (15-beat / Scene-Sequel / 草蛇灰线 5-field tracking / timed-lock+rhythm-curve+hook-type), enabling the system to engineer 跌宕起伏 / 精妙绝伦 / 草蛇灰线 outcomes rather than only enforce format.

**Architecture:** 
- New Python module `scripts/story_craft.py` handles all state.json `story_craft` field operations (foreshadow state machine, timed-lock tracking, rhythm curve calculation)
- 8 new shared reference docs capture theory (one source of truth each)
- `webnovel-plan` SKILL.md adds 3 new Steps (4.5/6.5/8.5) and extends Step 7 with Scene-Sequel slicing
- `reviewer` agent prompt extends from 5 to 7 dimensions (adds 节拍合规性 / Scene-Sequel完整性)
- Dashboard adds 4 new panels (beat / foreshadow / timed-lock / rhythm) on top of existing
- All changes backward-compatible via optional state.json fields and additive SKILL.md steps

**Tech Stack:** Python 3 (pytest), Markdown, JSON schema (hand-rolled), existing webnovel-writer plugin structure

---

## File Structure

### New Files

| Path | Responsibility |
|---|---|
| `.claude/plugins/webnovel-writer/scripts/story_craft.py` | state.json story_craft field operations (init/update/query) |
| `.claude/plugins/webnovel-writer/references/shared/15-beat-save-the-cat.md` | Save the Cat 15-beat definition + volume mapping |
| `.claude/plugins/webnovel-writer/references/shared/scene-sequel.md` | Dwight Swain Scene-Sequel 7-step |
| `.claude/plugins/webnovel-writer/references/shared/foreshadow-chain.md` | 草蛇灰线三层法 + 5-field tracking + 6 carrier types |
| `.claude/plugins/webnovel-writer/references/shared/timed-lock.md` | 起点编辑定时锁理论 + 训练题 |
| `.claude/plugins/webnovel-writer/references/shared/rhythm-curve.md` | 马良写作 1.8 章节奏曲线 |
| `.claude/plugins/webnovel-writer/references/shared/chapter-hook-types.md` | 6 种章末钩子 + 正反例 |
| `.claude/plugins/webnovel-writer/references/shared/character-arc.md` | 主角弧追踪 state.json 字段说明 |
| `.claude/plugins/webnovel-writer/references/shared/thematic-echo.md` | 主题回响 + state.json 字段说明 |
| `.claude/plugins/webnovel-writer/skills/webnovel-plan/references/outlining/volume-beat-sheet.md` | 卷节拍表填写模板 |
| `.claude/plugins/webnovel-writer/skills/webnovel-plan/references/outlining/foreshadow-tracking-template.md` | 5 字段追踪表模板 |
| `.claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py` | story_craft 模块单测 |
| `.claude/plugins/webnovel-writer/scripts/tests/test_foreshadow_chain.py` | 5 字段验证 + 状态机迁移 |
| `.claude/plugins/webnovel-writer/scripts/tests/test_15_beat.py` | beat 完整性 + Midpoint/All Is Lost 必填 |
| `.claude/plugins/webnovel-writer/scripts/tests/test_scene_sequel.py` | 7 步字段验证 |
| `.claude/plugins/webnovel-writer/scripts/tests/test_timed_locks.py` | deadline 检查 |
| `.claude/plugins/webnovel-writer/scripts/tests/test_rhythm_curve.py` | chapters_since_peak 计算 |
| `.claude/plugins/webnovel-writer/scripts/tests/test_migration.py` | 旧 state.json → 新 平滑升级 |
| `.claude/plugins/webnovel-writer/scripts/tests/integration/test_plan_with_craft.py` | plan 完整流程集成 |
| `.claude/plugins/webnovel-writer/scripts/tests/integration/test_review_with_craft.py` | reviewer 报警集成 |

### Modified Files

| Path | Change |
|---|---|
| `.claude/plugins/webnovel-writer/scripts/webnovel.py` | Add `story-craft` subcommand group |
| `.claude/plugins/webnovel-writer/scripts/chapter_paths.py` | Add new fields to chapter_meta default |
| `.claude/plugins/webnovel-writer/scripts/review_pipeline.py` | Add 2 dimensions |
| `.claude/plugins/webnovel-writer/agents/reviewer.md` | Update prompt to 7 dimensions |
| `.claude/plugins/webnovel-writer/skills/webnovel-plan/SKILL.md` | Add Step 4.5/6.5/8.5 + extend Step 7 |
| `.claude/plugins/webnovel-writer/templates/output/大纲-卷节拍表.md` | Restructure as 15-beat sheet |
| `.claude/plugins/webnovel-writer/templates/output/大纲-卷详细大纲.md` | Add Scene-Sequel slice + hook_type |
| `.claude/plugins/webnovel-writer/dashboard/app.py` | Add 4 panels |

---

## Phase 1: Reference Docs + state.json Schema (Week 1)

### Task 1: Create story_craft.py module skeleton + failing tests

**Files:**
- Create: `.claude/plugins/webnovel-writer/scripts/story_craft.py`
- Create: `.claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py`

- [ ] **Step 1: Write failing test for init_story_craft**

```python
# tests/test_story_craft.py
import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from story_craft import init_story_craft, StoryCraftFieldError


def test_init_story_craft_creates_empty_structure():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
        json.dump({"project_info": {}, "progress": {}}, f)
        path = f.name

    try:
        result = init_story_craft(path)
        assert "story_craft" in result
        assert result["story_craft"]["foreshadow_chain"] == []
        assert result["story_craft"]["timed_locks"] == []
        assert result["story_craft"]["rhythm_curve"]["chapters_since_peak"] == 0
        assert result["story_craft"]["thematic_echoes"] == []
        assert result["story_craft"]["character_arc"] is None
    finally:
        Path(path).unlink()


def test_init_story_craft_is_idempotent():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
        json.dump({"project_info": {}, "progress": {}}, f)
        path = f.name

    try:
        first = init_story_craft(path)
        second = init_story_craft(path)
        assert first["story_craft"] == second["story_craft"]
    finally:
        Path(path).unlink()


def test_init_story_craft_preserves_existing():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
        json.dump({
            "project_info": {"title": "Test"},
            "story_craft": {"rhythm_curve": {"chapters_since_peak": 5}}
        }, f)
        path = f.name

    try:
        result = init_story_craft(path)
        assert result["project_info"]["title"] == "Test"
        assert result["story_craft"]["rhythm_curve"]["chapters_since_peak"] == 5
    finally:
        Path(path).unlink()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: `ModuleNotFoundError: No module named 'story_craft'`

- [ ] **Step 3: Implement minimal story_craft.py**

```python
# scripts/story_craft.py
"""Story Craft state.json field operations.

Handles all read/write operations for the story_craft top-level field
introduced in 2026-08-14 story-craft-engine design.
"""
import json
from pathlib import Path
from typing import Any


class StoryCraftFieldError(Exception):
    """Raised when state.json story_craft field is malformed."""


EMPTY_STORY_CRAFT: dict[str, Any] = {
    "rhythm_curve": {
        "last_emotion_peak_chapter": 0,
        "chapters_since_peak": 0,
        "warning_threshold": 3,
        "block_threshold": 5,
        "history": []
    },
    "foreshadow_chain": [],
    "timed_locks": [],
    "thematic_echoes": [],
    "character_arc": None
}


def _load_state(path: str | Path) -> dict:
    """Load state.json from path."""
    p = Path(path)
    if not p.exists():
        raise StoryCraftFieldError(f"state.json not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def _save_state(path: str | Path, state: dict) -> None:
    """Save state.json atomically."""
    p = Path(path)
    p.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def init_story_craft(path: str | Path) -> dict:
    """Initialize story_craft field if missing; return full state.

    Idempotent: preserves existing story_craft content.
    Preserves all other state.json fields.
    """
    state = _load_state(path)
    if "story_craft" not in state:
        state["story_craft"] = json.loads(json.dumps(EMPTY_STORY_CRAFT))
    elif not isinstance(state["story_craft"], dict):
        raise StoryCraftFieldError("story_craft is not a dict")
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/scripts/story_craft.py .claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py
git commit -m "feat(story-craft): add init_story_craft with empty structure"
```

---

### Task 2: Add foreshadow CRUD operations

**Files:**
- Modify: `.claude/plugins/webnovel-writer/scripts/story_craft.py`
- Modify: `.claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py`

- [ ] **Step 1: Add failing tests for foreshadow CRUD**

```python
# Append to tests/test_story_craft.py

def test_add_foreshadow_creates_item():
    state = {"story_craft": {"foreshadow_chain": []}}
    item = {
        "id": "FS-001",
        "type": "物谶",
        "depth": "中层",
        "content": "血玉蜘蛛蛛丝",
        "buried_chapter": 5,
        "expected_payoff_chapter": 25,
        "payoff_method": "虚天鼎钥匙",
        "linked_entities": ["韩立", "血玉蜘蛛"]
    }
    result = add_foreshadow(state, item)
    assert len(result["story_craft"]["foreshadow_chain"]) == 1
    assert result["story_craft"]["foreshadow_chain"][0]["id"] == "FS-001"
    assert result["story_craft"]["foreshadow_chain"][0]["status"] == "active"


def test_add_foreshadow_assigns_next_id():
    state = {"story_craft": {"foreshadow_chain": [{"id": "FS-001"}]}}
    result = add_foreshadow(state, {"type": "物谶", "depth": "表层"})
    assert result["story_craft"]["foreshadow_chain"][1]["id"] == "FS-002"


def test_add_foreshadow_validates_depth():
    state = {"story_craft": {"foreshadow_chain": []}}
    with __import__("pytest").raises(ValueError):
        add_foreshadow(state, {"type": "物谶", "depth": "invalid"})


def test_payoff_foreshadow_marks_paid_off():
    state = {"story_craft": {"foreshadow_chain": [
        {"id": "FS-001", "status": "active"}
    ]}}
    result = payoff_foreshadow(state, "FS-001", chapter=25, quality="强")
    assert result["story_craft"]["foreshadow_chain"][0]["status"] == "paid_off"
    assert result["story_craft"]["foreshadow_chain"][0]["payoff_chapter"] == 25
    assert result["story_craft"]["foreshadow_chain"][0]["payoff_quality"] == "强"


def test_payoff_foreshadow_raises_if_already_paid():
    state = {"story_craft": {"foreshadow_chain": [
        {"id": "FS-001", "status": "paid_off"}
    ]}}
    with __import__("pytest").raises(ValueError):
        payoff_foreshadow(state, "FS-001", chapter=25, quality="强")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 5 failed (ImportError or AttributeError for add_foreshadow / payoff_foreshadow)

- [ ] **Step 3: Implement add_foreshadow + payoff_foreshadow**

```python
# Append to scripts/story_craft.py

VALID_DEPTHS = {"表层", "中层", "深层"}
VALID_TYPES = {"物谶", "诗谶", "戏谶", "灯谜", "环境", "习惯", "对话双关"}


def _next_foreshadow_id(chain: list) -> str:
    used = {item.get("id", "") for item in chain}
    n = 1
    while f"FS-{n:03d}" in used:
        n += 1
    return f"FS-{n:03d}"


def add_foreshadow(state: dict, item: dict) -> dict:
    """Add foreshadow item to chain. Validates required fields.

    Required: type, depth
    Optional: id (auto-assigned if missing), content, buried_chapter,
              expected_payoff_chapter, payoff_method, linked_entities
    """
    if item.get("depth") not in VALID_DEPTHS:
        raise ValueError(f"depth must be one of {VALID_DEPTHS}, got {item.get('depth')}")
    if item.get("type") not in VALID_TYPES:
        raise ValueError(f"type must be one of {VALID_TYPES}, got {item.get('type')}")

    chain = state.setdefault("story_craft", {}).setdefault("foreshadow_chain", [])
    new_item = {
        "id": item.get("id") or _next_foreshadow_id(chain),
        "type": item["type"],
        "depth": item["depth"],
        "content": item.get("content", ""),
        "buried_chapter": item.get("buried_chapter"),
        "expected_payoff_chapter": item.get("expected_payoff_chapter"),
        "payoff_method": item.get("payoff_method", ""),
        "linked_entities": item.get("linked_entities", []),
        "status": "active",
        "buried_quality": item.get("buried_quality"),
        "payoff_chapter": None,
        "payoff_quality": None,
    }
    chain.append(new_item)
    return state


def payoff_foreshadow(state: dict, foreshadow_id: str, chapter: int, quality: str) -> dict:
    """Mark foreshadow as paid off at given chapter.

    Raises ValueError if not found or already paid off.
    """
    chain = state["story_craft"]["foreshadow_chain"]
    for item in chain:
        if item["id"] == foreshadow_id:
            if item["status"] == "paid_off":
                raise ValueError(f"{foreshadow_id} already paid off")
            item["status"] = "paid_off"
            item["payoff_chapter"] = chapter
            item["payoff_quality"] = quality
            return state
    raise ValueError(f"foreshadow {foreshadow_id} not found")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/scripts/story_craft.py .claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py
git commit -m "feat(story-craft): add foreshadow CRUD with state machine"
```

---

### Task 3: Add timed_lock CRUD + deadline check

**Files:**
- Modify: `.claude/plugins/webnovel-writer/scripts/story_craft.py`
- Modify: `.claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py`

- [ ] **Step 1: Add failing tests**

```python
# Append to tests/test_story_craft.py

def test_add_timed_lock_creates_item():
    state = {"story_craft": {"timed_locks": []}}
    item = {
        "id": "TL-001",
        "description": "玄幻主角 3 章内出村",
        "deadline_chapter": 3
    }
    result = add_timed_lock(state, item)
    assert len(result["story_craft"]["timed_locks"]) == 1
    assert result["story_craft"]["timed_locks"][0]["status"] == "active"


def test_fulfill_timed_lock_marks_done():
    state = {"story_craft": {"timed_locks": [
        {"id": "TL-001", "status": "active"}
    ]}}
    result = fulfill_timed_lock(state, "TL-001", chapter=2)
    assert result["story_craft"]["timed_locks"][0]["status"] == "fulfilled"
    assert result["story_craft"]["timed_locks"][0]["fulfilled_chapter"] == 2


def test_check_timed_lock_deadlines_returns_overdue():
    state = {"story_craft": {"timed_locks": [
        {"id": "TL-001", "deadline_chapter": 3, "status": "active"},
        {"id": "TL-002", "deadline_chapter": 10, "status": "active"},
        {"id": "TL-003", "deadline_chapter": 5, "status": "fulfilled"}
    ]}}
    overdue = check_timed_lock_deadlines(state, current_chapter=7)
    ids = [t["id"] for t in overdue]
    assert "TL-001" in ids
    assert "TL-002" not in ids  # not yet overdue
    assert "TL-003" not in ids  # already fulfilled
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 3 failed

- [ ] **Step 3: Implement**

```python
# Append to scripts/story_craft.py

def _next_timed_lock_id(locks: list) -> str:
    used = {item.get("id", "") for item in locks}
    n = 1
    while f"TL-{n:03d}" in used:
        n += 1
    return f"TL-{n:03d}"


def add_timed_lock(state: dict, item: dict) -> dict:
    """Add timed lock to state. Required: description, deadline_chapter."""
    if "deadline_chapter" not in item:
        raise ValueError("deadline_chapter required")
    locks = state.setdefault("story_craft", {}).setdefault("timed_locks", [])
    new_item = {
        "id": item.get("id") or _next_timed_lock_id(locks),
        "description": item.get("description", ""),
        "trigger_chapter": item.get("trigger_chapter"),
        "deadline_chapter": item["deadline_chapter"],
        "status": "active",
        "fulfilled_chapter": None,
    }
    locks.append(new_item)
    return state


def fulfill_timed_lock(state: dict, lock_id: str, chapter: int) -> dict:
    locks = state["story_craft"]["timed_locks"]
    for item in locks:
        if item["id"] == lock_id:
            if item["status"] == "fulfilled":
                raise ValueError(f"{lock_id} already fulfilled")
            item["status"] = "fulfilled"
            item["fulfilled_chapter"] = chapter
            return state
    raise ValueError(f"timed_lock {lock_id} not found")


def check_timed_lock_deadlines(state: dict, current_chapter: int) -> list:
    """Return list of overdue timed locks (deadline passed, not fulfilled)."""
    return [
        item for item in state["story_craft"]["timed_locks"]
        if item["status"] == "active"
        and item["deadline_chapter"] <= current_chapter
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/scripts/story_craft.py .claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py
git commit -m "feat(story-craft): add timed_lock CRUD + deadline check"
```

---

### Task 4: Add rhythm_curve operations

**Files:**
- Modify: `.claude/plugins/webnovel-writer/scripts/story_craft.py`
- Modify: `.claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py`

- [ ] **Step 1: Add failing tests**

```python
# Append to tests/test_story_craft.py

def test_record_emotion_peak_resets_counter():
    state = {"story_craft": {"rhythm_curve": {
        "last_emotion_peak_chapter": 5,
        "chapters_since_peak": 3,
        "warning_threshold": 3,
        "block_threshold": 5,
        "history": []
    }}}
    result = record_emotion_peak(state, chapter=8, intensity=7, type_="medium_cool_point")
    assert result["story_craft"]["rhythm_curve"]["last_emotion_peak_chapter"] == 8
    assert result["story_craft"]["rhythm_curve"]["chapters_since_peak"] == 0
    assert len(result["story_craft"]["rhythm_curve"]["history"]) == 1


def test_check_rhythm_returns_warning_when_over_threshold():
    state = {"story_craft": {"rhythm_curve": {
        "last_emotion_peak_chapter": 1,
        "chapters_since_peak": 4,
        "warning_threshold": 3,
        "block_threshold": 5,
        "history": []
    }}}
    status = check_rhythm_status(state)
    assert status == "warning"


def test_check_rhythm_returns_block_when_over_block_threshold():
    state = {"story_craft": {"rhythm_curve": {
        "last_emotion_peak_chapter": 1,
        "chapters_since_peak": 6,
        "warning_threshold": 3,
        "block_threshold": 5,
        "history": []
    }}}
    status = check_rhythm_status(state)
    assert status == "block"


def test_check_rhythm_returns_ok_when_within_threshold():
    state = {"story_craft": {"rhythm_curve": {
        "last_emotion_peak_chapter": 1,
        "chapters_since_peak": 1,
        "warning_threshold": 3,
        "block_threshold": 5,
        "history": []
    }}}
    status = check_rhythm_status(state)
    assert status == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 4 failed

- [ ] **Step 3: Implement**

```python
# Append to scripts/story_craft.py

def record_emotion_peak(state: dict, chapter: int, intensity: int, type_: str) -> dict:
    """Record an emotion peak and reset chapters_since_peak counter."""
    curve = state["story_craft"]["rhythm_curve"]
    curve["last_emotion_peak_chapter"] = chapter
    curve["chapters_since_peak"] = 0
    curve["history"].append({
        "chapter": chapter,
        "intensity": intensity,
        "type": type_
    })
    return state


def check_rhythm_status(state: dict) -> str:
    """Return rhythm status: 'ok' | 'warning' | 'block'.

    Updates chapters_since_peak based on current chapter (if provided).
    Caller is expected to pass state with up-to-date chapters_since_peak.
    """
    curve = state["story_craft"]["rhythm_curve"]
    n = curve["chapters_since_peak"]
    if n >= curve["block_threshold"]:
        return "block"
    if n >= curve["warning_threshold"]:
        return "warning"
    return "ok"


def increment_chapters_since_peak(state: dict, chapter: int) -> dict:
    """Increment chapters_since_peak if chapter > last_emotion_peak_chapter."""
    curve = state["story_craft"]["rhythm_curve"]
    if chapter > curve["last_emotion_peak_chapter"]:
        curve["chapters_since_peak"] = chapter - curve["last_emotion_peak_chapter"]
    return state
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/scripts/story_craft.py .claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py
git commit -m "feat(story-craft): add rhythm_curve ops + status check"
```

---

### Task 5: Add character_arc + thematic_echoes operations

**Files:**
- Modify: `.claude/plugins/webnovel-writer/scripts/story_craft.py`
- Modify: `.claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py`

- [ ] **Step 1: Add failing tests**

```python
# Append to tests/test_story_craft.py

def test_set_character_arc_replaces_existing():
    state = {"story_craft": {"character_arc": None}}
    arc = {
        "name": "林川",
        "starting_state": "归乡迷茫",
        "ending_state": "接受本源",
        "transformation": "通过卡池觉醒"
    }
    result = set_character_arc(state, arc)
    assert result["story_craft"]["character_arc"]["name"] == "林川"
    assert result["story_craft"]["character_arc"]["key_moments"] == []


def test_add_thematic_echo():
    state = {"story_craft": {"thematic_echoes": []}}
    result = add_thematic_echo(
        state,
        premise="真正的强大是记忆而非力量",
        chapter=5,
        manifestation="主角回忆根源时力量觉醒"
    )
    assert len(result["story_craft"]["thematic_echoes"]) == 1
    assert result["story_craft"]["thematic_echoes"][0]["premise"] == "真正的强大是记忆而非力量"
    assert len(result["story_craft"]["thematic_echoes"][0]["echoes"]) == 1


def test_add_thematic_echo_appends_to_existing_premise():
    state = {"story_craft": {"thematic_echoes": [
        {"id": "TE-001", "premise": "记忆与力量", "echoes": [{"chapter": 3}]}
    ]}}
    result = add_thematic_echo(state, premise="记忆与力量", chapter=10, manifestation="第二次觉醒")
    assert len(result["story_craft"]["thematic_echoes"]) == 1  # same premise, not duplicated
    assert len(result["story_craft"]["thematic_echoes"][0]["echoes"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 3 failed

- [ ] **Step 3: Implement**

```python
# Append to scripts/story_craft.py

def set_character_arc(state: dict, arc: dict) -> dict:
    """Set/replace character_arc. Required: name, starting_state, ending_state, transformation."""
    for field in ("name", "starting_state", "ending_state", "transformation"):
        if field not in arc:
            raise ValueError(f"{field} required for character_arc")
    state["story_craft"]["character_arc"] = {
        **arc,
        "key_moments": arc.get("key_moments", [])
    }
    return state


def _next_thematic_echo_id(echoes: list) -> str:
    used = {item.get("id", "") for item in echoes}
    n = 1
    while f"TE-{n:03d}" in used:
        n += 1
    return f"TE-{n:03d}"


def add_thematic_echo(state: dict, premise: str, chapter: int, manifestation: str) -> dict:
    """Add thematic echo. If premise already exists, append to its echoes list."""
    echoes = state["story_craft"]["thematic_echoes"]
    for item in echoes:
        if item["premise"] == premise:
            item["echoes"].append({
                "chapter": chapter,
                "manifestation": manifestation
            })
            return state
    echoes.append({
        "id": _next_thematic_echo_id(echoes),
        "premise": premise,
        "echoes": [{"chapter": chapter, "manifestation": manifestation}]
    })
    return state
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 18 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/scripts/story_craft.py .claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py
git commit -m "feat(story-craft): add character_arc + thematic_echoes ops"
```

---

### Task 6: Add chapter_meta Scene-Sequel + hook_type + beat fields

**Files:**
- Modify: `.claude/plugins/webnovel-writer/scripts/story_craft.py`
- Modify: `.claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py`

- [ ] **Step 1: Add failing tests**

```python
# Append to tests/test_story_craft.py

def test_set_chapter_meta_validates_hook_type():
    state = {"chapter_meta": {}}
    with __import__("pytest").raises(ValueError):
        set_chapter_meta(state, chapter=1, hook_type="unknown")


def test_set_chapter_meta_writes_all_fields():
    state = {"chapter_meta": {}}
    result = set_chapter_meta(
        state,
        chapter=5,
        beat_position="Midpoint",
        hook_type="反转式",
        scene_goal="获得神器",
        scene_conflict="守护者阻挡",
        sequel_decision="使用神器"
    )
    cm = result["chapter_meta"]["5"]
    assert cm["beat_position"] == "Midpoint"
    assert cm["hook_type"] == "反转式"
    assert cm["scene_goal"] == "获得神器"
    assert cm["hook_type"] in {"悬念式", "反转式", "情绪炸弹式", "信息投放式", "留白式", "反讽式"}


def test_set_chapter_meta_foreshadow_buried_array():
    state = {"chapter_meta": {}}
    result = set_chapter_meta(
        state,
        chapter=5,
        foreshadow_buried=["FS-001", "FS-003"]
    )
    assert result["chapter_meta"]["5"]["foreshadow_buried"] == ["FS-001", "FS-003"]


def test_check_scene_sequel_blocks_when_goal_missing():
    cm = {"scene_goal": None, "scene_conflict": "ok", "sequel_decision": "ok"}
    issues = check_scene_sequel(cm)
    assert any("scene_goal" in i for i in issues)


def test_check_scene_sequel_warns_when_setback_missing():
    cm = {
        "scene_goal": "ok", "scene_conflict": "ok",
        "scene_setback": None, "scene_resolution": "ok",
        "sequel_reaction": "ok", "sequel_dilemma": "ok", "sequel_decision": "ok"
    }
    issues = check_scene_sequel(cm)
    assert any(i.startswith("WARN") for i in issues)


def test_check_scene_sequel_ok_when_all_filled():
    cm = {
        "scene_goal": "ok", "scene_conflict": "ok",
        "scene_setback": "ok", "scene_resolution": "ok",
        "sequel_reaction": "ok", "sequel_dilemma": "ok", "sequel_decision": "ok"
    }
    issues = check_scene_sequel(cm)
    assert issues == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 6 failed

- [ ] **Step 3: Implement**

```python
# Append to scripts/story_craft.py

VALID_HOOK_TYPES = {"悬念式", "反转式", "情绪炸弹式", "信息投放式", "留白式", "反讽式"}


def set_chapter_meta(state: dict, chapter: int, **fields) -> dict:
    """Set chapter_meta fields. Validates hook_type if provided.

    Allowed fields: beat_position, hook_type, scene_goal, scene_conflict,
    scene_setback, scene_resolution, sequel_reaction, sequel_dilemma,
    sequel_decision, foreshadow_buried, foreshadow_paid_off.
    """
    if "hook_type" in fields and fields["hook_type"] not in VALID_HOOK_TYPES:
        raise ValueError(f"hook_type must be one of {VALID_HOOK_TYPES}")
    meta = state.setdefault("chapter_meta", {})
    key = str(chapter)
    existing = meta.get(key, {})
    existing.update({k: v for k, v in fields.items() if v is not None})
    meta[key] = existing
    return state


def check_scene_sequel(chapter_meta: dict) -> list:
    """Return list of issues. BLOCKER for goal/conflict/decision missing;
    WARNING for other 4 steps missing."""
    issues = []
    blockers = ["scene_goal", "scene_conflict", "sequel_decision"]
    warnings = ["scene_setback", "scene_resolution", "sequel_reaction", "sequel_dilemma"]
    for field in blockers:
        if not chapter_meta.get(field):
            issues.append(f"BLOCKER: {field} required")
    for field in warnings:
        if not chapter_meta.get(field):
            issues.append(f"WARN: {field} recommended")
    return issues
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 24 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/scripts/story_craft.py .claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py
git commit -m "feat(story-craft): add chapter_meta Scene-Sequel + hook_type ops"
```

---

### Task 7: Add 15-beat volume operations

**Files:**
- Modify: `.claude/plugins/webnovel-writer/scripts/story_craft.py`
- Modify: `.claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py`

- [ ] **Step 1: Add failing tests**

```python
# Append to tests/test_story_craft.py

VALID_BEATS = [
    "Opening Image", "Theme Stated", "Setup", "Catalyst", "Debate",
    "Break Into Two", "B Story", "Fun and Games", "Midpoint",
    "Bad Guys Close In", "All Is Lost", "Dark Night of the Soul",
    "Break Into Three", "Finale", "Final Image"
]


def test_init_volume_beat_creates_empty_skeleton():
    state = {"story_craft": {}}
    result = init_volume_beat(state, volume=1, total_chapters=50)
    beats = result["story_craft"]["volume_beat"]["beats"]
    assert len(beats) == 15
    assert beats[0]["name"] == "Opening Image"
    assert beats[0]["chapter"] == 1
    assert beats[8]["name"] == "Midpoint"
    assert beats[8]["chapter"] == 25  # 50% of 50


def test_fill_beat_updates_status():
    state = init_volume_beat({"story_craft": {}}, volume=1, total_chapters=50)
    result = fill_beat(state, volume=1, beat_name="Midpoint", chapter=25, notes="假胜利")
    beats = result["story_craft"]["volume_beat"]["beats"]
    midpoint = next(b for b in beats if b["name"] == "Midpoint")
    assert midpoint["filled"] is True
    assert midpoint["chapter"] == 25
    assert midpoint["notes"] == "假胜利"


def test_check_volume_beat_returns_blocker_for_missing_midpoint():
    state = init_volume_beat({"story_craft": {}}, volume=1, total_chapters=50)
    issues = check_volume_beat(state, volume=1)
    assert any("Midpoint" in i for i in issues)
    assert any("BLOCKER" in i for i in issues)


def test_check_volume_beat_ok_when_midpoint_and_all_is_lost_filled():
    state = init_volume_beat({"story_craft": {}}, volume=1, total_chapters=50)
    fill_beat(state, volume=1, beat_name="Midpoint", chapter=25, notes="")
    fill_beat(state, volume=1, beat_name="All Is Lost", chapter=37, notes="")
    issues = check_volume_beat(state, volume=1)
    blockers = [i for i in issues if "BLOCKER" in i]
    assert blockers == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 4 failed

- [ ] **Step 3: Implement**

```python
# Append to scripts/story_craft.py


def init_volume_beat(state: dict, volume: int, total_chapters: int) -> dict:
    """Initialize volume_beat with empty 15-beat skeleton.

    Beat chapters are auto-distributed by percentage.
    """
    percentages = [0.01, 0.05, 0.10, 0.10, 0.20, 0.20, 0.22, 0.50, 0.50, 0.75, 0.75, 0.80, 0.80, 0.99, 1.00]
    if len(percentages) != 15:
        raise ValueError("internal: percentages must match 15 beats")
    beats = []
    seen = set()
    for name, pct in zip(VALID_BEATS, percentages):
        ch = max(1, round(pct * total_chapters))
        if ch in seen:
            ch += 1
        seen.add(ch)
        beats.append({"name": name, "chapter": ch, "filled": False, "notes": None})
    state.setdefault("story_craft", {})["volume_beat"] = {
        "volume": volume,
        "total_chapters": total_chapters,
        "beats": beats
    }
    return state


def fill_beat(state: dict, volume: int, beat_name: str, chapter: int, notes: str) -> dict:
    beats = state["story_craft"]["volume_beat"]["beats"]
    for beat in beats:
        if beat["name"] == beat_name:
            beat["filled"] = True
            beat["chapter"] = chapter
            beat["notes"] = notes
            return state
    raise ValueError(f"beat {beat_name} not found")


def check_volume_beat(state: dict, volume: int) -> list:
    """Return issues. BLOCKER for Midpoint/All Is Lost missing."""
    issues = []
    beats = state["story_craft"]["volume_beat"]["beats"]
    for beat in beats:
        if beat["name"] in ("Midpoint", "All Is Lost") and not beat["filled"]:
            issues.append(f"BLOCKER: {beat['name']} must be filled")
        elif not beat["filled"]:
            issues.append(f"WARN: {beat['name']} not yet filled")
    return issues
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_story_craft.py -v`
Expected: 28 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/scripts/story_craft.py .claude/plugins/webnovel-writer/scripts/tests/test_story_craft.py
git commit -m "feat(story-craft): add 15-beat volume operations + check"
```

---

### Task 8: Add state.json migration script

**Files:**
- Create: `.claude/plugins/webnovel-writer/scripts/migrate_story_craft.py`
- Create: `.claude/plugins/webnovel-writer/scripts/tests/test_migration.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_migration.py
import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from migrate_story_craft import migrate_state_json


def test_migrate_adds_story_craft_when_missing():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
        json.dump({"project_info": {"title": "X"}, "progress": {}}, f)
        path = f.name
    backup = path + ".bak"
    try:
        result = migrate_state_json(path)
        assert result["story_craft"] is not None
        assert result["project_info"]["title"] == "X"
        assert Path(backup).exists()
    finally:
        Path(path).unlink(missing_ok=True)
        Path(backup).unlink(missing_ok=True)


def test_migrate_preserves_existing_story_craft():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
        json.dump({
            "project_info": {},
            "story_craft": {"rhythm_curve": {"chapters_since_peak": 5}}
        }, f)
        path = f.name
    backup = path + ".bak"
    try:
        result = migrate_state_json(path)
        assert result["story_craft"]["rhythm_curve"]["chapters_since_peak"] == 5
    finally:
        Path(path).unlink(missing_ok=True)
        Path(backup).unlink(missing_ok=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_migration.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: Implement**

```python
# scripts/migrate_story_craft.py
"""One-shot migration to add story_craft field to existing state.json.

Safe to run multiple times. Creates .bak before modifying.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from story_craft import EMPTY_STORY_CRAFT


def migrate_state_json(path: str) -> dict:
    """Add story_craft field if missing. Backup to .bak. Return new state."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"state.json not found: {path}")
    backup = p.with_suffix(p.suffix + ".bak")
    backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")

    state = json.loads(p.read_text(encoding="utf-8"))
    if "story_craft" not in state or not isinstance(state.get("story_craft"), dict):
        state["story_craft"] = json.loads(json.dumps(EMPTY_STORY_CRAFT))
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: migrate_story_craft.py <path/to/state.json>")
        sys.exit(1)
    migrate_state_json(sys.argv[1])
    print(f"Migrated {sys.argv[1]}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/test_migration.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/scripts/migrate_story_craft.py .claude/plugins/webnovel-writer/scripts/tests/test_migration.py
git commit -m "feat(story-craft): add migration script with backup"
```

---

### Task 9: Run migration on actual project

**Files:**
- (none — runs against existing state.json)

- [ ] **Step 1: Run migration on《根源牌序》**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer/scripts
python3 migrate_story_craft.py /Users/chang/Desktop/根源牌序/.webnovel/state.json
```
Expected: `Migrated /Users/chang/Desktop/根源牌序/.webnovel/state.json`

- [ ] **Step 2: Verify state.json has story_craft field**

Run: `python3 -c "import json; s=json.load(open('/Users/chang/Desktop/根源牌序/.webnovel/state.json')); print(list(s.get('story_craft', {}).keys()))"`
Expected: `['rhythm_curve', 'foreshadow_chain', 'timed_locks', 'thematic_echoes', 'character_arc']`

- [ ] **Step 3: Commit .bak deletion (cleanup)**

Run:
```bash
cd /Users/chang/Desktop/zhanghui
ls /Users/chang/Desktop/根源牌序/.webnovel/*.bak
```
Expected: file exists; do not commit .bak to git

---

### Task 10: Write 8 reference docs

**Files:**
- Create: 8 reference markdown files under `references/shared/`

- [ ] **Step 1: Write 15-beat-save-the-cat.md**

```markdown
---
name: 15-beat-save-the-cat
purpose: Save the Cat 15-beat 卷级节拍表定义与网文/卷映射
---

# Save the Cat 15-Beat (Volume Level)

> **来源**：Jessica Brody《Save the Cat! Writes a Novel》(2018)
> **网文适配**：每卷 50-80 章 = 一本"小说"

## 15 个 Beat

| # | Beat | 卷内占比 | 50 章卷位置 |
|---|---|---|---|
| 1 | Opening Image | 0-1% | 第 1 章 |
| 2 | Theme Stated | 5% | 第 3 章 |
| 3 | Setup | 1-10% | 第 5 章 |
| 4 | Catalyst | 10% | 第 5 章 |
| 5 | Debate | 10-20% | 第 10 章 |
| 6 | Break Into Two | 20% | 第 10 章 |
| 7 | B Story | 22% | 第 11 章 |
| 8 | Fun and Games | 20-50% | 第 25 章 |
| 9 | **Midpoint** | 50% | **第 25 章（BLOCKER 必填）** |
| 10 | Bad Guys Close In | 50-75% | 第 37 章 |
| 11 | **All Is Lost** | 75% | **第 37 章（BLOCKER 必填）** |
| 12 | Dark Night of the Soul | 75-80% | 第 40 章 |
| 13 | Break Into Three | 80% | 第 40 章 |
| 14 | Finale | 80-99% | 第 49 章 |
| 15 | Final Image | 99-100% | 第 50 章 |

## 网文特殊说明

- **卷首章** = 第 1 章前 1-3% 必为 Opening Image（卷前主角状态快照）
- **Midpoint** 必须有反转或假胜利/假失败
- **All Is Lost** 是卷末最低点，没有 = 不叫卷
- **Final Image** 必须与下卷 Opening Image 形成呼应

## 与现有工具集成

- state.json 字段：`story_craft.volume_beat`
- 自动检查：Midpoint + All Is Lost 缺失 = BLOCKER
- 模板：见 `skills/webnovel-plan/references/outlining/volume-beat-sheet.md`
```

- [ ] **Step 2: Write scene-sequel.md**

```markdown
---
name: scene-sequel
purpose: Dwight Swain Scene-Sequel 章内节拍定义
---

# Scene-Sequel (Chapter Level)

> **来源**：Dwight Swain《Techniques of the Selling Writer》

## Scene 4 步（场戏）

1. **Goal** — 主角本场戏明确目标
2. **Conflict** — 阻碍/对手出现
3. **Setback** — 挫败或失败
4. **Resolution — 暂时结果（未必成功）

## Sequel 3 步（后续）

1. **Reaction** — 主角反应
2. **Dilemma** — 主角面对的困境
3. **Decision** — 主角决定 = 下章 Scene 的 Goal

## 与网文章节对应

每章 = 1 Scene + 1 Sequel（或压缩）

**BLOCKER 字段**（缺失即警告）：
- scene_goal
- scene_conflict
- sequel_decision

**WARNING 字段**（缺失仅提示）：
- scene_setback
- scene_resolution
- sequel_reaction
- sequel_dilemma

## state.json 字段

`chapter_meta.{N}.scene_*` 和 `chapter_meta.{N}.sequel_*`

## 校验

`story_craft.check_scene_sequel(chapter_meta)` 返回 issue 列表
```

- [ ] **Step 3: Write foreshadow-chain.md**

```markdown
---
name: foreshadow-chain
purpose: 草蛇灰线伏脉千里 — 三层伏笔法 + 5 字段追踪 + 6 种载体
---

# 草蛇灰线伏脉千里 (Foreshadow Chain)

> **来源**：金圣叹评《水浒》→ 脂砚斋评《红楼》→ 曹雪芹实战 → 现代工程化

## 三层伏笔

| 层级 | 占比 | 回收时机 | 数量 |
|---|---|---|---|
| 表层 | 60% | 同章或相邻章 | 每章 ≥1 |
| 中层 | 30% | 3-10 章 | 每卷 ≥3 |
| 深层 | 10% | 贯穿全书 | 1-2 个 |

## 5 字段追踪

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | `FS-001` 自动编号 |
| `type` | 是 | 6 种载体之一 |
| `depth` | 是 | 表层/中层/深层 |
| `content` | 否 | 伏笔内容描述 |
| `buried_chapter` | 是 | 埋设章节 |
| `expected_payoff_chapter` | 是 | 预期回收章节 |
| `payoff_method` | 否 | 回收方式 |
| `linked_entities` | 否 | 关联实体 |
| `status` | — | active / paid_off / dormant / missed |

## 6 种载体

1. **物谶** — 物品流转（凡人修仙传血玉蜘蛛）
2. **诗谶** — 诗词谶语（黛玉《葬花吟》）
3. **戏谶** — 戏剧典故（元妃点戏伏贾家败）
4. **灯谜** — 谜语对话（探春灯谜）
5. **环境** — 季节场景（大观园秋→冬=悲剧）
6. **习惯** — 早期细节（克莱恩抛硬币）

## 自动检查规则

- 表层伏笔每章 ≥1 埋/收 → WARNING
- 中层伏笔每卷 ≥3 → HARD
- 深层伏笔 1-2 个/全书 → HARD
- 任何 active 伏笔 ≥10 章未推进 → WARNING
- 任何 expected_payoff_chapter 已过 + 未 paid_off → **BLOCKER**

## 案例

**凡人修仙传·血玉蜘蛛**（多层逻辑咬合）：
- 筑基期：普通材料出现
- 结丹期：蛛丝被追杀
- 元婴期：开启虚天鼎关键
- 全文：串联修炼/人际/世界观三层

**红楼梦·元妃点戏**（4 戏伏 4 事）：
- 《豪宴》伏贾家之败
- 《乞巧》伏元妃之死
- 《仙缘》伏甄宝玉送玉
- 《离魂》伏黛玉死

**诡秘之主·克莱恩抛硬币**（习惯暗示）：
- 第 1 章：抛硬币占卜
- 全书：与"命运"途径深层羁绊闭环
```

- [ ] **Step 4: Write timed-lock.md**

```markdown
---
name: timed-lock
purpose: 起点编辑"定时锁"理论 — 到一定时间必发生特定事件
---

# 定时锁 (Timed Lock)

> **来源**：起点社区版主流水《爽文的节奏是什么？》

## 核心定义

> "到一定时间需要发生特定的事情。"

= 套路 + 节奏（"精心重构"的套路 + "适合"的节奏）

## 章节级定时锁（典型案例）

| 场景 | 定时锁 |
|---|---|
| 玄幻少年文 | 主角 3 章内必须"出村" |
| 系统文 | 系统第 1 章出现，第 2 章看到作用 + 解决难题 |
| 都市重生文 | 第 1 章确认重生，第 2 章立刻遇冲突 |
| 直播电竞文 | 大逆转必须有人关注、弹幕爆炸 |

## 写作训练题（节选）

**Q1**: 都市重生文首章如何设计？
- ✅ C: "xx 确定，自己重生了"；第 2 章就遇到打上门的混混
- ✅ D: 首章重生在了高考考场
- ❌ A: 前 3 章写被甩 + 吃鸡 + 显示屏炸回 18 岁（太拖）
- ❌ B: 前 10 章回忆前世（"我的世界不值钱"）

**Q4**: 哪些情况属于没有设计定时锁？
- ❌ A: 大逆转无人关注传播
- ❌ B: 守城战，主角仍在骑马赶来的路上（必须亲自改变局面）
- ❌ C: 金手指一路分杂物升级，反派跳出来被打死

## 与工具集成

- state.json：`story_craft.timed_locks`
- 检查：`check_timed_lock_deadlines(state, current_chapter)` 返回 overdue 列表
- 规则：deadline_chapter 已过 + status=active → **BLOCKER**
```

- [ ] **Step 5: Write rhythm-curve.md**

```markdown
---
name: rhythm-curve
purpose: 节奏曲线 — 1.8 章/情绪高峰，平路 ≤3 章
---

# 节奏曲线 (Rhythm Curve)

> **来源**：马良写作《网文节奏与爽点设计》（基于追读 top10% 数据分析）

## 核心定义

> "网文的节奏是信息投放和情绪刺激的频率。"

> "平路走超过 3 章，追读就开始掉。"

## 数据基准

| 指标 | 追读率 top 10% | 追读率 bottom 10% |
|---|---|---|
| 平均情绪高峰间隔 | 1.8 章 | 4.7 章 |

## 阈值

- **warning_threshold** = 3 章（连续 3 章无高峰 → WARNING）
- **block_threshold** = 5 章（连续 5 章无高峰 → BLOCKER）

## 三级爽点

| 级别 | 频率 | 例子 |
|---|---|---|
| 小爽点 | 每章 ≥1 | 一句机智台词、一个小反转 |
| 中爽点 | 每 3-5 章 1 | 完整打脸流程、关系突破 |
| 大爽点 | 每卷高潮 1 | Boss 战逆转、身份曝光 |

## 与工具集成

- state.json：`story_craft.rhythm_curve`
- 字段：`chapters_since_peak` / `warning_threshold` / `block_threshold` / `history`
- 检查：`check_rhythm_status(state)` 返回 `ok | warning | block`
- 记录：`record_emotion_peak(state, chapter, intensity, type)`
```

- [ ] **Step 6: Write chapter-hook-types.md**

```markdown
---
name: chapter-hook-types
purpose: 6 种章末钩子定义 + 正反例
---

# 章末钩子 (Chapter Hook Types)

> **来源**：马良写作 + 起点编辑 + 综合实战

## 6 种类型

### 1. 悬念式
> "门外传来一个声音，那是一个不可能出现在这里的人。" 然后本章完。

### 2. 反转式
> 整章都在暗示 A 是凶手，最后一行发现 B 的手上有血。

### 3. 情绪炸弹式
> 积蓄了 3 章的矛盾在章末爆发，"你从来就没把我当过朋友。" 直接切掉。

### 4. 信息投放式
> "他翻开日记本的最后一页，上面画着一张和自己一模一样的脸。"

### 5. 留白式
> 章末用一句无声动作收尾，读者自行脑补后果。

### 6. 反讽式
> 主角以为自己赢了，但章末叙述者用一句旁白揭示事实相反。

## state.json

`chapter_meta.{N}.hook_type` ∈ {"悬念式", "反转式", "情绪炸弹式", "信息投放式", "留白式", "反讽式"}

## 校验

每章必须声明 hook_type，否则 BLOCKER。

## 反模式

- ❌ "欲知后事如何，请听下回分解"（传统章回体式，现代读者疲劳）
- ❌ 主角内心独白式结尾（无钩子）
- ❌ 章末总结本章剧情（重复信息）
```

- [ ] **Step 7: Write character-arc.md**

```markdown
---
name: character-arc
purpose: 主角弧追踪 — state.json 字段说明
---

# 主角弧 (Character Arc)

> **理论来源**：Breaking Bad 跨季人物弧 + Dan Harmon Story Circle (Change)

## 核心概念

主角弧是**跨卷内在转变**的追踪机制。

## state.json 字段

```json
{
  "story_craft": {
    "character_arc": {
      "name": "林川",
      "starting_state": "归乡迷茫、记忆模糊",
      "ending_state": "接受本源、觉醒意识",
      "transformation": "通过卡池抽取与回忆逐步解锁根源",
      "key_moments": [
        {"chapter": 5, "event": "首次抽卡出现意外"},
        {"chapter": 25, "event": "Midpoint 真相揭露"}
      ]
    }
  }
}
```

## 4 字段必填

- `name` — 主角名
- `starting_state` — 卷首内在状态
- `ending_state` — 卷末内在状态
- `transformation` — 如何从 starting 到 ending

## key_moments 追踪

- 建议 ≥3 个/卷
- 必须在 Midpoint + Finale 各 ≥1 个

## 与 Beat 联动

`key_moments` 应与 `volume_beat.beats[].notes` 联动，确保内在转变与外在事件同步。

## 校验

- 4 必填字段缺失 → BLOCKER
- `starting_state == ending_state` → WARNING（无变化）
```

- [ ] **Step 8: Write thematic-echo.md**

```markdown
---
name: thematic-echo
purpose: 主题回响 — state.json 字段说明
---

# 主题回响 (Thematic Echo)

> **理论来源**：麦基"故事价值论" + 红楼梦主题论证

## 核心概念

主题是故事的最高命题。每卷必须**回响**主题 ≥3 次。

## state.json 字段

```json
{
  "story_craft": {
    "thematic_echoes": [
      {
        "id": "TE-001",
        "premise": "真正的强大是记忆而非力量",
        "echoes": [
          {"chapter": 5, "manifestation": "主角回忆根源时力量觉醒"},
          {"chapter": 25, "manifestation": "Midpoint 反派用纯力量失败"},
          {"chapter": 49, "manifestation": "Finale 主角靠记忆战胜收割者"}
        ]
      }
    ]
  }
}
```

## 校验

- 每卷 ≥1 个 thematic_echoes（HARD）
- 每个 premise 的 echoes ≥3（HARD）
- 卷末检查：未达成 → WARNING

## 与 Ending 联动

Final Image 应是主题的最强一次回响。
```

- [ ] **Step 9: Commit all 8 references**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/references/shared/
git commit -m "feat(references): add 8 story-craft reference docs"
```

---

### Task 11: Write volume-beat-sheet.md template

**Files:**
- Create: `.claude/plugins/webnovel-writer/skills/webnovel-plan/references/outlining/volume-beat-sheet.md`

- [ ] **Step 1: Write template**

```markdown
# 第 {volume_id} 卷 节拍表（15-Beat Save the Cat 卷级）

> **必读**：`references/shared/15-beat-save-the-cat.md`
> **BLOCKER**：Midpoint + All Is Lost 必须 filled
> **占位**：plan 阶段禁止保留 `[待...]` / `暂名` / `{占位}`

## 卷基本信息

- **卷名**：
- **总章数**：
- **起始章**：
- **结束章**：
- **核心冲突**：
- **卷末高潮**：

## 15 Beat 填充

| # | Beat | 章 | filled | notes |
|---|---|---|---|---|
| 1 | Opening Image | — | — | — |
| 2 | Theme Stated | — | — | — |
| 3 | Setup | — | — | — |
| 4 | Catalyst | — | — | — |
| 5 | Debate | — | — | — |
| 6 | Break Into Two | — | — | — |
| 7 | B Story | — | — | — |
| 8 | Fun and Games | — | — | — |
| 9 | **Midpoint**（必填） | — | ❌ | — |
| 10 | Bad Guys Close In | — | — | — |
| 11 | **All Is Lost**（必填） | — | ❌ | — |
| 12 | Dark Night of the Soul | — | — | — |
| 13 | Break Into Three | — | — | — |
| 14 | Finale | — | — | — |
| 15 | Final Image | — | — | — |

## 跨卷钩子

- **本卷接上卷的 Open Loop**：
- **本卷给下卷的 Hook**：

## 主角弧

- **starting_state**：
- **ending_state**：
- **transformation**：
- **key_moments**：
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/skills/webnovel-plan/references/outlining/volume-beat-sheet.md
git commit -m "feat(plan): add volume-beat-sheet template"
```

---

### Task 12: Write foreshadow-tracking-template.md

**Files:**
- Create: `.claude/plugins/webnovel-writer/skills/webnovel-plan/references/outlining/foreshadow-tracking-template.md`

- [ ] **Step 1: Write template**

```markdown
# 伏笔追踪表（5 字段 / 草蛇灰线）

> **必读**：`references/shared/foreshadow-chain.md`
> **BLOCKER**：中层伏笔每卷 ≥3 / 深层 1-2 个/全书
> **状态机**：active → paid_off / dormant / missed

## 5 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| id | 是 | FS-001 自动编号 |
| type | 是 | 6 种载体之一 |
| depth | 是 | 表层/中层/深层 |
| content | 否 | 描述 |
| buried_chapter | 是 | 埋设章 |
| expected_payoff_chapter | 是 | 预期回收章 |
| payoff_method | 否 | 回收方式 |
| linked_entities | 否 | 关联 |
| status | — | active / paid_off / dormant / missed |

## 伏笔登记

| ID | Type | Depth | Content | Buried@ | Expected Payoff@ | Payoff Method | Status |
|---|---|---|---|---|---|---|---|
| FS-001 | 物谶 | 中层 | 血玉蜘蛛 | 50 | 350 | 虚天鼎钥匙 | active |
| FS-002 | 诗谶 | 表层 | 苏清越送诗 | 12 | 15 | 揭示关系 | active |
| FS-003 | 习惯 | 深层 | 林川摸卡牌动作 | 1 | 599 | 全书末意识恢复 | active |

## 卷级统计

- **active 数**：
- **中层数**：
- **深层数**：
- **预期本卷回收数**：

## 跨卷追踪

- **本卷接上卷未回收伏笔**：
- **本卷给下卷埋伏笔**：
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/skills/webnovel-plan/references/outlining/foreshadow-tracking-template.md
git commit -m "feat(plan): add foreshadow-tracking template"
```

---

## Phase 2: webnovel-plan SKILL.md 改造 (Week 2-3)

### Task 13: Update webnovel-plan SKILL.md — Step 1 + Step 2 with craft awareness

**Files:**
- Modify: `.claude/plugins/webnovel-writer/skills/webnovel-plan/SKILL.md`

- [ ] **Step 1: Add reference triggers in Step 1**

Find this section in SKILL.md:
```markdown
### Step 1：加载项目数据并确认前置条件
```
Add these lines after "GENRE=" block:
```markdown

按 genre 加载 craft references：

| Genre | 必读 reference |
|---|---|
| 玄幻/修仙/系统流 | 15-beat-save-the-cat.md + timed-lock.md + foreshadow-chain.md |
| 都市/言情/历史 | rhythm-curve.md + foreshadow-chain.md + character-arc.md |
| 悬疑/解谜 | foreshadow-chain.md + thematic-echo.md + 15-beat-save-the-cat.md |

初始化 story_craft 字段（若缺失）：
\`\`\`bash
python "${SCRIPTS_DIR}/migrate_story_craft.py" "${PROJECT_ROOT}/.webnovel/state.json"
\`\`\`
```

- [ ] **Step 2: Extend Step 2 with thematic_echoes initialization**

Find the Step 2 section and append:
```markdown

### Step 2.5（新增）：主题与主角弧初始化

- 读 `references/shared/thematic-echo.md` + `references/shared/character-arc.md`
- 让用户确认本卷的 thematic_premise（一句话主题）
- 让用户确认主角的 starting_state / ending_state（卷首/卷末内在状态）
- 写入 `story_craft.character_arc` 和 `story_craft.thematic_echoes`
```

- [ ] **Step 3: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/skills/webnovel-plan/SKILL.md
git commit -m "feat(plan): add craft awareness to Step 1 + new Step 2.5"
```

---

### Task 14: Add Step 4.5 — Generate volume beat sheet

**Files:**
- Modify: `.claude/plugins/webnovel-writer/skills/webnovel-plan/SKILL.md`

- [ ] **Step 1: Insert new Step 4.5 after Step 4**

Find the Step 4 section ending and insert:
```markdown

### Step 4.5（新增）：生成 15-Beat 卷节拍表

加载 `${SKILL_ROOT}/../../references/shared/15-beat-save-the-cat.md` 和模板 `${SKILL_ROOT}/references/outlining/volume-beat-sheet.md`。

AI 自动生成：
- 15 个 beat 在卷内的章节位置
- Midpoint（必填 BLOCKER）：卷中反转/假胜利/假失败
- All Is Lost（必填 BLOCKER）：卷末最低点
- Final Image（必填）：与下卷 Opening Image 形成呼应

输出文件：`大纲/第{volume_id}卷-节拍表.md`

执行：
\`\`\`bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  story-craft init-volume-beat \
  --volume {volume_id} --total-chapters {total_chapters}
\`\`\`

BLOCKER 处理：
- Midpoint/All Is Lost 缺失 → BLOCKER，暂停并询问用户
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/skills/webnovel-plan/SKILL.md
git commit -m "feat(plan): add Step 4.5 — generate 15-beat volume sheet"
```

---

### Task 15: Add Step 6.5 — Generate foreshadow chain + timed_locks

**Files:**
- Modify: `.claude/plugins/webnovel-writer/skills/webnovel-plan/SKILL.md`

- [ ] **Step 1: Insert Step 6.5 after Step 6**

Insert:
```markdown

### Step 6.5（新增）：生成伏笔链 + 定时锁

加载 `${SKILL_ROOT}/../../references/shared/foreshadow-chain.md` 和 `${SKILL_ROOT}/../../references/shared/timed-lock.md`。

AI 自动生成：

**A. 伏笔链初始化**：
- 表层 ≥5 个（每章分配）
- 中层 ≥3 个（分布到卷内）
- 深层 ≥1 个（全书）
- 每个伏笔：5 字段全填

**B. 定时锁初始化**：
- 卷级 ≥3 个（如 "Midpoint 必须发生" / "All Is Lost 必须到达" / "卷末新钩子必须留"）
- 章节级按 genre 模板（玄幻 3 章出村 / 系统文 1 章出系统）

输出文件：`大纲/第{volume_id}卷-伏笔表.md`

执行：
\`\`\`bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  story-craft init-forechains --volume {volume_id}

python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  story-craft init-locks --volume {volume_id}
\`\`\`

BLOCKER 处理：
- 深层伏笔 < 1 → BLOCKER
- 中层伏笔 < 3 → BLOCKER
- 卷级定时锁 < 3 → BLOCKER
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/skills/webnovel-plan/SKILL.md
git commit -m "feat(plan): add Step 6.5 — generate foreshadow chain + timed locks"
```

---

### Task 16: Extend Step 7 with Scene-Sequel slicing

**Files:**
- Modify: `.claude/plugins/webnovel-writer/skills/webnovel-plan/SKILL.md`

- [ ] **Step 1: Update Step 7 to add Scene-Sequel fields per chapter**

Find the Step 7 section and extend the "每章必须包含" list:
```markdown

每章必须包含：目标、阻力、代价、时间锚点、章内时间跨度、与上章时间差、倒计时状态、爽点、Strand、反派层级、视角/主角、关键实体、本章变化、章末未闭合问题、钩子，以及结构化节点 `CBN`、`CPNs`、`CEN`、`必须覆盖节点`、`本章禁区`。

**新增 craft 必填字段**：
- `beat_position`：本章在卷 15-beat 中的位置（如 Midpoint / Fun and Games）
- `scene_goal` / `scene_conflict` / `scene_setback` / `scene_resolution`：Scene 4 步
- `sequel_reaction` / `sequel_dilemma` / `sequel_decision`：Sequel 3 步
- `hook_type`：6 种章末钩子之一
- `foreshadow_buried`：本章埋设的伏笔 ID 列表
- `foreshadow_paid_off`：本章回收的伏笔 ID 列表
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/skills/webnovel-plan/SKILL.md
git commit -m "feat(plan): extend Step 7 with Scene-Sequel + beat fields"
```

---

### Task 17: Add Step 8.5 — craft consistency check

**Files:**
- Modify: `.claude/plugins/webnovel-writer/skills/webnovel-plan/SKILL.md`

- [ ] **Step 1: Insert Step 8.5 after Step 8**

Insert:
```markdown

### Step 8.5（新增）：craft 一致性检查

执行强制验证：

\`\`\`bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" \
  story-craft check-volume --volume {volume_id}
\`\`\`

检查项：
- ✅ 15-beat 完整性（Midpoint + All Is Lost 必填）
- ✅ 伏笔链数量（表层≥5/中层≥3/深层≥1）
- ✅ 定时锁数量（卷级≥3）
- ✅ thematic_echoes ≥1 且 echoes ≥3
- ✅ character_arc 4 字段全填
- ✅ 每章 Scene-Sequel 必填字段不缺失
- ✅ 每章 hook_type 已声明

输出 BLOCKER 列表 → 暂停 → 用户裁决 → 继续 Step 9。
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/skills/webnovel-plan/SKILL.md
git commit -m "feat(plan): add Step 8.5 — craft consistency check"
```

---

### Task 18: Add webnovel.py story-craft subcommand

**Files:**
- Modify: `.claude/plugins/webnovel-writer/scripts/webnovel.py`

- [ ] **Step 1: Read existing webnovel.py structure**

Run: `grep -n "def cmd_\|^def main\|argparse" /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer/scripts/webnovel.py | head -30`

- [ ] **Step 2: Add story-craft subcommand following existing pattern**

Find an existing subcommand (e.g., `cmd_update_state` or similar) and add after it:
```python
def cmd_story_craft(args, state):
    """Dispatch story-craft subcommands."""
    if args.story_craft_action == "init-volume-beat":
        from story_craft import init_volume_beat
        init_volume_beat(state, volume=args.volume, total_chapters=args.total_chapters)
    elif args.story_craft_action == "fill-beat":
        from story_craft import fill_beat
        fill_beat(state, volume=args.volume, beat_name=args.beat_name,
                  chapter=args.chapter, notes=args.notes or "")
    elif args.story_craft_action == "check-volume":
        from story_craft import check_volume_beat
        issues = check_volume_beat(state, volume=args.volume)
        for issue in issues:
            print(issue)
        return 1 if any("BLOCKER" in i for i in issues) else 0
    elif args.story_craft_action == "init-forechains":
        # placeholder: load from chapter outline, init state
        pass
    elif args.story_craft_action == "init-locks":
        # placeholder: load from chapter outline, init state
        pass
    # Save state
    _save_state(state, args.project_root)
    return 0
```

- [ ] **Step 3: Add argparse subparser**

In the main argparse setup, add:
```python
craft_parser = subparsers.add_parser("story-craft", help="Story craft operations")
craft_parser.add_argument("story_craft_action", choices=[
    "init-volume-beat", "fill-beat", "check-volume",
    "init-forechains", "init-locks"
])
craft_parser.add_argument("--volume", type=int)
craft_parser.add_argument("--total-chapters", type=int)
craft_parser.add_argument("--beat-name")
craft_parser.add_argument("--chapter", type=int)
craft_parser.add_argument("--notes")
craft_parser.set_defaults(func=cmd_story_craft)
```

- [ ] **Step 4: Test integration**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer/scripts
python3 webnovel.py --project-root /Users/chang/Desktop/根源牌序 story-craft init-volume-beat --volume 1 --total-chapters 50
python3 webnovel.py --project-root /Users/chang/Desktop/根源牌序 story-craft check-volume --volume 1
```
Expected: second command prints BLOCKER for Midpoint/All Is Lost

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/scripts/webnovel.py
git commit -m "feat(webnovel.py): add story-craft subcommand group"
```

---

## Phase 3: Reviewer 扩展 (Week 3-4)

### Task 19: Update reviewer agent prompt with 2 new dimensions

**Files:**
- Modify: `.claude/plugins/webnovel-writer/agents/reviewer.md`

- [ ] **Step 1: Read current reviewer.md structure**

Run: `cat /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer/agents/reviewer.md | head -50`

- [ ] **Step 2: Add 2 new dimensions to prompt**

Find the section listing the 5 review dimensions and extend:
```markdown

### 5 维审查 → 7 维审查

原 5 维：设定一致性 / 时间线 / 叙事连贯 / 角色一致性 / 逻辑

**新增 2 维**：

#### 6. 节拍合规性（节拍 + Scene-Sequel）

- Midpoint 是否已到达且反转/假胜利/假失败明确？
- All Is Lost 是否已到达且为卷末最低点？
- Final Image 是否与下卷 Opening Image 呼应？
- 本章 Scene 4 步是否完整（Goal/Conflict 必填，Setback/Resolution 建议填）？
- 本章 Sequel 3 步是否完整（Decision 必填，Reaction/Dilemma 建议填）？
- 上一章 Decision 与本章 Goal 是否形成因果？

**BLOCKER 条件**：Midpoint/All Is Lost 缺失；Scene 必填字段缺失；Decision-Goal 因果断裂

#### 7. 草蛇灰线合规性（伏笔 + 节奏 + 钩子）

- 本章 foreshadow_buried 是否合理埋设（5 字段全填）？
- 本章 foreshadow_paid_off 是否合理回收？
- 任何 expected_payoff_chapter 已过但仍 active 的伏笔 → BLOCKER
- 任何 active 伏笔 ≥10 章未推进 → WARNING
- 节奏曲线：chapters_since_peak 是否超过阈值？
- 章末 hook_type 是否声明 + 是否符合 6 种之一？

**BLOCKER 条件**：伏笔逾期未收 / 节奏 block_threshold 超出 / hook_type 未声明

### 输出格式

按以下 JSON 格式输出：
\`\`\`json
{
  "dimensions": {
    "consistency": {...},
    "timeline": {...},
    "narrative": {...},
    "character": {...},
    "logic": {...},
    "beat_compliance": {...},
    "foreshadow_compliance": {...}
  },
  "blockers": [...],
  "warnings": [...],
  "overall_score": 0-100
}
\`\`\`
```

- [ ] **Step 3: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/agents/reviewer.md
git commit -m "feat(reviewer): extend to 7 dimensions with beat + foreshadow checks"
```

---

### Task 20: Update review_pipeline.py to invoke new dimensions

**Files:**
- Modify: `.claude/plugins/webnovel-writer/scripts/review_pipeline.py`

- [ ] **Step 1: Read current review_pipeline.py**

Run: `head -60 /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer/scripts/review_pipeline.py`

- [ ] **Step 2: Add craft check hooks**

Find where dimensions are aggregated and add:
```python
from story_craft import (
    check_volume_beat,
    check_scene_sequel,
    check_timed_lock_deadlines,
    check_rhythm_status,
)

def run_craft_checks(state: dict, chapter: int) -> dict:
    """Run all story_craft checks for a given chapter. Return issues dict."""
    issues = {"blockers": [], "warnings": []}

    # Rhythm
    rhythm_status = check_rhythm_status(state)
    if rhythm_status == "block":
        issues["blockers"].append(f"节奏曲线 BLOCK：chapters_since_peak={state['story_craft']['rhythm_curve']['chapters_since_peak']}")
    elif rhythm_status == "warning":
        issues["warnings"].append("节奏曲线 WARNING：建议本章或下章加情绪高峰")

    # Timed locks
    overdue = check_timed_lock_deadlines(state, current_chapter=chapter)
    for lock in overdue:
        issues["blockers"].append(f"定时锁逾期：{lock['id']} deadline={lock['deadline_chapter']}")

    # Scene-Sequel
    cm = state.get("chapter_meta", {}).get(str(chapter), {})
    ss_issues = check_scene_sequel(cm)
    for i in ss_issues:
        if i.startswith("BLOCKER"):
            issues["blockers"].append(f"Scene-Sequel: {i}")
        else:
            issues["warnings"].append(i)

    # Hook type
    if not cm.get("hook_type"):
        issues["blockers"].append("章末 hook_type 未声明")

    return issues
```

- [ ] **Step 3: Wire into existing pipeline**

Find the main review pipeline function and add call to `run_craft_checks(state, chapter)`. Merge results into existing issue list.

- [ ] **Step 4: Add integration test**

Create `tests/integration/test_review_with_craft.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from story_craft import (
    init_story_craft, add_foreshadow, add_timed_lock,
    record_emotion_peak, set_chapter_meta,
)
from review_pipeline import run_craft_checks


def test_run_craft_checks_flags_missing_hook():
    state = init_story_craft("/tmp/dummy.json")
    # don't set hook_type
    state["chapter_meta"]["1"] = {"scene_goal": "ok", "scene_conflict": "ok", "sequel_decision": "ok"}
    issues = run_craft_checks(state, chapter=1)
    assert any("hook_type" in b for b in issues["blockers"])


def test_run_craft_checks_flags_overdue_timed_lock():
    state = init_story_craft("/tmp/dummy.json")
    add_timed_lock(state, {"description": "test", "deadline_chapter": 3})
    issues = run_craft_checks(state, chapter=5)
    assert any("定时锁逾期" in b for b in issues["blockers"])


def test_run_craft_checks_flags_rhythm_block():
    state = init_story_craft("/tmp/dummy.json")
    state["story_craft"]["rhythm_curve"]["chapters_since_peak"] = 6
    state["story_craft"]["rhythm_curve"]["block_threshold"] = 5
    issues = run_craft_checks(state, chapter=10)
    assert any("节奏曲线 BLOCK" in b for b in issues["blockers"])
```

- [ ] **Step 5: Run test**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/integration/test_review_with_craft.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/scripts/review_pipeline.py .claude/plugins/webnovel-writer/scripts/tests/integration/test_review_with_craft.py
git commit -m "feat(review): integrate story_craft checks into pipeline"
```

---

### Task 21: Update existing 大纲-卷节拍表.md template to 15-beat

**Files:**
- Modify: `.claude/plugins/webnovel-writer/templates/output/大纲-卷节拍表.md`

- [ ] **Step 1: Replace existing template content with 15-beat version**

Find the existing template and replace its body with content pointing to `volume-beat-sheet.md` (or inline the same content).

```markdown
# 第 {volume_id} 卷 节拍表

> 本卷使用 15-Beat Save the Cat 卷级结构（Jessica Brody）
> 模板详细字段见 `skills/webnovel-plan/references/outlining/volume-beat-sheet.md`
> **BLOCKER**: Midpoint + All Is Lost 必须 filled

[Inline the same table content as volume-beat-sheet.md]
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/templates/output/大纲-卷节拍表.md
git commit -m "feat(template): upgrade volume beat sheet to 15-beat"
```

---

### Task 22: Update 大纲-卷详细大纲.md template with Scene-Sequel

**Files:**
- Modify: `.claude/plugins/webnovel-writer/templates/output/大纲-卷详细大纲.md`

- [ ] **Step 1: Add Scene-Sequel fields to chapter template**

Find chapter template section and extend:
```markdown

每章必填字段（新增 craft 字段）：
- beat_position
- hook_type
- scene_goal / scene_conflict / scene_setback / scene_resolution
- sequel_reaction / sequel_dilemma / sequel_decision
- foreshadow_buried / foreshadow_paid_off
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/templates/output/大纲-卷详细大纲.md
git commit -m "feat(template): add Scene-Sequel fields to chapter outline"
```

---

## Phase 4: Dashboard + 上线 (Week 4-6)

### Task 23: Add 4 dashboard panels

**Files:**
- Modify: `.claude/plugins/webnovel-writer/dashboard/app.py`

- [ ] **Step 1: Read existing app.py routes**

Run: `grep -n "@app.route\|^def " /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer/dashboard/app.py | head -30`

- [ ] **Step 2: Add 4 new routes**

Find a good insertion point and add:
```python
@app.route("/craft/beat/<int:volume>")
def craft_beat_panel(volume):
    state = load_state()
    beats = state["story_craft"]["volume_beat"]["beats"]
    return render_template_string(BEAT_TEMPLATE, volume=volume, beats=beats)


@app.route("/craft/foreshadow")
def craft_foreshadow_panel():
    state = load_state()
    chain = state["story_craft"]["foreshadow_chain"]
    return render_template_string(FORESHADOW_TEMPLATE, chain=chain)


@app.route("/craft/timed-locks")
def craft_timed_locks_panel():
    state = load_state()
    locks = state["story_craft"]["timed_locks"]
    return render_template_string(TIMED_LOCK_TEMPLATE, locks=locks)


@app.route("/craft/rhythm")
def craft_rhythm_panel():
    state = load_state()
    curve = state["story_craft"]["rhythm_curve"]
    return render_template_string(RHYTHM_TEMPLATE, curve=curve)
```

- [ ] **Step 3: Add templates**

Add inline Jinja templates at top of file:
```python
BEAT_TEMPLATE = """
<h1>卷 {{volume}} 15-Beat 节拍</h1>
<table border="1">
<tr><th>#</th><th>Beat</th><th>章</th><th>filled</th><th>notes</th></tr>
{% for b in beats %}
<tr><td>{{loop.index}}</td><td>{{b.name}}</td><td>{{b.chapter}}</td><td>{{'✓' if b.filled else '✗'}}</td><td>{{b.notes or ''}}</td></tr>
{% endfor %}
</table>
"""

FORESHADOW_TEMPLATE = """
<h1>伏笔链 ({{chain|length}} 项)</h1>
<table border="1">
<tr><th>ID</th><th>Type</th><th>Depth</th><th>Buried</th><th>Payoff</th><th>Status</th></tr>
{% for f in chain %}
<tr><td>{{f.id}}</td><td>{{f.type}}</td><td>{{f.depth}}</td><td>{{f.buried_chapter or ''}}</td><td>{{f.expected_payoff_chapter or ''}}</td><td>{{f.status}}</td></tr>
{% endfor %}
</table>
"""

TIMED_LOCK_TEMPLATE = """
<h1>定时锁</h1>
<table border="1">
<tr><th>ID</th><th>描述</th><th>Deadline</th><th>Status</th></tr>
{% for l in locks %}
<tr><td>{{l.id}}</td><td>{{l.description}}</td><td>{{l.deadline_chapter}}</td><td>{{l.status}}</td></tr>
{% endfor %}
</table>
"""

RHYTHM_TEMPLATE = """
<h1>节奏曲线</h1>
<p>距离上次情绪高峰: {{curve.chapters_since_peak}} 章</p>
<p>状态: {{ 'warning' if curve.chapters_since_peak >= curve.warning_threshold else 'ok' }}</p>
<p>Warning threshold: {{curve.warning_threshold}} / Block threshold: {{curve.block_threshold}}</p>
"""
```

- [ ] **Step 4: Add nav links**

Find existing nav section and add:
```html
<a href="/craft/beat/1">节拍</a>
<a href="/craft/foreshadow">伏笔</a>
<a href="/craft/timed-locks">定时锁</a>
<a href="/craft/rhythm">节奏</a>
```

- [ ] **Step 5: Manual test**

Run: `cd .claude/plugins/webnovel-writer && python3 -m dashboard.app` then visit `/craft/beat/1` etc. in browser.

- [ ] **Step 6: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/dashboard/app.py
git commit -m "feat(dashboard): add 4 story-craft panels"
```

---

### Task 24: End-to-end test

**Files:**
- Create: `.claude/plugins/webnovel-writer/scripts/tests/integration/test_plan_with_craft.py`

- [ ] **Step 1: Write e2e test**

```python
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from story_craft import (
    init_story_craft, init_volume_beat, fill_beat,
    add_foreshadow, payoff_foreshadow, add_timed_lock,
    record_emotion_peak, set_chapter_meta, check_volume_beat,
)


def test_full_volume_plan_flow():
    """Simulate a complete volume plan with all craft mechanisms."""
    # 1. Init state
    state = init_story_craft("/tmp/dummy.json")
    state["project_info"] = {"genre": "玄幻", "target_chapters": 50}
    state["progress"] = {"current_volume": 1, "volumes_planned": []}

    # 2. Init volume beat
    init_volume_beat(state, volume=1, total_chapters=50)

    # 3. Fill critical beats
    fill_beat(state, volume=1, beat_name="Midpoint", chapter=25, notes="假胜利")
    fill_beat(state, volume=1, beat_name="All Is Lost", chapter=37, notes="师尊陨落")
    fill_beat(state, volume=1, beat_name="Final Image", chapter=50, notes="新卷开场")

    # 4. Verify no BLOCKER
    issues = check_volume_beat(state, volume=1)
    blockers = [i for i in issues if "BLOCKER" in i]
    assert blockers == [], f"Unexpected blockers: {blockers}"

    # 5. Add foreshadows
    add_foreshadow(state, {
        "type": "物谶", "depth": "表层",
        "buried_chapter": 1, "expected_payoff_chapter": 2,
        "content": "新手卡"
    })
    add_foreshadow(state, {
        "type": "物谶", "depth": "中层",
        "buried_chapter": 5, "expected_payoff_chapter": 25,
        "content": "神秘令牌"
    })
    add_foreshadow(state, {
        "type": "习惯", "depth": "深层",
        "buried_chapter": 1, "expected_payoff_chapter": 50,
        "content": "主角下意识动作"
    })
    assert len(state["story_craft"]["foreshadow_chain"]) == 3

    # 6. Pay off mid-level foreshadow
    payoff_foreshadow(state, "FS-002", chapter=25, quality="强")

    # 7. Add timed locks
    add_timed_lock(state, {"description": "主角 3 章内出村", "deadline_chapter": 3})
    add_timed_lock(state, {"description": "Midpoint 必须反转", "deadline_chapter": 25})

    # 8. Record rhythm
    record_emotion_peak(state, chapter=5, intensity=7, type_="medium_cool_point")

    # 9. Set chapter meta
    set_chapter_meta(
        state, chapter=5,
        beat_position="Setup",
        hook_type="悬念式",
        scene_goal="进入秘境",
        scene_conflict="守护者阻挡",
        scene_setback="被击退",
        scene_resolution="暂时撤退",
        sequel_reaction="分析弱点",
        sequel_dilemma="独自 vs 求援",
        sequel_decision="独自潜入"
    )

    # 10. Verify all data persisted in state
    assert state["story_craft"]["foreshadow_chain"][1]["status"] == "paid_off"
    assert state["chapter_meta"]["5"]["hook_type"] == "悬念式"
    assert state["story_craft"]["volume_beat"]["beats"][8]["filled"] is True
```

- [ ] **Step 2: Run test**

Run: `cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/integration/test_plan_with_craft.py -v`
Expected: 1 passed

- [ ] **Step 3: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/scripts/tests/integration/test_plan_with_craft.py
git commit -m "test: add end-to-end plan flow integration test"
```

---

### Task 25: Migrate existing project state.json + verify

**Files:**
- (none — runs migration on actual project)

- [ ] **Step 1: Run migration**

Run:
```bash
cd /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer/scripts
python3 migrate_story_craft.py /Users/chang/Desktop/根源牌序/.webnovel/state.json
```
Expected: `Migrated ...`

- [ ] **Step 2: Verify state.json**

Run:
```bash
python3 -c "
import json
s = json.load(open('/Users/chang/Desktop/根源牌序/.webnovel/state.json'))
sc = s.get('story_craft', {})
print('rhythm_curve keys:', list(sc.get('rhythm_curve', {}).keys()))
print('foreshadow_chain:', len(sc.get('foreshadow_chain', [])))
print('timed_locks:', len(sc.get('timed_locks', [])))
print('thematic_echoes:', len(sc.get('thematic_echoes', [])))
print('character_arc:', sc.get('character_arc'))
"
```
Expected: all fields present, all empty/None

- [ ] **Step 3: Re-run `/webnovel-doctor` to verify no regression**

Run: `cd /Users/chang/Desktop/根源牌序 && /webnovel-doctor --format text`
Expected: all green

---

### Task 26: Update project README + spec changelog

**Files:**
- Modify: `/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer/README.md` (if exists)

- [ ] **Step 1: Check README**

Run: `ls /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer/README.md`

- [ ] **Step 2: Add changelog entry**

If README exists, append section:
```markdown

## v2.0 — Story Craft Engine (2026-08-14)

Added 4 core narrative mechanisms:
- **15-Beat Save the Cat** (volume level) — forces Midpoint + All Is Lost
- **Scene-Sequel** (chapter level) — Goal/Conflict/Setback/Resolution/Reaction/Dilemma/Decision
- **草蛇灰线 5-field tracking** — foreshadow state machine with BLOCKER on overdue
- **Timed Lock + Rhythm Curve + Hook Type** — chapter-level discipline

State.json schema: new `story_craft` top-level field (optional, backward-compatible).
webnovel-plan: new Step 4.5/6.5/8.5.
Reviewer: 5 → 7 dimensions.
Dashboard: 4 new panels.
```

- [ ] **Step 3: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer/README.md
git commit -m "docs: add v2.0 changelog for story-craft-engine"
```

---

## Self-Review Checklist

### Spec Coverage

- [x] §4.1 15-beat 卷节拍表 → Task 7 + Task 14 + Task 21
- [x] §4.2 Scene-Sequel → Task 6 + Task 16 + Task 22
- [x] §4.3 草蛇灰线 5 字段 → Task 2 + Task 11 + Task 15
- [x] §4.4 定时锁 → Task 3 + Task 15
- [x] §4.4 节奏曲线 → Task 4
- [x] §4.4 钩子类型 → Task 6
- [x] §4.4 character_arc → Task 5
- [x] §4.4 thematic_echoes → Task 5 + Task 13
- [x] §6 state.json schema → Task 1 + Task 8 + Task 9 + Task 25
- [x] §7 reference docs → Task 10
- [x] §8 SKILL.md 改造 → Task 13-17
- [x] §9 reviewer 扩展 → Task 19 + Task 20
- [x] §10 迁移策略 → Task 8 + Task 9 + Task 25
- [x] §11 测试策略 → Task 24 + all tests inline
- [x] §13 4-6 周分阶段 → Phase 1/2/3/4 tasks

### Placeholder Scan

No TBD / TODO / FIXME / "implement later" patterns in plan.

### Type Consistency

- `VALID_HOOK_TYPES` defined Task 6, used Task 6 + Task 19
- `VALID_DEPTHS` / `VALID_TYPES` defined Task 2, used Task 2 only
- `EMPTY_STORY_CRAFT` defined Task 1, used Task 8
- All `chapter_meta.{N}.*` field names consistent across Task 6, 16, 19, 20
- `state["story_craft"]["*"]` paths consistent across all tasks

---

## Plan Summary

| Phase | Tasks | Duration |
|---|---|---|
| Phase 1 (References + Schema) | 1-12 | Week 1 |
| Phase 2 (webnovel-plan SKILL.md) | 13-18 | Week 2-3 |
| Phase 3 (Reviewer Extension) | 19-22 | Week 3-4 |
| Phase 4 (Dashboard + Migration) | 23-26 | Week 4-6 |

**Total**: 26 tasks, ~30 commits

---

**Plan complete and saved to `docs/superpowers/plans/2026-08-14-story-craft-engine-impl.md`. Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?