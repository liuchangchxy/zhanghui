#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Story Pressure derivation and the continuity advisories built on top of it.

The planning pipeline had no step that asked "what does this story currently owe?" before
deciding what happens next, so the first plausible idea won by default. `story_pressure` derives
a compact, ranked digest from state that already exists; `plan_consistency.check_story_continuity`
verifies the outline's `**承接压力**` declaration against the same derivation.

These tests pin the two properties the whole design rests on:

* the digest is **deterministic and read-only** — same state in, same ids out, nothing written;
* the continuity check **only judges explicit declarations**, and its one heuristic (repeated
  chapter signature) stays quiet on a normal volume. A check that fires everywhere gets ignored.
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


def _state(**overrides) -> dict:
    state = {
        "progress": {
            "current_volume": 1,
            "current_chapter": 3,
            "chapter_status": {"1": "chapter_committed", "2": "chapter_committed"},
        },
        "story_craft": {
            "timed_locks": [
                {"id": "TL-001", "description": "拆站通告倒计时", "deadline_chapter": 6, "status": "active"},
                {"id": "TL-002", "description": "已解决的事", "deadline_chapter": 4, "status": "resolved"},
            ],
            "foreshadow_chain": [
                {
                    "id": "FS-001",
                    "content": "值班记录本上多出一行十年前的笔迹",
                    "buried_chapter": 2,
                    "expected_payoff_chapter": 5,
                    "status": "active",
                },
                {
                    "id": "FS-002",
                    "content": "第 9 章才埋的伏笔",
                    "buried_chapter": 9,
                    "expected_payoff_chapter": 12,
                    "status": "active",
                },
            ],
        },
        "plot_threads": {
            "foreshadowing": [
                {"loop_id": "L1", "content": "科长为什么要压这件事", "source_chapter": 1, "status": "open"}
            ]
        },
        "entity_state": {
            "xu_zhiyuan": {
                "stance": {
                    "liang_mu": "许知远承诺不写梁沐的名字",
                    "zheng_pei": "确认郑培知情程度超出职位范围",
                },
                "decision": "先自查，不惊动科长",
            }
        },
        "chapter_meta": {"2": {"sequel_decision": "梁沐说那天该在检修期"}},
    }
    state.update(overrides)
    return state


