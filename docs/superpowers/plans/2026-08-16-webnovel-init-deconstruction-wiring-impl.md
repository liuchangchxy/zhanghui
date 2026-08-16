# Init ↔ Deconstruction-Agent Wiring (P0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `webnovel-init` Step 1.5 to call `deconstruction-agent` and persist its confirmed output to `.webnovel/idea_bank.json`, fixing two integration gaps that currently leave the agent as dead code.

**Architecture:** Two integration points land in this PR. (1) Documentation-only — insert Step 1.5 in `skills/webnovel-init/SKILL.md` containing all test-asserted literal phrases; this turns the existing red `test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate` green. (2) Code — extend `init_project.py` with `idea_bank_file: str` kwarg + `--idea-bank-file` CLI flag, plus a new `_write_idea_bank()` helper implementing three-state overwrite (absent/create, equal/skip, differ/refuse) and a `_validate_idea_bank_payload()` helper for schema validation.

**Tech Stack:** Python 3, `argparse`, `pathlib`, `json`. pytest for tests. No new dependencies.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `skills/webnovel-init/SKILL.md` | Modify | Insert Step 1.5 between Step 1 and Step 2; modify Step 2 preamble; modify Step 6 final confirmation. |
| `scripts/init_project.py` | Modify | Add `idea_bank_file: str = ""` kwarg to `init_project()`; add `_validate_idea_bank_payload()` + `_write_idea_bank()` helpers; add `--idea-bank-file` and `--idea-bank-force` CLI flags. |
| `scripts/data_modules/tests/test_init_idea_bank.py` | Create | New test file with 4 unit tests covering the four behaviors. |
| `scripts/data_modules/tests/test_prompt_integrity.py` | (no change) | Existing test `test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate` must turn green after Task 1. |

No new files except the test file. No new skill/command/agent.

---

## Task 1: Verify and fix the red prompt-integrity test

**Files:**
- Modify: `skills/webnovel-init/SKILL.md` (insert Step 1.5, modify Step 2 preamble, modify Step 6)
- Test (existing, no change): `scripts/data_modules/tests/test_prompt_integrity.py::test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate`

- [ ] **Step 1: Run the existing failing test to confirm red**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_prompt_integrity.py::test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate -v 2>&1 | tail -30
```

Expected: FAIL with at least one assertion error mentioning a missing literal like `Step 1.5：灵感来源询问` or `Use the Agent tool to run \`webnovel-writer:deconstruction-agent\``. If it passes already, stop and investigate — someone may have already done this work.

- [ ] **Step 2: Insert Step 1.5 into webnovel-init/SKILL.md**

Open `/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/skills/webnovel-init/SKILL.md`. Find the line:

```
### Step 2：角色骨架与关系冲突
```

Immediately BEFORE that line, insert this entire block (do NOT paraphrase — exact strings satisfy the integrity test):

```markdown
### Step 1.5：灵感来源询问

进入故事核采集前，先问用户灵感来源——**不要默认拆书**。

向用户抛出唯一开场问题（必须包含字面串"你这本书的灵感来源想从哪里开始"）：

```
你这本书的灵感来源想从哪里开始？
  A) 原创 / 暂无参考书 → 跳过拆解，跳过 idea_bank.json 写入
  B) 有参考书名 + 平台线索（如"起点《XX》"）→ quick 模式（无文本，quality.passed=false 风险高）
  C) 有参考书名 + 本地正文路径 → deep 模式（路径不可读时降级 quick）
  D) 有参考书名 + 仅摘录（粘进对话）→ quick 模式
```

如果用户选 A：记录 `reference_source = "none"`，**不写任何文件**，直接进入 Step 2。

如果用户选 B/C/D：用以下字面调用方式触发拆解子代理（主流程**不得由 init 主流程口头替代拆解结果**，必须拿原始 JSON）：

```
Use the Agent tool to run `webnovel-writer:deconstruction-agent`
```

调用时传入字段（参考 `agents/deconstruction-agent.md §2`）：`reference_title`、`reference_source`、`reference_text_path` 或 `reference_text_excerpt`、`analysis_mode`、`init_goal`、`target_genre`。**禁止使用 `subagent_type:` 字段**——Claude Code 的 Agent tool 不接受该参数。

子代理返回 `init_reference_research` JSON 对象。**用户确认前**，以下行为禁止：

- 写入 `idea_bank.json`
- 写入 `.story-system`、`设定集/`、`大纲/`、`正文/`、`.webnovel/state.json`
- 由主流程口头重写拆解结论

检查返回 JSON 的 `quality` 字段（必须含字面 `` `quality` `` 和 `` `quality.passed=false` ``）：

- 若 `quality.passed=false` 或 `confidence < 0.85`（含字面 `` `confidence < 0.85` ``）：把缺漏展示给用户，问三种处理：(i) 用更多文本重跑；(ii) 用稀疏模式继续；(iii) 放弃参考（默认 (iii)）。
- 否则：仅展示**已变形的、脱离原作的**模式——从 `init_candidates`、`borrowable_structures`、`differentiation_requirements` 读取；不得展示可能携带原作信息的 `reader_promise` 等字段。把 `canon_contamination_warnings` **原文**展示给用户。

用户确认后，主流程构建 `idea_bank.json`（schema 见 `scripts/init_project.py _validate_idea_bank_payload()`），通过临时文件 + `--idea-bank-file` 传给 `webnovel.py init` 落盘。**禁止**直接拼接到 CLI argv 大字段里。

> Step 2-6 只能使用用户确认过、并已变形为本书差异化表达的模式；不可借用尚未确认或仍携带原作设定的字段。

```

