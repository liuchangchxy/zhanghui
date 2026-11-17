#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Opening Bridge: read-only projection + verbatim brief composition.

These tests pin the two properties the mechanism depends on:
1. the projection reads *only* chapter N-1's durable accepted commit (no fallback to an
   older accepted chapter, no draft, no extraction file, nothing from chapter >= N);
2. attaching a bridge leaves the Context Agent's Creative Brief byte-for-byte intact.
"""

import json
from pathlib import Path

import pytest

from data_modules.chapter_commit_service import ChapterCommitService
from data_modules.opening_bridge import (
    BRIDGE_HEADER,
    ORIGINAL_HEADER,
    SCOPE_LINE,
    build_packet,
    compose_brief,
    format_packet_text,
    split_composed_brief,
)
from data_modules.tests.commit_helpers import build_commit_with_reconciliation


def _write_commit(project_root: Path, payload: dict) -> Path:
    target = project_root / ".story-system" / "commits"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"chapter_{int(payload['meta']['chapter']):03d}.commit.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _commit(project_root: Path, chapter: int, *, events=None, scenes=None, summary=""):
    service = ChapterCommitService(project_root)
    payload = build_commit_with_reconciliation(
        service,
        chapter=chapter,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={
            "accepted_events": events or [],
            "state_deltas": [],
            "entity_deltas": [{"entity_id": "xu", "action": "upsert", "entity_type": "角色", "payload": {"name": "许知远"}}],
            "scenes": scenes or [],
            "summary_text": summary,
        },
    )
    assert payload and payload["meta"]["status"] == "accepted"
    _write_commit(project_root, payload)


def _reject_commit(project_root: Path, chapter: int) -> None:
    service = ChapterCommitService(project_root)
    payload = build_commit_with_reconciliation(
        service,
        chapter=chapter,
        review_result={"blocking_count": 0},
        fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )
    assert payload is not None
    payload["meta"]["status"] = "rejected"
    _write_commit(project_root, payload)


def test_unavailable_when_previous_chapter_has_no_commit(tmp_path):
    packet = build_packet(tmp_path, 7)
    assert packet["available"] is False
    assert packet["reason"] == "previous_chapter_not_accepted"
    assert format_packet_text(packet) == ""


def test_no_fallback_to_an_older_accepted_chapter(tmp_path):
    _commit(tmp_path, 4, summary="第四章")
    _reject_commit(tmp_path, 5)
    packet = build_packet(tmp_path, 6)
    assert packet["available"] is False, "a rejected chapter 5 must not fall back to accepted chapter 4"
    assert packet["previous_chapter"] == 5


def test_reads_accepted_facts_from_the_previous_commit_only(tmp_path):
    _commit(
        tmp_path,
        6,
        events=[
            {
                "event_id": "evt-ch6-001",
                "chapter": 6,
                "event_type": "character_state_changed",
                "subject": "xu",
                "payload": {"field": "decision.verification_route", "old": "", "new": "递了调阅申请，被驳回"},
            }
        ],
        scenes=[{"index": 1, "content": "结尾原文"}],
        summary="第六章摘要",
    )
    _commit(
        tmp_path,
        7,
        events=[
            {
                "event_id": "evt-ch7-001",
                "chapter": 7,
                "event_type": "character_state_changed",
                "subject": "xu",
                "payload": {"field": "decision.future", "old": "", "new": "下一章才知道的事"},
            }
        ],
        summary="第七章摘要：不许出现",
    )

    packet = build_packet(tmp_path, 7)
    assert packet["available"] is True
    assert packet["source"]["commit_path"].endswith("chapter_006.commit.json")
    assert packet["source"]["status"] == "accepted"
    assert len(packet["source"]["commit_sha256"]) == 64
    text = format_packet_text(packet)
    assert "递了调阅申请，被驳回" in text
    assert "结尾原文" in text
    assert "下一章才知道的事" not in text
    assert "第七章摘要" not in text
    assert "许知远" in text, "entity ids must be rendered as names"


def test_packet_does_not_read_uncommitted_extraction_file(tmp_path):
    (tmp_path / ".webnovel" / "tmp").mkdir(parents=True)
    (tmp_path / ".webnovel" / "tmp" / "extraction_result.json").write_text(
        json.dumps({"summary_text": "未提交提取"}, ensure_ascii=False), encoding="utf-8"
    )
    packet = build_packet(tmp_path, 3)
    assert packet["available"] is False
    assert "未提交提取" not in format_packet_text(packet)


def test_chapter_one_has_no_bridge(tmp_path):
    packet = build_packet(tmp_path, 1)
    assert packet["available"] is False
    assert packet["reason"] == "no_previous_chapter"


def test_compose_brief_keeps_the_original_brief_verbatim():
    brief = "1. 开篇委托\n2. 这章的故事\n   - 本章目标：仍然执行原计划\n3. 收在哪里"
    body = "上一章 accepted：许知远递交了调阅申请。\n本章开场：郑培把申请退回来，追问一句。"
    composed = compose_brief(brief, body)

    assert composed.startswith(BRIDGE_HEADER)
    assert SCOPE_LINE in composed
    assert f"{ORIGINAL_HEADER}\n{brief}" in composed
    assert composed.index(BRIDGE_HEADER) < composed.index(ORIGINAL_HEADER)
    recovered_body, recovered_brief = split_composed_brief(composed)
    assert recovered_brief == brief
    assert recovered_body == body


def test_compose_brief_fails_closed_on_empty_bridge():
    with pytest.raises(ValueError):
        compose_brief("原任务书", "  \n ")


def test_compose_brief_fails_closed_on_empty_brief():
    with pytest.raises(ValueError):
        compose_brief("", "上一章 accepted：x\n本章开场：y")


@pytest.mark.parametrize(
    "body, reason",
    [
        ("【原 Creative Brief】\n上一章 accepted：x\n本章开场：y", "section header"),
        ("上一章 accepted：x\n本章开场：y\n\n二、这章的故事\n他去做另一件事。", "second-brief body"),
        ("上一章 accepted：x\n本章开场：y\n" + "很长的一段计划。" * 40, "too long"),
        ("只有一句没有格式的话。", "missing the two required prefixes"),
        ("上一章 accepted：x", "missing the opening line"),
    ],
)
def test_compose_brief_rejects_a_body_that_could_be_a_second_brief(body, reason):
    """The bridge must stay an opening beat; the seal enforces the shape, not the orchestrator."""
    with pytest.raises(ValueError):
        compose_brief("原任务书", body)
