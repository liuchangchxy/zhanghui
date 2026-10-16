#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Timed-lock closure tests (task K / M10).

A timed lock is a **planning obligation** (Intent): "must happen by chapter N". It is not a
Canon fact, so closing it needs official evidence — an accepted chapter, optionally pinned to
an exact quote from the published prose. In the real acceptance run TL-004 was fulfilled by
chapter 1 but stayed `active`, so the Reviewer kept reporting it as overdue in chapter 2, and
there was no command to close it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "plugins" / "zhanghui" / "scripts"
for path in (SCRIPTS, SCRIPTS.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _state(locks: list[dict] | None = None) -> dict:
    return {
        "story_craft": {
            "timed_locks": locks
            if locks is not None
            else [
                {
                    "id": "TL-004",
                    "description": "第1章内主角必须接触到匿名信",
                    "trigger_chapter": None,
                    "deadline_chapter": 1,
                    "status": "active",
                    "fulfilled_chapter": None,
                }
            ]
        }
    }


def test_first_fulfillment_marks_the_lock_and_records_evidence():
    from story_craft import fulfill_timed_lock

    state = _state()
    fulfill_timed_lock(state, "TL-004", 1, evidence="夹层里的一封信", evidence_sha256="abc123")

    lock = state["story_craft"]["timed_locks"][0]
    assert lock["status"] == "fulfilled"
    assert lock["fulfilled_chapter"] == 1
    assert lock["fulfilled_evidence"] == "夹层里的一封信"
    assert lock["fulfilled_evidence_sha256"] == "abc123"


def test_repeat_fulfillment_is_idempotent_for_the_same_chapter():
    from story_craft import fulfill_timed_lock

    state = _state()
    fulfill_timed_lock(state, "TL-004", 1)
    before = json.dumps(state, ensure_ascii=False, sort_keys=True)
    fulfill_timed_lock(state, "TL-004", 1)
    assert json.dumps(state, ensure_ascii=False, sort_keys=True) == before


def test_fulfillment_refuses_to_re_point_at_another_chapter():
    from story_craft import fulfill_timed_lock

    state = _state()
    fulfill_timed_lock(state, "TL-004", 1)
    with pytest.raises(ValueError):
        fulfill_timed_lock(state, "TL-004", 3)


def test_unknown_lock_is_rejected():
    from story_craft import fulfill_timed_lock

    with pytest.raises(ValueError):
        fulfill_timed_lock(_state(), "TL-999", 1)


def test_fulfilled_locks_are_not_reported_as_overdue():
    from story_craft import check_timed_lock_deadlines, fulfill_timed_lock

    state = _state(
        [
            {"id": "TL-004", "deadline_chapter": 1, "status": "active", "fulfilled_chapter": None},
            {"id": "TL-005", "deadline_chapter": 6, "status": "active", "fulfilled_chapter": None},
        ]
    )
    fulfill_timed_lock(state, "TL-004", 1)

    overdue = check_timed_lock_deadlines(state, current_chapter=2)
    assert [lock["id"] for lock in overdue] == []  # TL-005 deadline is 6, not yet due

    overdue_later = check_timed_lock_deadlines(state, current_chapter=7)
    assert [lock["id"] for lock in overdue_later] == ["TL-005"]


def test_rollback_restores_an_active_lock():
    """K8: 回滚/恢复到兑现前状态后，锁必须重新被判为 active。"""
    from story_craft import check_timed_lock_deadlines, fulfill_timed_lock

    state = _state()
    fulfill_timed_lock(state, "TL-004", 1)
    assert check_timed_lock_deadlines(state, current_chapter=2) == []

    snapshot = json.dumps(state, ensure_ascii=False)
    restored = json.loads(snapshot)
    restored["story_craft"]["timed_locks"][0]["status"] = "active"
    restored["story_craft"]["timed_locks"][0]["fulfilled_chapter"] = None
    assert [lock["id"] for lock in check_timed_lock_deadlines(restored, current_chapter=2)] == ["TL-004"]


# --------------------------------------------------------------------------- #
# CLI-level: evidence must come from an accepted chapter
# --------------------------------------------------------------------------- #

_INIT_DIRS = (".webnovel", ".webnovel/backups", ".webnovel/archive", ".webnovel/summaries",
              "设定集", "大纲", "正文", "审查报告", ".webnovel/tmp")
_INIT_FILES = ("设定集/世界观.md", "设定集/力量体系.md", "设定集/主角卡.md", "设定集/反派设计.md",
               "大纲/总纲.md", ".env.example")

PROSE_QUOTE = "他在记录本的夹层里摸到了一封信。"

OUTLINE = """# 第一卷 潮痕

### 第1章：停用的潮位站
- 目标：按流程完成旧潮位站的资产清点并归档
- 阻力：老周以流程为由拖延开门
- 必须覆盖节点：清点、发现匿名信
- 本章禁区：不得引入超自然力量
"""

PROSE = f"""许知远推开旧潮位站的铁门，灰尘在阳光里浮起来。
{PROSE_QUOTE}
他记下了日期，和一个已停用十年的潮位站编号。

<chapter_changes>
{{
  "character_state_changes": [
    {{"character_id": "xu_zhiyuan", "change_type": "status_update", "importance": "normal", "details": "发现匿名信"}}
  ],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}}
</chapter_changes>"""


def _project(tmp_path: Path, *, accepted: bool) -> Path:
    """Build a real project; when `accepted`, drive the genuine commit chain for chapter 1."""
    for rel in _INIT_DIRS:
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)
    for rel in _INIT_FILES:
        (tmp_path / rel).write_text(f"# {rel}\n", encoding="utf-8")
    (tmp_path / "大纲" / "第1卷-详细大纲.md").write_text(OUTLINE, encoding="utf-8")
    for name in ("第1卷-节拍表.md", "第1卷-时间线.md"):
        (tmp_path / "大纲" / name).write_text("# 内容\n", encoding="utf-8")
    state = {
        "project_info": {"title": "海港旧信", "genre": "悬疑"},
        "progress": {"current_volume": 1, "current_chapter": 0,
                     "volumes_planned": [{"volume": 1, "chapters_range": "1-24", "title": "潮痕"}]},
        "protagonist_state": {"name": "许知远"},
        "chapter_meta": {
            "2": {
                "beat_position": "Theme Stated",
                "hook_type": "悬念式",
                "scene_goal": "查清信上那个日期对应什么事件",
                "scene_conflict": "卷宗标注限制查阅",
                "scene_setback": "调阅被驳回",
                "scene_resolution": "改用公开资料",
                "sequel_reaction": "意识到信指向一件已被收口的事",
                "sequel_dilemma": "走关系 vs 走流程",
                "sequel_decision": "先从公开资料入手",
            }
        },
        "story_craft": _state()["story_craft"],
        "entity_state": {},
        "world_settings": {"characters": [], "locations": [], "items": []},
    }
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (tmp_path / ".story-system").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".story-system" / "MASTER_SETTING.json").write_text(
        json.dumps({"entities": [{"name": "许知远", "id": "xu_zhiyuan", "type": "角色"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    from story_craft import init_volume_beat

    init_volume_beat(state, volume=1, total_chapters=24)
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if accepted:
        # the commit chain must run before any prose exists under 正文/, otherwise the runtime
        # (correctly) refuses to regenerate foundational contracts for an "existing story"
        _commit_chapter_one(tmp_path)
    (tmp_path / "正文" / "第0001章-停用的潮位站.md").write_text(
        f"许知远推开旧潮位站的铁门。\n{PROSE_QUOTE}\n他记下了日期。\n", encoding="utf-8"
    )
    return tmp_path


def _commit_chapter_one(root: Path) -> None:
    """Run the real prepare -> ingest -> commit chain so the durable commit is genuinely valid."""
    from data_modules.chapter_runtime import ChapterRuntime
    from data_modules.reconciliation import reconcile_changes, split_chapter_and_changes

    runtime = ChapterRuntime(root)
    prep = runtime.prepare(chapter=1, with_package=True)
    assert prep.ok is True, prep.blockers
    pkg = runtime.attach_creative_brief(chapter=1, creative_brief="## 一、基调\n冷峻克制。\n")
    ingest = runtime.ingest_draft(chapter=1, prose=PROSE, package_fingerprint=pkg.package_fingerprint)
    assert ingest.ok is True, ingest.error

    _, proposal = split_chapter_and_changes(PROSE)
    extraction_result = {
        "chapter_meta": {},
        "accepted_events": [
            {"event_type": "character_state_changed", "subject": "xu_zhiyuan",
             "summary": "发现匿名信", "payload": {"status": "发现匿名信"}}
        ],
        "state_deltas": [],
        "entity_deltas": [{"entity_id": "xu_zhiyuan", "current": {"identity": "档案管理员"}}],
    }
    result = runtime.commit(
        chapter=1,
        draft_id=ingest.draft_id,
        review_result={"chapter": 1, "blocking_count": 0, "must_check_results": [], "blocking_rule_results": []},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result=extraction_result,
        reconciliation_result=reconcile_changes(proposal, extraction_result, chapter_text=PROSE),
    )
    assert result.ok is True, f"{result.error_code}: {result.error}"
    assert result.chapter_outcome == "accepted"


def _run_cli(root: Path, *argv: str):
    """Drive the real CLI entry point in a subprocess (third test layer: real CLI integration)."""
    import subprocess

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + str(SCRIPTS.parent) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPTS / "webnovel.py"), "--project-root", str(root), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )

    class _Result:
        returncode = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr

    return _Result()


def test_cli_refuses_without_an_accepted_commit(tmp_path: Path):
    root = _project(tmp_path, accepted=False)
    result = _run_cli(root, "story-craft", "fulfill-lock", "--lock-id", "TL-004", "--chapter", "1")
    assert result.returncode == 1
    assert "没有已接受的正式提交" in result.stderr
    # state untouched
    state = json.loads((root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["story_craft"]["timed_locks"][0]["status"] == "active"


def test_cli_refuses_unverifiable_evidence(tmp_path: Path):
    root = _project(tmp_path, accepted=True)
    result = _run_cli(
        root, "story-craft", "fulfill-lock", "--lock-id", "TL-004", "--chapter", "1",
        "--evidence", "正文里根本没有这句话",
    )
    assert result.returncode == 1
    assert "找不到" in result.stderr


def test_cli_fulfills_with_verified_evidence_and_is_idempotent(tmp_path: Path):
    root = _project(tmp_path, accepted=True)
    result = _run_cli(
        root, "story-craft", "fulfill-lock", "--lock-id", "TL-004", "--chapter", "1",
        "--evidence", PROSE_QUOTE,
    )
    assert result.returncode == 0, result.stderr
    state = json.loads((root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    lock = state["story_craft"]["timed_locks"][0]
    assert lock["status"] == "fulfilled"
    assert lock["fulfilled_chapter"] == 1
    assert lock["fulfilled_evidence_sha256"]

    first = json.dumps(state, ensure_ascii=False, sort_keys=True)
    repeat = _run_cli(
        root, "story-craft", "fulfill-lock", "--lock-id", "TL-004", "--chapter", "1",
        "--evidence", PROSE_QUOTE,
    )
    assert repeat.returncode == 0
    second = (root / ".webnovel" / "state.json").read_text(encoding="utf-8")
    assert json.loads(second)["story_craft"]["timed_locks"][0]["fulfilled_chapter"] == 1
    assert json.loads(second)["story_craft"]["timed_locks"][0]["status"] == "fulfilled"
    assert first == json.dumps(json.loads(second), ensure_ascii=False, sort_keys=True)


def test_check_volume_points_at_the_fulfillment_command(tmp_path: Path):
    """K5: 截止章已接受时，闸门要给出可执行的兑现裁决路径。"""
    root = _project(tmp_path, accepted=True)
    result = _run_cli(root, "story-craft", "check-volume", "--volume", "1", "--chapter", "2")
    assert result.returncode == 0, result.stderr
    assert "fulfill-lock" in result.stdout
    assert "TL-004" in result.stdout
