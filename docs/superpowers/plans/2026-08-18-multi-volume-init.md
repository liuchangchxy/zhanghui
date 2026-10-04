# Multi-Volume Init Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable authors to build a full-volume skeleton in `webnovel-init` (with optional AI drafting in candidate state) and let `webnovel-plan` use that skeleton for V+1 anchor writeback.

**Architecture:** Add a `VolumeStateManager` module that owns the per-volume status state machine (confirmed/draft/deferred). Wire it into `init_project.py` so the existing `_build_master_outline` path becomes the default. Add an opt-in `AI Volume Drafter` that produces candidate volumes (not persisted). Modify `webnovel-plan` Step 9 to read the new state and write back V+1 anchors only.

**Tech Stack:** Python 3 (data modules), pytest (tests), markdown (templates + SKILL.md files).

**Spec:** `docs/superpowers/specs/2026-08-18-multi-volume-init-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/data_modules/volume_state.py` (NEW) | VolumeStateManager + dataclasses + state machine + JSON I/O |
| `scripts/data_modules/ai_volume_drafter.py` (NEW) | Pure-function AI drafter (takes LLM-callable, returns CandidateVolume) |
| `scripts/init_project.py` (MODIFY) | Add `volume_skeleton` param + default to `_build_master_outline` |
| `templates/output/大纲-总纲.md` (MODIFY) | Make 卷划分 table render-friendly for N rows |
| `skills/webnovel-init/SKILL.md` (MODIFY) | Add Step 1.6 (collector loop) + Step 5.5 (AI drafter) |
| `skills/webnovel-init/references/multi-volume-ux.md` (NEW) | Design rationale reference for the agent |
| `skills/webnovel-plan/SKILL.md` (MODIFY) | Step 9 anchor writeback reads new state |
| `scripts/tests/unit/test_volume_state.py` (NEW) | State machine + invariants tests |
| `scripts/tests/unit/test_ai_volume_drafter.py` (NEW) | Drafter pure-function tests (mock LLM) |
| `scripts/tests/integration/test_init_multi_volume.py` (NEW) | End-to-end init flow |
| `scripts/tests/integration/test_plan_v_plus_one_anchor.py` (NEW) | V+1 anchor semantics per spec §5.4 |

---

