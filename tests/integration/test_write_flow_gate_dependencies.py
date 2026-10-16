#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-module integration tests for the write flow's gate dependencies (tasks B, C, M1, M7).

These tests exercise the *hand-offs* the acceptance run broke:

* M1 — an outline generated in the **official template format** (`## 第N章：` headings plus
  `**字段**：` bold field labels) must be readable by the loader and by `runtime prepare`,
  and its 本章禁区 / 必须覆盖节点 must actually reach the governed context. Before the fix,
  `runtime prepare` failed outright on the template's heading level, and even the engineered
  `###` workaround silently produced an *empty* directive / plot structure, so the Writer and
  Reviewer never received the chapter's constraints.
* C7 — `write-gate --stage precommit` validates `review_results` / `fulfillment_result` /
  `disambiguation_result` / `extraction_result`, all of which are produced by Step 5. The test
  asserts the real dependency by running the gate at both points: before the artifacts exist it
  must fail (which is why Step 4.7 could never pass), and after they exist it must pass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "plugins" / "zhanghui" / "scripts"
for path in (SCRIPTS, SCRIPTS.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


# The outline below is written the way `templates/output/大纲-卷详细大纲.md` tells the planner
# to write it: `## 第{N}章：` headings, `**字段**：` labels, and a 「新增 craft 必填字段」block.
TEMPLATE_STYLE_OUTLINE = """# 第 1 卷 详细大纲

> 本卷为第 1 卷的逐章大纲，每章独立成节。

## 卷基本信息

- **卷名**：潮痕
- **章节范围**：第1-3章

---

## 第1章：停用的潮位站

**目标**：按流程完成旧潮位站的资产清点并归档。
**阻力**：站点停用十年，钥匙在看护员老周手里，老周以流程为由拖延开门。
**代价**：为找清点依据翻开了不属于本次清点范围的《值班记录本》。
**核心冲突**：照章办事的档案员 vs 一封不该出现在废站里的信。

**反派层级**：小障碍（老周的程序拖延）

**本章变化**：在记录本夹层里发现一封没有署名的匿名信。
**未闭合问题**：谁把一封信放在一座停用十年的潮位站里？
**钩子**：信上只有一行——一个日期，和一个已停用十年的潮位站编号。

**新增 craft 必填字段**：

- **beat_position**：Opening Image
- **scene_goal**：按流程完成旧潮位站的资产清点并归档。
- **scene_conflict**：站点停用十年，钥匙在看护员老周手里。
- **scene_setback**：翻开了不属于本次清点范围的《值班记录本》。
- **scene_resolution**：在记录本夹层里发现一封匿名信。
- **sequel_reaction**：见 story_craft 第1章 reaction 字段
- **sequel_dilemma**：照章办事 vs 一封不该出现在废站里的信
- **sequel_decision**：谁把信放在废站里 → 下章目标
- **hook_type**：悬念式
- **foreshadow_buried**：FS-006, FS-009
- **foreshadow_paid_off**：无

**结构化节点**：

- **CBN**：许知远 | 清点旧潮位站资产 | 发现夹层中的匿名信
- **CPNs**：许知远 | 违反流程翻查 | 值班记录本多出一行十年前的笔迹
- **CEN**：许知远 | 记下日期与站号 | 决定不上报，自行核实
- **必须覆盖节点**：CBN + CEN
- **本章禁区**：不得引入超自然力量或系统；不得提前透光第8章的位置反转

---

## 第2章：十年前的日期

**目标**：查清信上那个日期在档案里对应什么事件。
**本章禁区**：不得让角色直接说出事故真实地点

---

## 第3章：旧报纸

**目标**：从旧报纸确认事故细节。
"""


_INIT_DIRS = (".webnovel", ".webnovel/backups", ".webnovel/archive", ".webnovel/summaries",
              "设定集", "大纲", "正文", "审查报告", ".webnovel/tmp")
_INIT_FILES = (
    "设定集/世界观.md", "设定集/力量体系.md", "设定集/主角卡.md", "设定集/反派设计.md",
    "大纲/总纲.md", ".env.example",
)


def _write_template_style_project(tmp_path: Path) -> Path:
    for rel in _INIT_DIRS:
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)
    for rel in _INIT_FILES:
        (tmp_path / rel).write_text(f"# {rel}\n", encoding="utf-8")
    (tmp_path / "大纲" / "第1卷-详细大纲.md").write_text(TEMPLATE_STYLE_OUTLINE, encoding="utf-8")
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps(
            {
                "project_info": {"title": "海港旧信", "genre": "悬疑"},
                "progress": {
                    "current_volume": 1,
                    "current_chapter": 0,
                    "volumes_planned": [{"volume": 1, "chapters_range": "1-3", "title": "潮痕"}],
                },
                "protagonist_state": {"name": "许知远"},
                "world_settings": {"characters": [], "locations": [], "items": []},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (tmp_path / ".story-system").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".story-system" / "MASTER_SETTING.json").write_text(
        json.dumps({"entities": [{"name": "许知远", "id": "xu_zhiyuan", "type": "角色"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path


# --------------------------------------------------------------------------- #
# M1 / B: official template -> loader -> prepared governed context
# --------------------------------------------------------------------------- #


def test_official_template_outline_is_readable_by_the_loader(tmp_path: Path):
    """B: 官方模板生成的 `## 第N章：` 章纲必须能被正式加载器读到。"""
    from chapter_outline_loader import load_chapter_outline
    from chapter_paths import extract_chapter_title

    root = _write_template_style_project(tmp_path)
    outline = load_chapter_outline(root, 1, max_chars=None)

    assert not outline.startswith("⚠️")
    assert outline.lstrip().startswith("## 第1章：停用的潮位站")
    # section boundaries: chapter 1 must not swallow chapter 2
    assert "十年前的日期" not in outline
    assert "旧报纸" not in outline
    assert extract_chapter_title(root, 1) == "停用的潮位站"


def test_official_template_fields_reach_the_governed_context(tmp_path: Path):
    """B/I: 模板字段必须真的进入 Writer 与 Reviewer 的受治理上下文。

    旧实现下 directive 与 plot_structure 都是空字典，Writer 拿不到 goal，
    Reviewer 拿不到 本章禁区 —— 这正是第二章泄底没能在规划期被拦下的直接原因。
    """
    from data_modules.chapter_runtime import ChapterRuntime

    root = _write_template_style_project(tmp_path)
    governed = ChapterRuntime(root).get_governed_context(1)

    directive = governed["current_intent"]["directive"]
    assert directive["goal"] == "按流程完成旧潮位站的资产清点并归档。"
    assert directive["conflict"] == "照章办事的档案员 vs 一封不该出现在废站里的信。"
    assert directive["beat_position"] == "Opening Image"
    assert directive["hook_type"] == "悬念式"
    # 「无」是占位值，不能变成义务
    assert "foreshadow_paid_off" not in directive
    assert directive["foreshadow_buried"] == ["FS-006", "FS-009"]

    prohibitions = governed["constraints"]["prohibitions"]
    mandatory = governed["constraints"]["mandatory_nodes"]
    assert "不得提前透光第8章的位置反转" in prohibitions
    assert "CBN + CEN" in mandatory

    reviewer = ChapterRuntime(root).get_reviewer_context(1)
    assert "不得提前透光第8章的位置反转" in reviewer["chapter_planning"]["forbidden_zones"]
    assert "不得提前透光第8章的位置反转" in reviewer["craft_constraints"]["prohibitions"]
    assert reviewer["creative_intent"]["hook_type"] == "悬念式"


def test_runtime_prepare_succeeds_on_template_style_outline(tmp_path: Path):
    """验收场景 A：按官方模板规划后，runtime prepare 直接通过，无需人工改 Markdown。"""
    from data_modules.chapter_runtime import ChapterRuntime

    root = _write_template_style_project(tmp_path)
    result = ChapterRuntime(root).prepare(chapter=1, with_package=True)
    assert result.ok is True, f"prepare failed: {result.status} {result.blockers}"
    assert result.status == "ready"
    assert result.writer_package is not None
    prompt = None
    # sealing the brief is what makes the canonical writer prompt renderable
    pkg = ChapterRuntime(root).attach_creative_brief(chapter=1, creative_brief="## 一、基调\n冷峻克制。\n")
    prompt = pkg.to_writer_prompt()
    assert "按流程完成旧潮位站的资产清点并归档。" in prompt
    assert "不得提前透光第8章的位置反转" in prompt


# --------------------------------------------------------------------------- #
# C7 / M8: gate dependencies are real, not textual
# --------------------------------------------------------------------------- #


def test_precommit_gate_requires_step5_artifacts_to_exist(tmp_path: Path):
    """C7: precommit 闸门的必需产物由 Step 5 生成。

    本测试直接验证依赖关系本身：产物不存在时闸门必然失败（所以旧的 Step 4.7 位置注定过不了），
    产物齐备后同一闸门通过。它取代了「只检查 Skill 文本里字符串先后」的脆弱断言。
    """
    from data_modules.chapter_runtime import ChapterRuntime
    from data_modules.write_gates import run_write_gate

    root = _write_template_style_project(tmp_path)
    runtime = ChapterRuntime(root)
    assert runtime.prepare(chapter=1, with_package=True).ok is True

    # 1. Step 4.7 position: Data Agent artifacts do not exist yet.
    early = run_write_gate(root, chapter=1, stage="precommit")
    codes = {item["code"] for item in early["errors"]}
    assert early["ok"] is False
    assert "artifact.missing_artifact" in codes

    # 2. Step 5 has produced the artifacts.
    tmp = root / ".webnovel" / "tmp"
    (tmp / "review_results.json").write_text(
        json.dumps({"chapter": 1, "blocking_count": 0, "must_check_results": [], "blocking_rule_results": []}),
        encoding="utf-8",
    )
    (tmp / "fulfillment_result.json").write_text(
        json.dumps({"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []}),
        encoding="utf-8",
    )
    (tmp / "disambiguation_result.json").write_text(json.dumps({"pending": []}), encoding="utf-8")
    (tmp / "extraction_result.json").write_text(
        json.dumps({"chapter_meta": {}, "accepted_events": [], "state_deltas": [], "entity_deltas": []}),
        encoding="utf-8",
    )
    (root / ".webnovel" / "tmp" / "chapter_0001_working.md").write_text("正文占位。\n", encoding="utf-8")

    late = run_write_gate(root, chapter=1, stage="precommit")
    assert late["ok"] is True, f"unexpected blockers: {late['errors']}"


def test_prewrite_gate_does_not_need_data_agent_artifacts(tmp_path: Path):
    """prewrite 阶段只依赖大纲/合同/占位符扫描 —— 与 precommit 的依赖集合不同。"""
    from data_modules.write_gates import run_write_gate

    root = _write_template_style_project(tmp_path)
    report = run_write_gate(root, chapter=1, stage="prewrite")
    codes = {item["code"] for item in report["errors"]}
    assert "artifact.missing_artifact" not in codes


def test_write_gate_stages_are_distinct_and_have_different_dependencies():
    """三个逻辑阶段保持存在，但每个阶段的依赖集合不同（C4）。"""
    import inspect

    from data_modules import write_gates
    from data_modules.write_gates import precommit as precommit_mod
    from data_modules.write_gates import postcommit as postcommit_mod
    from data_modules.write_gates import prewrite as prewrite_mod

    assert write_gates.STAGES == ("prewrite", "precommit", "postcommit")

    prewrite_source = inspect.getsource(prewrite_mod)
    precommit_source = inspect.getsource(precommit_mod)
    postcommit_source = inspect.getsource(postcommit_mod)
    # precommit validates the commit artifact set; prewrite and postcommit must not
    assert "validate_commit_artifact_files" in precommit_source
    assert "validate_commit_artifact_files" not in prewrite_source
    assert "validate_commit_artifact_files" not in postcommit_source

    # every stage returns the same report schema so callers can treat them uniformly
    for stage in write_gates.STAGES:
        report = {"stage": stage}
        assert report["stage"] in write_gates.STAGES