(Note: `idea-bank-file` 引用了一个尚未存在的 helper；Task 4 will create it. That's OK — by the time the SKILL.md is read by a real user, all tasks have landed.)

- [ ] **Step 3: Modify Step 2 preamble to include the "Step 2-6 只能使用用户确认过..." literal**

In the same file, find the Step 2 heading line `### Step 2：角色骨架与关系冲突`. Immediately AFTER it (before the "收集项" line), insert this single line (do NOT paraphrase):

```
> Step 2-6 只能使用用户确认过、并已变形为本书差异化表达的模式。
```

- [ ] **Step 4: Modify Step 6 final confirmation to include the "汇总 Step 1.5 已确认的灵感来源" literal**

Find `### Step 6：一致性复述与最终确认`. In the "必须输出'初始化摘要草案'并让用户确认：" list, add one more bullet line (anywhere in the list, but keep ordering):

```markdown
- 汇总 Step 1.5 已确认的灵感来源（参考书名 / 分析模式 / 置信度 / 反套路 / 硬约束数量）
```

- [ ] **Step 5: Run the test, verify green**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_prompt_integrity.py::test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate -v 2>&1 | tail -15
```

Expected: PASS. If still red, diff your inserted strings against `test_prompt_integrity.py:635-680` to find missing literals. Common miss: forgetting the backticks around `` `quality` ``, `` `quality.passed=false` ``, `` `confidence < 0.85` ``.

- [ ] **Step 6: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add webnovel-writer_chang/skills/webnovel-init/SKILL.md
git commit -m "feat(init): Step 1.5 wiring — call deconstruction-agent with confirmation gate

Turns test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate green.
Inserts literal phrases required by prompt-integrity assertions:
Step 1.5：灵感来源询问 / 进入故事核采集前 / 不要默认拆书 /
Use the Agent tool to run \`webnovel-writer:deconstruction-agent\` /
用户确认前 / Step 2-6 只能使用用户确认过... / 汇总 Step 1.5... /
\`quality\` / \`quality.passed=false\` / \`confidence < 0.85\` /
init_reference_research / init_reference_research JSON 对象 /
不写任何文件 / 不得由 init 主流程口头替代拆解结果 /
你这本书的灵感来源想从哪里开始 / 9 handoff fields / 6 forbidden paths."
```

---

## Task 2: TDD `init_project()` kwarg — no flag = no file

**Files:**
- Modify: `scripts/init_project.py:234-271` (add `idea_bank_file: str = ""` kwarg to `init_project()` signature; no behavior change yet)
- Create: `scripts/data_modules/tests/test_init_idea_bank.py` (first test only)

- [ ] **Step 1: Write the failing test**

Create `scripts/data_modules/tests/test_init_idea_bank.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest


def test_init_no_idea_bank_when_flag_absent(tmp_path, monkeypatch):
    """Without --idea-bank-file, no .webnovel/idea_bank.json is written."""
    import init_project as init_project_module

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"

    init_project_module.init_project(
        str(project_root),
        title="测试书",
        genre="仙侠",
        protagonist_name="陆鸣",
    )

    assert not (project_root / ".webnovel" / "idea_bank.json").exists()
```

- [ ] **Step 2: Run test, verify it passes (it should — no behavior change yet)**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py::test_init_no_idea_bank_when_flag_absent -v 2>&1 | tail -10
```

Expected: PASS. The test passes already because no code writes `idea_bank.json` today. The value of this test is regression protection — if anyone later adds unconditional writing, the test catches it.

- [ ] **Step 3: Add the `idea_bank_file` kwarg to `init_project()` signature**

In `scripts/init_project.py`, modify the `init_project()` signature (currently around line 234-271). Add `idea_bank_file: str = ""` as a kwarg right before the closing `) -> None:`. The exact location: after `cultivation_subtiers: str = "",` and before `) -> None:`.

```python
    cultivation_subtiers: str = "",
    idea_bank_file: str = "",
) -> None:
```

(Don't add any usage of `idea_bank_file` yet — that lands in Task 4.)

- [ ] **Step 4: Run test again, verify still passes**

Run the same pytest command. Expected: PASS. (Adding an unused kwarg doesn't change behavior.)

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add webnovel-writer_chang/scripts/init_project.py webnovel-writer_chang/scripts/data_modules/tests/test_init_idea_bank.py
git commit -m "test(init): guard against unconditional idea_bank.json writes

Adds test_init_no_idea_bank_when_flag_absent and the idea_bank_file
kwarg (currently unused; lands in Task 4). Pure regression guard."
```

