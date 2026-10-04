# P3: Write/Review Consume reference_research — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Make `webnovel-write` and `webnovel-review` consume `reference_research/` produced by P0-Full + P1+P2. Write gets reference context at Step 0 + Step 1 + Step 2A; review detects `do_not_copy` violations.

**Architecture:** One new helper module + 4 doc/agent updates + 10+ tests. Reuses `reference_research_scanner.py` from the 14-fix cycle.

**Tech Stack:** Python 3, pathlib, json. No new deps.

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `scripts/data_modules/reference_research_injector.py` | **Create** | 3 public functions: build_step1_summary, build_step2a_prompt_section, build_do_not_copy_check_data |
| `scripts/data_modules/tests/test_reference_research_injector.py` | **Create** | 12+ unit tests |
| `skills/webnovel-write/SKILL.md` | Modify | Step 0 + Step 1 + Step 2A wiring |
| `skills/webnovel-review/SKILL.md` | Modify | Step 3 do_not_copy check |
| `agents/context-agent.md` | Modify | load-context pack + taskbook §4 |
| `agents/reviewer.md` | Modify | New category + read do_not_copy_check.json |
| `scripts/data_modules/tests/test_prompt_integrity.py` | Modify | 3 new tests |

---

## Task 1: `reference_research_injector.py` helper + 12 unit tests

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/scripts/data_modules/reference_research_injector.py`
- Create: `.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_reference_research_injector.py`

- [ ] **Step 1: Write failing tests**

Create `scripts/data_modules/tests/test_reference_research_injector.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pytest
import sys


def _build_minimal_tree(project_root, book_safe="fanren", ref_title="凡人修仙传",
                        do_not_copy=None, canon_contamination=None,
                        borrowable=None, satisfaction=None):
    """Build a minimal reference_research tree at project_root/.webnovel/reference_research/<book_safe>/."""
    import pathlib
    from init_reference_tree import build_reference_tree

    schema = {
        "source": {"reference_title": ref_title, "reference_source": "book_name",
                   "analysis_mode": "quick", "confidence": 0.9},
        "reader_promise": "",
        "opening_hook_patterns": [],
        "cool_point_loops": [],
        "protagonist_patterns": "",
        "antagonist_pressure_patterns": "",
        "pacing_notes": "",
        "narrative_function": "升级流",
        "boundary_reason": {},
        "protagonist_action_chain": [],
        "emotion_curve": [],
        "satisfaction_point": satisfaction or [],
        "foreshadowing": [],
        "gains_costs": [],
        "character_changes": [],
        "borrowable_structures": borrowable or [],
        "differentiation_requirements": "",
        "init_candidates": {},
        "do_not_copy": do_not_copy or [],
        "canon_contamination_warnings": canon_contamination or [],
        "quality": {"passed": True, "confidence": 0.9, "coverage": 0.9},
    }
    return build_reference_tree(project_root, schema, ref_title)


def test_build_step1_summary_with_no_trees(tmp_path):
    """Empty project returns empty string."""
    from data_modules.reference_research_injector import build_step1_summary
    assert build_step1_summary(tmp_path) == ""


def test_build_step1_summary_with_one_tree(tmp_path):
    """Returns formatted summary with primary tree info."""
    from data_modules.reference_research_injector import build_step1_summary
    _build_minimal_tree(tmp_path, borrowable=["宗门阶梯式升级"])
    summary = build_step1_summary(tmp_path)
    assert "对标参考" in summary
    assert "凡人修仙传" in summary
    assert "升级流" in summary


def test_build_step1_summary_token_limit(tmp_path):
    """Output is ≤ 200 tokens."""
    from data_modules.reference_research_injector import build_step1_summary
    _build_minimal_tree(
        tmp_path,
        do_not_copy=["X" * 50 for _ in range(20)],
        canon_contamination=["Y" * 50 for _ in range(20)],
        borrowable=["Z" * 50 for _ in range(20)],
        satisfaction=["W" * 50 for _ in range(10)],
    )
    summary = build_step1_summary(tmp_path)
    # Token heuristic: 1 token ≈ 2 chars for Chinese (or 4 for English)
    assert len(summary) <= 800  # 200 tokens × 4 chars/token conservative