## Task 1: VolumeRecord + CandidateVolume dataclasses

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/scripts/data_modules/volume_state.py`

- [ ] **Step 1: Create the dataclass module with stub**

```python
"""Volume state management for multi-volume init.

Owns per-volume status state machine (confirmed / draft / deferred)
plus planning_horizon metadata. See
docs/superpowers/specs/2026-08-18-multi-volume-init-design.md
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class VolumeStatus(str, Enum):
    CONFIRMED = "confirmed"
    DRAFT = "draft"
    DEFERRED = "deferred"


class VolumeSource(str, Enum):
    HUMAN = "human"
    AI = "ai"


@dataclass
class VolumeRecord:
    index: int
    title: str = ""
    chapter_range: list[int] = field(default_factory=lambda: [0, 0])
    core_conflict: str = ""
    climax: str = ""
    key_cool_points: list[str] = field(default_factory=list)
    characters_to_appear: list[str] = field(default_factory=list)
    foreshadowing: list[str] = field(default_factory=list)
    status: VolumeStatus = VolumeStatus.DRAFT
    source: VolumeSource = VolumeSource.HUMAN
    updated_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["source"] = self.source.value
        return d


@dataclass
class CandidateVolume:
    """In-memory draft from AI drafter. Never persisted."""
    index: int
    title: str = ""
    chapter_range: list[int] = field(default_factory=lambda: [0, 0])
    core_conflict: str = ""
    climax: str = ""
    key_cool_points: list[str] = field(default_factory=list)
    characters_to_appear: list[str] = field(default_factory=list)
    foreshadowing: list[str] = field(default_factory=list)
    source: VolumeSource = VolumeSource.AI


@dataclass
class PlanningHorizon:
    expected_total_volumes: Optional[int] = None
    confirmed_through_volume: int = 0
    later_volumes_status: str = "deferred"  # deferred | unknown | planned
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer_chang/scripts/data_modules/volume_state.py
git commit -m "feat(volume_state): add dataclasses (VolumeRecord, CandidateVolume, PlanningHorizon)"
```

---

## Task 2: VolumeStateManager state machine — write failing test

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/scripts/tests/unit/test_volume_state.py`

- [ ] **Step 1: Create test file**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import pytest

from data_modules.volume_state import (
    VolumeStateManager,
    VolumeRecord,
    VolumeStatus,
    VolumeSource,
    CandidateVolume,
)


@pytest.fixture
def fresh_state():
    return {"project_info": {}, "volumes": []}


def test_append_human_volume_persists(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    rec = VolumeRecord(
        index=1,
        title="起势",
        chapter_range=[1, 80],
        core_conflict="宗门考核",
        climax="夺得首席",
        status=VolumeStatus.CONFIRMED,
        source=VolumeSource.HUMAN,
    )
    mgr.append_or_update(rec)
    assert fresh_state["volumes"][0]["title"] == "起势"
    assert fresh_state["volumes"][0]["status"] == "confirmed"
    assert fresh_state["project_info"]["confirmed_through_volume"] == 1


def test_append_draft_does_not_persist(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    cand = CandidateVolume(
        index=2,
        title="AI 起草",
        core_conflict="伏魔",
        climax="封印松动",
    )
    mgr.append_draft(cand)
    # Drafts live in memory only
    assert fresh_state["volumes"] == []
    assert mgr.has_pending_draft(2)


def test_confirm_volume_promotes_draft(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    cand = CandidateVolume(index=1, title="X", core_conflict="A", climax="B")
    mgr.append_draft(cand)
    mgr.confirm_volume(1)
    assert fresh_state["volumes"][0]["status"] == "confirmed"
    assert fresh_state["volumes"][0]["source"] == "ai"


def test_ai_cannot_overwrite_confirmed(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    rec = VolumeRecord(
        index=1, title="V1", core_conflict="X", climax="Y",
        status=VolumeStatus.CONFIRMED, source=VolumeSource.HUMAN,
    )
    mgr.append_or_update(rec)
    # New AI draft for same index
    cand = CandidateVolume(index=1, title="AI 试图覆盖", core_conflict="Z", climax="W")
    mgr.append_draft(cand)
    mgr.confirm_volume(1)  # should refuse, not overwrite
    assert fresh_state["volumes"][0]["title"] == "V1"
    assert fresh_state["volumes"][0]["core_conflict"] == "X"


def test_set_deferred(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    rec = VolumeRecord(
        index=1, title="V1", core_conflict="X", climax="Y",
        status=VolumeStatus.CONFIRMED, source=VolumeSource.HUMAN,
    )
    mgr.append_or_update(rec)
    mgr.set_deferred(1)
    assert fresh_state["volumes"][0]["status"] == "deferred"


def test_index_continuity_invariant(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    # Try to add index=3 with no index=1,2 — must reject
    rec = VolumeRecord(
        index=3, title="V3", status=VolumeStatus.CONFIRMED, source=VolumeSource.HUMAN,
    )
    with pytest.raises(ValueError, match="index continuity"):
        mgr.append_or_update(rec)


def test_later_volumes_status_deferred_by_default(fresh_state):
    mgr = VolumeStateManager(fresh_state)
    rec = VolumeRecord(
        index=1, title="V1", core_conflict="X", climax="Y",
        status=VolumeStatus.CONFIRMED, source=VolumeSource.HUMAN,
    )
    mgr.append_or_update(rec)
    horizon = mgr.get_planning_horizon()
    assert horizon.later_volumes_status == "deferred"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .claude/plugins/webnovel-writer_chang && python3 -m pytest scripts/tests/unit/test_volume_state.py -v`
Expected: ImportError or AttributeError for `VolumeStateManager`

- [ ] **Step 3: Commit the failing test**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer_chang/scripts/tests/unit/test_volume_state.py
git commit -m "test(volume_state): add state machine tests (red)"
```

---

## Task 3: Implement VolumeStateManager

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/scripts/data_modules/volume_state.py:54-end`

- [ ] **Step 1: Append the manager class to volume_state.py**

```python
class VolumeStateManager:
    """Owns volumes[] + planning_horizon in state.json.

    Invariants:
      - volumes[i].index` is contiguous (no holes)
      - confirmed fields are not overwritten by AI drafts
      - drafts never persist
    """

    _ALLOWED_TRANSITIONS = {
        VolumeStatus.DRAFT: {VolumeStatus.CONFIRMED, VolumeStatus.DEFERRED},
        VolumeStatus.CONFIRMED: {VolumeStatus.DEFERRED},
        VolumeStatus.DEFERRED: {VolumeStatus.CONFIRMED},
    }

    def __init__(self, state: dict):
        self.state = state
        self.state.setdefault("volumes", [])
        self.state.setdefault("project_info", {})
        self._drafts: dict[int, CandidateVolume] = {}

    # ----- read -----

    def list_volumes(self) -> list[VolumeRecord]:
        return [self._from_dict(d) for d in self.state["volumes"]]

    def get_volume(self, index: int) -> VolumeRecord | None:
        for d in self.state["volumes"]:
            if d["index"] == index:
                return self._from_dict(d)
        return None

    def get_planning_horizon(self) -> PlanningHorizon:
        pi = self.state["project_info"]
        return PlanningHorizon(
            expected_total_volumes=pi.get("expected_total_volumes"),
            confirmed_through_volume=pi.get("confirmed_through_volume", 0),
            later_volumes_status=pi.get("later_volumes_status", "deferred"),
        )

    def has_pending_draft(self, index: int) -> bool:
        return index in self._drafts

    # ----- write: human input -----

    def append_or_update(self, rec: VolumeRecord) -> None:
        self._check_continuity(rec.index)
        existing = self._find_dict_index(rec.index)
        d = rec.to_dict()
        d["updated_at"] = _now_iso()
        if existing is not None:
            self.state["volumes"][existing] = d
        else:
            self.state["volumes"].append(d)
        self._sort_by_index()
        self._update_horizon()

    # ----- write: AI draft -----

    def append_draft(self, candidate: CandidateVolume) -> None:
        self._drafts[candidate.index] = candidate

    def confirm_volume(self, index: int) -> None:
        """Promote in-memory draft (or existing deferred record) to confirmed."""
        if index in self._drafts:
            cand = self._drafts.pop(index)
            existing = self._find_dict_index(index)
            if existing is not None:
                existing_rec = self._from_dict(self.state["volumes"][existing])
                if existing_rec.status == VolumeStatus.CONFIRMED:
                    # AI must NOT overwrite confirmed
                    return
            rec = VolumeRecord(
                index=cand.index,
                title=cand.title,
                chapter_range=cand.chapter_range,
                core_conflict=cand.core_conflict,
                climax=cand.climax,
                key_cool_points=cand.key_cool_points,
                characters_to_appear=cand.characters_to_appear,
                foreshadowing=cand.foreshadowing,
                status=VolumeStatus.CONFIRMED,
                source=VolumeSource.AI,
            )
            self.append_or_update(rec)
        else:
            existing = self._find_dict_index(index)
            if existing is None:
                raise ValueError(f"No record for volume {index}")
            self.state["volumes"][existing]["status"] = "confirmed"
            self.state["volumes"][existing]["updated_at"] = _now_iso()
            self._update_horizon()

    def set_deferred(self, index: int) -> None:
        existing = self._find_dict_index(index)
        if existing is None:
            raise ValueError(f"No record for volume {index}")
        cur = self.state["volumes"][existing]["status"]
        if cur == "confirmed":  # confirmed → deferred allowed
            self.state["volumes"][existing]["status"] = "deferred"
            self.state["volumes"][existing]["updated_at"] = _now_iso()
            self._update_horizon()

    # ----- internal -----

    def _find_dict_index(self, index: int) -> int | None:
        for i, d in enumerate(self.state["volumes"]):
            if d["index"] == index:
                return i
        return None

    def _check_continuity(self, new_index: int) -> None:
        existing_indexes = sorted(d["index"] for d in self.state["volumes"])
        if not existing_indexes:
            if new_index != 1:
                raise ValueError(
                    f"index continuity violated: first volume must be 1, got {new_index}"
                )
            return
        expected_max = existing_indexes[-1] + 1
        if new_index > expected_max:
            raise ValueError(
                f"index continuity violated: expected next index {expected_max}, got {new_index}"
            )

    def _sort_by_index(self) -> None:
        self.state["volumes"].sort(key=lambda d: d["index"])

    def _update_horizon(self) -> None:
        confirmed = [d["index"] for d in self.state["volumes"] if d["status"] == "confirmed"]
        self.state["project_info"]["confirmed_through_volume"] = max(confirmed) if confirmed else 0
        # If user explicitly set deferred earlier, keep it; else default
        if "later_volumes_status" not in self.state["project_info"]:
            self.state["project_info"]["later_volumes_status"] = "deferred"

    def _from_dict(self, d: dict) -> VolumeRecord:
        return VolumeRecord(
            index=d["index"],
            title=d.get("title", ""),
            chapter_range=d.get("chapter_range", [0, 0]),
            core_conflict=d.get("core_conflict", ""),
            climax=d.get("climax", ""),
            key_cool_points=d.get("key_cool_points", []),
            characters_to_appear=d.get("characters_to_appear", []),
            foreshadowing=d.get("foreshadowing", []),
            status=VolumeStatus(d.get("status", "draft")),
            source=VolumeSource(d.get("source", "human")),
            updated_at=d.get("updated_at", ""),
        )


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd .claude/plugins/webnovel-writer_chang && python3 -m pytest scripts/tests/unit/test_volume_state.py -v`
Expected: 7 PASSED