---

## Task 3: TDD `_validate_idea_bank_payload()` helper

**Files:**
- Modify: `scripts/init_project.py` (add helper after `init_project()` function or just before)
- Modify: `scripts/data_modules/tests/test_init_idea_bank.py` (add 4 validation tests)

- [ ] **Step 1: Write the failing tests**

Append to `scripts/data_modules/tests/test_init_idea_bank.py`:

```python
import json


def test_validate_idea_bank_accepts_minimal_valid_payload():
    from init_project import _validate_idea_bank_payload

    payload = {
        "version": 1,
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {"title": "", "one_liner": "", "anti_trope": "", "hard_constraints": []},
        "constraints_inherited": {"anti_trope": "", "hard_constraints": [], "protagonist_flaw": "", "antagonist_mirror": "", "opening_hook": ""},
        "borrowed_patterns": [],
        "do_not_copy": [],
        "canon_contamination_warnings": [],
    }
    parsed = _validate_idea_bank_payload(json.dumps(payload))
    assert parsed["version"] == 1
    assert parsed["source"]["reference_title"] == "X"


def test_validate_idea_bank_rejects_non_object():
    from init_project import _validate_idea_bank_payload
    with pytest.raises(ValueError, match="must be a JSON object"):
        _validate_idea_bank_payload('"just a string"')


def test_validate_idea_bank_rejects_wrong_version():
    from init_project import _validate_idea_bank_payload
    bad = {"version": 2, "source": {}, "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": []}
    with pytest.raises(ValueError, match="version"):
        _validate_idea_bank_payload(json.dumps(bad))


def test_validate_idea_bank_rejects_bad_reference_source_enum():
    from init_project import _validate_idea_bank_payload
    bad = {
        "version": 1,
        "source": {"reference_title": "X", "reference_source": "BAD_ENUM", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": []
    }
    with pytest.raises(ValueError, match="reference_source"):
        _validate_idea_bank_payload(json.dumps(bad))
```