def test_build_step2a_section_with_no_trees(tmp_path):
    """Empty project returns empty string."""
    from data_modules.reference_research_injector import build_step2a_prompt_section
    assert build_step2a_prompt_section(tmp_path) == ""


def test_build_step2a_section_includes_do_not_copy(tmp_path):
    """Includes do_not_copy items from primary tree."""
    from data_modules.reference_research_injector import build_step2a_prompt_section
    _build_minimal_tree(tmp_path, do_not_copy=["韩立人设", "神秘小瓶机制"])
    section = build_step2a_prompt_section(tmp_path)
    assert "对标书红黑名单" in section
    assert "不可照搬" in section
    assert "韩立人设" in section
    assert "神秘小瓶机制" in section


def test_build_step2a_section_includes_canon_contamination(tmp_path):
    """Includes canon_contamination_warnings."""
    from data_modules.reference_research_injector import build_step2a_prompt_section
    _build_minimal_tree(tmp_path, canon_contamination=["原作人物名: 韩立", "原作地名: 落云宗"])
    section = build_step2a_prompt_section(tmp_path)
    assert "原作人物名" in section
    assert "韩立" in section


def test_build_step2a_section_borrowable_limited(tmp_path):
    """borrowable_structures limited to ≤ 5 items."""
    from data_modules.reference_research_injector import build_step2a_prompt_section
    _build_minimal_tree(tmp_path, borrowable=[f"结构{i}" for i in range(10)])
    section = build_step2a_prompt_section(tmp_path)
    # Count borrowable lines
    borrowable_lines = [l for l in section.split("\n") if l.startswith("- 结构")]
    assert len(borrowable_lines) <= 5


def test_build_step2a_section_includes_satisfaction(tmp_path):
    """Includes satisfaction_point items."""
    from data_modules.reference_research_injector import build_step2a_prompt_section
    _build_minimal_tree(tmp_path, satisfaction=["灵根检测反转", "宗门大比逆袭"])
    section = build_step2a_prompt_section(tmp_path)
    assert "灵根检测反转" in section


def test_build_do_not_copy_check_data_finds_violation(tmp_path):
    """Detects forbidden item in chapter text."""
    from data_modules.reference_research_injector import build_do_not_copy_check_data
    _build_minimal_tree(tmp_path, do_not_copy=["韩立人设"])
    chapter_text = "第一章：觉醒。\n韩立微微一笑道：让我们开始修炼。"
    violations = build_do_not_copy_check_data(tmp_path, chapter_text)
    assert len(violations) >= 1
    assert violations[0]["item"] == "韩立人设"
    assert violations[0]["chapter_line"] == 2
    assert "韩立" in violations[0]["matched_text"]
    assert violations[0]["severity"] == "critical"
    assert violations[0]["category"] == "do_not_copy_violation"


def test_build_do_not_copy_check_data_no_violation(tmp_path):
    """Clean chapter → empty list."""
    from data_modules.reference_research_injector import build_do_not_copy_check_data
    _build_minimal_tree(tmp_path, do_not_copy=["韩立人设"])
    chapter_text = "第一章：主角李明开始修炼。"
    violations = build_do_not_copy_check_data(tmp_path, chapter_text)
    assert violations == []


def test_build_do_not_copy_check_data_no_trees(tmp_path):
    """No trees → empty list (graceful fallback)."""
    from data_modules.reference_research_injector import build_do_not_copy_check_data
    violations = build_do_not_copy_check_data(tmp_path, "anything")
    assert violations == []


def test_build_step1_summary_multiple_trees_primary_first(tmp_path, monkeypatch):
    """When idea_bank.json.reference_research_path is set, that tree's info appears first."""
    from data_modules.reference_research_injector import build_step1_summary
    # Build two trees
    _build_minimal_tree(tmp_path, book_safe="a", ref_title="《A书》")
    _build_minimal_tree(tmp_path, book_safe="b", ref_title="《B书》")
    # Write idea_bank.json with reference_research_path pointing to "b"
    webnovel = tmp_path / ".webnovel"
    webnovel.mkdir(exist_ok=True)
    (webnovel / "idea_bank.json").write_text(
        json.dumps({"reference_research_path": ".webnovel/reference_research/b/"}),
        encoding="utf-8",
    )
    summary = build_step1_summary(tmp_path)
    # "B书" should appear before "A书" in the summary
    assert summary.index("B书") < summary.index("A书")
