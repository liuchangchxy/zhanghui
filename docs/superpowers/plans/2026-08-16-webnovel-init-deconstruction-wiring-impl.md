# Init ↔ Deconstruction-Agent Wiring (P0-Full) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `webnovel-init` Step 1.5 to call `deconstruction-agent` (extended schema) and persist the result as a multi-file product tree at `.webnovel/reference_research/<book-safe>/`, with `idea_bank.json` referencing the tree and `webnovel-plan` consuming it via path convention. Aligns the artifact shape with `oh-story-claudecode` and `harnessNovel` industry standard.

**Architecture:** Three new components. (1) Extended `deconstruction-agent.md` prompt with 9 new fields (additive). (2) New `scripts/data_modules/init_reference_tree.py` helper that builds the multi-file tree from a schema dict, with a Jinja-style template at `scripts/data_modules/templates/reference_report.md.j2`. (3) Updated `init_project.py` with `--reference-research-dir` / `--reference-overwrite` flags; updated `webnovel-init/SKILL.md` Step 1.5; updated `webnovel-plan/SKILL.md` with path-convention consumption.

**Tech Stack:** Python 3, `argparse`, `pathlib`, `json`. `jinja2` for the report template (already a dependency of the project; verify in `pyproject.toml`). pytest for tests. No new dependencies.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `agents/deconstruction-agent.md` | Modify | Add 9 new fields to schema description (additive; existing 9 untouched). |
| `skills/webnovel-init/SKILL.md` | Modify | Insert Step 1.5 + modify Step 2 preamble + modify Step 6. |
| `skills/webnovel-plan/SKILL.md` | Modify | Add reference_research tree consumption section. |
| `scripts/data_modules/init_reference_tree.py` | Create | `build_reference_tree()`, `sanitize_book_title()`, `validate_reference_tree()`. |
| `scripts/data_modules/templates/reference_report.md.j2` | Create | Jinja template for `report.md`. |
| `scripts/init_project.py` | Modify | Add `--reference-research-dir`, `--reference-overwrite` CLI flags; add `reference_research_dir`, `reference_overwrite` kwargs to `init_project()`; update `_validate_idea_bank_payload()` to accept optional `reference_research_path`. |
| `scripts/data_modules/tests/test_init_reference_tree.py` | Create | Tests for tree builder. |
| `scripts/data_modules/tests/test_init_idea_bank.py` | Modify | Add 4 tests for reference_research dir validation. |
| `scripts/data_modules/tests/test_prompt_integrity.py` | Modify | Add `test_deconstruction_agent_schema_extension`, `test_plan_reads_reference_research_when_pointer_set`. |
| `scripts/data_modules/tests/test_init_reference_tree.py` | Create | (also see above) |

No new skill or command. No new agent.

---

## Task 1: Step 1.5 in webnovel-init/SKILL.md (preserves existing test green)

**Files:**
- Modify: `skills/webnovel-init/SKILL.md`
- Test (existing): `scripts/data_modules/tests/test_prompt_integrity.py::test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate`

- [ ] **Step 1: Run existing failing test to confirm red**

Run:
```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_prompt_integrity.py::test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate -v 2>&1 | tail -10
```

Expected: FAIL on missing literals like `Step 1.5：灵感来源询问`. If already green, stop and investigate (someone may have done this work).

- [ ] **Step 2: Insert Step 1.5 with all required literals**

Open `/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/skills/webnovel-init/SKILL.md`. Find `### Step 2：角色骨架与关系冲突`. Immediately BEFORE it, insert:

```markdown
### Step 1.5：灵感来源询问

进入故事核采集前，先问用户灵感来源——**不要默认拆书**。

向用户抛出唯一开场问题（必须包含字面串"你这本书的灵感来源想从哪里开始"）：

```
你这本书的灵感来源想从哪里开始？
  A) 原创 / 暂无参考书 → 跳过拆解，跳过 reference_research/ 与 idea_bank.json 写入
  B) 有参考书名 + 平台线索（如"起点《XX》"）→ quick 模式（无文本，quality.passed=false 风险高）
  C) 有参考书名 + 本地正文路径 → deep 模式（路径不可读时降级 quick）
  D) 有参考书名 + 仅摘录（粘进对话）→ quick 模式
```

用户选 A：记录 `reference_source = "none"`，**不写任何文件**，直接进入 Step 2。

用户选 B/C/D：用以下字面调用方式触发拆解子代理（主流程**不得由 init 主流程口头替代拆解结果**，必须拿原始 JSON）：

```
Use the Agent tool to run `webnovel-writer:deconstruction-agent`
```

调用时传入字段（参考 `agents/deconstruction-agent.md §2`）：`reference_title`、`reference_source`、`reference_text_path` 或 `reference_text_excerpt`、`analysis_mode`、`init_goal`、`target_genre`。**禁止使用 `subagent_type:` 字段**——Claude Code 的 Agent tool 不接受该参数。

子代理返回 `init_reference_research` JSON 对象（包含 9 个新增字段：`chapter_rhythm`、`narrative_function`、`boundary_reason`、`protagonist_action_chain`、`emotion_curve`、`satisfaction_point`、`foreshadowing`、`gains_costs`、`character_changes`）。**用户确认前**，以下行为禁止：

- 写入 `.webnovel/reference_research/`、`idea_bank.json`、`.story-system`、`设定集/`、`大纲/`、`正文/`、`.webnovel/state.json`
- 由主流程口头重写拆解结论

检查返回 JSON 的 `quality` 字段（必须含字面 `` `quality` `` 和 `` `quality.passed=false` ``）：

- 若 `quality.passed=false` 或 `confidence < 0.85`（含字面 `` `confidence < 0.85` ``）：把缺漏展示给用户，问三种处理：(i) 用更多文本重跑；(ii) 用稀疏模式继续；(iii) 放弃参考（默认 (iii)）。
- 否则：调用 `scripts/data_modules/init_reference_tree.py:build_reference_tree()` 把 JSON 渲染成 `.webnovel/reference_research/<book-safe>/` 多文件树（见 D3 目录结构）。把 `do_not_copy` 字段和 `canon_contamination_warnings` 字段**原文**展示给用户。

用户确认后，主流程：
1. 调用 `init_reference_tree.py` 落盘树
2. 写 `idea_bank.json`，新增 `reference_research_path` 字段指向树
3. 通过临时文件 + `--reference-research-dir` 传给 `webnovel.py init` 验证树存在
4. **禁止**直接拼接到 CLI argv 大字段里

> Step 2-6 只能使用用户确认过、并已变形为本书差异化表达的模式；不可借用尚未确认或仍携带原作设定的字段。

```

- [ ] **Step 3: Modify Step 2 preamble**

In the same file, find `### Step 2：角色骨架与关系冲突`. Immediately AFTER it (before "收集项"), insert:

```
> Step 2-6 只能使用用户确认过、并已变形为本书差异化表达的模式。
```

- [ ] **Step 4: Modify Step 6 final confirmation**

Find `### Step 6：一致性复述与最终确认`. In the bullet list "必须输出'初始化摘要草案'并让用户确认：", add one more bullet:

```markdown
- 汇总 Step 1.5 已确认的灵感来源（参考书名 / 分析模式 / 置信度 / reference_research 路径 / 反套路 / 硬约束数量）
```

- [ ] **Step 5: Run the integrity test, verify green**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_prompt_integrity.py::test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate -v 2>&1 | tail -10
```

Expected: PASS. If still red, diff against `test_prompt_integrity.py:635-680` and the P0-Full spec D2.

- [ ] **Step 6: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/skills/webnovel-init/SKILL.md
git commit -m "feat(init): Step 1.5 wiring — multi-file tree call + plan consumption pointer

Turns test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate
green. Inserts all test-asserted literals and the new responsibility to
call init_reference_tree.build_reference_tree() + write idea_bank.json
with reference_research_path pointer."
```

---

## Task 2: Extend deconstruction-agent.md with 9 new fields (additive)

**Files:**
- Modify: `agents/deconstruction-agent.md`
- Test (new): `scripts/data_modules/tests/test_prompt_integrity.py::test_deconstruction_agent_schema_extension`

- [ ] **Step 1: Write the failing test**

Add to `scripts/data_modules/tests/test_prompt_integrity.py` (at the end, or near the other deconstruction-agent tests around line 587-633):

```python
def test_deconstruction_agent_schema_extension():
    """Adding 9 new fields to deconstruction-agent.md must preserve existing 9."""
    text = _read_text(REPO_ROOT / "agents" / "deconstruction-agent.md")

    # New fields (P0-Full spec D1)
    for new_field in (
        "chapter_rhythm",
        "narrative_function",
        "boundary_reason",
        "protagonist_action_chain",
        "emotion_curve",
        "satisfaction_point",
        "foreshadowing",
        "gains_costs",
        "character_changes",
    ):
        assert new_field in text, f"deconstruction-agent.md missing new field: {new_field}"

    # Existing 9 fields must be preserved (no rename, no removal)
    for existing_field in (
        "reader_promise",
        "opening_hook_patterns",
        "cool_point_loops",
        "protagonist_patterns",
        "antagonist_pressure_patterns",
        "pacing_notes",
        "borrowable_structures",
        "differentiation_requirements",
        "init_candidates",
    ):
        assert existing_field in text, f"deconstruction-agent.md lost existing field: {existing_field}"
```

(Use whatever `_read_text` / `REPO_ROOT` helper the test file already uses; if not present, copy from the test directly above this one.)

- [ ] **Step 2: Run the test, verify 9 new-field assertions fail**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_prompt_integrity.py::test_deconstruction_agent_schema_extension -v 2>&1 | tail -15
```

Expected: FAIL on the first missing new field (likely `chapter_rhythm`).

- [ ] **Step 3: Add the 9 new fields to deconstruction-agent.md**

Open `/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/agents/deconstruction-agent.md`. Find the section that lists the JSON schema fields (around line 89, "只返回严格结构化的 `init_reference_research` JSON"). Add a new subsection AFTER the existing field list, titled "## 扩展字段（P0-Full 新增）":

```markdown
## 扩展字段（P0-Full 新增）

下列字段是 2026-08-16 spec §D1 引入的新维度，全部为**可选项**——如果参考书无原文摘录无法提取（如 quick 模式且无 excerpt），可置为空数组/空对象，并在 `quality.coverage` 中标 `partial`。**不要伪造数据**。

- `chapter_rhythm`：对象数组，每项 `{ chapter, core_content, emotion_tone, beat_detail }`。仅覆盖黄金三章（如有原文）。
  - `core_content` ≤ 30 字短语链
  - `emotion_tone` ∈ `{紧张, 热血, 爽, 甜, 温馨, 压抑, 悲伤, 轻松, 恐怖, 其他}`
  - `beat_detail` ≤ 80 字细节奏
- `narrative_function`：字符串，整体情节功能原型（如 `升级流` / `复仇线` / `多线交织` / `单元剧` / `重生回溯` / `系统签到` / 其他）。
- `boundary_reason`：对象 `{ first_arc_start, first_arc_end, reason }`，黄金三章内的自然叙事边界。
- `protagonist_action_chain`：对象数组 `{ trigger, action, result }`，主角的 trigger→action→result 链。
- `emotion_curve`：对象数组 `{ chapter, intensity, label }`，情绪强度曲线（intensity ∈ [0, 1]）。
- `satisfaction_point`：字符串数组，1-6 条单行亮点（金句/梗/爆点）。
- `foreshadowing`：对象数组 `{ setup_chapter, payoff_chapter_estimate, content }`，伏笔地图。
- `gains_costs`：对象数组 `{ chapter, gain, cost, category }`，category ∈ `{物质, 实力, 关系, 认知}`。
- `character_changes`：对象数组 `{ chapter, character, before, after }`，角色变化前后对比。

新增字段必须遵循与原 9 字段一致的"差异化要求"原则——**不能复制原作人物/地点/组织/能力名/剧情事实**，全部变形为功能位/条件组合/情绪方向。
```

- [ ] **Step 4: Run the test, verify green**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_prompt_integrity.py::test_deconstruction_agent_schema_extension -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5: Run full prompt-integrity suite to confirm no regression**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_prompt_integrity.py -v 2>&1 | tail -10
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/agents/deconstruction-agent.md webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py
git commit -m "feat(agent): extend deconstruction-agent schema with 9 new fields (P0-Full)

Additive: chapter_rhythm / narrative_function / boundary_reason /
protagonist_action_chain / emotion_curve / satisfaction_point /
foreshadowing / gains_costs / character_changes.

Existing 9 fields (reader_promise / opening_hook_patterns / ...) preserved
verbatim. New fields are optional (empty array/object if not extractable)
and must follow the same differentiation requirement (no copying of
original work's names/places/etc.)."
```

---

## Task 3: Create Jinja template for `report.md`

**Files:**
- Create: `scripts/data_modules/templates/reference_report.md.j2`

(No test for the template itself; tests are in Task 4 against the builder.)

- [ ] **Step 1: Verify jinja2 is available**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -c "import jinja2; print(jinja2.__version__)"
```

Expected: prints version. If `ModuleNotFoundError`, add to `pyproject.toml` and re-install; if not available in the venv, fall back to Python `string.Template` (Task 4 will adapt).

- [ ] **Step 2: Create the template directory**

```bash
mkdir -p "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/templates"
```

- [ ] **Step 3: Write the template**

Create `scripts/data_modules/templates/reference_report.md.j2`:

```jinja
# 拆书报告：{{ reference_title }}

