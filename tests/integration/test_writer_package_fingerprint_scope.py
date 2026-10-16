#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WriterPackage fingerprint scope tests (task H / M11).

The fingerprint decides whether an in-flight chapter's sealed inputs are still valid. It used
to hash the whole volume outline file and the whole `state.json`, so editing chapter 8's
outline invalidated chapter 2's package and any unrelated state touch forced a re-seal.

These tests pin both directions: real upstream changes must still invalidate, and unrelated
changes must not.
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


def _outline_text() -> str:
    lines = ["# 第 1 卷 详细大纲", "", "## 卷基本信息", "", "- **卷名**：潮痕", "", "---", ""]
    for num in range(1, 13):
        lines += [
            f"## 第{num}章：第{num}章标题",
            "",
            f"**目标**：第{num}章目标。",
            f"**阻力**：第{num}章阻力。",
            f"**本章变化**：第{num}章变化。",
            f"**本章禁区**：第{num}章禁区。",
            "",
            "**结构化节点**：",
            "",
            f"- **CBN**：主角 | 第{num}章开端 | 结果",
            f"- **CEN**：主角 | 第{num}章收束 | 结果",
            f"- **必须覆盖节点**：CBN + CEN",
            "",
            "---",
            "",
        ]
    return "\n".join(lines)


_INIT_DIRS = (".webnovel", ".webnovel/backups", ".webnovel/archive", ".webnovel/summaries",
              "设定集", "大纲", "正文", "审查报告", ".webnovel/tmp")
_INIT_FILES = ("设定集/世界观.md", "设定集/力量体系.md", "设定集/主角卡.md", "设定集/反派设计.md",
               "大纲/总纲.md", ".env.example")