```

- [ ] **Step 2: Run tests, verify all fail with ImportError**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_reference_research_injector.py -v 2>&1 | tail -15
```

Expected: All 12 FAIL with `No module named 'reference_research_injector'`.

- [ ] **Step 3: Implement `reference_research_injector.py`**

Create `/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/reference_research_injector.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Build prompt-section injections for webnovel-write from reference_research/.

Implements 2026-08-16-p3-write-review-consume-reference-research-design §D1.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _primary_tree_path(project_root: Path, idea_bank_pointer: str | None) -> Path | None:
    """Determine primary reference_research tree from idea_bank pointer."""
    if not idea_bank_pointer:
        return None
    # pointer is like ".webnovel/reference_research/<book-safe>/"
    parts = Path(idea_bank_pointer).parts
    if "reference_research" not in parts:
        return None
    idx = parts.index("reference_research")
    if idx + 1 >= len(parts):
        return None
    book_safe = parts[idx + 1].rstrip("/")
    return project_root / ".webnovel" / "reference_research" / book_safe


def _load_idea_bank_pointer(project_root: Path) -> str | None:
    """Read reference_research_path from idea_bank.json if present."""
    idea_bank = project_root / ".webnovel" / "idea_bank.json"
    if not idea_bank.is_file():
        return None
    try:
        data = json.loads(idea_bank.read_text(encoding="utf-8"))
        return data.get("reference_research_path")
    except (json.JSONDecodeError, OSError):
        return None


def _ordered_trees(project_root: Path) -> list[Path]:
    """Return valid reference_research trees, primary (from idea_bank) first."""
    from data_modules.reference_research_scanner import scan_reference_research_trees

    trees = scan_reference_research_trees(project_root)
    primary = _primary_tree_path(project_root, _load_idea_bank_pointer(project_root))
    if primary and primary in trees:
        trees = [primary] + [t for t in trees if t != primary]
    return trees


def _read_json_field(tree: Path, field: str, default=None) -> Any:
    schema = tree / "_schema.json"
    if not schema.is_file():
        return default
    try:
        data = json.loads(schema.read_text(encoding="utf-8"))
        return data.get(field, default)
    except (json.JSONDecodeError, OSError):
        return default


def _read_md_lines(tree: Path, filename: str) -> list[str]:
    f = tree / filename
    if not f.is_file():
        return []
    lines = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        # Strip bullet markers like "- ", "* ", "1. ", "2. "
        line = re.sub(r"^[-*\d.]+\s*", "", line).strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def build_step1_summary(project_root: Path, max_tokens: int = 200) -> str:
    """Build a ≤ max_tokens summary for Step 1 taskbook injection.

    Format:
      ## 对标参考（来自 reference_research/）
      主对标书：《凡人修仙传》 题材：升级流
      可借鉴：宗门阶梯式升级结构
      规避：韩立人设、神秘小瓶机制
    """
    trees = _ordered_trees(project_root)
    if not trees:
        return ""

    primary = trees[0]
    ref_title = _read_json_field(primary, "source", {}).get("reference_title", primary.name)
    narrative = _read_json_field(primary, "narrative_function", "") or "未标注"
    borrowable = _read_json_field(primary, "borrowable_structures", [])[:2]  # cap at 2
    do_not_copy = _read_json_field(primary, "do_not_copy", [])[:3]  # cap at 3

    lines = [
        "## 对标参考（来自 reference_research/）",
        f"主对标书：《{ref_title}》 题材：{narrative}",
    ]
    if borrowable:
        lines.append("可借鉴：" + "、".join(borrowable))
    if do_not_copy:
        lines.append("规避：" + "、".join(do_not_copy))

    summary = "\n".join(lines)
    # Hard cap: 200 tokens × 4 chars = 800 chars
    if len(summary) > 800:
        summary = summary[:797] + "..."
    return summary


def build_step2a_prompt_section(project_root: Path) -> str:
    """Build a longer '对标书红黑名单' section for Step 2A prompt injection."""
    trees = _ordered_trees(project_root)
    if not trees:
        return ""

    primary = trees[0]
    ref_title = _read_json_field(primary, "source", {}).get("reference_title", primary.name)

    dnc = _read_json_field(primary, "do_not_copy", [])
    ccw = _read_json_field(primary, "canon_contamination_warnings", [])
    borrowable = _read_json_field(primary, "borrowable_structures", [])[:5]
    satisfaction = _read_json_field(primary, "satisfaction_point", [])[:2]

    lines = [
        "## 对标书红黑名单（必读）",
        "",
        f"> 参考书：《{ref_title}》",
        "",
    ]

    if dnc:
        lines.append("### 不可照搬（do_not_copy）")
        for item in dnc:
            lines.append(f"- {item}")
        lines.append("")

    if ccw:
        lines.append("### 必须规避的角色名/地名（canon_contamination_warnings）")
        for item in ccw:
            lines.append(f"- {item}")
        lines.append("")

    if borrowable:
        lines.append("### 可借鉴的结构（borrowable_structures，3-5条）")
        for item in borrowable:
            lines.append(f"- {item}")
        lines.append("")

    if satisfaction:
        lines.append("### 反转 hooks（satisfaction_point，1-2条）")
        for item in satisfaction:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def build_do_not_copy_check_data(project_root: Path, chapter_text: str) -> list[dict]:
    """Scan chapter text against do_not_copy items, return violation list.

    Each violation:
      {
        "item": str,
        "source_book": str,
        "chapter_line": int,
        "matched_text": str,
        "severity": "critical",
        "category": "do_not_copy_violation"
      }
    """
    trees = _ordered_trees(project_root)
    if not trees:
        return []

    violations = []
    lines = chapter_text.splitlines()
    for tree in trees:
        ref_title = _read_json_field(tree, "source", {}).get("reference_title", tree.name)
        for item in _read_json_field(tree, "do_not_copy", []):
            if len(item) < 2:  # skip trivial 1-char items
                continue
            for line_num, line in enumerate(lines, start=1):
                if item in line:
                    violations.append({
                        "item": item,
                        "source_book": ref_title,
                        "chapter_line": line_num,
                        "matched_text": line.strip()[:200],  # cap snippet length
                        "severity": "critical",
                        "category": "do_not_copy_violation",
                    })
    return violations
```

