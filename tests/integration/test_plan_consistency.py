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


# --------------------------------------------------------------------------- #
# story continuity (advisory)
# --------------------------------------------------------------------------- #


def _write_state(tmp_path: Path, state: dict) -> None:
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )


def _pressure_state() -> dict:
    return {
        "progress": {"current_volume": 1, "current_chapter": 2,
                     "chapter_status": {"1": "chapter_committed"}},
        "story_craft": {
            "timed_locks": [
                {"id": "TL-001", "description": "拆站通告倒计时", "deadline_chapter": 6, "status": "active"}
            ],
            "foreshadow_chain": [
                {"id": "FS-001", "content": "值班记录本上多出一行十年前的笔迹",
                 "buried_chapter": 1, "expected_payoff_chapter": 5, "status": "active"}
            ],
        },
        "entity_state": {"xu_zhiyuan": {"stance": {"liang_mu": "许知远承诺不写梁沐的名字"}}},
        "chapter_meta": {"1": {"sequel_decision": "梁沐说那天该在检修期"}},
    }


def _continuity(report: dict, code: str) -> list[dict]:
    return [item for item in report["advisories"] if item["code"] == code]


def test_declared_pressure_is_accepted(tmp_path: Path):
    from data_modules.plan_consistency import run_plan_consistency

    _write_state(tmp_path, _pressure_state())
    chapters = {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2, 3)}
    chapters[2] = chapters[2].replace(
        "**本章变化**", "**承接压力**：FS-001、PREV-1\n**本章变化**", 1
    )
    _write_outline(tmp_path, chapters)

    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 3))
    assert report["ok"] is True
    assert _continuity(report, "story_pressure_unknown") == []
    # Once the convention is in use, the chapters that skipped it are named individually —
    # that per-chapter signal is the whole point. Chapter 2 declared, and chapter 1 is already
    # accepted (its prose is frozen, so it cannot be asked to add the line).
    undeclared = _continuity(report, "story_pressure_not_declared")
    assert [item["chapter"] for item in undeclared] == [3]


def test_unknown_pressure_id_is_reported(tmp_path: Path):
    """声明了不存在的 ID，说明声明与真实故事状态脱节。"""
    from data_modules.plan_consistency import run_plan_consistency

    _write_state(tmp_path, _pressure_state())
    chapters = {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2, 3)}
    chapters[2] = chapters[2].replace(
        "**本章变化**", "**承接压力**：FS-999\n**本章变化**", 1
    )
    _write_outline(tmp_path, chapters)

    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 3))
    unknown = _continuity(report, "story_pressure_unknown")
    assert len(unknown) == 1
    assert unknown[0]["chapter"] == 2
    assert "FS-999" in unknown[0]["message"]
    assert report["ok"] is True  # advisory, never a blocker


def test_low_ranked_but_real_pressure_is_allowed_with_a_note(tmp_path: Path):
    """规划者可以有意取一条低优先级压力；存在即通过，只是提醒确认。"""
    from data_modules.plan_consistency import run_plan_consistency

    _write_state(tmp_path, _pressure_state())
    chapters = {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2, 3)}
    chapters[2] = chapters[2].replace(
        "**本章变化**", "**承接压力**：CH-xu_zhiyuan-stance-liang_mu\n**本章变化**", 1
    )
    _write_outline(tmp_path, chapters)

    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 3))
    assert _continuity(report, "story_pressure_unknown") == []


def test_a_volume_that_never_used_the_convention_is_not_nagged(tmp_path: Path):
    """约定启用前规划的旧卷不该被逐章刷屏 —— 那样检查会被学会忽略。"""
    from data_modules.plan_consistency import run_plan_consistency

    _write_state(tmp_path, _pressure_state())
    _write_outline(tmp_path, {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2, 3)})

    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 3))
    assert _continuity(report, "story_pressure_not_declared") == []
    assert report["ok"] is True


def test_once_the_convention_is_used_the_skipped_chapters_are_named(tmp_path: Path):
    """只要有一章声明了，剩下的章就必须说明它是暂缓还是没看。"""
    from data_modules.plan_consistency import run_plan_consistency

    _write_state(tmp_path, _pressure_state())
    chapters = {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2, 3)}
    chapters[1] = chapters[1].replace(
        "**本章变化**", "**承接压力**：FS-001\n**本章变化**", 1
    )
    _write_outline(tmp_path, chapters)

    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 3))
    undeclared = _continuity(report, "story_pressure_not_declared")
    assert [item["chapter"] for item in undeclared] == [2, 3]
    assert undeclared[0]["evidence"]["offered_sample"]
    assert report["ok"] is True


def test_no_derivable_pressure_means_no_nagging(tmp_path: Path):
    """没有已提交故事状态的项目，不该被要求声明它根本没有的压力。"""
    from data_modules.plan_consistency import run_plan_consistency

    _write_state(tmp_path, {"progress": {"current_volume": 1}})
    _write_outline(tmp_path, {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2, 3)})

    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 3))
    assert _continuity(report, "story_pressure_not_declared") == []


def _cast_chapter(num: int, actor: str, *, other: str | None = None) -> str:
    text = _chapter(num, goal=f"第{num}章目标")
    text = text.replace(f"{num}号角色 | 第{num}章开端 | 结果", f"{actor} | 第{num}章开端 | 结果")
    text = text.replace(f"{num}号角色 | 第{num}章收束 | 结果", f"{other or actor} | 第{num}章收束 | 结果")
    return text


