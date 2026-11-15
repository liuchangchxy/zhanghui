#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Planning-stage consistency tests (task I / I6).

The reference acceptance run lost a whole chapter rewrite because chapter 2's outline asserted
the chapter-8 location reveal, and nothing checked that at planning time. The checks here
distinguish clearly between:

* deterministic structural problems (numbering, required fields, timeline monotonicity), which
  are blockers, and
* information leakage, which is only reported against an **explicit** protection declaration —
  the author's own outline reference to a later chapter's reveal, or an entry in
  `.webnovel/intent/reveal_protection.json`. Un-declared semantic leakage is deliberately not
  guessed at; the check prints candidates for confirmation instead.
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


def _chapter(
    num: int,
    *,
    goal: str,
    change: str | None = None,
    prohibitions: str = "不得引入超自然力量",
) -> str:
    lines = [
        f"## 第{num}章：第{num}章标题",
        "",
        f"**目标**：{goal}",
        f"**阻力**：第{num}章阻力。",
        f"**核心冲突**：第{num}章冲突。",
        f"**本章变化**：{change or f'第{num}章变化。'}",
        f"**钩子**：第{num}章钩子。",
        "",
        "**新增 craft 必填字段**：",
        "",
        f"- **beat_position**：Setup",
        f"- **hook_type**：悬念式",
        f"- **scene_goal**：{goal}",
        f"- **scene_conflict**：第{num}章冲突。",
        f"- **sequel_decision**：第{num}章决定。",
        "",
        "**结构化节点**：",
        "",
        f"- **CBN**：{num}号角色 | 第{num}章开端 | 结果",
        f"- **CEN**：{num}号角色 | 第{num}章收束 | 结果",
        f"- **必须覆盖节点**：CBN + CEN",
        f"- **本章禁区**：{prohibitions}",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def _filler(up_to: int, exclude: set[int]) -> dict[int, str]:
    """A realistic volume: boilerplate repeats across chapters, reveals do not."""
    return {
        n: _chapter(n, goal=f"第{n}章目标。")
        for n in range(1, up_to + 1)
        if n not in exclude
    }


def _write_outline(tmp_path: Path, chapters: dict[int, str], *, order: list[int] | None = None) -> Path:
    (tmp_path / "大纲").mkdir(parents=True, exist_ok=True)
    (tmp_path / "设定集").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    text = "# 第 1 卷 详细大纲\n\n## 卷基本信息\n\n- **卷名**：测试卷\n\n---\n\n"
    sequence = order if order is not None else sorted(chapters)
    text += "\n".join(chapters[num] for num in sequence)
    path = tmp_path / "大纲" / "第1卷-详细大纲.md"
    path.write_text(text, encoding="utf-8")
    (tmp_path / "大纲" / "总纲.md").write_text("# 总纲\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# deterministic structural checks
# --------------------------------------------------------------------------- #


def test_structural_checks_pass_on_a_clean_outline(tmp_path: Path):
    from data_modules.plan_consistency import run_plan_consistency

    _write_outline(tmp_path, {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2, 3)})
    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 3))

    assert report["ok"] is True
    assert report["policy_action"] == "ALLOW"
    assert report["chapters_found"] == [1, 2, 3]


def test_missing_chapter_is_a_blocker(tmp_path: Path):
    from data_modules.plan_consistency import run_plan_consistency

    _write_outline(tmp_path, {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 3)})
    report = run_plan_consistency(tmp_path, volume=1)

    assert report["ok"] is False
    codes = {item["code"] for item in report["blockers"]}
    assert "outline_chapter_gaps" in codes


def test_out_of_order_chapters_are_a_blocker(tmp_path: Path):
    from data_modules.plan_consistency import run_plan_consistency

    _write_outline(
        tmp_path, {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2)}, order=[2, 1]
    )
    report = run_plan_consistency(tmp_path, volume=1)
    codes = {item["code"] for item in report["blockers"]}
    assert "outline_out_of_order" in codes


def test_missing_required_fields_are_a_blocker(tmp_path: Path):
    from data_modules.plan_consistency import run_plan_consistency

    bare = "## 第1章：缺字段\n\n**目标**：只有一个目标。\n\n---\n\n"
    _write_outline(tmp_path, {1: bare})
    report = run_plan_consistency(tmp_path, volume=1)

    assert report["ok"] is False
    finding = next(item for item in report["blockers"] if item["code"] == "outline_chapter_missing_fields")
    assert finding["chapter"] == 1
    assert "本章禁区" in finding["evidence"]["missing"]
    assert finding["options"]


def test_timeline_monotonicity(tmp_path: Path):
    from data_modules.plan_consistency import parse_timeline_anchors, run_plan_consistency

    _write_outline(tmp_path, {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2, 3)})
    (tmp_path / "大纲" / "第1卷-时间线.md").write_text(
        "\n".join(
            [
                "| 章 | 时间锚点 |",
                "|---|---|",
                "| 第1章 | D-30 清晨 |",
                "| 第2章 | D-28 傍晚 |",
                "| 第3章 | D-31 上午 |",
            ]
        ),
        encoding="utf-8",
    )
    anchors = parse_timeline_anchors((tmp_path / "大纲" / "第1卷-时间线.md").read_text(encoding="utf-8"))
    assert anchors == [(1, -30), (2, -28), (3, -31)]

    report = run_plan_consistency(tmp_path, volume=1)
    finding = next(item for item in report["blockers"] if item["code"] == "timeline_not_monotonic")
    assert finding["chapter"] == 3