- [ ] **Step 3: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer_chang/scripts/data_modules/volume_state.py
git commit -m "feat(volume_state): implement VolumeStateManager (state machine + invariants)"
```

---

## Task 4: AI Volume Drafter — write failing test

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/scripts/data_modules/ai_volume_drafter.py`
- Create: `.claude/plugins/webnovel-writer_chang/scripts/tests/unit/test_ai_volume_drafter.py`

- [ ] **Step 1: Create the drafter stub**

```python
"""AI Volume Drafter — pure function that produces CandidateVolume.

Takes an LLM-callable so tests can mock it. Never persists output.
See docs/superpowers/specs/2026-08-18-multi-volume-init-design.md §5.2.
"""
from __future__ import annotations

from typing import Callable

from data_modules.volume_state import (
    CandidateVolume, VolumeSource, VolumeRecord, VolumeStatus,
)


def draft_next_volume(
    *,
    one_line_concept: str,
    confirmed_volumes: list[VolumeRecord],
    genre: str,
    target_index: int,
    llm_call: Callable[[str], str],
) -> CandidateVolume:
    """Call llm_call with a prompt, parse the response into CandidateVolume.

    Raises ValueError on parse failure. Returns status=draft, source=ai.
    """
    prompt = _build_prompt(one_line_concept, confirmed_volumes, genre, target_index)
    raw = llm_call(prompt)
    return _parse(raw, target_index)


def _build_prompt(
    concept: str, prior: list[VolumeRecord], genre: str, target_index: int,
) -> str:
    prior_text = "\n".join(
        f"- V{v.index} {v.title}: 冲突={v.core_conflict}, 高潮={v.climax}"
        for v in prior
    ) or "(无)"
    return (
        f"题材：{genre}\n"
        f"全书一句话：{concept}\n"
        f"已确认前卷（必须承接且不重复伏笔）：\n{prior_text}\n\n"
        f"请起草第 {target_index} 卷的骨架：\n"
        f"卷名：\n"
        f"核心冲突：\n"
        f"卷末高潮：\n"
        f"严格遵循格式：\n"
        f"卷名：<20字以内>\n"
        f"核心冲突：<一句话>\n"
        f"卷末高潮：<一句话>\n"
    )


def _parse(raw: str, target_index: int) -> CandidateVolume:
    title = _extract(raw, "卷名")
    conflict = _extract(raw, "核心冲突")
    climax = _extract(raw, "卷末高潮")
    if not (title and conflict and climax):
        raise ValueError(f"LLM output missing required fields: {raw[:200]}")
    return CandidateVolume(
        index=target_index,
        title=title,
        core_conflict=conflict,
        climax=climax,
        source=VolumeSource.AI,
    )


def _extract(text: str, key: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith(key + "："):
            return line.split("：", 1)[1].strip()
    return ""
```