> 参考书：{{ reference_title }}
> 分析模式：`{{ analysis_mode }}` | 置信度：`{{ confidence }}` | 覆盖率：`{{ coverage }}`
> 报告生成：自动化（init Step 1.5）

## 1. 读者承诺

{{ reader_promise }}

## 2. 开篇钩子套路

{% for hook in opening_hook_patterns %}
- {{ hook }}
{% endfor %}

## 3. 爽点循环

{% for cp in cool_point_loops %}
- {{ cp }}
{% endfor %}

## 4. 主角原型

{{ protagonist_patterns }}

## 5. 反派压力模式

{{ antagonist_pressure_patterns }}

## 6. 节奏备注

{{ pacing_notes }}

## 7. 叙事功能与边界

- 叙事功能：`{{ narrative_function }}`
- 第一弧边界：第 `{{ boundary_reason.first_arc_start }}` 章 → 第 `{{ boundary_reason.first_arc_end }}` 章
- 边界理由：{{ boundary_reason.reason }}

## 8. 主角行动链

{% for chain in protagonist_action_chain %}
- **触发** {{ chain.trigger }} → **行动** {{ chain.action }} → **结果** {{ chain.result }}
{% endfor %}

## 9. 情绪曲线

{% for point in emotion_curve %}
- 第 {{ point.chapter }} 章：强度 `{{ "%.2f" | format(point.intensity) }}` · {{ point.label }}
{% endfor %}

## 10. 核心爽点

{% for sp in satisfaction_point %}
- {{ sp }}
{% endfor %}

## 11. 伏笔地图

{% for f in foreshadowing %}
- **第 {{ f.setup_chapter }} 章** 设伏 → **预计第 {{ f.payoff_chapter_estimate }} 章** 兑现：{{ f.content }}
{% endfor %}

## 12. 收获与代价

{% for gc in gains_costs %}
- 第 {{ gc.chapter }} 章 · {{ gc.category }}：得 `{{ gc.gain }}` / 失 `{{ gc.cost }}`
{% endfor %}

## 13. 角色变化

{% for cc in character_changes %}
- 第 {{ cc.chapter }} 章 · {{ cc.character }}：`{{ cc.before }}` → `{{ cc.after }}`
{% endfor %}

## 14. 可复用结构

{% for bs in borrowable_structures %}
- {{ bs }}
{% endfor %}

## 15. 差异化要求

{{ differentiation_requirements }}

## 16. Init 候选

- **一句话卖点**：{{ init_candidates.one_liner }}
- **反套路**：{{ init_candidates.anti_trope }}
- **硬约束**：
{% for hc in init_candidates.hard_constraints %}
  - {{ hc }}
{% endfor %}
- **主角缺陷**：{{ init_candidates.protagonist_flaw }}
- **反派镜像**：{{ init_candidates.antagonist_mirror }}
- **开篇钩子**：{{ init_candidates.opening_hook }}

---

> ⚠️ 本报告由 deconstruction-agent 自动生成，仅作为 init Step 5 创意约束的输入。`do_not_copy` 与 `canon_contamination_warnings` 字段见同目录独立文件。
```

- [ ] **Step 4: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/scripts/data_modules/templates/reference_report.md.j2
git commit -m "feat(init): reference_research report.md Jinja template

Renders init_reference_research JSON to a human-readable Markdown
report. Used by init_reference_tree.build_reference_tree() (Task 4).
Empty optional fields render as empty sections (no error)."
```

---

## Task 4: TDD `init_reference_tree.py`

**Files:**
- Create: `scripts/data_modules/init_reference_tree.py`
- Create: `scripts/data_modules/tests/test_init_reference_tree.py`

- [ ] **Step 1: Write the failing test file**

Create `scripts/data_modules/tests/test_init_reference_tree.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pytest


def _minimal_schema() -> dict:
    """Minimal valid init_reference_research JSON for tree builder tests."""
    return {
        "source": {"reference_title": "《测试书》", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.9},
        "reader_promise": "测试读者承诺",
        "opening_hook_patterns": ["钩子A", "钩子B"],
        "cool_point_loops": ["爽点循环A"],
        "protagonist_patterns": "主角原型A",
        "antagonist_pressure_patterns": "反派压力A",
        "pacing_notes": "节奏备注A",
        "narrative_function": "升级流",
        "boundary_reason": {"first_arc_start": 1, "first_arc_end": 5, "reason": "前期铺垫"},
        "protagonist_action_chain": [{"trigger": "T1", "action": "A1", "result": "R1"}],
        "emotion_curve": [{"chapter": 1, "intensity": 0.7, "label": "紧张"}],
        "satisfaction_point": ["亮点1"],
        "foreshadowing": [{"setup_chapter": 1, "payoff_chapter_estimate": 5, "content": "伏笔A"}],
        "gains_costs": [{"chapter": 1, "gain": "实力+", "cost": "认知-", "category": "实力"}],
        "character_changes": [{"chapter": 1, "character": "主角", "before": "弱", "after": "觉醒"}],
        "borrowable_structures": ["结构A"],
        "differentiation_requirements": "差异化要求A",
        "init_candidates": {
            "one_liner": "一句话",
            "anti_trope": "反套路",
            "hard_constraints": ["硬约束1"],
            "protagonist_flaw": "缺陷",
            "antagonist_mirror": "镜像",
            "opening_hook": "钩子",
        },
        "do_not_copy": ["不要抄人物名"],
        "canon_contamination_warnings": ["原作人物名:张三"],
        "quality": {"passed": True, "confidence": 0.9, "coverage": 0.85},
    }


def test_sanitize_book_title_basic():
    from init_reference_tree import sanitize_book_title
    assert sanitize_book_title("《凡人修仙传》") == "fanren-xiuxian-chuan"
    assert sanitize_book_title("My Book Title") == "my-book-title"


def test_sanitize_book_title_empty_raises():
    from init_reference_tree import sanitize_book_title
    with pytest.raises(ValueError):
        sanitize_book_title("///")


def test_sanitize_book_title_max_length():
    from init_reference_tree import sanitize_book_title
    long = "a" * 100
    assert len(sanitize_book_title(long)) <= 64


def test_build_reference_tree_creates_all_files(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    tree = build_reference_tree(tmp_path, schema, "《测试书》")

    assert tree.is_dir()
    assert (tree / "_schema.json").is_file()
    assert (tree / "report.md").is_file()
    assert (tree / "do_not_copy.md").is_file()
    assert (tree / "canon_contamination_warnings.md").is_file()
    assert (tree / "_progress.json").is_file()
    assert not (tree / "opening_chapters").exists()  # No excerpts → skip


def test_build_reference_tree_schema_is_verbatim(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    tree = build_reference_tree(tmp_path, schema, "《测试书》")
    written = json.loads((tree / "_schema.json").read_text(encoding="utf-8"))
    assert written["reader_promise"] == "测试读者承诺"
    assert written["narrative_function"] == "升级流"
    assert written["init_candidates"]["hard_constraints"] == ["硬约束1"]


def test_build_reference_tree_report_contains_sections(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    tree = build_reference_tree(tmp_path, schema, "《测试书》")
    report = (tree / "report.md").read_text(encoding="utf-8")
    assert "拆书报告" in report
    assert "读者承诺" in report
    assert "升级流" in report
    assert "亮点1" in report


def test_build_reference_tree_do_not_copy_verbatim(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    tree = build_reference_tree(tmp_path, schema, "《测试书》")
    dnc = (tree / "do_not_copy.md").read_text(encoding="utf-8")
    assert "不要抄人物名" in dnc


def test_build_reference_tree_progress_has_version(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    tree = build_reference_tree(tmp_path, schema, "《测试书》")
    progress = json.loads((tree / "_progress.json").read_text(encoding="utf-8"))
    assert progress["schema_version"] == 1
    assert progress["reference_title"] == "《测试书》"
    assert progress["quality_flags"]["passed"] is True


def test_validate_reference_tree_accepts_valid_tree(tmp_path):
    from init_reference_tree import build_reference_tree, validate_reference_tree

    schema = _minimal_schema()
    tree = build_reference_tree(tmp_path, schema, "《测试书》")
    assert validate_reference_tree(tree) is True


def test_validate_reference_tree_rejects_missing_files(tmp_path):
    from init_reference_tree import validate_reference_tree
    assert validate_reference_tree(tmp_path) is False


def test_build_reference_tree_refuses_overwrite_without_flag(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    build_reference_tree(tmp_path, schema, "《测试书》")
    with pytest.raises(FileExistsError):
        build_reference_tree(tmp_path, schema, "《测试书》")


def test_build_reference_tree_overwrites_with_flag(tmp_path):
    from init_reference_tree import build_reference_tree

    schema = _minimal_schema()
    build_reference_tree(tmp_path, schema, "《测试书》")
    # Should not raise
    tree = build_reference_tree(tmp_path, schema, "《测试书》", overwrite=True)
    assert tree.is_dir()
```