def test_repeated_solo_investigation_is_flagged_once(tmp_path: Path):
    """同一角色独自推进的结构在 5 章内出现 3 次 —— 这是真实的模式重复。"""
    from data_modules.plan_consistency import run_plan_consistency

    _write_state(tmp_path, _pressure_state())  # chapter 1 already accepted
    chapters = {
        1: _cast_chapter(1, "许知远"),
        2: _cast_chapter(2, "许知远"),
        3: _cast_chapter(3, "许知远"),
        4: _cast_chapter(4, "梁沐"),
        5: _cast_chapter(5, "许知远"),
        6: _cast_chapter(6, "郑培"),
        7: _cast_chapter(7, "许知远"),
    }
    _write_outline(tmp_path, chapters)

    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 7))
    repeated = _continuity(report, "story_structure_repeated")
    assert len(repeated) == 1
    assert repeated[0]["evidence"]["chapters"] == [2, 3, 5, 7]
    assert report["ok"] is True


def test_a_rut_confined_to_accepted_chapters_is_not_reported(tmp_path: Path):
    """已 accepted 的章改不了，报它只是噪声。"""
    from data_modules.plan_consistency import run_plan_consistency

    _write_state(tmp_path, _pressure_state())
    chapters = {
        1: _cast_chapter(1, "许知远"),
        2: _cast_chapter(2, "许知远"),
        3: _cast_chapter(3, "梁沐", other="老周"),
        4: _cast_chapter(4, "许知远"),
    }
    _write_outline(tmp_path, chapters)

    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 4))
    assert _continuity(report, "story_structure_repeated") == []


def test_different_casts_are_not_a_repeat(tmp_path: Path):
    """连续多章都是多人戏，但出场人物各不相同 —— 不是重复。"""
    from data_modules.plan_consistency import run_plan_consistency

    _write_state(tmp_path, _pressure_state())
    chapters = {
        1: _cast_chapter(1, "许知远", other="老周"),
        2: _cast_chapter(2, "许知远", other="梁沐"),
        3: _cast_chapter(3, "许知远", other="郑培"),
        4: _cast_chapter(4, "许知远", other="科长"),
    }
    _write_outline(tmp_path, chapters)

    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 4))
    assert _continuity(report, "story_structure_repeated") == []


def test_report_exposes_the_offered_pressures(tmp_path: Path):
    """报告要能说明规划者当时被提供了什么，否则无法判断章节是否脱节。"""
    from data_modules.plan_consistency import run_plan_consistency

    _write_state(tmp_path, _pressure_state())
    _write_outline(tmp_path, {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2, 3)})

    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 3))
    offered = report["story_pressures"]
    assert [item["chapter"] for item in offered] == [1, 2, 3]
    assert "FS-001" in offered[1]["offered"]
    assert offered[1]["total_available"] >= 1


def test_a_malformed_node_does_not_invent_a_cast_member(tmp_path: Path):
    """`；` 切开 CPN 时会把散文留在第一段；那不是角色名，不能拿来当出场人物。"""
    from data_modules.plan_consistency import chapter_signature

    prose = "许知远 | 抄下条款 | 确认记录本不在清单内；铁门漆上的号比 009 小"
    signature = chapter_signature(
        {"cbn": "许知远 | 开端 | 结果", "cpns": [prose], "cen": "许知远 | 收束 | 结果"}
    )
    assert signature == ("solo", frozenset({"许知远"}))


def test_node_without_pipes_is_ignored(tmp_path: Path):
    from data_modules.plan_consistency import chapter_signature

    signature = chapter_signature({"cbn": "许知远独自去站里", "cpns": [], "cen": "他离开"})
    assert signature == ("unknown", frozenset())


def test_deliberate_deferral_is_not_a_false_unknown_id(tmp_path: Path):
    """「无（…暂缓：FS-001）」是有意暂缓，不是写了不存在的 ID。"""
    from data_modules.plan_consistency import run_plan_consistency

    _write_state(tmp_path, _pressure_state())
    chapters = {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2, 3)}
    chapters[2] = chapters[2].replace(
        "**本章变化**", "**承接压力**：无（本章为过渡，暂缓：FS-001）\n**本章变化**", 1
    )
    _write_outline(tmp_path, chapters)

    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 3))
    assert _continuity(report, "story_pressure_unknown") == []
    # The deferral counts as having looked: chapter 2 is not in the "never looked" bucket.
    # Chapter 1 is already accepted and therefore exempt.
    undeclared = _continuity(report, "story_pressure_not_declared")
    assert [item["chapter"] for item in undeclared] == [3]


def test_annotated_declaration_is_not_a_false_unknown_id(tmp_path: Path):
    from data_modules.plan_consistency import run_plan_consistency

    _write_state(tmp_path, _pressure_state())
    chapters = {n: _chapter(n, goal=f"第{n}章目标") for n in (1, 2, 3)}
    chapters[2] = chapters[2].replace(
        "**本章变化**", "**承接压力**：FS-001（第1章埋的）\n**本章变化**", 1
    )
    _write_outline(tmp_path, chapters)

    report = run_plan_consistency(tmp_path, volume=1, expected_range=(1, 3))
    assert _continuity(report, "story_pressure_unknown") == []


def test_zero_padded_chapter_meta_still_yields_the_previous_consequence(tmp_path: Path):
    """`chapter_meta` 的键由 state_manager 写成 "0001"；普通 str(chapter) 查不到。"""
    from data_modules.story_pressure import build_story_pressures, pressure_ids

    state = _pressure_state()
    state["chapter_meta"] = {"0001": {"sequel_decision": "梁沐说那天该在检修期"}}
    _write_state(tmp_path, state)

    ids = pressure_ids(build_story_pressures(tmp_path, 2, limit=50))
    assert "PREV-1" in ids