- [ ] **Step 2: Create the failing test**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from data_modules.ai_volume_drafter import draft_next_volume
from data_modules.volume_state import VolumeRecord, VolumeStatus, VolumeSource


def test_draft_returns_candidate_from_llm():
    fake_response = "卷名：起势\n核心冲突：宗门考核\n卷末高潮：夺得首席\n"
    cand = draft_next_volume(
        one_line_concept="少年修仙",
        confirmed_volumes=[],
        genre="修仙",
        target_index=1,
        llm_call=lambda prompt: fake_response,
    )
    assert cand.title == "起势"
    assert cand.core_conflict == "宗门考核"
    assert cand.climax == "夺得首席"
    assert cand.source == VolumeSource.AI


def test_draft_prompt_mentions_prior_volumes():
    captured = {}
    def fake_llm(prompt):
        captured["prompt"] = prompt
        return "卷名：V2\n核心冲突：X\n卷末高潮：Y\n"

    prior = [VolumeRecord(
        index=1, title="V1", core_conflict="A", climax="B",
        status=VolumeStatus.CONFIRMED, source=VolumeSource.HUMAN,
    )]
    draft_next_volume(
        one_line_concept="c", confirmed_volumes=prior,
        genre="玄幻", target_index=2, llm_call=fake_llm,
    )
    assert "V1" in captured["prompt"]
    assert "已确认前卷" in captured["prompt"]


def test_draft_raises_on_missing_fields():
    def fake_llm(prompt):
        return "卷名：只有名字"  # 缺核心冲突和卷末高潮

    import pytest
    with pytest.raises(ValueError, match="missing required fields"):
        draft_next_volume(
            one_line_concept="c", confirmed_volumes=[],
            genre="玄幻", target_index=1, llm_call=fake_llm,
        )
```

- [ ] **Step 3: Run test to verify it passes (stub already implements logic)**

Run: `cd .claude/plugins/webnovel-writer_chang && python3 -m pytest scripts/tests/unit/test_ai_volume_drafter.py -v`
Expected: 3 PASSED

- [ ] **Step 4: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer_chang/scripts/data_modules/ai_volume_drafter.py \
        .claude/plugins/webnovel-writer_chang/scripts/tests/unit/test_ai_volume_drafter.py
git commit -m "feat(ai_drafter): add draft_next_volume + tests (LLM-callable injected)"
```

---

## Task 5: Wire VolumeStateManager into init_project.py — write failing test

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/scripts/tests/integration/test_init_multi_volume.py`

- [ ] **Step 1: Create the failing integration test**

```python
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from init_project import init_project