- [ ] **Step 4: Run tests, verify all 12 pass**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_reference_research_injector.py -v 2>&1 | tail -15
```

Expected: 12 PASSED.

- [ ] **Step 5: Sync + commit**

```bash
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/scripts/data_modules/reference_research_injector.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_reference_research_injector.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/tests/

cd /Users/chang/Desktop/zhanghui
git add -A
git commit -m "feat(injector): reference_research_injector — write/review consumption helper

Three public functions:
- build_step1_summary() returns ≤ 200 token summary for Step 1 taskbook
- build_step2a_prompt_section() returns full 红黑名单 for Step 2A prompt
- build_do_not_copy_check_data() scans chapter text vs do_not_copy items

12 unit tests cover: empty state, single tree, multi-tree primary ordering,
token limit, do_not_copy detection with line numbers + matched text,
borrowable structures capped at 5, satisfaction point inclusion."
```

---

## Task 2: write SKILL.md + context-agent.md wiring

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md`
- Modify: `.claude/plugins/webnovel-writer_chang/agents/context-agent.md`
- Modify: `.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py`

- [ ] **Step 1: Write failing test**

Add to `scripts/data_modules/tests/test_prompt_integrity.py`:

```python
def test_write_skill_references_reference_research_injector():
    """webnovel-write SKILL.md must call reference_research_injector at Step 0 + Step 2A."""
    text = _read_text(SKILLS_DIR / "webnovel-write" / "SKILL.md")
    assert "reference_research_injector" in text, "write SKILL must inject reference_research"
    # Must reference both step1 summary and step2a section call (CLI or Python)
    assert "build-step1-summary" in text or "build_step1_summary" in text
    assert "build-step2a-section" in text or "build_step2a_prompt_section" in text
```