# --------------------------------------------------------------------------- #
# reveal protection (I6: the chapter-2 / chapter-8 case)
# --------------------------------------------------------------------------- #

# chapter 2 the way it was written *before* the acceptance fix: it states the location that
# chapter 8 is supposed to reveal.
LEAKY_CH2 = _chapter(
    2,
    goal="从旧报纸确认日期正是旧航道事故当天。",
    change="确认该日期正是旧航道事故当天。",
)
FIXED_CH2 = _chapter(
    2,
    goal="从公开地方志与旧报纸确认该日期对应一起船舶事故（公开记载未载明地点）。",
    change="确认该日期对应一起船舶事故，公开记载未载明地点。",
)
CH8 = _chapter(
    8,
    goal="用潮位差反推事故船当夜可能的船位。",
    change="三个可能位置里只有一个落在旧航道。",
    prohibitions="不得直接说出结论",
)


def test_declared_protection_flags_the_leaking_early_chapter(tmp_path: Path):
    """I6 回归样例：早期章纲写出后期反转的地名时，规划期必须给出冲突证据与裁决选项。"""
    from data_modules.plan_consistency import run_plan_consistency

    leaky = LEAKY_CH2.replace(
        "确认该日期正是旧航道事故当天。",
        "确认该日期正是旧航道事故当天（为第8章位置反转保留）。",
        1,
    )
    _write_outline(tmp_path, {**_filler(8, {2, 8}), 2: leaky, 8: CH8})

    report = run_plan_consistency(tmp_path, volume=1)

    leaks = [item for item in report["advisories"] if item["code"] == "intent_reveal_leak"]
    assert leaks, report
    finding = leaks[0]
    assert finding["chapter"] == 2
    assert finding["evidence"]["revealed_at_chapter"] == 8
    assert "旧航道" in finding["evidence"]["term"]
    assert finding["evidence"]["early_line"]
    assert len(finding["options"]) >= 2


def test_author_maintained_protection_file_flags_existing_projects(tmp_path: Path):
    """已有项目可以显式登记反转保护，而不必改章纲措辞。"""
    from data_modules.plan_consistency import run_plan_consistency

    _write_outline(tmp_path, {**_filler(8, {2, 8}), 2: LEAKY_CH2, 8: CH8})
    protection_dir = tmp_path / ".webnovel" / "intent"
    protection_dir.mkdir(parents=True, exist_ok=True)
    (protection_dir / "reveal_protection.json").write_text(
        json.dumps(
            {"protections": [{"term": "旧航道", "revealed_at_chapter": 8, "source": "作者确认"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = run_plan_consistency(tmp_path, volume=1)
    leaks = [item for item in report["advisories"] if item["code"] == "intent_reveal_leak"]
    assert leaks
    assert leaks[0]["chapter"] == 2


def test_fixed_chapter_does_not_flag(tmp_path: Path):
    from data_modules.plan_consistency import run_plan_consistency

    declared = FIXED_CH2.replace(
        "确认该日期对应一起船舶事故，公开记载未载明地点。",
        "确认该日期对应一起船舶事故，公开记载未载明地点（为第8章位置反转保留）。",
        1,
    )
    _write_outline(tmp_path, {**_filler(8, {2, 8}), 2: declared, 8: CH8})

    report = run_plan_consistency(tmp_path, volume=1)
    assert [item for item in report["advisories"] if item["code"] == "intent_reveal_leak"] == []


def test_undeclared_semantic_leak_is_not_guessed(tmp_path: Path):
    """未声明的语义泄露不下判断 —— 只给候选清单，避免制造假门禁。"""
    from data_modules.plan_consistency import run_plan_consistency

    _write_outline(tmp_path, {**_filler(8, {2, 8}), 2: LEAKY_CH2, 8: CH8})

    report = run_plan_consistency(tmp_path, volume=1)
    assert [item for item in report["advisories"] if item["code"] == "intent_reveal_leak"] == []
    assert "candidate_protection_note" in report


def test_common_names_and_boilerplate_never_flagged(tmp_path: Path):
    """角色名与模板套话不能被当成反转词。"""
    from data_modules.plan_consistency import derive_candidate_protections, run_plan_consistency

    sections = {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2, 3, 8)}  # noqa: E501
    (tmp_path / "大纲").mkdir(parents=True, exist_ok=True)
    (tmp_path / "设定集").mkdir(parents=True, exist_ok=True)
    (tmp_path / "设定集" / "世界观.md").write_text(
        "第8章真相：主角许知远其实一直在查这件事。\n", encoding="utf-8"
    )
    terms = {item["term"] for item in derive_candidate_protections(tmp_path, sections)}
    assert "许知远" not in terms
    assert "下章目标" not in terms