def test_init_writes_multi_volume_outline_when_volumes_provided():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        init_project(
            project_dir=str(project_path),
            title="Test",
            genre="玄幻",
            target_chapters=300,
            target_words=900000,
            # Pass 3 confirmed volumes
            volume_skeleton=[
                {"index": 1, "title": "起势", "chapter_range": [1, 80],
                 "core_conflict": "宗门考核", "climax": "夺得首席",
                 "status": "confirmed", "source": "human"},
                {"index": 2, "title": "深入", "chapter_range": [81, 180],
                 "core_conflict": "敌派入侵", "climax": "师尊受伤",
                 "status": "confirmed", "source": "human"},
                {"index": 3, "title": "反转", "chapter_range": [181, 300],
                 "core_conflict": "身份揭露", "climax": "退宗",
                 "status": "confirmed", "source": "human"},
            ],
        )
        # state.json should contain all 3 volumes
        state = json.loads((project_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
        assert len(state["volumes"]) == 3
        assert state["volumes"][0]["title"] == "起势"
        assert state["project_info"]["confirmed_through_volume"] == 3

        # 总纲 should have 3 rows in 卷划分 table
        outline = (project_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
        assert "### 第1卷" in outline
        assert "### 第2卷" in outline
        assert "### 第3卷" in outline


def test_init_no_volumes_writes_empty_outline():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        init_project(
            project_dir=str(project_path),
            title="Test",
            genre="玄幻",
            target_chapters=300,
            target_words=900000,
            volume_skeleton=None,
        )
        state = json.loads((project_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
        assert state["volumes"] == []
        assert state["project_info"]["confirmed_through_volume"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/plugins/webnovel-writer_chang && python3 -m pytest scripts/tests/integration/test_init_multi_volume.py -v`
Expected: TypeError (unexpected kwarg `volume_skeleton`) or similar

- [ ] **Step 3: Commit the failing test**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer_chang/scripts/tests/integration/test_init_multi_volume.py
git commit -m "test(init): add multi-volume init integration test (red)"
```

---

## Task 6: Implement volume_skeleton param in init_project.py

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/scripts/init_project.py:317` (add param)
- Modify: `.claude/plugins/webnovel-writer_chang/scripts/init_project.py:680` (use new path)

- [ ] **Step 1: Add `volume_skeleton` parameter to `init_project()`**

Read the current `def init_project(...)` signature around line 317. Add this new parameter before `reference_research_dir`:

```python
    volume_skeleton: Optional[List[Dict[str, Any]]] = None,
```

(Add `from typing import Optional, List, Dict, Any` near the top of the file if not already present.)

- [ ] **Step 2: Replace the outline-routing block (around line 678-683)**

Find this:
```python
    outline_content = output_outline.strip() if output_outline else ""
    if outline_content:
        outline_content = _inject_volume_rows(outline_content, int(target_chapters)).rstrip() + "\n"
    else:
        outline_content = _build_master_outline(int(target_chapters))
    _write_text_if_missing(project_path / "大纲" / "总纲.md", outline_content)
```

Replace with:
```python
    outline_content = output_outline.strip() if output_outline else ""

    # Multi-volume: if user supplied a volume_skeleton, render all volumes
    if volume_skeleton:
        outline_content = _render_volume_skeleton_outline(
            volume_skeleton, int(target_chapters)
        )
    elif outline_content:
        outline_content = _inject_volume_rows(outline_content, int(target_chapters)).rstrip() + "\n"
    else:
        outline_content = _build_master_outline(int(target_chapters))
    _write_text_if_missing(project_path / "大纲" / "总纲.md", outline_content)
```

- [ ] **Step 3: Add the helper function `_render_volume_skeleton_outline` (after `_build_master_outline`, around line 211)**

```python
def _render_volume_skeleton_outline(
    skeleton: List[Dict[str, Any]], target_chapters: int,
) -> str:
    """Render a multi-volume 总纲 from a user-supplied skeleton list.

    Each skeleton entry has: index, title, chapter_range, core_conflict, climax, status.
    Missing fields render as empty placeholders.
    """
    lines: list[str] = [
        "# 总纲",
        "",
        "> 本文件由 init_project.py 通过 volume_skeleton 自动生成。",
        "",
        "## 卷划分",
        "",
        "| 卷号 | 卷名 | 章节范围 | 核心冲突 | 卷末高潮 | 状态 |",
        "|------|------|----------|----------|----------|------|",
    ]
    for v in skeleton:
        idx = v.get("index", "?")
        title = v.get("title", "")
        rng = v.get("chapter_range", [])
        rng_str = f"第{rng[0]}-{rng[1]}章" if len(rng) == 2 else ""
        conflict = v.get("core_conflict", "")
        climax = v.get("climax", "")
        status = v.get("status", "confirmed")
        lines.append(f"| {idx} | {title} | {rng_str} | {conflict} | {climax} | {status} |")
    lines.append("")
    lines.append(f"> 预计总章节数：{target_chapters}")
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Add volume state writing to `init_project()`**

Find the block around line 388 that updates `state["project_info"]`. Add this AFTER it:

```python
    # Volume skeleton — write volumes[] to state.json
    if volume_skeleton:
        from data_modules.volume_state import VolumeRecord, VolumeSource, VolumeStatus
        volumes: list[dict] = []
        for v in volume_skeleton:
            try:
                status = VolumeStatus(v.get("status", "confirmed"))
            except ValueError:
                status = VolumeStatus.CONFIRMED
            try:
                source = VolumeSource(v.get("source", "human"))
            except ValueError:
                source = VolumeSource.HUMAN
            rec = VolumeRecord(
                index=int(v["index"]),
                title=v.get("title", ""),
                chapter_range=v.get("chapter_range", [0, 0]),
                core_conflict=v.get("core_conflict", ""),
                climax=v.get("climax", ""),
                status=status,
                source=source,
            ).to_dict()
            rec["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            volumes.append(rec)
        state["volumes"] = volumes
        state["project_info"]["confirmed_through_volume"] = max(
            (v["index"] for v in volumes if v["status"] == "confirmed"), default=0
        )
        state["project_info"]["later_volumes_status"] = "deferred"
```

(Verify `datetime` is already imported; add `from datetime import datetime` at top if not.)

- [ ] **Step 5: Run the integration test to verify it passes**

Run: `cd .claude/plugins/webnovel-writer_chang && python3 -m pytest scripts/tests/integration/test_init_multi_volume.py -v`
Expected: 2 PASSED

- [ ] **Step 6: Run the existing init tests to verify no regression**

Run: `cd .claude/plugins/webnovel-writer_chang && python3 -m pytest scripts/tests/ -v -k "init or volume"`
Expected: all PASS (existing tests should not break since `volume_skeleton=None` keeps old behavior)

- [ ] **Step 7: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer_chang/scripts/init_project.py
git commit -m "feat(init): support volume_skeleton param + render multi-volume 总纲"
```

---

## Task 7: Add multi-volume-ux reference doc

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/skills/webnovel-init/references/multi-volume-ux.md`

- [ ] **Step 1: Write the reference doc**

```markdown
# Multi-Volume Init UX — Design Reference

Compact rationale for the agent implementing Step 1.6 of `webnovel-init`.

## Source projects

| Project | What we borrow |
|---|---|
| `references/04-ai-agent-systems/ainovel-cli/` | Rolling planning state model: subsequent volumes may not exist; `append_volume` and `expand_arc` are explicit actions |
| `references/04-ai-agent-systems/storyforge/` | Interactive UX: AI drafts enter candidate state, user accepts/modifies/rejects; per-volume edit |
| `references/04-ai-agent-systems/tianming-novel-ai-writer/` | Per-volume field schema (most complete) |

## Three patterns we explicitly reject

| Anti-pattern | Source | Why we reject |
|---|---|---|
| Pre-fill V3-V20 empty rows | (None of the 9 references does this) | Misleads user into thinking they must fill all volumes |
| Force user to commit to total volume count | 天命 `VolumeDesignViewModel.AIGenerate.cs:207-259` | Authors often don't know up front |
| AI silently overwrites user fields | (Anti-pattern from denova `system.go:191`) | Loses user intent; AI must surface candidate state |

## The flow we implement

```
For each V_k:
  1. Ask: title / range / conflict / climax / optional fields
  2. Then offer:
     A) Continue to V_{k+1}
     B) AI draft V_{k+1} (returns CandidateVolume, user must accept)
     C) Defer ("暂不确定后续卷") — exits loop, writes confirmed_through_volume=k
     D) Bulk-paste remaining volumes
```

## Status semantics

- `confirmed`: user-confirmed, persisted to state.json
- `draft`: AI-generated, lives in memory only, user must `confirm_volume()` to persist
- `deferred`: explicit "暂不确定", persists with empty fields

## Hard constraints

- `volumes[i].index` must be contiguous (no holes) — enforced by `VolumeStateManager._check_continuity`
- AI draft cannot auto-upgrade to `confirmed` — must go through user `confirm_volume()` call
- `confirmed` fields are not overwritten by AI (defense in depth)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer_chang/skills/webnovel-init/references/multi-volume-ux.md
git commit -m "docs(init): add multi-volume UX design reference"
```

---

## Task 8: Modify webnovel-init SKILL.md — add Step 1.6 and Step 5.5

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-init/SKILL.md`

- [ ] **Step 1: Add Step 1.6 section after Step 1**

Find the end of `### Step 1：故事核与商业定位` (around line 171). Add:

```markdown
### Step 1.6：多卷骨架采集（新增）

> **条件触发**：仅当用户预期 ≥ 2 卷时进入；若用户明确说"单卷完结"，跳过本步。

本步用 `references/multi-volume-ux.md` 作为设计依据（强制必读，优先级高于本文件）。

#### 1.6.1 询问总卷数

```
你预计全书大约几卷？

A. 已知具体数（如 8 卷） → 让我知道
B. 大概范围（如 5-10 卷） → 让我知道
C. 不确定，先填第一卷  → 跳过本项
D. 让 AI 建议
```

记录 `expected_total_volumes`（可空）。

#### 1.6.2 逐卷采集循环

每轮采集 `VolumeRecord`，必填字段：
- `title`（卷名）
- `chapter_range`（章节范围，格式 "1-80" 或 "约 60 章"）
- `core_conflict`（核心冲突，一句话）
- `climax`（卷末高潮/状态变化）

可选字段：`key_cool_points` / `characters_to_appear` / `foreshadowing`。

每卷结束时调用 `VolumeStateManager.append_or_update()`，**不要**自己写 state.json。

#### 1.6.3 每卷结束时的 4 选 1

```
A) 继续填写 V_{k+1}
B) 让 AI 起草 V_{k+1}（进入 Step 5.5）
C) 暂不确定后续卷，结束采集（设置 later_volumes_status=deferred）
D) 批量粘贴剩余卷（一次贴多行表格）
```

#### 1.6.4 批量粘贴模式

支持 markdown 表格直接粘贴：

```
| 卷号 | 卷名 | 章节范围 | 核心冲突 | 卷末高潮 |
| 1 | 起势 | 1-80 | 宗门考核 | 夺得首席 |
| 2 | 深入 | 81-180 | 敌派入侵 | 师尊受伤 |
```

逐行解析为 `VolumeRecord`，与逐卷循环走相同的状态机。

#### 硬约束

- `volumes[i].index` 必须连续无空洞（由 `VolumeStateManager` 强制）
- 不创建空的 V2-VN 记录；用户没填就是没有
- 不预填占位行到总纲

### Step 5.5：AI 卷骨架起草（新增）

> **触发条件**：仅当用户在 Step 1.6.3 选 B 时进入。

调用 `data_modules/ai_volume_drafter.py:draft_next_volume()`：
- 输入：用户的一句话 + 已 confirmed 卷列表 + 题材 + 目标 index
- 输出：`CandidateVolume`（status=draft, source=ai）
- **绝对不直接写盘**——只放在 `VolumeStateManager._drafts` 里

调用 LLM：沿用主 LLM 配置（与 `webnovel-write` 同源）。

#### 用户裁决

AI 返回后，必须询问用户：

```
AI 起草了 V_{k+1}：