def _write_project(tmp_path: Path, state: dict) -> Path:
    root = tmp_path / "book"
    (root / ".webnovel").mkdir(parents=True, exist_ok=True)
    (root / "大纲").mkdir(parents=True, exist_ok=True)
    (root / "设定集").mkdir(parents=True, exist_ok=True)
    (root / ".webnovel" / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    (root / "大纲" / "总纲.md").write_text("# 总纲\n", encoding="utf-8")
    return root


# --------------------------------------------------------------------------- #
# digest derivation
# --------------------------------------------------------------------------- #


def test_digest_covers_every_pressure_source(tmp_path: Path):
    from data_modules.story_pressure import build_story_pressures, pressure_ids

    root = _write_project(tmp_path, _state())
    digest = build_story_pressures(root, 3, limit=20)
    ids = pressure_ids(digest)

    assert "TL-001" in ids  # timed lock, still active
    assert "FS-001" in ids  # foreshadow already buried
    assert "LO-L1" in ids  # open loop planted in ch1
    assert "CH-xu_zhiyuan-stance-liang_mu" in ids  # the promise
    assert "PREV-2" in ids  # previous chapter's hand-off


def test_inactive_and_future_pressures_are_excluded(tmp_path: Path):
    from data_modules.story_pressure import build_story_pressures, pressure_ids

    root = _write_project(tmp_path, _state())
    ids = pressure_ids(build_story_pressures(root, 3, limit=50))

    assert "TL-002" not in ids  # status: resolved
    assert "FS-002" not in ids  # buried at ch9, this is ch3 — not a pressure yet


def test_digest_is_read_only_and_deterministic(tmp_path: Path):
    from data_modules.story_pressure import build_story_pressures

    root = _write_project(tmp_path, _state())
    state_path = root / ".webnovel" / "state.json"
    before = state_path.read_text(encoding="utf-8")

    first = build_story_pressures(root, 3)
    second = build_story_pressures(root, 3)

    assert first == second
    assert state_path.read_text(encoding="utf-8") == before


def test_digest_is_compact_and_capped(tmp_path: Path):
    from data_modules.story_pressure import DEFAULT_LIMIT, build_story_pressures, format_pressure_block

    root = _write_project(tmp_path, _state())
    digest = build_story_pressures(root, 3)

    assert len(digest["pressures"]) <= DEFAULT_LIMIT
    assert len(format_pressure_block(digest)) < 2000


def test_deadline_that_is_due_soon_outranks_an_open_loop(tmp_path: Path):
    from data_modules.story_pressure import build_story_pressures

    root = _write_project(tmp_path, _state())
    ids = [item["id"] for item in build_story_pressures(root, 3)["pressures"]]

    # TL-001 is 3 chapters away; the open loop has no deadline.
    assert ids.index("TL-001") < ids.index("LO-L1")


def test_character_stance_outranks_generic_belief(tmp_path: Path):
    from data_modules.story_pressure import build_story_pressures

    state = _state()
    state["entity_state"]["xu_zhiyuan"]["belief"] = {"a": "天快下雨了", "b": "档案科很安静"}
    root = _write_project(tmp_path, state)
    ids = [item["id"] for item in build_story_pressures(root, 3)["pressures"]]

    # The commitment must not be crowded out by descriptive beliefs.
    assert "CH-xu_zhiyuan-stance-liang_mu" in ids
    assert ids.index("CH-xu_zhiyuan-stance-liang_mu") < len(ids)


def test_one_stance_dict_cannot_hide_every_decision(tmp_path: Path):
    """A protagonist with many stances must not crowd `decision` out of the digest.

    `decision` is the field that says what he intends to do next — the most actionable pressure
    in the file. Before the per-sub-field cap, three stances filled all four character slots and
    the digest contained no decision at all, at the default limit.
    """
    from data_modules.story_pressure import build_story_pressures, pressure_ids

    state = _state()
    state["entity_state"]["xu_zhiyuan"]["stance"] = {
        "anonymous_letter": "未上报；决定先自行核实",
        "liang_mu": "承诺不写名字、不传话",
        "zheng_pei": "确认郑培知情超出职位范围",
        "lao_zhou": "老周拒绝交纸",
    }
    state["entity_state"]["xu_zhiyuan"]["decision"] = {
        "verification_route": "去地方志办公室查公开《潮汐表》"
    }
    root = _write_project(tmp_path, state)
    ids = pressure_ids(build_story_pressures(root, 3))  # default limit

    assert "CH-xu_zhiyuan-decision-verification_route" in ids
    # ...and the cap still leaves room for the most urgent stance.
    assert any(i.startswith("CH-xu_zhiyuan-stance-") for i in ids)


def test_project_without_state_yields_an_empty_digest(tmp_path: Path):
    from data_modules.story_pressure import build_story_pressures

    root = tmp_path / "empty"
    (root / ".webnovel").mkdir(parents=True)
    digest = build_story_pressures(root, 1)

    assert digest["pressures"] == []
    assert digest["total_available"] == 0


# --------------------------------------------------------------------------- #
# outline declaration hand-off
# --------------------------------------------------------------------------- #


def test_outline_declaration_is_parsed_and_kept_out_of_writer_notes():
    from chapter_outline_loader import (
        extract_outline_residual_notes,
        parse_chapter_execution_directive,
    )

    section = (
        "## 第7章：复算\n\n"
        "**目标**：拿到逐时潮位。\n"
        "**承接压力**：FS-006、CH-xu_zhiyuan-stance-liang_mu、PREV-6\n"
        "**本章禁区**：不得让郑培当场承认\n"
    )
    directive = parse_chapter_execution_directive(section)

    # Kept verbatim: the line may carry annotations, and splitting it here would shred them.
    assert directive["story_pressures"] == "FS-006、CH-xu_zhiyuan-stance-liang_mu、PREV-6"
    # The planner-facing field must not leak into the Writer as free-form author notes.
    assert "承接压力" not in extract_outline_residual_notes(section)


@pytest.mark.parametrize(
    "raw, expected_ids, expected_deferral",
    [
        ("FS-006、PREV-6", ["FS-006", "PREV-6"], False),
        ("无", [], True),
        ("无（本章为过渡，暂缓：FS-006）", ["FS-006"], True),
        ("FS-006（第3章埋的）", ["FS-006"], False),
        ("CH-xu_zhiyuan-stance-liang_mu、TL-001", ["CH-xu_zhiyuan-stance-liang_mu", "TL-001"], False),
        # No separator between Chinese text and the id. `\b` would refuse these: Python counts
        # CJK ideographs as word characters, so there is no word boundary between `见` and `F`.
        # A planner writing `见FS-006` means FS-006, and must not be told it declared nothing.
        ("见FS-006", ["FS-006"], False),
        ("承接压力FS-006", ["FS-006"], False),
        # ...but a latin token that merely ends in the prefix is not an id.
        ("XFS-006", [], False),
        ("", [], False),
        (None, [], False),
    ],
)
def test_declaration_parser_survives_annotations(raw, expected_ids, expected_deferral):
    """规划者会加注解；注解不能变成「不存在的压力 ID」。"""
    from data_modules.plan_consistency import parse_declared_pressures

    ids, is_deferral = parse_declared_pressures(raw)
    assert ids == expected_ids
    assert is_deferral is expected_deferral


def test_a_lock_whose_deadline_is_already_accepted_is_not_a_live_debt(tmp_path: Path):
    """截止章已 accepted 但记录仍 active —— 是记录没更新，不是规划者要还的债。"""
    from data_modules.story_pressure import build_story_pressures

    state = _state()
    state["progress"]["chapter_status"] = {"1": "chapter_committed", "2": "chapter_committed",
                                           "3": "chapter_committed"}
    state["story_craft"]["timed_locks"].append(
        {"id": "TL-009", "description": "第3章内必须建立合作关系", "deadline_chapter": 3,
         "status": "active"}
    )
    root = _write_project(tmp_path, state)
    digest = build_story_pressures(root, 4, limit=50)
    by_id = {item["id"]: item for item in digest["pressures"]}

    assert by_id["TL-009"]["stale"] is True
    assert by_id["TL-001"]["stale"] is False
    # Never ranked above something the planner can still act on.
    ids = [item["id"] for item in digest["pressures"]]
    assert ids.index("TL-009") > ids.index("FS-001")


def test_stale_pressure_is_labelled_as_a_record_issue_not_a_debt(tmp_path: Path):
    from data_modules.story_pressure import build_story_pressures, format_pressure_block

    state = _state()
    state["progress"]["chapter_status"] = {"1": "chapter_committed", "2": "chapter_committed",
                                           "3": "chapter_committed"}
    state["story_craft"]["timed_locks"].append(
        {"id": "TL-009", "description": "第3章内必须建立合作关系", "deadline_chapter": 3,
         "status": "active"}
    )
    root = _write_project(tmp_path, state)
    block = format_pressure_block(build_story_pressures(root, 4, limit=50))

    assert "记录未更新" in block
    assert "已逾期" not in block


@pytest.mark.parametrize(
    "bad_state",
    [
        {"story_craft": {"timed_locks": {"not": "a list"}}},
        {"story_craft": {"foreshadow_chain": "nope"}},
        {"plot_threads": "nope"},
        {"plot_threads": {"foreshadowing": {"a": 1}}},
        {"entity_state": {"a": "a string"}},
        {"entity_state": []},
        {"chapter_meta": [1, 2, 3]},
        {"chapter_meta": {"2": "not a dict"}},
        {"progress": "x"},
        {"progress": {"chapter_status": ["1"]}},
        {"story_craft": None, "plot_threads": None, "entity_state": None},
    ],
)
def test_malformed_state_never_crashes(tmp_path: Path, bad_state: dict):
    """state.json 是作者/Agent 写的；一个形状错误不该让每次章节 prepare 都崩掉。"""
    from data_modules.plan_consistency import check_story_continuity
    from data_modules.story_pressure import build_story_pressures

    root = _write_project(tmp_path, bad_state)

    build_story_pressures(root, 1)
    findings, _ = check_story_continuity(root, {1: "## 第1章：标题\n\n**目标**：x\n"})


def test_pressure_ids_are_unique(tmp_path: Path):
    """两个来源若派生出同一个 id，按 id 去重的地方会静默丢条目。"""
    from data_modules.story_pressure import build_story_pressures

    state = _state()
    state["story_craft"]["timed_locks"].append(
        {"id": "TL-001", "description": "重复 id 的锁", "deadline_chapter": 9, "status": "active"}
    )
    root = _write_project(tmp_path, state)
    ids = [item["id"] for item in build_story_pressures(root, 3, limit=50)["pressures"]]

    assert len(ids) == len(set(ids)), ids


def test_non_utf8_state_file_degrades_instead_of_raising(tmp_path: Path):
    """编码错误的 state.json 不能让 plan-check 抛异常。"""
    from data_modules.story_pressure import build_story_pressures

    root = tmp_path / "book"
    (root / ".webnovel").mkdir(parents=True)
    (root / ".webnovel" / "state.json").write_bytes(
        json.dumps({"progress": {"current_chapter": 3}}, ensure_ascii=False).encode("gbk")
    )

    digest = build_story_pressures(root, 3)
    assert digest["pressures"] == []


@pytest.mark.parametrize("status", ["已解决", "完成", "complete", "已回收（第12章）"])
def test_canonical_resolved_statuses_are_recognised(tmp_path: Path, status: str):
    """项目自己的 state_validator 认这些写法；这里不能另立一套。"""
    from data_modules.story_pressure import build_story_pressures, pressure_ids

    state = _state()
    state["plot_threads"]["foreshadowing"][0]["status"] = status
    root = _write_project(tmp_path, state)

    assert "LO-L1" not in pressure_ids(build_story_pressures(root, 3, limit=50))


def test_open_loop_due_chapter_drives_ranking(tmp_path: Path):
    """未读 target_chapter 时所有 open loop 都算无期限，最该还的那条可能被挤掉。"""
    from data_modules.story_pressure import build_story_pressures

    state = _state()
    state["plot_threads"]["foreshadowing"] = [
        {"loop_id": "zzz_far", "content": "很久以后才需要的事", "source_chapter": 1,
         "target_chapter": 30, "status": "未回收"},
        {"loop_id": "aaa_due", "content": "下一章就该交代的事", "source_chapter": 1,
         "target_chapter": 4, "status": "未回收"},
    ]
    root = _write_project(tmp_path, state)
    ids = [item["id"] for item in build_story_pressures(root, 3, limit=50)["pressures"]]

    assert ids.index("LO-aaa_due") < ids.index("LO-zzz_far")


def test_duplicate_ids_keep_the_most_urgent_record(tmp_path: Path):
    """去重必须在排序之后，否则先被收集到的那条（可能最不重要）会赢。"""
    from data_modules.story_pressure import build_story_pressures

    state = _state()
    state["story_craft"]["timed_locks"] = [
        {"id": "TL-001", "description": "很久以后", "deadline_chapter": 20, "status": "active"},
        {"id": "TL-001", "description": "本章就该到", "deadline_chapter": 4, "status": "active"},
    ]
    root = _write_project(tmp_path, state)
    by_id = {item["id"]: item for item in build_story_pressures(root, 3, limit=50)["pressures"]}

    assert by_id["TL-001"]["text"] == "本章就该到"
