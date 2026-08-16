# P1+P2: Standalone Deconstruct Skill + Chart-Scan Marked-References — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/webnovel-deconstruct` standalone skill (P2) + chart-scan `marked-references.json` manifest + plan auto-discovery (P1). Reuses P0-Full infrastructure (`deconstruction-agent`, `init_reference_tree.py`).

**Architecture:** Three layers. (1) New `skills/webnovel-deconstruct/SKILL.md` + `commands/deconstruct.md` + `scripts/data_modules/marked_references.py` helper. (2) Unlock `deconstruction-agent` description to allow multi-caller. (3) Update `webnovel-plan/SKILL.md` for auto-discovery + `webnovel-chart-scan/SKILL.md` for marked-references flow + `webnovel-chart-scan/scripts/output.py` for `write_marked_references()` helper.

**Tech Stack:** Python 3, `argparse`, `pathlib`, `json`. No new dependencies.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `commands/deconstruct.md` | Create | Slash command wrapper |
| `skills/webnovel-deconstruct/SKILL.md` | Create | Main P2 skill |
| `agents/deconstruction-agent.md` | Modify | Frontmatter description: allow init + deconstruct callers |
| `scripts/data_modules/marked_references.py` | Create | Read/write/validate `marked-references.json` |
| `skills/webnovel-chart-scan/SKILL.md` | Modify | Add marked-references section |
| `skills/webnovel-chart-scan/scripts/output.py` | Modify | Add `write_marked_references()` helper |
| `skills/webnovel-plan/SKILL.md` | Modify | Auto-discover `.webnovel/reference_research/*/` |
| `scripts/data_modules/tests/test_marked_references.py` | Create | 5 tests for helper |
| `scripts/data_modules/tests/test_prompt_integrity.py` | Modify | Add 3 new tests |

No new skill registration (skills/ dir auto-discovered by manifest).

---

## Task 1: Slash command wrapper for `/webnovel-deconstruct`

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/commands/deconstruct.md`

(Independent task — pure file create, ~5 lines.)

- [ ] **Step 1: Create the file**

Create `/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/commands/deconstruct.md`:

```markdown
---
description: 独立拆解参考书到 .webnovel/reference_research/ 库（多书并存，不动 idea_bank）
---
Use the Skill tool to invoke the `webnovel-deconstruct` skill
```

- [ ] **Step 2: Sync to marketplace copy**

```bash
cp "/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/commands/deconstruct.md" "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/commands/"
```

- [ ] **Step 3: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/commands/deconstruct.md
git commit -m "feat(deconstruct): add /webnovel-deconstruct slash command wrapper"
```

**Self-Review:** File created? Both copies in sync? Commit on main?

---

## Task 2: Unlock deconstruction-agent description + test

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/agents/deconstruction-agent.md` (frontmatter only)
- Modify: `.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py` (add 1 test)

- [ ] **Step 1: Write the failing test**

Add to `scripts/data_modules/tests/test_prompt_integrity.py` (find the end of the file or near other deconstruction tests):

```python
def test_deconstruction_agent_is_not_init_only():
    """Agent description must allow multiple callers (init Step 1.5 + standalone deconstruct)."""
    text = _read_text(REPO_ROOT / "agents" / "deconstruction-agent.md")
    assert "/webnovel-deconstruct" in text, "agent must mention deconstruct skill as caller"
    assert "/webnovel-init" in text, "agent must still mention init Step 1.5 as caller"
```

- [ ] **Step 2: Run test, verify it fails**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_deconstruction_agent_is_not_init_only -v 2>&1 | tail -8
```

Expected: FAIL — `deconstruction-agent.md` description currently says "/webnovel-init 的参考书拆解子代理" (no `/webnovel-deconstruct`).

- [ ] **Step 3: Modify agent frontmatter**

Open `/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/agents/deconstruction-agent.md`. Find the `description:` line in frontmatter (top of file). Change from:

```
description: /webnovel-init 的参考书拆解子代理。
```

To:

```
description: 从参考书抽取可迁移的创作模式。可被 /webnovel-init（Step 1.5）和 /webnovel-deconstruct（独立）调用。
```

Do NOT modify the body of the agent prompt — only the frontmatter description.

- [ ] **Step 4: Run test, verify green**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_deconstruction_agent_is_not_init_only -v 2>&1 | tail -8
```

Expected: PASS.

- [ ] **Step 5: Sync + commit**

```bash
cp "/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/agents/deconstruction-agent.md" "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/agents/"

cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/agents/deconstruction-agent.md .claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py
git commit -m "feat(agent): unlock deconstruction-agent description for multi-caller

Previously locked to /webnovel-init Step 1.5 only. Now also callable
from /webnovel-deconstruct (standalone skill). Body of agent prompt
unchanged — caller is responsible for persistence."
```

**Self-Review:** Test passes? No body change? Both copies in sync?

---

## Task 3: `marked_references.py` helper + 5 tests

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/scripts/data_modules/marked_references.py`
- Create: `.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_marked_references.py`

- [ ] **Step 1: Write the failing tests**

Create `scripts/data_modules/tests/test_marked_references.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pytest


def test_schema_version_required():
    """Payload missing schema_version raises ValueError."""
    from marked_references import validate_marked_references
    with pytest.raises(ValueError, match="schema_version"):
        validate_marked_references({"references": []})


def test_minimal_valid_payload():
    """Minimal valid payload: {schema_version: 1, references: []}."""
    from marked_references import validate_marked_references
    payload = {"schema_version": 1, "references": []}
    parsed = validate_marked_references(payload)
    assert parsed["schema_version"] == 1
    assert parsed["references"] == []


def test_reference_must_have_platform_and_title():
    """Reference missing platform or title raises ValueError."""
    from marked_references import validate_marked_references
    with pytest.raises(ValueError, match="platform"):
        validate_marked_references({"schema_version": 1, "references": [{"title": "X"}]})
    with pytest.raises(ValueError, match="title"):
        validate_marked_references({"schema_version": 1, "references": [{"platform": "qidian"}]})


def test_roundtrip_via_disk(tmp_path):
    """write_marked_references + load_marked_references round-trip preserves data."""
    from marked_references import write_marked_references, load_marked_references
    path = tmp_path / "marked-references.json"
    payload = {
        "schema_version": 1,
        "marked_at": "2026-08-16T12:34:56Z",
        "references": [
            {"platform": "qidian", "title": "凡人修仙传", "author": "忘语", "category": "仙侠"},
        ],
    }
    write_marked_references(payload, path)
    loaded = load_marked_references(path)
    assert loaded == payload


def test_load_returns_none_if_file_missing(tmp_path):
    """load_marked_references returns None when file absent (not error)."""
    from marked_references import load_marked_references
    result = load_marked_references(tmp_path / "does_not_exist.json")
    assert result is None
```

- [ ] **Step 2: Run tests, verify they fail (module doesn't exist)**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_marked_references.py -v 2>&1 | tail -10
```

Expected: All 5 FAIL with `No module named 'marked_references'`.

- [ ] **Step 3: Implement the helper**

Create `/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/marked_references.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read/write/validate chart-scan marked-references.json files.

Implements 2026-08-16-webnovel-deconstruct-standalone-design §D4.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CURRENT_SCHEMA_VERSION = 1


def validate_marked_references(data: dict) -> dict:
    """Validate marked-references.json payload dict.

    Required schema:
      - schema_version == 1
      - references: list of {platform, title, author?, category?}

    Raises ValueError on any miss. Returns the input dict on success.
    """
    if not isinstance(data, dict):
        raise ValueError("marked-references.json must be a JSON object")

    if data.get("schema_version") != CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f"marked-references.json schema_version must be {CURRENT_SCHEMA_VERSION}, "
            f"got {data.get('schema_version')!r}"
        )

    references = data.get("references")
    if not isinstance(references, list):
        raise ValueError("marked-references.json references must be a list")

    for i, ref in enumerate(references):
        if not isinstance(ref, dict):
            raise ValueError(f"marked-references.json references[{i}] must be an object")
        if "platform" not in ref:
            raise ValueError(f"marked-references.json references[{i}] missing 'platform'")
        if "title" not in ref:
            raise ValueError(f"marked-references.json references[{i}] missing 'title'")

    return data