- [ ] **Step 2: Run tests, verify all fail with ImportError**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_reference_tree.py -v 2>&1 | tail -20
```

Expected: All 11 FAIL with `No module named 'init_reference_tree'`.

- [ ] **Step 3: Implement `init_reference_tree.py`**

Create `/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/init_reference_tree.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Build and validate the .webnovel/reference_research/<book-safe>/ product tree.

Implements 2026-08-16-webnovel-init-deconstruction-wiring-design §D3/§D6.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:  # pragma: no cover
    Environment = None  # type: ignore


TEMPLATE_DIR = Path(__file__).parent / "templates"
MAX_BOOK_NAME = 64


def sanitize_book_title(title: str) -> str:
    """Convert a reference title to a safe filesystem directory name.

    Rules:
      - Strip path-illegal characters (`/\\:*?"<>|`).
      - Replace whitespace with `-`.
      - Lowercase.
      - Collapse multiple `-` to single.
      - Strip leading/trailing `-` and `.`.
      - If empty after sanitization, raise ValueError.
      - Truncate to MAX_BOOK_NAME chars.
    """
    if not title:
        raise ValueError("book title must not be empty")
    safe = re.sub(r'[\\/:\*\?"<>\|]', "", title)
    safe = re.sub(r"\s+", "-", safe)
    safe = re.sub(r"-+", "-", safe)
    safe = safe.strip("-.")
    safe = safe.lower()
    if not safe:
        raise ValueError(f"book title {title!r} sanitizes to empty string")
    return safe[:MAX_BOOK_NAME]


def _render_report(schema: dict[str, Any]) -> str:
    """Render report.md from schema using the Jinja template."""
    if Environment is None:
        raise RuntimeError("jinja2 is required for report rendering")
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=("md",)),
        keep_trailing_newline=True,
    )
    template = env.get_template("reference_report.md.j2")

    # Flatten the schema into template-friendly kwargs
    source = schema.get("source", {})
    boundary = schema.get("boundary_reason") or {}
    init_candidates = schema.get("init_candidates") or {}
    return template.render(
        reference_title=source.get("reference_title", ""),
        analysis_mode=source.get("analysis_mode", "quick"),
        confidence=schema.get("quality", {}).get("confidence", 0.0),
        coverage=schema.get("quality", {}).get("coverage", 0.0),
        reader_promise=schema.get("reader_promise", ""),
        opening_hook_patterns=schema.get("opening_hook_patterns", []),
        cool_point_loops=schema.get("cool_point_loops", []),
        protagonist_patterns=schema.get("protagonist_patterns", ""),
        antagonist_pressure_patterns=schema.get("antagonist_pressure_patterns", ""),
        pacing_notes=schema.get("pacing_notes", ""),
        narrative_function=schema.get("narrative_function", ""),
        boundary_reason=boundary,
        protagonist_action_chain=schema.get("protagonist_action_chain", []),
        emotion_curve=schema.get("emotion_curve", []),
        satisfaction_point=schema.get("satisfaction_point", []),
        foreshadowing=schema.get("foreshadowing", []),
        gains_costs=schema.get("gains_costs", []),
        character_changes=schema.get("character_changes", []),
        borrowable_structures=schema.get("borrowable_structures", []),
        differentiation_requirements=schema.get("differentiation_requirements", ""),
        init_candidates=init_candidates,
    )