卷名：<X>
核心冲突：<Y>
卷末高潮：<Z>

A) 接受（status: draft → confirmed）
B) 修改后接受（让用户改字段后接受）
C) 拒绝，自己填
D) 完全跳过这一卷（设 deferred）
```

只有 A / B 走 `VolumeStateManager.confirm_volume(k+1)`。

#### 禁止行为

- 禁止 AI 自动确认（无用户决议则不写入 state.json）
- 禁止从已确认卷推断未填字段
- 禁止覆盖已 confirmed 卷的字段
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer_chang/skills/webnovel-init/SKILL.md
git commit -m "docs(init): add Step 1.6 (multi-volume collector) + Step 5.5 (AI drafter)"
```

---

## Task 9: Modify webnovel-plan SKILL.md Step 9 — V+1 anchor from state

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-plan/SKILL.md:336-344`

- [ ] **Step 1: Replace the Step 9 "执行最小总纲写回" block**

Find this section:

```markdown
执行最小总纲写回（只更新 `大纲/总纲.md` 的 V+1 卷名 / 核心冲突 / 卷末高潮与伏笔表，不生成下一卷详细大纲 / 节拍表 / 时间线 / 章纲）：

\`\`\`bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "$PROJECT_ROOT" master-outline-sync \
  --volume {volume_id} \
  --writeback-file "大纲/第{volume_id}卷-总纲写回.json" \
  --format text

\`\`\`
```