def load_marked_references(path: Path) -> dict | None:
    """Load and validate marked-references.json from path.

    Returns the parsed dict, or None if file does not exist.
    Raises ValueError on schema mismatch.
    """
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return None
    raw = p.read_text(encoding="utf-8")
    data = json.loads(raw)
    return validate_marked_references(data)


def write_marked_references(payload: dict, path: Path) -> Path:
    """Validate and write marked-references.json to path.

    Returns the resolved path. Raises ValueError on schema mismatch.
    """
    validated = validate_marked_references(payload)
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(validated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return p
```

- [ ] **Step 4: Run tests, verify all 5 pass**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_marked_references.py -v 2>&1 | tail -10
```

Expected: 5 PASSED.

- [ ] **Step 5: Sync + commit**

```bash
cp "/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/data_modules/marked_references.py" "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/"
cp "/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_marked_references.py" "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/tests/"

cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/scripts/data_modules/marked_references.py .claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_marked_references.py
git commit -m "feat(scan): marked_references.py helper — read/write/validate manifest

Schema:
  - schema_version: 1
  - references: [{platform, title, author?, category?}]

Used by chart-scan SKILL.md (manual write) and webnovel-deconstruct
skill (--from-scan reads)."
```

**Self-Review:** All 5 tests pass? Both copies in sync?

---

## Task 4: `webnovel-deconstruct` SKILL.md (main skill file)

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/skills/webnovel-deconstruct/SKILL.md`

(Depends on Tasks 1, 2 — references both the slash command and the unlocked agent. Pure doc create, ~120 lines.)

- [ ] **Step 1: Create the skill file**

Create `/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/skills/webnovel-deconstruct/SKILL.md`:

```markdown
---
name: webnovel-deconstruct
description: 独立拆解参考书到 .webnovel/reference_research/ 库（多书并存，不动 idea_bank）。当用户想调研对标书、对比多本、或不在 /webnovel-init 流程内拆解时调用。
---

# Webnovel Deconstruct — 独立拆书

## 目标

把一本参考书拆解成结构化产物，落到 `<project_root>/.webnovel/reference_research/<book-safe>/` 下，与 `/webnovel-init` Step 1.5 走相同的落点。本 skill 是独立入口，**不动** `idea_bank.json`、`.webnovel/state.json`、设定集、大纲、正文、`.story-system/`。

## 调用时机

- 用户主动 `/webnovel-deconstruct "《凡人修仙传》"` 调研对标书
- `/webnovel-chart-scan` 扫榜后，用户想批量拆对标清单（`--from-scan`）
- 已写到一半，想回头补一本参考书的拆解
- 学习 / 研究用途（不出 init_candidates，只产出 report.md + do_not_copy）

## 输入形态

CLI 形式（命令壳 `commands/deconstruct.md` 已经在）：

```bash
# 书名 + 平台线索（quick 模式，无文本风险高）
/webnovel-deconstruct --book "起点《凡人修仙传》"

# 本地正文路径（deep 模式，路径不可读时降级 quick）
/webnovel-deconstruct --text-path /path/to/chapter1.txt

# 对话粘摘录（quick 模式）
/webnovel-deconstruct --excerpt "<摘录 1000 字以内>"

# 从 chart-scan marked-references.json 批量拆
/webnovel-deconstruct --from-scan

# 严格模式：拒绝重拆已有 <book-safe>/（默认是覆盖）
/webnovel-deconstruct --strict
```

如果参数不足，向用户追问（一次一个，问清楚为止）。**不要默认拆书**。

## 执行步骤

1. **收集输入**：通过 CLI 参数或 AskUserQuestion 收集 `{reference_title, reference_source, reference_text_path|reference_text_excerpt, analysis_mode}`。`--from-scan` 时从 `./chart-scan/marked-references.json` 读 `references[]` 数组逐条处理。

2. **调用 deconstruction-agent**：
   ```
   Use the Agent tool to run `webnovel-writer:deconstruction-agent`
   ```
   传入 §2 列出的字段。**禁止使用 `subagent_type:` 字段**。

3. **质量门控**：检查返回 `init_reference_research.quality`：
   - `quality.passed=false` 或 `confidence < 0.85`：向用户展示缺漏，三选一：
     - (i) 用更多文本重跑
     - (ii) 用稀疏模式继续
     - (iii) 放弃（默认）
   - 通过：进入第 4 步。

4. **展示原文必读项**：把 `do_not_copy` 和 `canon_contamination_warnings` 字段**原文**展示给用户——这些是负面约束，用户写新书时要避开。

5. **用户确认门**：**用户确认前**禁止任何文件写。

6. **落盘**：用户确认后：
   - 调用 `from init_reference_tree import build_reference_tree`
   - 调用 `build_reference_tree(project_path, schema, reference_title, overwrite=True)`（P2 默认覆盖）
   - 旧树存在时，`_schema.json` 自动备份为 `_schema.json.bak-<ts>`

7. **退出**：输出 `<project>/.webnovel/reference_research/<book-safe>/` 绝对路径，提示用户：
   - 下次 `/webnovel-plan` 会自动发现这本书
   - 多本书并存没问题，每个 `<book-safe>/` 独立
   - 重拆同一本用 `overwrite=True`（默认）或 `--strict` 拒绝

## 禁止行为（与 init §1.5 一致）

- 写入 `idea_bank.json`、`.webnovel/state.json`、`.webnovel/reference_research/` 之外的位置
- 写入 `设定集/`、`大纲/`、`正文/`、`.story-system/`
- 调用 `init_project.py`（这是 init 的职责）
- 主流程口头重写或简化 agent 返回的结构化字段

## 错误处理

- 用户给了不存在的书名（agent 不认识）：让用户补 platform/title/excerpt 三选一
- `--text-path` 路径不可读：自动降级 quick + 让用户改用 `--excerpt`
- `--from-scan` 但 `marked-references.json` 不存在：提示用户先扫榜 + 标记
- 输出路径冲突：默认覆盖（除非 `--strict`）；备份旧 `_schema.json` 到 `.bak-<ts>`
```

- [ ] **Step 2: Sync + commit**

```bash
cp "/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/skills/webnovel-deconstruct/SKILL.md" "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/skills/"

cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/skills/webnovel-deconstruct/SKILL.md
git commit -m "feat(skill): webnovel-deconstruct SKILL.md — independent deconstruction entry

Multi-book per project. Default overwrite with backup. Same quality
gate as init Step 1.5. Never touches idea_bank.json or state.json."
```

**Self-Review:** File exists? All 7 sections present (Goal/调用时机/输入/执行/禁止/错误)? Both copies in sync?

---

## Task 5: chart-scan SKILL.md update + integrity test

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/SKILL.md`
- Modify: `.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py` (add 1 test)

- [ ] **Step 1: Write the failing test**

Add to `scripts/data_modules/tests/test_prompt_integrity.py`:

```python
def test_chart_scan_skill_mentions_marked_references():
    """chart-scan SKILL.md must mention marked-references.json + /webnovel-deconstruct."""
    text = _read_text(SKILLS_DIR / "webnovel-chart-scan" / "SKILL.md")
    assert "marked-references" in text or "marked_references" in text, (
        "chart-scan SKILL.md must mention marked-references manifest"
    )
    assert "/webnovel-deconstruct" in text or "webnovel-deconstruct" in text, (
        "chart-scan SKILL.md must mention deconstruct skill for handoff"
    )
```

- [ ] **Step 2: Run test, verify it fails**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_chart_scan_skill_mentions_marked_references -v 2>&1 | tail -8
```

Expected: FAIL — chart-scan SKILL.md has no mention of marked-references or deconstruct yet.

- [ ] **Step 3: Add marked-references section to chart-scan SKILL.md**

Open `/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/SKILL.md`. Find the end of the file (after the platform coverage table at the end). Append a new section:

```markdown

### 标记对标书（联动 /webnovel-deconstruct）

读完 `report.md` 后，可以告诉 Claude "标记对标：《A》《B》《C》"（书名列表）。Claude 会把标记清单写到 `./chart-scan/marked-references.json`。

之后运行 `/webnovel-deconstruct --from-scan` 会读取这个清单，批量拆解所有标记的书。

`marked-references.json` schema：

```json
{
  "schema_version": 1,
  "marked_at": "<ISO8601>",
  "from_scan": "./chart-scan/books.json",
  "references": [
    {"platform": "qidian", "title": "凡人修仙传", "author": "忘语", "category": "仙侠"}
  ]
}
```

查看当前标记清单：直接读 `./chart-scan/marked-references.json`（如果有）。

**注意**：chart-scan 自身**不会**自动写 `marked-references.json`——用户必须明确告诉 Claude "标记对标"。这是有意的设计：保持 chart-scan 的 hermetic 性质，避免自动行为带来的认知负担。
```

- [ ] **Step 4: Run test, verify green**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_chart_scan_skill_mentions_marked_references -v 2>&1 | tail -8
```

Expected: PASS.

- [ ] **Step 5: Sync + commit**

```bash
cp "/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/SKILL.md" "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/skills/webnovel-chart-scan/SKILL.md"
cp "/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py" "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/tests/"

cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/SKILL.md .claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py
git commit -m "feat(scan): chart-scan marked-references.json handoff to /webnovel-deconstruct

Adds 标记对标书 section. chart-scan stays hermetic (no auto-write);
user must explicitly mark. marked-references.json schema documented."
```

**Self-Review:** Test passes? Both copies in sync?

---

## Task 6: chart-scan `output.py` add `write_marked_references()` helper

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/scripts/output.py`

- [ ] **Step 1: Read current `output.py`**

Read `/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/scripts/output.py` to understand its style and existing helpers.

- [ ] **Step 2: Add `write_marked_references()` helper**

Append to the file (or near other write helpers):

```python
def write_marked_references(references: list[dict], output_dir: str | Path) -> Path:
    """Write chart-scan/marked-references.json with the schema from P1+P2 spec.

    References is a list of {platform, title, author?, category?}.
    Output path is output_dir / "marked-references.json".

    Returns the resolved path.
    """
    from datetime import datetime, timezone
    import sys

    # Import the validation helper from data_modules
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
    from data_modules.marked_references import validate_marked_references

    output_path = Path(output_dir).expanduser().resolve() / "marked-references.json"
    payload = {
        "schema_version": 1,
        "marked_at": datetime.now(timezone.utc).isoformat(),
        "from_scan": str((Path(output_dir) / "books.json").resolve()),
        "references": references,
    }
    validate_marked_references(payload)  # raises ValueError on schema mismatch
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
```

- [ ] **Step 3: Verify no regression in chart-scan tests**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py -v 2>&1 | tail -10
```

Expected: All P0-Full + P1+P2 tests pass.

- [ ] **Step 4: Sync + commit**

```bash
cp "/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/scripts/output.py" "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/skills/webnovel-chart-scan/scripts/output.py"

cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/scripts/output.py
git commit -m "feat(scan): write_marked_references() helper in chart-scan output.py

Pure helper — callable from SKILL.md flow. chart-scan itself still
doesn't auto-write (preserved hermetic behavior)."
```

**Self-Review:** Helper added? Existing tests still pass? Both copies in sync?

---

## Task 7: plan SKILL.md auto-discovery + integrity test

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-plan/SKILL.md`
- Modify: `.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py` (add 1 test)

- [ ] **Step 1: Write the failing test**

Add to `scripts/data_modules/tests/test_prompt_integrity.py`:

```python
def test_plan_auto_discovers_reference_research():
    """plan SKILL.md must scan .webnovel/reference_research/*/ for ALL trees, not just idea_bank pointer."""
    text = _read_text(SKILLS_DIR / "webnovel-plan" / "SKILL.md")
    assert ".webnovel/reference_research/" in text, "plan must reference the directory"
    # Must indicate multi-tree scanning (glob or directory walk)
    assert ("*" in text or "glob" in text.lower() or "扫描" in text or "scan" in text.lower()), (
        "plan must indicate it scans the directory for multiple trees"
    )
```

- [ ] **Step 2: Run test, verify it fails**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_plan_auto_discovers_reference_research -v 2>&1 | tail -8
```

Expected: FAIL — current plan SKILL.md (P0-Full) only mentions `idea_bank.json.reference_research_path`, no directory scan.

- [ ] **Step 3: Update plan SKILL.md consumption section**

Open `/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/skills/webnovel-plan/SKILL.md`. Find the existing "### 按需读取 reference_research 拆书产物" section (around line 100). Replace its body with:

```markdown
读完 `idea_bank.json` 后，按以下规则加载所有可用拆书产物：

1. **如果 `idea_bank.reference_research_path` 存在** → 该路径指向的树是**主对标书**（primary）
2. **扫描 `.webnovel/reference_research/*/`**（glob 模式）：
   - 每个子目录都是一本书的拆书树（`<book-safe>/`）
   - 加载所有树的 `_schema.json` + `report.md`（节选）+ `do_not_copy.md` + `canon_contamination_warnings.md`
   - 多本书作为**次要参考**（secondary）参与章节级对齐
3. **去重**：相同 `<book-safe>` 不重复加载
4. **主从优先级**：主对标书（来自 init §1.5）的字段优先；次要参考（来自 standalone deconstruct）补充多样性

在卷纲 / 章纲阶段使用：

- `narrative_function` + `boundary_reason` → 对齐卷级结构（主对标书优先）
- `emotion_curve` + `satisfaction_point` → 章节级节奏参考（多本书交叉验证）
- `foreshadowing` → 跨章连续性约束
- `gains_costs` + `character_changes` → 主角缺陷兑现提醒

如果 `reference_research_path` 字段缺失（老项目 / 用户未提供参考书），按历史行为运行，仅依赖 directory scan。如果目录也不存在，跳过 reference 加载。

如果路径指向不存在的目录，输出提示 "reference_research missing: <path>"，继续运行。
```

- [ ] **Step 4: Run test, verify green**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_plan_auto_discovers_reference_research -v 2>&1 | tail -8
```

Expected: PASS.

- [ ] **Step 5: Sync + commit**

```bash
cp "/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/skills/webnovel-plan/SKILL.md" "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/skills/webnovel-plan/SKILL.md"
cp "/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py" "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/tests/"

cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/skills/webnovel-plan/SKILL.md .claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py
git commit -m "feat(plan): auto-discover .webnovel/reference_research/*/ trees

Previously plan only loaded idea_bank.reference_research_path (single
pointer from init). Now scans the directory for ALL trees — including
those created by standalone /webnovel-deconstruct. Primary vs secondary
book distinction preserved."
```

**Self-Review:** Test passes? Both copies in sync?

---

## Task 8: End-to-end manual smoke

**Files:** (none — verification only)

- [ ] **Step 1: Verify `/webnovel-deconstruct` slash command works**

```bash
# Mock a single book deconstruct
mkdir -p /tmp/p12_smoke_book
mkdir -p /tmp/p12_chart_scan

# Create a minimal schema (as if Step 1.5 produced it)
cat > /tmp/p12_schema.json << 'EOF'
{
  "source": {"reference_title": "《凡人修仙传》", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.9},
  "reader_promise": "凡人逆袭修仙",
  "opening_hook_patterns": ["开局废灵根检测"],
  "cool_point_loops": ["宗门阶梯式升级"],
  "protagonist_patterns": "谨慎实用主义",
  "antagonist_pressure_patterns": "宗门内斗",
  "pacing_notes": "每5章小高潮",
  "narrative_function": "升级流",
  "boundary_reason": {"first_arc_start": 1, "first_arc_end": 50, "reason": "入门期"},
  "protagonist_action_chain": [{"trigger": "灵根检测失败", "action": "坚持修炼", "result": "意外觉醒"}],
  "emotion_curve": [{"chapter": 1, "intensity": 0.7, "label": "压抑"}],
  "satisfaction_point": ["灵根检测反转"],
  "foreshadowing": [{"setup_chapter": 1, "payoff_chapter_estimate": 50, "content": "神秘小瓶"}],
  "gains_costs": [{"chapter": 1, "gain": "觉醒", "cost": "孤立", "category": "认知"}],
  "character_changes": [{"chapter": 1, "character": "韩立", "before": "平庸", "after": "觉醒"}],
  "borrowable_structures": ["宗门阶梯式"],
  "differentiation_requirements": "不复制韩立人设",
  "init_candidates": {"one_liner": "x", "anti_trope": "x", "hard_constraints": [], "protagonist_flaw": "x", "antagonist_mirror": "x", "opening_hook": "x"},
  "do_not_copy": ["韩立人设"],
  "canon_contamination_warnings": ["原作人物名:韩立"],
  "quality": {"passed": true, "confidence": 0.9, "coverage": 0.85}
}
EOF

# Build tree directly (simulating what /webnovel-deconstruct would do)
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -c "
import sys, json, pathlib
sys.path.insert(0, '.')
from init_reference_tree import build_reference_tree
schema = json.loads(pathlib.Path('/tmp/p12_schema.json').read_text(encoding='utf-8'))
tree = build_reference_tree(pathlib.Path('/tmp/p12_smoke_book'), schema, '《凡人修仙传》')
print('Tree:', tree)
"

# Verify
ls /tmp/p12_smoke_book/.webnovel/reference_research/fanren-xiuxian-chuan/
```

Expected: All 5 files created at the right path.

- [ ] **Step 2: Verify `idea_bank.json` NOT created**

```bash
ls /tmp/p12_smoke_book/.webnovel/idea_bank.json 2>&1
```

Expected: No such file (P2 doesn't touch idea_bank).

- [ ] **Step 3: Verify chart-scan marked-references round-trip**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -c "
import sys, json, pathlib
sys.path.insert(0, '.')
from marked_references import write_marked_references, load_marked_references
payload = {
    'schema_version': 1,
    'marked_at': '2026-08-16T12:34:56Z',
    'references': [
        {'platform': 'qidian', 'title': '凡人修仙传', 'author': '忘语'},
        {'platform': 'fanqie', 'title': '完美世界'},
    ]
}
path = write_marked_references(payload, pathlib.Path('/tmp/p12_chart_scan'))
print('Wrote:', path)
loaded = load_marked_references(path)
print('Loaded references count:', len(loaded['references']))
"

ls /tmp/p12_chart_scan/marked-references.json
cat /tmp/p12_chart_scan/marked-references.json
```

Expected: File written and loaded successfully, 2 references.

- [ ] **Step 4: Verify plan SKILL.md text mentions auto-discovery**

```bash
grep -A 2 "reference_research/\*" /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/skills/webnovel-plan/SKILL.md | head -5
```

Expected: At least one line mentioning `reference_research/*` glob pattern.

- [ ] **Step 5: Run the full test suite one final time**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest \
  data_modules/tests/test_prompt_integrity.py::test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate \
  data_modules/tests/test_prompt_integrity.py::test_deconstruction_agent_schema_extension \
  data_modules/tests/test_prompt_integrity.py::test_plan_reads_reference_research_when_pointer_set \
  data_modules/tests/test_prompt_integrity.py::test_deconstruction_agent_is_not_init_only \
  data_modules/tests/test_prompt_integrity.py::test_plan_auto_discovers_reference_research \
  data_modules/tests/test_prompt_integrity.py::test_chart_scan_skill_mentions_marked_references \
  data_modules/tests/test_marked_references.py \
  data_modules/tests/test_init_reference_tree.py \
  data_modules/tests/test_init_idea_bank.py \
  2>&1 | tail -10
```

Expected: All tests pass (1 + 1 + 1 + 1 + 1 + 1 + 5 + 12 + 10 = 31 tests, including all P0-Full regression).

- [ ] **Step 6: Cleanup**

```bash
rm -rf /tmp/p12_smoke_book /tmp/p12_chart_scan /tmp/p12_schema.json
```

- [ ] **Step 7: Report results**

Print a summary:
- 8 commits expected (1 per task)
- 8 new tests: 1 (agent multi-caller) + 5 (marked_references) + 1 (plan auto-discovery) + 1 (chart-scan mentions) = 8
- All P0-Full tests still pass (no regression)
- Manual smoke confirms P2 doesn't touch idea_bank

## Acceptance Criteria Checklist

- [ ] `commands/deconstruct.md` exists
- [ ] `skills/webnovel-deconstruct/SKILL.md` exists with 7 sections
- [ ] `deconstruction-agent.md` description mentions both `/webnovel-init` and `/webnovel-deconstruct`
- [ ] `chart-scan/SKILL.md` mentions `marked-references.json` and `/webnovel-deconstruct`
- [ ] `chart-scan/scripts/output.py` has `write_marked_references()` helper
- [ ] `scripts/data_modules/marked_references.py` exists with read/write/validate
- [ ] `plan/SKILL.md` mentions scanning `.webnovel/reference_research/*/`
- [ ] All 8 new tests pass (T1-T4 from spec)
- [ ] All P0-Full tests still pass (31 regression tests)
- [ ] Manual smoke succeeds end-to-end
- [ ] No `webnovel.py deconstruct` CLI subcommand (per non-goal)
- [ ] `idea_bank.json` NOT touched by P2 (verified by smoke)
- [ ] 8 commits on main, both copies in sync

## Out-of-Scope Reminder (do NOT implement here)

- **P3**: `webnovel-write` / `webnovel-review` consumption of `reference_research`
- **P4**: Full-text deconstruction beyond golden-three chapters
- **`webnovel.py deconstruct` CLI**: explicitly deferred per non-goal
- **English book titles**: separate spec if needed
- **Multi-user shared `reference_research/`**: separate spec if needed

## Self-Review Notes

- **Spec coverage**: D1→Task 1; D2→Task 4; D3→Task 2; D4→Tasks 5+6; D5→Task 7; D6 (file structure)→all tasks; D7 (out-of-scope)→"Out-of-Scope Reminder" section; T1→Task 2; T2→Task 3; T3→Task 7; T4→Task 5; T5→Task 8.
- **Placeholder scan**: no "TBD" / "TODO" / "implement later". Every code block is complete and runnable.
- **Type consistency**: `marked_references.py` `validate_marked_references` signature `(data: dict) -> dict` consistent across Task 3 tests and Task 6 helper. `write_marked_references(payload: dict, path: Path) -> Path` consistent.
- **Risk acknowledgment**: agent description change is the only body-adjacent risk; covered by T1 + Task 2 explicit test. Plan auto-discovery is the largest behavioral change; covered by T3 + Task 7 test.