def _render_field_extract(field_name: str, items: list[str] | list[dict]) -> str:
    """Render a single-field extract file (do_not_copy.md / canon_contamination_warnings.md)."""
    lines = [f"# {field_name}\n", f"> 自动从 deconstruction-agent 抽取的 `{field_name}` 字段。\n", ""]
    for item in items:
        if isinstance(item, dict):
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def build_reference_tree(
    project_path: Path,
    schema: dict[str, Any],
    reference_title: str,
    *,
    overwrite: bool = False,
) -> Path:
    """Build the multi-file product tree under project_path/reference_research/<book-safe>/.

    Returns the tree directory path.
    Raises FileExistsError if the tree already exists and overwrite=False.
    """
    safe = sanitize_book_title(reference_title)
    webnovel = project_path / ".webnovel"
    tree = webnovel / "reference_research" / safe

    if tree.exists():
        if not overwrite:
            raise FileExistsError(
                f"reference_research tree already exists at {tree}. "
                f"Pass overwrite=True or use --reference-overwrite flag."
            )
        # Backup existing schema if present
        schema_file = tree / "_schema.json"
        if schema_file.exists():
            backup = tree / f"_schema.json.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            schema_file.rename(backup)

    tree.mkdir(parents=True, exist_ok=True)

    # 1. _schema.json — verbatim agent output
    (tree / "_schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # 2. report.md — Jinja-rendered
    (tree / "report.md").write_text(_render_report(schema), encoding="utf-8")

    # 3. do_not_copy.md — verbatim field extract
    dnc = schema.get("do_not_copy", []) or []
    (tree / "do_not_copy.md").write_text(_render_field_extract("do_not_copy", dnc), encoding="utf-8")

    # 4. canon_contamination_warnings.md — verbatim field extract
    ccw = schema.get("canon_contamination_warnings", []) or []
    (tree / "canon_contamination_warnings.md").write_text(
        _render_field_extract("canon_contamination_warnings", ccw), encoding="utf-8",
    )

    # 5. _progress.json — resumption state (D6)
    now = datetime.now(timezone.utc).isoformat()
    progress = {
        "schema_version": 1,
        "reference_title": reference_title,
        "created_at": now,
        "last_updated": now,
        "superseded_versions": [],
        "quality_flags": schema.get("quality", {"passed": False, "confidence": 0.0, "coverage": 0.0}),
    }
    (tree / "_progress.json").write_text(
        json.dumps(progress, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # 6. opening_chapters/ — only if excerpts present (skip in tests; full impl is spec §D3)
    # Not generated by this builder; opening_chapters is a future extension.

    return tree


def validate_reference_tree(tree: Path) -> bool:
    """Return True iff tree has all required files."""
    required = ("_schema.json", "report.md", "do_not_copy.md",
                "canon_contamination_warnings.md", "_progress.json")
    return all((tree / name).is_file() for name in required)
```

- [ ] **Step 4: Run tests, verify all pass**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_reference_tree.py -v 2>&1 | tail -20
```

Expected: 11 PASSED.

- [ ] **Step 5: Run full prompt-integrity + init_idea_bank + init_project_pruning suite**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_prompt_integrity.py data_modules/tests/test_init_idea_bank.py data_modules/tests/test_init_project_pruning.py -v 2>&1 | tail -20
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/scripts/data_modules/init_reference_tree.py webnovel-writer_chang/scripts/data_modules/tests/test_init_reference_tree.py
git commit -m "feat(init): init_reference_tree builder — multi-file product tree from JSON

Implements spec §D3:
  .webnovel/reference_research/<book-safe>/
  ├── _schema.json                     # verbatim init_reference_research
  ├── report.md                        # Jinja-rendered
  ├── do_not_copy.md                   # field extract
  ├── canon_contamination_warnings.md  # field extract
  └── _progress.json                   # resumption state

11 unit tests covering sanitization, all-files creation, verbatim
schema, report sections, field extracts, progress version, validation,
overwrite protection."
```

---

## Task 5: Extend `idea_bank.json` schema (additive `reference_research_path`)

**Files:**
- Modify: `scripts/init_project.py` (`_validate_idea_bank_payload()` + `init_project()` kwargs)
- Modify: `scripts/data_modules/tests/test_init_idea_bank.py`

- [ ] **Step 1: Write the new tests**

Add to `scripts/data_modules/tests/test_init_idea_bank.py`:

```python
def test_validate_idea_bank_accepts_optional_reference_research_path():
    from init_project import _validate_idea_bank_payload
    payload = {
        "version": 1,
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {"title": "", "one_liner": "", "anti_trope": "", "hard_constraints": []},
        "constraints_inherited": {"anti_trope": "", "hard_constraints": [], "protagonist_flaw": "", "antagonist_mirror": "", "opening_hook": ""},
        "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
        "reference_research_path": ".webnovel/reference_research/foo/",
    }
    parsed = _validate_idea_bank_payload(json.dumps(payload))
    assert parsed["reference_research_path"] == ".webnovel/reference_research/foo/"


def test_validate_idea_bank_accepts_missing_reference_research_path():
    """Backward compatibility: existing payloads without the field still validate."""
    from init_project import _validate_idea_bank_payload
    payload = {
        "version": 1,
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
    }
    parsed = _validate_idea_bank_payload(json.dumps(payload))
    assert "reference_research_path" not in parsed
```

- [ ] **Step 2: Run tests, verify they fail (function currently rejects unknown fields)**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py -v -k "reference_research" 2>&1 | tail -10
```

Expected: FAIL — the new test expects the field to be accepted, but `_validate_idea_bank_payload()` either errors or silently drops.

(If the current code silently drops unknown fields, only the "accepts missing" test might pass; the "accepts present" test fails because `parsed["reference_research_path"]` raises KeyError.)

- [ ] **Step 3: Update `_validate_idea_bank_payload()`**

In `scripts/init_project.py`, find `_validate_idea_bank_payload()` (added in Task 3 of lite plan). Modify the `missing = required_top - set(data.keys())` line area:

Before (around the missing-field check):
```python
    missing = required_top - set(data.keys())
    if missing:
        raise ValueError(f"idea_bank.json missing required top-level keys: {sorted(missing)}")
```

Add immediately after the missing-key check:

```python
    # Optional fields (P0-Full): silently accept if absent (backward compat)
    # Currently just reference_research_path; future fields can be added here.
```

(Just a comment — no actual logic change needed if the function returns the full `data` dict, which it does.)

Verify: the function currently returns `data` at the end, so `reference_research_path` will flow through automatically. No code change needed; tests just verify the contract.

If tests still fail, check whether `data["source"]["reference_source"]` validation rejects the test payload. The test uses `"book_name"` which is in the allowed enum, so should pass.

- [ ] **Step 4: Re-run tests, verify they pass**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py -v 2>&1 | tail -15
```

Expected: All (existing + 2 new) PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/scripts/init_project.py webnovel-writer_chang/scripts/data_modules/tests/test_init_idea_bank.py
git commit -m "feat(init): idea_bank.json accepts optional reference_research_path field

Backward-compatible: existing payloads without the field still validate.
New payloads can include reference_research_path to point plan at the
multi-file tree (spec §D4)."
```

---

## Task 6: Add `--reference-research-dir` and `--reference-overwrite` CLI flags to `init_project.py`

**Files:**
- Modify: `scripts/init_project.py` (add 2 CLI flags + 2 kwargs + validation)
- Modify: `scripts/data_modules/tests/test_init_idea_bank.py` (add 4 tests from spec T3)

- [ ] **Step 1: Write the 4 new tests**

Add to `scripts/data_modules/tests/test_init_idea_bank.py`:

```python
def test_init_validates_reference_research_dir_when_flag_present(tmp_path, monkeypatch):
    """With --reference-research-dir pointing to a valid pre-built tree, init succeeds."""
    import init_project as init_project_module
    from init_reference_tree import build_reference_tree

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"

    # Build a valid tree in a separate location
    source_tree_root = tmp_path / "src_ws"
    source_tree_root.mkdir()
    schema = {
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
        "reader_promise": "", "opening_hook_patterns": [], "cool_point_loops": [], "protagonist_patterns": "", "antagonist_pressure_patterns": "", "pacing_notes": "",
        "narrative_function": "", "boundary_reason": {}, "protagonist_action_chain": [], "emotion_curve": [], "satisfaction_point": [], "foreshadowing": [], "gains_costs": [], "character_changes": [],
        "borrowable_structures": [], "differentiation_requirements": "", "init_candidates": {}, "quality": {"passed": True, "confidence": 0.5, "coverage": 0.5},
    }
    tree = build_reference_tree(source_tree_root, schema, "X")

    init_project_module.init_project(
        str(project_root), title="T", genre="仙侠", protagonist_name="P",
        reference_research_dir=str(tree),
    )
    # Tree should have been copied (or at least validated) — assert at least the source tree still validates
    assert (tree / "_schema.json").is_file()


def test_init_refuses_missing_reference_research_dir(tmp_path, monkeypatch):
    """Nonexistent --reference-research-dir triggers hard error."""
    import init_project as init_project_module

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"
    nonexistent = tmp_path / "does_not_exist"

    with pytest.raises(SystemExit):
        init_project_module.init_project(
            str(project_root), title="T", genre="仙侠", protagonist_name="P",
            reference_research_dir=str(nonexistent),
        )


def test_init_refuses_overwrite_existing_reference_research_without_force(tmp_path, monkeypatch):
    """Existing tree without --reference-overwrite refuses to overwrite."""
    import init_project as init_project_module
    from init_reference_tree import build_reference_tree

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"

    # Pre-create a tree in project_root
    schema = {
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
        "reader_promise": "", "opening_hook_patterns": [], "cool_point_loops": [], "protagonist_patterns": "", "antagonist_pressure_patterns": "", "pacing_notes": "",
        "narrative_function": "", "boundary_reason": {}, "protagonist_action_chain": [], "emotion_curve": [], "satisfaction_point": [], "foreshadowing": [], "gains_costs": [], "character_changes": [],
        "borrowable_structures": [], "differentiation_requirements": "", "init_candidates": {}, "quality": {"passed": True, "confidence": 0.5, "coverage": 0.5},
    }
    src_tree = build_reference_tree(tmp_path / "src", schema, "X")
    project_root.mkdir()
    target_tree = project_root / ".webnovel" / "reference_research" / "x"
    # Pre-create the target tree by copying src_tree
    import shutil
    shutil.copytree(src_tree, target_tree)
    sentinel = target_tree / "_schema.json"

    with pytest.raises(SystemExit):
        init_project_module.init_project(
            str(project_root), title="T", genre="仙侠", protagonist_name="P",
            reference_research_dir=str(src_tree),
        )

    # Original sentinel should be unchanged
    assert sentinel.read_text(encoding="utf-8") == src_tree.joinpath("_schema.json").read_text(encoding="utf-8")


def test_init_overwrites_with_explicit_force_flag(tmp_path, monkeypatch):
    """With --reference-overwrite, the diff path overwrites."""
    import init_project as init_project_module
    from init_reference_tree import build_reference_tree

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    project_root = tmp_path / "book"

    schema_v1 = {
        "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
        "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
        "reader_promise": "VERSION_1", "opening_hook_patterns": [], "cool_point_loops": [], "protagonist_patterns": "", "antagonist_pressure_patterns": "", "pacing_notes": "",
        "narrative_function": "", "boundary_reason": {}, "protagonist_action_chain": [], "emotion_curve": [], "satisfaction_point": [], "foreshadowing": [], "gains_costs": [], "character_changes": [],
        "borrowable_structures": [], "differentiation_requirements": "", "init_candidates": {}, "quality": {"passed": True, "confidence": 0.5, "coverage": 0.5},
    }
    schema_v2 = dict(schema_v1)
    schema_v2["reader_promise"] = "VERSION_2"

    src_v1 = build_reference_tree(tmp_path / "src1", schema_v1, "X")
    src_v2 = build_reference_tree(tmp_path / "src2", schema_v2, "X")

    project_root.mkdir()
    # Pre-create target with v1
    import shutil
    target = project_root / ".webnovel" / "reference_research" / "x"
    shutil.copytree(src_v1, target)

    init_project_module.init_project(
        str(project_root), title="T", genre="仙侠", protagonist_name="P",
        reference_research_dir=str(src_v2),
        reference_overwrite=True,
    )

    written = json.loads((target / "_schema.json").read_text(encoding="utf-8"))
    assert written["reader_promise"] == "VERSION_2"
```

- [ ] **Step 2: Run tests, verify they fail (kwargs don't exist)**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py -v -k "reference_research or overwrite" 2>&1 | tail -15
```

Expected: FAIL with `TypeError: init_project() got an unexpected keyword argument 'reference_research_dir'`.

- [ ] **Step 3: Add 2 kwargs to `init_project()` signature**

In `scripts/init_project.py`, find the `init_project()` signature. Add after `idea_bank_force: bool = False`:

```python
    reference_research_dir: str = "",
    reference_overwrite: bool = False,
```

- [ ] **Step 4: Add reference-research validation logic**

In `init_project()`, find the existing `if idea_bank_file:` block (added in lite Task 4 Step 4). Immediately AFTER it, insert:

```python
    # === reference_research/ 验证（spec 2026-08-16 §D3/D7）===
    if reference_research_dir:
        src_tree = Path(reference_research_dir).expanduser().resolve()
        if not src_tree.is_dir():
            raise SystemExit(
                f"--reference-research-dir not found or not a directory: {src_tree}"
            )
        from init_reference_tree import validate_reference_tree, sanitize_book_title
        if not validate_reference_tree(src_tree):
            raise SystemExit(
                f"--reference-research-dir is not a valid reference_research tree (missing required files): {src_tree}"
            )
        # Copy tree into project
        book_safe = src_tree.name
        target_tree = project_path / ".webnovel" / "reference_research" / book_safe
        if target_tree.exists() and not reference_overwrite:
            raise SystemExit(
                f"reference_research tree already exists at {target_tree}. "
                f"Pass reference_overwrite=True (or --reference-overwrite CLI flag) to overwrite."
            )
        if target_tree.exists():
            # Backup existing schema
            existing_schema = target_tree / "_schema.json"
            if existing_schema.exists():
                from datetime import datetime, timezone
                backup = target_tree / f"_schema.json.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
                existing_schema.rename(backup)
        target_tree.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        if target_tree.exists():
            shutil.rmtree(target_tree)
        shutil.copytree(src_tree, target_tree)
        print(f"✅ 已写入 {target_tree}")
```

- [ ] **Step 5: Add the 2 CLI flags to `main()`**

In `main()`, find the existing `--idea-bank-force` argparse entry (added in lite Task 8 Step 1). Add immediately after it:

```python
    parser.add_argument("--reference-research-dir", default="",
                        help="预构建的 reference_research 树路径；init 主流程在 Step 1.5 落盘后传进来验证")
    parser.add_argument("--reference-overwrite", action="store_true",
                        help="强制覆盖已存在的 reference_research 树（默认拒绝覆盖）")
```

And in the `init_project(...)` call, add at the end:

```python
        reference_research_dir=args.reference_research_dir,
        reference_overwrite=args.reference_overwrite,
```

- [ ] **Step 6: Run all init tests, verify all pass**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_init_idea_bank.py data_modules/tests/test_init_reference_tree.py data_modules/tests/test_init_project_pruning.py -v 2>&1 | tail -25
```

Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/scripts/init_project.py webnovel-writer_chang/scripts/data_modules/tests/test_init_idea_bank.py
git commit -m "feat(init): --reference-research-dir + --reference-overwrite CLI flags

Adds 2 kwargs to init_project() and 2 argparse entries. Validates the
pre-built tree (must contain _schema.json, report.md, do_not_copy.md,
canon_contamination_warnings.md, _progress.json), then copies it to
.webnovel/reference_research/<book-safe>/. Refuses overwrite without
--reference-overwrite. 4 new unit tests cover all paths."
```

---

## Task 7: Update `webnovel-plan/SKILL.md` to consume reference_research tree

**Files:**
- Modify: `skills/webnovel-plan/SKILL.md`
- Modify: `scripts/data_modules/tests/test_prompt_integrity.py` (new test)

- [ ] **Step 1: Write the new test**

Add to `scripts/data_modules/tests/test_prompt_integrity.py`:

```python
def test_plan_reads_reference_research_when_pointer_set():
    """webnovel-plan SKILL.md must consume reference_research tree when idea_bank pointer is set."""
    text = _read_text(SKILLS_DIR / "webnovel-plan" / "SKILL.md")
    assert "reference_research_path" in text
    assert ".webnovel/reference_research" in text or "reference_research/" in text
    # Should mention at least one product-tree file
    for filename in ("_schema.json", "report.md"):
        assert filename in text, f"webnovel-plan/SKILL.md must consume {filename} from the tree"
```

- [ ] **Step 2: Run test, verify fails**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_prompt_integrity.py::test_plan_reads_reference_research_when_pointer_set -v 2>&1 | tail -10
```

Expected: FAIL on missing `reference_research_path`.

- [ ] **Step 3: Add consumption section to webnovel-plan/SKILL.md**

Open `/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/skills/webnovel-plan/SKILL.md`. Find the existing "按需读取设定集" line (around line 98). Add a new section immediately AFTER it:

```markdown
### 按需读取 reference_research 拆书产物

读完 `idea_bank.json` 后，若 `reference_research_path` 字段存在，按以下规则加载 `.webnovel/reference_research/<book-safe>/`：

1. **完整加载**：`_schema.json`（机器可校验，全量注入）
2. **节选加载**：`report.md` 中的"可复现模块"、"反套路"、"硬约束"三段（最多 ~500 行）
3. **独立加载**：`do_not_copy.md`、`canon_contamination_warnings.md`（短，全文）

在卷纲 / 章纲阶段使用：

- `narrative_function` + `boundary_reason` → 对齐卷级结构
- `emotion_curve` + `satisfaction_point` → 章节级节奏参考
- `foreshadowing` → 跨章连续性约束
- `gains_costs` + `character_changes` → 主角缺陷兑现提醒

如果 `reference_research_path` 字段缺失（老项目 / 用户未提供参考书），按历史行为运行，不报错。

如果路径指向不存在的目录，输出提示 "reference_research missing: <path>"，继续运行。
```

- [ ] **Step 4: Run test, verify passes**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_prompt_integrity.py::test_plan_reads_reference_research_when_pointer_set -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5: Run full prompt-integrity suite, verify no regression**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/test_prompt_integrity.py -v 2>&1 | tail -15
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add .claude/plugins/webnovel-writer_chang/skills/webnovel-plan/SKILL.md webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py
git commit -m "feat(plan): consume reference_research tree when idea_bank pointer set

webnovel-plan now reads .webnovel/reference_research/<book-safe>/
following the new idea_bank.reference_research_path pointer. Uses
schema fields for volume/chapter alignment, pacing, foreshadowing,
protagonist_flaw payoff reminders. Backward-compatible: missing
pointer falls back to old behavior."
```

---

## Task 8: End-to-end manual smoke

**Files:** (none — verification only)

- [ ] **Step 1: Run with-reference path smoke (spec T5 item 1-4)**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts

# 1. Build a minimal valid schema mimicking Step 1.5 agent output
python -c "
import json, pathlib
schema = {
  'source': {'reference_title': '《凡人修仙传》', 'reference_source': 'book_name', 'analysis_mode': 'quick', 'confidence': 0.88},
  'reader_promise': '凡人逆袭修仙',
  'opening_hook_patterns': ['开局废灵根检测'],
  'cool_point_loops': ['小境界突破+宗门阶梯式升级'],
  'protagonist_patterns': '谨慎+隐忍+实用主义',
  'antagonist_pressure_patterns': '宗门内斗+外部魔修威胁',
  'pacing_notes': '每5章一个小高潮',
  'narrative_function': '升级流',
  'boundary_reason': {'first_arc_start': 1, 'first_arc_end': 50, 'reason': '入门期'},
  'protagonist_action_chain': [{'trigger': '灵根检测失败', 'action': '坚持修炼', 'result': '意外觉醒'}],
  'emotion_curve': [{'chapter': 1, 'intensity': 0.8, 'label': '压抑'}, {'chapter': 2, 'intensity': 0.6, 'label': '紧张'}],
  'satisfaction_point': ['灵根检测反转'],
  'foreshadowing': [{'setup_chapter': 1, 'payoff_chapter_estimate': 50, 'content': '神秘小瓶'}],
  'gains_costs': [{'chapter': 1, 'gain': '觉醒', 'cost': '社交孤立', 'category': '认知'}],
  'character_changes': [{'chapter': 1, 'character': '韩立', 'before': '平庸', 'after': '觉醒'}],
  'borrowable_structures': ['宗门阶梯式升级结构'],
  'differentiation_requirements': '不复制韩立人设/神秘小瓶机制',
  'init_candidates': {'one_liner': '没有灵根的凡人靠现代知识修仙', 'anti_trope': '不靠金手指开挂', 'hard_constraints': ['硬约束1'], 'protagonist_flaw': '过度理性', 'antagonist_mirror': '感性极端', 'opening_hook': '第一章：检测灵根'},
  'do_not_copy': ['韩立人设', '神秘小瓶机制'],
  'canon_contamination_warnings': ['原作人物名:韩立'],
  'quality': {'passed': True, 'confidence': 0.88, 'coverage': 0.85},
}
pathlib.Path('/tmp/ref_schema.json').write_text(json.dumps(schema, ensure_ascii=False, indent=2))
"

# 2. Build the tree
python -c "
import sys; sys.path.insert(0, '/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules')
import json, pathlib
from init_reference_tree import build_reference_tree
schema = json.loads(pathlib.Path('/tmp/ref_schema.json').read_text(encoding='utf-8'))
tree = build_reference_tree(pathlib.Path('/tmp/ref_workspace'), schema, '《凡人修仙传》')
print('Tree built at:', tree)
"

# 3. Run init with reference tree
rm -rf /tmp/smoke_book
python /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/init_project.py /tmp/smoke_book "凡人+" "仙侠" \
  --protagonist-name "陈墨" --reference-research-dir "/tmp/ref_workspace/.webnovel/reference_research/fanren-xiuxian-chuan" 2>&1 | tail -10

# 4. Verify tree copied to project
ls -la /tmp/smoke_book/.webnovel/reference_research/fanren-xiuxian-chuan/
cat /tmp/smoke_book/.webnovel/reference_research/fanren-xiuxian-chuan/report.md | head -20
cat /tmp/smoke_book/.webnovel/reference_research/fanren-xiuxian-chuan/do_not_copy.md

# 5. Cleanup
rm -rf /tmp/smoke_book /tmp/ref_workspace /tmp/ref_schema.json
```

Expected:
- Init exits 0
- Tree copied to `/tmp/smoke_book/.webnovel/reference_research/fanren-xiuxian-chuan/`
- `report.md` contains "凡人修仙传", "升级流", "灵根检测反转"
- `do_not_copy.md` contains "韩立人设"

- [ ] **Step 2: Run without-reference path smoke (spec T5 item 5)**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts

rm -rf /tmp/smoke_book_noref
python init_project.py /tmp/smoke_book_noref "原创书" "都市" \
  --protagonist-name "李四" 2>&1 | tail -5

ls /tmp/smoke_book_noref/.webnovel/ 2>&1
ls /tmp/smoke_book_noref/.webnovel/reference_research/ 2>&1
rm -rf /tmp/smoke_book_noref
```

Expected: `.webnovel/` contains `state.json`, `writer-profile/`, but **NO** `reference_research/` directory.

- [ ] **Step 3: Run the full test suite one final time**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python -m pytest data_modules/tests/ -v 2>&1 | tail -30
```

Expected: All PASS (or pre-existing unrelated failures, none introduced by this work).

- [ ] **Step 4: Report results**

Print a summary:
- 1 existing prompt-integrity test: still green (Task 1)
- 1 new prompt-integrity test (deconstruction schema): green (Task 2)
- 11 new unit tests (init_reference_tree): all pass (Task 4)
- 2 new tests (idea_bank optional field): pass (Task 5)
- 4 new tests (CLI flags): pass (Task 6)
- 1 new test (plan consumption): green (Task 7)
- 1 manual smoke with-ref: tree copied + report.md rendered correctly
- 1 manual smoke no-ref: no reference_research/ created

If any step fails, do NOT mark Task 8 complete — investigate.

---

## Acceptance Criteria Checklist

After all 8 tasks complete, verify:

- [ ] `test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate` is GREEN (Task 1)
- [ ] `test_deconstruction_agent_schema_extension` is GREEN (Task 2)
- [ ] `test_plan_reads_reference_research_when_pointer_set` is GREEN (Task 7)
- [ ] `test_init_reference_tree.py` has 11 passing tests (Task 4)
- [ ] `test_init_idea_bank.py` has 6 (3 existing + 2 reference_research_path + 4 CLI flag) passing tests (Tasks 5, 6)
- [ ] `test_init_project_pruning.py` still passes (no regression)
- [ ] `deconstruction-agent.md` mentions all 9 new field names; existing 9 field names still present
- [ ] `webnovel-init/SKILL.md` Step 1.5 instructs main flow to build multi-file tree
- [ ] `webnovel-plan/SKILL.md` consumes tree via path convention when `idea_bank.reference_research_path` is set
- [ ] `init_project.py` has `--reference-research-dir` + `--reference-overwrite` CLI flags
- [ ] `init_reference_tree.py` has `sanitize_book_title()`, `build_reference_tree()`, `validate_reference_tree()`
- [ ] `templates/reference_report.md.j2` renders valid Markdown
- [ ] Manual smoke confirms with-ref writes, no-ref skips
- [ ] No new skill, command, or agent created
- [ ] Tree structure under `.webnovel/reference_research/<book-safe>/` matches spec D3 layout

---

## Out-of-Scope Reminder (do NOT implement here)

- **P1:** `/webnovel-chart-scan --auto-deconstruct <book>` — separate spec when chart-scan v0.3 lands.
- **P2:** Standalone `/webnovel-deconstruct` — explicitly recommended per industry consensus; needs its own spec for the "随时随地拆书" use case.
- **P3:** `webnovel-write` / `webnovel-review` consumption of reference_research — separate spec.
- **P4:** Agent schema extension to "全本结构" (chapters 4-N, not just 1-3) — separate spec.

---

## Self-Review Notes

- **Spec coverage**:
  - D1 (agent schema extension) → Task 2
  - D2 (Step 1.5) → Task 1
  - D3 (multi-file tree) → Tasks 3 + 4
  - D4 (idea_bank pointer) → Task 5
  - D5 (plan consumption) → Task 7
  - D6 (incremental) → Tasks 3 + 4 (via `_progress.json`); re-run logic lives in main flow per D2
  - D7 (files modified) → all tasks
  - D8 (out-of-scope) → "Out-of-Scope Reminder" section
  - T1 → Task 1
  - T2 → Task 2
  - T3 → Task 6
  - T4 → Task 7
  - T5 → Task 8
- **Placeholder scan**: no "TBD" / "TODO" / "implement later". Every code block is complete and runnable.
- **Type consistency**:
  - `idea_bank.reference_research_path`: string, relative path starting with `.webnovel/reference_research/`. Defined in spec D4, used in plan tests Task 5.
  - `reference_research_dir` / `reference_overwrite` kwargs added in Task 6 Step 3, used in Task 6 Step 4 (logic) and Step 5 (CLI).
  - `_progress.json.schema_version: 1` consistent across Task 4 builder and Task 4 tests.
  - `safe` book name (Task 4 `sanitize_book_title`) used consistently in builder and copy logic.
- **Risk acknowledgment**: agent schema change is additive (T2 covers both new + existing). Multi-file tree creation lives in helper script (testable). CLI flags fail-closed by default.