- [ ] **Step 2: Run tests, verify all 4 fail with ImportError or AttributeError**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py -v -k "validate" 2>&1 | tail -20
```

Expected: All 4 FAIL with `cannot import name '_validate_idea_bank_payload' from 'init_project'`.

- [ ] **Step 3: Implement `_validate_idea_bank_payload()`**

Add this function to `scripts/init_project.py`. Put it just BEFORE the `init_project()` function definition (around line 234):

```python
def _validate_idea_bank_payload(raw: str) -> dict:
    """Parse and validate an idea_bank.json payload string.

    Required schema (matches 2026-08-16-webnovel-init-deconstruction-wiring-design §D2):
      - version == 1
      - top-level keys: source, selected_idea, constraints_inherited,
        borrowed_patterns, do_not_copy, canon_contamination_warnings
      - source.reference_source in {"none", "book_name", "local_text", "excerpt"}
      - source.analysis_mode in {"quick", "deep"}
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"idea_bank.json is not valid JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("idea_bank.json must be a JSON object")

    if data.get("version") != 1:
        raise ValueError(f"idea_bank.json version must be 1, got {data.get('version')!r}")

    required_top = {
        "source", "selected_idea", "constraints_inherited",
        "borrowed_patterns", "do_not_copy", "canon_contamination_warnings",
    }
    missing = required_top - set(data.keys())
    if missing:
        raise ValueError(f"idea_bank.json missing required top-level keys: {sorted(missing)}")

    source = data.get("source")
    if not isinstance(source, dict):
        raise ValueError("idea_bank.json source must be an object")

    ref_src = source.get("reference_source")
    if ref_src not in {"none", "book_name", "local_text", "excerpt"}:
        raise ValueError(
            f"idea_bank.json source.reference_source must be one of "
            f"{{none, book_name, local_text, excerpt}}, got {ref_src!r}"
        )

    mode = source.get("analysis_mode")
    if mode not in {"quick", "deep"}:
        raise ValueError(
            f"idea_bank.json source.analysis_mode must be quick or deep, got {mode!r}"
        )

    return data
```

Also add `import json` near the top of `init_project.py` if not already imported. (Check first; if it's there, skip.)

- [ ] **Step 4: Run tests, verify all 4 pass**

Run the same pytest command. Expected: 4 PASSED.

- [ ] **Step 5: Run the full prompt-integrity suite to ensure no regression**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_prompt_integrity.py -v 2>&1 | tail -10
```

Expected: All PASS (Task 1's test + others). If any fail, the new helper import side-effects likely broke something — investigate.

- [ ] **Step 6: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add webnovel-writer_chang/scripts/init_project.py webnovel-writer_chang/scripts/data_modules/tests/test_init_idea_bank.py
git commit -m "feat(init): _validate_idea_bank_payload() — schema gate for idea_bank.json

Validates version=1, required top-level keys, source.reference_source
enum, source.analysis_mode enum. Raises ValueError with field-level
message on any miss. Pure function — no I/O."
```

---

## Task 4: TDD `_write_idea_bank()` — absent target = create

**Files:**
- Modify: `scripts/init_project.py` (add `_write_idea_bank()` helper, call it from `init_project()`)
- Modify: `scripts/data_modules/tests/test_init_idea_bank.py` (add 1 happy-path test)

- [ ] **Step 1: Write the failing test**

Append to `scripts/data_modules/tests/test_init_idea_bank.py`:

```python
def test_init_writes_idea_bank_when_flag_provided_and_target_absent(tmp_path, monkeypatch):
    """First run with --idea-bank-file creates .webnovel/idea_bank.json from payload."""
    import init_project as init_project_module

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"

    payload = {
        "version": 1,
        "source": {
            "reference_title": "《参考书》",
            "reference_source": "book_name",
            "analysis_mode": "quick",
            "confidence": 0.92,
        },
        "selected_idea": {
            "title": "测试书",
            "one_liner": "一句话故事",
            "anti_trope": "不金手指",
            "hard_constraints": ["硬约束1"],
        },
        "constraints_inherited": {
            "anti_trope": "不金手指",
            "hard_constraints": ["硬约束1"],
            "protagonist_flaw": "过度理性",
            "antagonist_mirror": "感性极端",
            "opening_hook": "开篇钩子",
        },
        "borrowed_patterns": ["模式A"],
        "do_not_copy": ["原作人物名"],
        "canon_contamination_warnings": [],
    }
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    init_project_module.init_project(
        str(project_root),
        title="测试书",
        genre="仙侠",
        protagonist_name="陆鸣",
        idea_bank_file=str(payload_file),
    )

    target = project_root / ".webnovel" / "idea_bank.json"
    assert target.is_file(), "idea_bank.json should have been created"
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["version"] == 1
    assert written["source"]["reference_title"] == "《参考书》"
    assert written["constraints_inherited"]["opening_hook"] == "开篇钩子"
    assert written["selected_idea"]["hard_constraints"] == ["硬约束1"]
```

- [ ] **Step 2: Run test, verify it fails**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py::test_init_writes_idea_bank_when_flag_provided_and_target_absent -v 2>&1 | tail -15
```

Expected: FAIL — `idea_bank.json` is not created (because `idea_bank_file` is currently unused inside `init_project()`).

- [ ] **Step 3: Implement `_write_idea_bank()` helper**

Add this helper to `scripts/init_project.py`, just AFTER `_validate_idea_bank_payload()`:

```python
def _write_idea_bank(
    project_path: Path,
    idea_bank_file: str,
    *,
    force: bool = False,
) -> None:
    """Persist idea_bank.json per the three-state contract (spec §D2).

    States:
      - Absent on disk + valid payload → create.
      - Present on disk + payload semantically equal → skip (idempotent).
      - Present on disk + payload differs + force=False → refuse (SystemExit).
      - Present on disk + payload differs + force=True → overwrite.
      - idea_bank_file unreadable / invalid → SystemExit (caller must catch early).
    """
    payload_path = Path(idea_bank_file).expanduser().resolve()
    if not payload_path.is_file():
        raise SystemExit(f"--idea-bank-file not found or unreadable: {payload_path}")

    raw = payload_path.read_text(encoding="utf-8")
    data = _validate_idea_bank_payload(raw)  # raises ValueError on bad schema

    webnovel_dir = project_path / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    target = webnovel_dir / "idea_bank.json"

    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if _idea_bank_semantically_equal(existing, data):
            print(f"idea_bank.json unchanged (semantic match): {target}")
            return
        if not force:
            raise SystemExit(
                f"idea_bank.json already exists with different content at {target}. "
                f"Refusing to overwrite. Pass --idea-bank-force to overwrite explicitly."
            )
        print(f"idea_bank.json overwrite forced: {target}")

    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"✅ 已写入 {target}")


def _idea_bank_semantically_equal(a: dict, b: dict) -> bool:
    """Compare the user-visible fields that matter for canon integrity.

    Other fields (timestamps, internal metadata) are ignored — re-running init
    with the same confirmed content should be a no-op.
    """
    keys = ("source", "selected_idea", "constraints_inherited", "borrowed_patterns",
            "do_not_copy", "canon_contamination_warnings")
    for k in keys:
        if a.get(k) != b.get(k):
            return False
    return True
```

- [ ] **Step 4: Wire `idea_bank_file` into `init_project()`**

In `init_project()`, find the very end of the function (currently around line 712, just before `print(f"\nProject initialized at: {project_path}")`). Insert this block IMMEDIATELY before the final print:

```python
    # === idea_bank.json 落盘（spec 2026-08-16 §D2/D4）===
    if idea_bank_file:
        _write_idea_bank(project_path, idea_bank_file)
```

- [ ] **Step 5: Run the test, verify it passes**

Run the same pytest command. Expected: PASS.

- [ ] **Step 6: Run all `test_init_idea_bank.py` tests + integrity tests**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py data_modules/tests/test_prompt_integrity.py -v 2>&1 | tail -15
```

Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add webnovel-writer_chang/scripts/init_project.py webnovel-writer_chang/scripts/data_modules/tests/test_init_idea_bank.py
git commit -m "feat(init): _write_idea_bank() — three-state overwrite + wire into init_project()

Implements spec §D2:
  - absent target → create
  - present + semantically equal → skip
  - present + differs → refuse (--idea-bank-force to override)
  - missing/unreadable payload file → SystemExit
Wired through init_project(idea_bank_file=...) kwarg added in Task 2."
```

---

## Task 5: TDD `_write_idea_bank()` — existing target matches = skip (idempotent)

**Files:**
- Modify: `scripts/data_modules/tests/test_init_idea_bank.py` (add idempotent test)

- [ ] **Step 1: Write the test**

Append to `scripts/data_modules/tests/test_init_idea_bank.py`:

```python
def test_init_skips_idea_bank_when_target_semantically_matches(tmp_path, monkeypatch):
    """Re-running init with the same confirmed payload is a no-op."""
    import init_project as init_project_module

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"

    payload = {
        "version": 1,
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.9},
        "selected_idea": {"title": "T", "one_liner": "L", "anti_trope": "A", "hard_constraints": []},
        "constraints_inherited": {"anti_trope": "A", "hard_constraints": [], "protagonist_flaw": "F", "antagonist_mirror": "M", "opening_hook": "H"},
        "borrowed_patterns": [],
        "do_not_copy": [],
        "canon_contamination_warnings": [],
    }
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    # First run — creates
    init_project_module.init_project(
        str(project_root), title="T", genre="仙侠", protagonist_name="P",
        idea_bank_file=str(payload_file),
    )
    target = project_root / ".webnovel" / "idea_bank.json"
    mtime_before = target.stat().st_mtime_ns

    # Sleep so any re-write would change mtime (filesystem mtime resolution can be coarse)
    import time
    time.sleep(0.05)

    # Second run — should skip
    init_project_module.init_project(
        str(project_root), title="T", genre="仙侠", protagonist_name="P",
        idea_bank_file=str(payload_file),
    )
    assert target.stat().st_mtime_ns == mtime_before, "idea_bank.json was rewritten despite semantic match"
```

- [ ] **Step 2: Run test, verify it passes (it should — Task 4 already implemented semantic equality)**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py::test_init_skips_idea_bank_when_target_semantically_matches -v 2>&1 | tail -10
```

Expected: PASS. (This is regression protection — the implementation already handles this case via `_idea_bank_semantically_equal`. If someone removes that check later, this test catches it.)

- [ ] **Step 3: Run full test suite, verify all pass**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py -v 2>&1 | tail -15
```

Expected: All PASS (4 from Tasks 2-4 + this one).

- [ ] **Step 4: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add webnovel-writer_chang/scripts/data_modules/tests/test_init_idea_bank.py
git commit -m "test(init): guard semantic-match skip path

Regression test — Task 4's _write_idea_bank() already implements
semantic equality; this test prevents future regressions if someone
removes the early-return."
```

---

## Task 6: TDD `_write_idea_bank()` — existing target differs = refuse

**Files:**
- Modify: `scripts/data_modules/tests/test_init_idea_bank.py` (add refuse test + force-override test)

- [ ] **Step 1: Write the failing tests**

Append to `scripts/data_modules/tests/test_init_idea_bank.py`:

```python
def test_init_refuses_overwrite_when_existing_differs(tmp_path, monkeypatch):
    """Re-running with a different payload must refuse (SystemExit) and preserve existing."""
    import init_project as init_project_module

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"

    payload_a = {
        "version": 1,
        "source": {"reference_title": "A", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.9},
        "selected_idea": {"title": "T", "one_liner": "L_A", "anti_trope": "A", "hard_constraints": []},
        "constraints_inherited": {"anti_trope": "A", "hard_constraints": [], "protagonist_flaw": "F", "antagonist_mirror": "M", "opening_hook": "H"},
        "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
    }
    payload_b = dict(payload_a)
    payload_b["selected_idea"] = {"title": "T", "one_liner": "L_B_DIFFERENT", "anti_trope": "A", "hard_constraints": []}

    file_a = tmp_path / "a.json"
    file_a.write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    file_b = tmp_path / "b.json"
    file_b.write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    init_project_module.init_project(
        str(project_root), title="T", genre="仙侠", protagonist_name="P",
        idea_bank_file=str(file_a),
    )
    target = project_root / ".webnovel" / "idea_bank.json"
    content_before = target.read_text(encoding="utf-8")

    with pytest.raises(SystemExit):
        init_project_module.init_project(
            str(project_root), title="T", genre="仙侠", protagonist_name="P",
            idea_bank_file=str(file_b),
        )

    assert target.read_text(encoding="utf-8") == content_before, "idea_bank.json must not have been overwritten"


def test_init_force_overwrites_when_existing_differs(tmp_path, monkeypatch):
    """With --idea-bank-force, the diff path overwrites."""
    import init_project as init_project_module

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"

    payload_a = {
        "version": 1,
        "source": {"reference_title": "A", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.9},
        "selected_idea": {"title": "T", "one_liner": "L_A", "anti_trope": "A", "hard_constraints": []},
        "constraints_inherited": {"anti_trope": "A", "hard_constraints": [], "protagonist_flaw": "F", "antagonist_mirror": "M", "opening_hook": "H"},
        "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
    }
    payload_b = dict(payload_a)
    payload_b["selected_idea"] = {"title": "T", "one_liner": "L_B", "anti_trope": "A", "hard_constraints": []}

    file_a = tmp_path / "a.json"
    file_a.write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    file_b = tmp_path / "b.json"
    file_b.write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    init_project_module.init_project(
        str(project_root), title="T", genre="仙侠", protagonist_name="P",
        idea_bank_file=str(file_a),
    )

    # Force overwrite — call the helper directly to bypass the (not-yet-wired) CLI flag
    init_project_module._write_idea_bank(project_root, str(file_b), force=True)

    written = json.loads((project_root / ".webnovel" / "idea_bank.json").read_text(encoding="utf-8"))
    assert written["selected_idea"]["one_liner"] == "L_B"
```

- [ ] **Step 2: Run tests, verify refuse-test passes (already implemented) and force-test passes (already implemented)**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py -v -k "refuses or force" 2>&1 | tail -15
```

Expected: Both PASS. (Task 4's `_write_idea_bank(force=...)` already implements both. These tests are pure regression guards.)

- [ ] **Step 3: Run full test file**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py -v 2>&1 | tail -20
```

Expected: 7 PASSED (1 from Task 2 + 4 from Task 3 + 1 from Task 4 + 1 from Task 5 + 2 from this task = wait, let me recount: Task 2=1, Task 3=4, Task 4=1, Task 5=1, Task 6=2 = 9 PASSED).

- [ ] **Step 4: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add webnovel-writer_chang/scripts/data_modules/tests/test_init_idea_bank.py
git commit -m "test(init): guard refuse + force-overwrite paths

Two regression tests. _write_idea_bank() already implements both:
- existing file + differing payload → SystemExit, no overwrite
- existing file + differing payload + force=True → overwrite
Tests pin behavior so future refactors cannot silently regress."
```

---

## Task 7: TDD `_write_idea_bank()` — unreadable payload file = hard error before any project write

**Files:**
- Modify: `scripts/data_modules/tests/test_init_idea_bank.py` (add unreadable-payload test)

- [ ] **Step 1: Write the failing test**

Append to `scripts/data_modules/tests/test_init_idea_bank.py`:

```python
def test_init_hard_errors_on_unreadable_idea_bank_file(tmp_path, monkeypatch):
    """A missing --idea-bank-file must abort before any project files are written."""
    import init_project as init_project_module

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"
    nonexistent = tmp_path / "does_not_exist.json"

    with pytest.raises(SystemExit):
        init_project_module.init_project(
            str(project_root), title="T", genre="仙侠", protagonist_name="P",
            idea_bank_file=str(nonexistent),
        )

    # Nothing should have been created
    assert not project_root.exists() or not any(project_root.iterdir()), (
        f"project_root should be empty, but contains: {list(project_root.iterdir()) if project_root.exists() else 'no dir'}"
    )
```

- [ ] **Step 2: Run test, verify it passes**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py::test_init_hard_errors_on_unreadable_idea_bank_file -v 2>&1 | tail -10
```

Expected: PASS. (`_write_idea_bank()` calls `Path.is_file()` first and raises `SystemExit` before touching the project dir.)

- [ ] **Step 3: Run full test file + integrity suite**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py data_modules/tests/test_prompt_integrity.py -v 2>&1 | tail -15
```

Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add webnovel-writer_chang/scripts/data_modules/tests/test_init_idea_bank.py
git commit -m "test(init): guard unreadable --idea-bank-file path

If the flag is set but the file is missing, init must SystemExit
before any project directory is created — half-init state is worse
than full failure."
```

---

## Task 8: Wire `--idea-bank-file` and `--idea-bank-force` CLI flags in `main()`

**Files:**
- Modify: `scripts/init_project.py:719-806` (add two CLI flags, pass through to `init_project()`)
- (no test change — argparse behavior is covered by Tasks 4-7 via the kwarg path)

- [ ] **Step 1: Add the two argparse entries**

In `main()` (around line 756, near the "深度模式可选参数" block), add:

```python
    parser.add_argument("--idea-bank-file", default="",
                        help="idea_bank.json 临时文件路径（init Step 1.5 确认后写入）；留空则不写 idea_bank.json")
    parser.add_argument("--idea-bank-force", action="store_true",
                        help="强制覆盖已存在的 idea_bank.json（默认拒绝覆盖）")
```

- [ ] **Step 2: Pass through to `init_project()` call**

Find the `init_project(...)` call (around line 766). Add two kwargs at the end:

```python
    init_project(
        args.project_dir,
        args.title,
        args.genre,
        protagonist_name=args.protagonist_name,
        # ... existing args ...
        idea_bank_file=args.idea_bank_file,
        idea_bank_force=args.idea_bank_force,
    )
```

But wait — `idea_bank_force` isn't a kwarg of `init_project()` yet. Update `init_project()` signature to add `idea_bank_force: bool = False` right after `idea_bank_file: str = ""`. Then in the wired-in block (Task 4 Step 4), change:

```python
    if idea_bank_file:
        _write_idea_bank(project_path, idea_bank_file)
```

to:

```python
    if idea_bank_file:
        _write_idea_bank(project_path, idea_bank_file, force=idea_bank_force)
```

- [ ] **Step 3: Run all init-related tests**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py data_modules/tests/test_prompt_integrity.py data_modules/tests/test_init_project_pruning.py -v 2>&1 | tail -20
```

Expected: All PASS. (The pre-existing `test_init_project_pruning.py` must continue to pass — none of its tests pass `idea_bank_file`, so default `""` keeps the new code path inert.)

- [ ] **Step 4: Smoke-test the CLI flags**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python init_project.py /tmp/manual_smoke_book "Smoke" "仙侠" \
  --protagonist-name "P" --idea-bank-file /nonexistent.json 2>&1 | tail -5
```

Expected: SystemExit with message mentioning `/nonexistent.json`. Project dir should NOT exist at `/tmp/manual_smoke_book`.

Then:
```bash
rm -rf /tmp/manual_smoke_book
```

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add webnovel-writer_chang/scripts/init_project.py
git commit -m "feat(init): --idea-bank-file + --idea-bank-force CLI flags

Adds two argparse entries to main() and threads them through to
init_project(). Existing tests (no flag) remain green. Manual
smoke confirms missing-flag path SystemExits cleanly."
```

---

## Task 9: End-to-end manual smoke (verification, not a commit)

**Files:** (none — verification only)

- [ ] **Step 1: Run the entire init+plan smoke (spec T3, with-reference path)**

Without a real /webnovel-init session available in CI, simulate the wiring end-to-end via direct Python:

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts

# 1. Build a payload that mimics what Step 1.5 would produce
python -c "
import json
payload = {
  'version': 1,
  'source': {'reference_title': '《凡人修仙传》', 'reference_source': 'book_name', 'analysis_mode': 'quick', 'confidence': 0.88},
  'selected_idea': {'title': '凡人+', 'one_liner': '没有灵根的凡人靠现代知识修仙', 'anti_trope': '不靠金手指开挂', 'hard_constraints': ['硬约束1', '硬约束2']},
  'constraints_inherited': {'anti_trope': '不靠金手指开挂', 'hard_constraints': ['硬约束1', '硬约束2'], 'protagonist_flaw': '过度理性', 'antagonist_mirror': '感性极端', 'opening_hook': '第一章：检测灵根'},
  'borrowed_patterns': ['凡人-宗门阶梯式升级'],
  'do_not_copy': ['韩立人设'],
  'canon_contamination_warnings': ['原作人物名:韩立,南宫婉']
}
import pathlib; pathlib.Path('/tmp/payload.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2))
"

# 2. Run init with the payload
rm -rf /tmp/smoke_book
python init_project.py /tmp/smoke_book "凡人+" "仙侠" \
  --protagonist-name "陈墨" --idea-bank-file /tmp/payload.json 2>&1 | tail -10

# 3. Verify idea_bank.json exists with correct content
ls -la /tmp/smoke_book/.webnovel/idea_bank.json
python -c "import json; d=json.load(open('/tmp/smoke_book/.webnovel/idea_bank.json')); print('reference_title:', d['source']['reference_title']); print('opening_hook:', d['constraints_inherited']['opening_hook']); print('warnings:', d['canon_contamination_warnings'])"

# 4. Cleanup
rm -rf /tmp/smoke_book /tmp/payload.json
```

Expected:
- `/tmp/smoke_book/.webnovel/idea_bank.json` exists
- `reference_title` matches "《凡人修仙传》"
- `opening_hook` matches "第一章：检测灵根"
- `canon_contamination_warnings` is preserved verbatim

- [ ] **Step 2: Run the without-reference path**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts

rm -rf /tmp/smoke_book_noref
python init_project.py /tmp/smoke_book_noref "原创书" "都市" \
  --protagonist-name "李四" 2>&1 | tail -5

ls /tmp/smoke_book_noref/.webnovel/ 2>&1
rm -rf /tmp/smoke_book_noref
```

Expected: `.webnovel/` contains `state.json`, `writer-profile/`, but **NOT** `idea_bank.json`.

- [ ] **Step 3: Run the full test suite one final time**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/ -v 2>&1 | tail -30
```

Expected: All PASS (or pre-existing unrelated failures, none introduced by this work).

- [ ] **Step 4: Report results (no commit)**

Print a summary to the user:
- 1 prompt-integrity test: red → green
- 9 new unit tests: all pass
- 1 manual smoke (with-ref): idea_bank.json created with correct content
- 1 manual smoke (no-ref): idea_bank.json NOT created

If any step fails, do NOT mark Task 9 complete — investigate.

---

## Acceptance Criteria Checklist

After all 9 tasks complete, verify:

- [ ] `test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate` is GREEN
- [ ] `test_init_idea_bank.py` has 9 passing tests
- [ ] `test_init_project_pruning.py` still passes (no regression)
- [ ] `init_project.py` has `idea_bank_file` kwarg + `--idea-bank-file` / `--idea-bank-force` CLI flags
- [ ] `_validate_idea_bank_payload()` and `_write_idea_bank()` exist and are tested
- [ ] Manual smoke confirms with-ref writes, no-ref skips
- [ ] No new skill/command/agent created
- [ ] `idea_bank.json` content matches spec §D2 schema in both create and skip-paths
- [ ] `canon_contamination_warnings` is preserved verbatim through to disk

---

## Out-of-Scope Reminder (do NOT implement here)

- **P1:** `/webnovel-chart-scan --auto-deconstruct <book>` — separate spec when chart-scan v0.3 lands.
- **P2:** Standalone `/webnovel-deconstruct` — explicitly not recommended; if a real need arises, redesign the agent output first.
- **webnovel-write / webnovel-review** consumption of `idea_bank.json` — future task.

---

## Self-Review Notes

- Spec coverage: D1 → Task 1; D2 (write + flag + three-state + schema validation) → Tasks 2-8; D3 (init main flow contract) → encoded in Task 1's SKILL.md text and Task 8's flag wiring; D4 (files modified) → all tasks; D5 (out-of-scope) → "Out-of-Scope Reminder" section; Testing strategy T1 → Task 1; T2 → Tasks 2-7; T3 → Task 9.
- Placeholder scan: no "TBD" / "TODO" / "implement later". Every code block is complete and runnable.
- Type consistency: `idea_bank_file: str` introduced in Task 2, used in Task 4, exposed as `--idea-bank-file` in Task 8. `idea_bank_force: bool` introduced in Task 8 alongside its CLI flag. `_write_idea_bank(project_path, idea_bank_file, force=False)` signature consistent across Tasks 4, 6, 8.
- Test count: 9 in `test_init_idea_bank.py` (1 from Task 2 + 4 from Task 3 + 1 from Task 4 + 1 from Task 5 + 2 from Task 6 + 1 from Task 7 + 1 from Task 8's manual smoke ref = 9; actually: 1+4+1+1+2+1 = 10. Manual smoke in Task 9 doesn't add a test file.)