Replace with:

```markdown
执行最小总纲写回（语义调整）：从 `.webnovel/state.json` 读取 `volumes[]`，按状态决定 V+1 行的填充：

- 若 V+1 `status=confirmed`：从 state.json 取其 `title / core_conflict / climax`，写回总纲 V+1 行
- 若 V+1 `status=deferred` 或不存在：V+1 行留空（不伪造）
- **不生成** V+2+ 详细大纲 / 节拍表 / 时间线 / 章纲（与原硬约束一致）

读 V+1 字段用 `VolumeStateManager.get_volume(volume_id + 1)`：

\`\`\`python
from data_modules.volume_state import VolumeStateManager
import json
state = json.loads(open("${PROJECT_ROOT}/.webnovel/state.json", encoding="utf-8").read())
mgr = VolumeStateManager(state)
next_vol = mgr.get_volume(${volume_id} + 1)
# next_vol is None 或 status=deferred → 跳过
# next_vol.status=confirmed → 用其字段填总纲 V+1 行
\`\`\`

\`\`\`bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "$PROJECT_ROOT" master-outline-sync \
  --volume {volume_id} \
  --writeback-file "大纲/第{volume_id}卷-总纲写回.json" \
  --format text

\`\`\`
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer_chang/skills/webnovel-plan/SKILL.md
git commit -m "docs(plan): Step 9 reads volumes[] for V+1 anchor (per spec §5.4)"
```

---