def _project(tmp_path: Path) -> Path:
    for rel in _INIT_DIRS:
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)
    for rel in _INIT_FILES:
        (tmp_path / rel).write_text(f"# {rel}\n", encoding="utf-8")
    (tmp_path / "大纲" / "第1卷-详细大纲.md").write_text(_outline_text(), encoding="utf-8")
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps(
            {
                "project_info": {"title": "指纹书", "genre": "悬疑"},
                "progress": {
                    "current_volume": 1,
                    "current_chapter": 0,
                    "volumes_planned": [{"volume": 1, "chapters_range": "1-12", "title": "潮痕"}],
                },
                "chapter_meta": {"8": {"scene_goal": "第8章目标"}},
                "review_checkpoints": {},
                "protagonist_state": {"name": "许知远"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (tmp_path / ".story-system").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _edit_outline(root: Path, chapter: int, marker: str) -> None:
    path = root / "大纲" / "第1卷-详细大纲.md"
    text = path.read_text(encoding="utf-8")
    old = f"**目标**：第{chapter}章目标。"
    assert old in text
    path.write_text(text.replace(old, f"**目标**：第{chapter}章目标{marker}。"), encoding="utf-8")


def _fingerprints(root: Path, chapter: int) -> dict:
    from data_modules.chapter_runtime import ChapterRuntime

    return ChapterRuntime(root).compute_source_fingerprints(chapter)


def _edit_state(root: Path, mutate) -> None:
    path = root / ".webnovel" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    mutate(state)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# must invalidate
# --------------------------------------------------------------------------- #


def test_editing_the_current_chapter_outline_invalidates(tmp_path: Path):
    root = _project(tmp_path)
    before = _fingerprints(root, 2)
    _edit_outline(root, 2, "（改）")
    after = _fingerprints(root, 2)
    assert before["outline"] != after["outline"]


def test_editing_the_previous_chapter_outline_invalidates(tmp_path: Path):
    """第 N-1 章的 sequel_decision 是第 N 章目标的种子 —— 跨章失效必须保留（H5）。"""
    root = _project(tmp_path)
    before = _fingerprints(root, 2)
    _edit_outline(root, 1, "（改）")
    after = _fingerprints(root, 2)
    assert before["outline_prev"] != after["outline_prev"]


def test_editing_volume_level_preamble_invalidates(tmp_path: Path):
    root = _project(tmp_path)
    before = _fingerprints(root, 2)
    path = root / "大纲" / "第1卷-详细大纲.md"
    text = path.read_text(encoding="utf-8").replace("- **卷名**：潮痕", "- **卷名**：潮痕（改）")
    path.write_text(text, encoding="utf-8")
    after = _fingerprints(root, 2)
    assert before["outline_volume"] != after["outline_volume"]


def test_contract_change_invalidates(tmp_path: Path):
    root = _project(tmp_path)
    from data_modules.chapter_runtime import ChapterRuntime

    runtime = ChapterRuntime(root)
    runtime.prepare(chapter=2, with_package=False)
    before = runtime.compute_source_fingerprints(2)
    review_path = runtime.paths.review_json(2)
    if not review_path.is_file():
        pytest.skip("review contract not generated in this fixture")
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    payload["must_check"] = ["新增检查项"]
    review_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    after = runtime.compute_source_fingerprints(2)
    assert before["contracts"] != after["contracts"]


def test_new_accepted_commit_invalidates(tmp_path: Path, monkeypatch):
    """新的前序 accepted commit 必须让本章封口失效（Canon 变了，本章写作依据就变了）。"""
    from data_modules import chapter_runtime as runtime_module
    from data_modules.chapter_runtime import ChapterRuntime

    root = _project(tmp_path)
    runtime = ChapterRuntime(root)
    real_loader = runtime_module.load_runtime_sources
    before = runtime.compute_source_fingerprints(2)
    assert before["latest_commit"] == "none"

    class _Sources:
        latest_accepted_commit = {"chapter": 1, "status": "accepted", "commit_sha256": "deadbeef"}
        fallback_sources: list = []
        contracts: dict = {}

    monkeypatch.setattr(runtime_module, "load_runtime_sources", lambda *a, **k: _Sources())
    after = runtime.compute_source_fingerprints(2)
    assert after["latest_commit"] != before["latest_commit"]
    assert after["latest_commit"] != "none"

    monkeypatch.setattr(runtime_module, "load_runtime_sources", real_loader)
    assert runtime.compute_source_fingerprints(2) == before


def test_story_craft_change_invalidates(tmp_path: Path):
    """定时锁 / 伏笔链属于 Craft 约束，变化必须影响本章封口。"""
    root = _project(tmp_path)
    before = _fingerprints(root, 2)

    def mutate(state):
        state["story_craft"] = {"timed_locks": [{"id": "TL-004", "deadline_chapter": 2, "status": "active"}]}

    _edit_state(root, mutate)
    after = _fingerprints(root, 2)
    assert before["state"] != after["state"]


# --------------------------------------------------------------------------- #
# must NOT invalidate
# --------------------------------------------------------------------------- #


def test_editing_a_later_chapter_outline_does_not_invalidate(tmp_path: Path):
    """验收场景 F：修改第 8 章无关规划，第 2 章不发生无意义封口失效。"""
    root = _project(tmp_path)
    before = _fingerprints(root, 2)
    _edit_outline(root, 8, "（改）")
    after = _fingerprints(root, 2)
    assert before == after


def test_editing_a_far_later_chapter_outline_does_not_invalidate(tmp_path: Path):
    root = _project(tmp_path)
    before = _fingerprints(root, 3)
    _edit_outline(root, 12, "（改）")
    assert _fingerprints(root, 3) == before


def test_unrelated_state_changes_do_not_invalidate(tmp_path: Path):
    """另一章的 chapter_meta / 审查 checkpoint / 派生投影变化不应触发重封口。"""
    root = _project(tmp_path)
    before = _fingerprints(root, 2)

    def mutate(state):
        state["chapter_meta"]["8"] = {"scene_goal": "第8章目标（改）"}
        state["review_checkpoints"]["1"] = {"score": 96}
        state["protagonist_state"] = {"name": "许知远", "status": "已更新"}
        state["entity_state"] = {"xu": {"location": "旧潮位站"}}

    _edit_state(root, mutate)
    assert _fingerprints(root, 2) == before


def test_state_json_reformatting_does_not_invalidate(tmp_path: Path):
    """纯格式重建（缩进/键序）没有改变事实，不应产生无意义失效。"""
    root = _project(tmp_path)
    before = _fingerprints(root, 2)
    path = root / ".webnovel" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(state, ensure_ascii=False, indent=4, sort_keys=True), encoding="utf-8")
    assert _fingerprints(root, 2) == before


def test_other_chapter_edits_do_not_change_this_chapters_package_fingerprint(tmp_path: Path):
    """端到端：整份 package fingerprint 也只在真正相关变化时改变。"""
    from data_modules.chapter_runtime import ChapterRuntime

    root = _project(tmp_path)
    runtime = ChapterRuntime(root)
    before = runtime.compute_package_fingerprint(2, creative_brief="任务书")

    _edit_outline(root, 9, "（改）")
    assert runtime.compute_package_fingerprint(2, creative_brief="任务书") == before

    _edit_outline(root, 2, "（改）")
    assert runtime.compute_package_fingerprint(2, creative_brief="任务书") != before