- [ ] **Step 2: Run test, verify fails**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_write_skill_references_reference_research_injector -v 2>&1 | tail -8
```

Expected: FAIL.

- [ ] **Step 3: Add Step 0 wiring to write SKILL.md**

Open `/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md`. Find the "个人语料检测" and "写作宪法加载" blocks (around L157–166). Add a new block immediately after them:

```markdown

**对标参考检测（reference_research）**：
- 调用 `python3 ${SCRIPTS_DIR}/data_modules/reference_research_injector.py build-step1-summary --project-root "${PROJECT_ROOT}"`，得到 ≤ 200 token 摘要字符串
- 若返回空串 → 跳过（无 `reference_research/` 树，不报错）
- 若非空 → 摘要拼接到 context-agent 任务书的"对标参考"段
```

- [ ] **Step 4: Add Step 1 wiring to context-agent.md**

Open `/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/agents/context-agent.md`. Find the section listing the `load-context` base pack fields. Add a new row:

```markdown
| `reference_research_summary` | string | ≤ 200 token | `reference_research_injector.build_step1_summary()` |
```

Find the §4 taskbook template. Add a new sub-section:

```markdown

### 对标参考（来自 reference_research/）

<`reference_research_summary` 内容，自然语言改写，不暴露字段名 / 路径 / 系统术语>
```

- [ ] **Step 5: Add Step 2A wiring to write SKILL.md**

Open write SKILL.md. Find the `cat core-constraints.md` line in Step 2A. Insert **before** it:

```markdown
调用 `python3 ${SCRIPTS_DIR}/data_modules/reference_research_injector.py build-step2a-section --project-root "${PROJECT_ROOT}"`，
若非空 → 把"对标书红黑名单"段（必读，含 do_not_copy / canon_contamination_warnings / borrowable_structures / satisfaction_point）追加到章节起草提示词的"约束"段，作为 L1 注入。
主流程**不口头重写或简化**该段；原样作为约束素材传下去。
若返回空串 → 跳过此注入。
```

- [ ] **Step 6: Run test, verify passes**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_write_skill_references_reference_research_injector -v 2>&1 | tail -8
```

Expected: PASS.

- [ ] **Step 7: Sync + commit**

```bash
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/skills/webnovel-write/SKILL.md
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/agents/context-agent.md /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/agents/
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/tests/

cd /Users/chang/Desktop/zhanghui
git add -A
git commit -m "feat(write): wire reference_research_injector into write Step 0/1/2A

Step 0: detect reference_research tree, get ≤ 200 token summary
Step 1: context-agent load-context pack includes reference_research_summary
        field; taskbook §4 has 对标参考 sub-section
Step 2A: 红黑名单 section appended to drafting prompt as L1 injection

Injections are graceful no-ops when no reference_research tree exists."
```

---

## Task 3: review SKILL.md + reviewer.md do_not_copy check

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-review/SKILL.md`
- Modify: `.claude/plugins/webnovel-writer_chang/agents/reviewer.md`
- Modify: `.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py`

- [ ] **Step 1: Write 2 failing tests**

Add to `scripts/data_modules/tests/test_prompt_integrity.py`:

```python
def test_review_skill_references_do_not_copy_check():
    """webnovel-review SKILL.md must perform do_not_copy check in Step 3."""
    text = _read_text(SKILLS_DIR / "webnovel-review" / "SKILL.md")
    assert "do_not_copy" in text, "review SKILL must check do_not_copy"
    assert "do_not_copy_check.json" in text, "review must reference new artifact"
    assert "reference_research_injector" in text or "build-do-not-copy-check-data" in text, (
        "review must call injector helper"
    )


def test_reviewer_agent_supports_do_not_copy_violation_category():
    """agents/reviewer.md must declare do_not_copy_violation as a valid issue category."""
    text = _read_text(AGENTS_DIR / "reviewer.md")
    assert "do_not_copy_violation" in text, "reviewer.md must list do_not_copy_violation category"
```

- [ ] **Step 2: Run tests, verify fail**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_review_skill_references_do_not_copy_check data_modules/tests/test_prompt_integrity.py::test_reviewer_agent_supports_do_not_copy_violation_category -v 2>&1 | tail -8
```

Expected: 2 FAIL.

- [ ] **Step 3: Add do_not_copy check to review SKILL.md**