## Task 10: Add plan-flow V+1 anchor tests (per spec §5.4)

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/scripts/tests/integration/test_plan_v_plus_one_anchor.py`

> **Note**: Spec referenced `test_plan_flow_writes_minimal_next_volume_anchor.py` but that file exists only in the upstream archive (`references/03-webnovel-writer-upstream/...`), not in our fork. We create a new test file with the same intent.

- [ ] **Step 1: Create the test file**

```python
"""Verify the spec §5.4 contract:
  - plan V1 does NOT pre-generate 第N卷-详细大纲.md / 节拍表.md / 时间线.md for N >= 2
  - V+1 row in 总纲.md is filled iff V+1 is confirmed in state.json
  - V+1 row is empty / omitted iff V+1 is deferred or absent
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from init_project import init_project


def _init_project(tmp_path, skeleton):
    init_project(
        project_dir=str(tmp_path),
        title="Anchor Test",
        genre="玄幻",
        target_chapters=100,
        target_words=300000,
        volume_skeleton=skeleton,
    )


def test_plan_v1_no_v2_confirmation_omits_v2_row(tmp_path):
    """Only V1 confirmed → V2 row NOT pre-generated in 总纲."""
    _init_project(tmp_path, [
        {"index": 1, "title": "V1", "chapter_range": [1, 100],
         "core_conflict": "A", "climax": "B",
         "status": "confirmed", "source": "human"},
    ])
    outline = (tmp_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
    assert "### 第1卷" in outline
    assert "### 第2卷" not in outline
    # No detailed outline auto-generated for V2
    assert not (tmp_path / "大纲" / "第2卷-详细大纲.md").exists()
    assert not (tmp_path / "大纲" / "第2卷-节拍表.md").exists()
    assert not (tmp_path / "大纲" / "第2卷-时间线.md").exists()


def test_plan_v1_with_v2_confirmed_writes_v2_row_only(tmp_path):
    """V2 confirmed → V2 row filled, but still no detailed outline."""
    _init_project(tmp_path, [
        {"index": 1, "title": "V1", "chapter_range": [1, 50],
         "core_conflict": "A", "climax": "B",
         "status": "confirmed", "source": "human"},
        {"index": 2, "title": "V2-深入", "chapter_range": [51, 100],
         "core_conflict": "C", "climax": "D",
         "status": "confirmed", "source": "human"},
    ])
    outline = (tmp_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
    assert "### 第1卷" in outline
    assert "### 第2卷" in outline
    # Title from state.json propagates
    assert "V2-深入" in outline
    # Detailed outline STILL not auto-generated (the hard constraint)
    assert not (tmp_path / "大纲" / "第2卷-详细大纲.md").exists()
    assert not (tmp_path / "大纲" / "第2卷-节拍表.md").exists()
    assert not (tmp_path / "大纲" / "第2卷-时间线.md").exists()


def test_plan_v1_three_volumes_no_v4_row(tmp_path):
    """Three volumes confirmed → V4+ NOT pre-generated."""
    _init_project(tmp_path, [
        {"index": i, "title": f"V{i}", "chapter_range": [(i-1)*30+1, i*30],
         "core_conflict": "X", "climax": "Y",
         "status": "confirmed", "source": "human"}
        for i in range(1, 4)
    ])
    outline = (tmp_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
    for i in range(1, 4):
        assert f"### 第{i}卷" in outline
    assert "### 第4卷" not in outline
```

- [ ] **Step 2: Run all plan-flow related tests**

Run: `cd .claude/plugins/webnovel-writer_chang && python3 -m pytest scripts/tests/integration/test_plan_v_plus_one_anchor.py scripts/tests/integration/test_init_multi_volume.py -v`
Expected: 5 PASSED (3 new + 2 from Task 5/6)

- [ ] **Step 3: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer_chang/scripts/tests/integration/test_plan_v_plus_one_anchor.py
git commit -m "test(plan): add V+1 anchor semantics tests (confirmed vs deferred per spec §5.4)"
```

---

## Task 11: End-to-end smoke test

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/scripts/tests/integration/test_e2e_multi_volume_init.py`

- [ ] **Step 1: Write the smoke test**

```python
"""End-to-end smoke test: init with multi-volume skeleton + plan V1 + verify
state.json and 总纲.md final shape."""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from init_project import init_project


def test_e2e_3_volume_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        init_project(
            project_dir=str(project_path),
            title="E2E Test",
            genre="修仙",
            target_chapters=240,
            target_words=720000,
            volume_skeleton=[
                {"index": 1, "title": "出村", "chapter_range": [1, 80],
                 "core_conflict": "宗门入门考核", "climax": "夺得内门资格",
                 "key_cool_points": ["首战告捷"],
                 "status": "confirmed", "source": "human"},
                {"index": 2, "title": "深入", "chapter_range": [81, 160],
                 "core_conflict": "敌派渗透", "climax": "师尊负伤",
                 "status": "confirmed", "source": "human"},
                {"index": 3, "title": "反转", "chapter_range": [161, 240],
                 "core_conflict": "身世揭露", "climax": "退宗出走",
                 "status": "confirmed", "source": "human"},
            ],
        )

        # Verify state.json shape
        state = json.loads((project_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
        assert len(state["volumes"]) == 3
        assert state["project_info"]["confirmed_through_volume"] == 3
        assert state["project_info"]["later_volumes_status"] == "deferred"

        # Verify 总纲 has all 3 volumes
        outline = (project_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
        for i in range(1, 4):
            assert f"### 第{i}卷" in outline

        # Verify no auto-generated detailed outline for V2, V3
        assert not (project_path / "大纲" / "第2卷-详细大纲.md").exists()
        assert not (project_path / "大纲" / "第3卷-详细大纲.md").exists()


def test_e2e_user_stops_at_v1():
    """User explicitly defers V2+: only V1 in state, no V2 stub."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        init_project(
            project_dir=str(project_path),
            title="Single Vol",
            genre="都市",
            target_chapters=100,
            target_words=300000,
            volume_skeleton=[
                {"index": 1, "title": "V1", "chapter_range": [1, 100],
                 "core_conflict": "A", "climax": "B",
                 "status": "confirmed", "source": "human"},
            ],
        )
        state = json.loads((project_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
        assert len(state["volumes"]) == 1
        assert state["project_info"]["confirmed_through_volume"] == 1

        outline = (project_path / "大纲" / "总纲.md").read_text(encoding="utf-8")
        assert "### 第1卷" in outline
        assert "### 第2卷" not in outline  # NOT pre-filled
```

- [ ] **Step 2: Run smoke test**

Run: `cd .claude/plugins/webnovel-writer_chang && python3 -m pytest scripts/tests/integration/test_e2e_multi_volume_init.py -v`
Expected: 2 PASSED

- [ ] **Step 3: Run full test suite to verify no regression**

Run: `cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/ -v --tb=short`
Expected: all PASSED (existing + new)

- [ ] **Step 4: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer_chang/scripts/tests/integration/test_e2e_multi_volume_init.py
git commit -m "test(e2e): smoke test for 3-volume init + user-stops-at-v1 flow"
```

---

## Task 12: Update INDEX + close out

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/README.md` (optional: mention the new feature)

- [ ] **Step 1: Add a one-line entry to README under existing feature list**

Find the section listing skills/features in `README.md`. After the existing entries, add:

```markdown
- **Multi-volume init** (`webnovel-init` Step 1.6 + Step 5.5) — collect V1-VN skeleton with optional AI drafting; status state machine per spec `docs/superpowers/specs/2026-08-18-multi-volume-init-design.md`
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chang/Desktop/zhanghui
git add .claude/plugins/webnovel-writer_chang/README.md
git commit -m "docs(readme): mention multi-volume init feature"
```

---

## Self-Review Checklist

Before handing off, verify:

- [ ] Each spec section (§1-§9) maps to ≥1 task:
  - §4 data model → Task 1 (dataclasses) + Task 3 (manager)
  - §5.1 Collector → Task 8 (Step 1.6)
  - §5.2 Drafter → Task 4
  - §5.3 State Manager → Tasks 2, 3
  - §5.4 Plan integration → Tasks 9, 10
  - §6 file changes → all tasks touch the right files
  - §7 testing → Tasks 2, 5, 10, 11
  - §8 risks → Task 12 (docs), embedded in §5.2 drafter constraints
- [ ] No "TBD" / "TODO" / "similar to Task N" placeholders
- [ ] Type consistency: `VolumeStateManager.append_or_update` called consistently in Tasks 6, 8, 10
- [ ] All file paths absolute (relative to project root)
- [ ] All commit commands have full paths