Open `/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/skills/webnovel-review/SKILL.md`. Find Step 3 "并行 Task 调用" section. Add after:

```markdown

**do_not_copy 检查（reviewer 任务之前执行）**：

1. 调用 `python3 ${SCRIPTS_DIR}/data_modules/reference_research_injector.py build-do-not-copy-check-data --project-root "${PROJECT_ROOT}" --chapter-text "$(cat .webnovel/tmp/chapter_text.txt)"`
2. 检查返回的 violations 列表
3. 写入 `.webnovel/tmp/do_not_copy_check.json`：

   ```json
   {"violations": [...每个含 item / source_book / chapter_line / matched_text / severity / category ...]}
   ```

4. 无 violations → 写空文件 `{"violations": []}`
5. reviewer 任务读取此 artifact 并把每个 violation 加入 `issues` 数组
```

- [ ] **Step 4: Add do_not_copy_violation category to reviewer.md**

Open `/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/agents/reviewer.md`. Find the section listing issue categories. Add `do_not_copy_violation` to the list. Update §5 / §6 / §7 wording accordingly.

Add a new step (after §3 reading do_not_copy_check.json):

```markdown

### 读取 do_not_copy_check.json

1. Read `.webnovel/tmp/do_not_copy_check.json`（由 review SKILL Step 3 调用 injector 生成）
2. For each violation in `violations[]`:
   - Convert to `issue` entry:
     ```json
     {
       "severity": "critical",
       "category": "do_not_copy_violation",
       "location": "ch{NNN}:line{MM}",
       "description": "出现 do_not_copy.md 中禁止的元素：<item>（来自《<source_book>》）",
       "evidence": "<matched_text>（do_not_copy.md 第 X 行）",
       "fix_hint": "删除或改写该元素。可借鉴 borrowable_structures 中的对应结构。",
       "blocking": true
     }
     ```
   - Append to the final `issues` array
```

- [ ] **Step 5: Run tests, verify pass**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_review_skill_references_do_not_copy_check data_modules/tests/test_prompt_integrity.py::test_reviewer_agent_supports_do_not_copy_violation_category -v 2>&1 | tail -8
```

Expected: 2 PASS.

- [ ] **Step 6: Sync + commit**

```bash
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/skills/webnovel-review/SKILL.md /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/skills/webnovel-review/SKILL.md
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/agents/reviewer.md /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/agents/
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/tests/

cd /Users/chang/Desktop/zhanghui
git add -A
git commit -m "feat(review): do_not_copy check + new category do_not_copy_violation

review SKILL Step 3 now calls reference_research_injector to scan
chapter text against do_not_copy items; results written to
.webnovel/tmp/do_not_copy_check.json.

reviewer.md declares do_not_copy_violation as an 8th issue category;
each violation becomes a critical issue with line number + evidence."
```

---

## Task 4: End-to-end smoke + final verification

**Files:** (verification only)

- [ ] **Step 1: Build a reference_research tree at /tmp/p3_smoke**

```bash
mkdir -p /tmp/p3_smoke
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -c "
import sys, json, pathlib
sys.path.insert(0, '.')
from data_modules.init_reference_tree import build_reference_tree
schema = {
  'source': {'reference_title': '凡人修仙传', 'reference_source': 'book_name', 'analysis_mode': 'quick', 'confidence': 0.9},
  'reader_promise': '',
  'opening_hook_patterns': [], 'cool_point_loops': [],
  'protagonist_patterns': '', 'antagonist_pressure_patterns': '', 'pacing_notes': '',
  'narrative_function': '升级流',
  'boundary_reason': {}, 'protagonist_action_chain': [],
  'emotion_curve': [], 'satisfaction_point': ['灵根检测反转'],
  'foreshadowing': [], 'gains_costs': [], 'character_changes': [],
  'borrowable_structures': ['宗门阶梯式升级结构', '小境界突破循环'],
  'differentiation_requirements': '',
  'init_candidates': {},
  'do_not_copy': ['韩立人设', '神秘小瓶机制'],
  'canon_contamination_warnings': ['原作人物名: 韩立'],
  'quality': {'passed': True, 'confidence': 0.9, 'coverage': 0.9}
}
build_reference_tree(pathlib.Path('/tmp/p3_smoke'), schema, '凡人修仙传')
print('Tree built')
"
ls /tmp/p3_smoke/.webnovel/reference_research/fanren-xiuxian-chuan/
```

- [ ] **Step 2: Verify Step 1 summary**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -c "
import sys
sys.path.insert(0, '.')
from data_modules.reference_research_injector import build_step1_summary
import pathlib
s = build_step1_summary(pathlib.Path('/tmp/p3_smoke'))
print(s)
print(f'len: {len(s)} chars')
assert len(s) <= 800
print('OK: ≤ 200 tokens')
"
```

Expected: Output contains 主对标书、可借鉴、规避。Len ≤ 800.

- [ ] **Step 3: Verify Step 2A section**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -c "
import sys
sys.path.insert(0, '.')
from data_modules.reference_research_injector import build_step2a_prompt_section
import pathlib
s = build_step2a_prompt_section(pathlib.Path('/tmp/p3_smoke'))
print(s)
"
```

Expected: Output contains all 4 sections (不可照搬、canon_contamination、可借鉴、反转 hooks).

- [ ] **Step 4: Verify do_not_copy check**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -c "
import sys
sys.path.insert(0, '.')
from data_modules.reference_research_injector import build_do_not_copy_check_data
import pathlib, json
chapter_text = '''第一章：觉醒
韩立微微一笑道：让我们开始修炼。
第二章：突破
李明看到韩立使用神秘小瓶。'''
violations = build_do_not_copy_check_data(pathlib.Path('/tmp/p3_smoke'), chapter_text)
print(json.dumps(violations, ensure_ascii=False, indent=2))
assert len(violations) >= 3, f'expected ≥3 violations, got {len(violations)}'
print('OK')
"
```

Expected: 3 violations (line 2 "韩立", line 4 "韩立", line 4 "神秘小瓶").

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest \
  data_modules/tests/test_prompt_integrity.py \
  data_modules/tests/test_init_reference_tree.py \
  data_modules/tests/test_init_idea_bank.py \
  data_modules/tests/test_marked_references.py \
  data_modules/tests/test_reference_research_scanner.py \
  data_modules/tests/test_reference_research_injector.py \
  -v 2>&1 | tail -15
```

Expected: All P3 tests (12+ injector + 3 prompt_integrity) pass + all P0-Full/P1+P2/14-fix tests pass. Pre-existing prompt_integrity failures (39) stay — out of scope.

- [ ] **Step 6: Cleanup**

```bash
rm -rf /tmp/p3_smoke
```

---

## Acceptance Criteria Checklist

- [ ] `reference_research_injector.py` exists with 3 public functions
- [ ] 12+ injector tests pass
- [ ] `test_write_skill_references_reference_research_injector` passes
- [ ] `test_review_skill_references_do_not_copy_check` passes
- [ ] `test_reviewer_agent_supports_do_not_copy_violation_category` passes
- [ ] All P0-Full + P1+P2 + 14-fix tests pass (no regression)
- [ ] Manual smoke: violation detected with line number + matched text
- [ ] Both copies in sync
- [ ] No new Critical bugs introduced (adversarial review gate to come)

## Out-of-Scope Reminder

- 39 pre-existing prompt_integrity failures (separate Cleanup cycle)
- P4 full-text deconstruction
- canon_contamination_warnings review check (v2)
- borrowable_structures enforcement review
- English / multi-language
- Multi-user shared reference_research/

## Self-Review Notes

- **Spec coverage**: D1→Task 1; D2.1→Task 2 Step 3; D2.2→Task 2 Step 4; D2.3→Task 2 Step 5; D3.1→Task 3 Step 3; D3.2→Task 3 Step 3; D4.1→Task 3 Step 4; D4.2→Task 3 Step 4; D5→Task 2 Step 4.
- **Placeholder scan**: no "TBD"/"TODO"/"implement later".
- **Type consistency**: `_ordered_trees()` returns `list[Path]` consistent across all 3 functions; `_primary_tree_path` returns `Path | None`; `build_do_not_copy_check_data` returns `list[dict]`.
- **Risk acknowledgment**: Token-limit enforcement in `build_step1_summary` (800 char hard cap) prevents the most likely regression.