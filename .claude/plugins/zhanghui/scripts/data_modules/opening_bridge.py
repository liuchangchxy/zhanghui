#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only projection: what the *previous* chapter durably left behind.

The Opening Bridge is a one-scene instruction appended after the Context Agent has
finished the Creative Brief (Step 1B) and before Step 1C seals the Native Writer
Package. It needs exactly one input that the Context Agent is not asked to re-plan:
the previous chapter's **accepted** CHAPTER_COMMIT.

This module only reads. It never writes project state, never edits an outline, and
never asks a model anything. The commit it reads is validated by
`durable_projection.read_durable_commit`, and it must be the commit of chapter N-1
with ``meta.status == "accepted"``. If that commit is missing, rejected, or belongs
to a different chapter, the projection reports ``available: false`` and the write
flow continues unchanged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from .durable_projection import DurableCommitError, read_durable_commit
from .story_contracts import StoryContractPaths

SCHEMA_VERSION = "opening-bridge/v1"
BRIDGE_HEADER = "【开场承接】"
ORIGINAL_HEADER = "【原 Creative Brief】"
ACCEPTED_PREFIX = "上一章 accepted："
OPENING_PREFIX = "本章开场："
MAX_BRIDGE_CHARS = 220
SCOPE_LINE = (
    "作用范围仅限开场：完成这个回应后，继续执行下方原任务书；"
    "本章目标、阻力、代价、情节节点与结尾仍以下方原任务书为准。"
)
MAX_FACTS = 14
FACT_CHARS = 180
ENDING_CHARS = 700
SUMMARY_CHARS = 1200


def _rel(project_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(Path(project_root)))
    except ValueError:  # pragma: no cover - defensive
        return str(path)


def _clip(text: Any, limit: int) -> str:
    value = "" if text is None else str(text).strip()
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _entity_names(extraction: Dict[str, Any]) -> Dict[str, str]:
    names: Dict[str, str] = {}
    for item in extraction.get("entity_deltas") or []:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") or {}
        name = payload.get("name") if isinstance(payload, dict) else None
        if item.get("entity_id") and name:
            names[str(item["entity_id"])] = str(name)
    for item in extraction.get("entities_appeared") or []:
        if isinstance(item, dict) and item.get("id") and item["id"] not in names:
            mentions = item.get("mentions") or []
            if mentions:
                names[str(item["id"])] = str(mentions[0])
    return names


def _fact_from_event(event: Dict[str, Any], names: Dict[str, str]) -> Dict[str, str] | None:
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        return None
    subject = names.get(str(event.get("subject") or ""), str(event.get("subject") or ""))
    kind = str(event.get("event_type") or "")
    if kind == "character_state_changed":
        field = str(payload.get("field") or "")
        new = payload.get("new")
        if not str(new or "").strip():
            return None
        label = "动作/决定" if field.startswith("decision") else ("处境" if field.startswith(("location", "status")) else "状态")
        return {"kind": label, "subject": subject, "field": field, "text": _clip(new, FACT_CHARS)}
    if kind == "relationship_changed":
        return {
            "kind": "关系",
            "subject": subject,
            "field": "",
            "text": _clip(payload.get("change") or payload.get("new") or payload.get("description"), FACT_CHARS),
        }
    if kind == "open_loop_created":
        return {"kind": "未解问题", "subject": subject, "field": "", "text": _clip(payload.get("content"), FACT_CHARS)}
    if kind == "world_rule_revealed":
        return {"kind": "已建立规则", "subject": subject, "field": "", "text": _clip(payload.get("rule_content"), FACT_CHARS)}
    return None


def _unavailable(project_root: Path, chapter: int, reason: str, detail: str = "") -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "chapter": chapter,
        "previous_chapter": chapter - 1,
        "available": False,
        "reason": reason,
        "detail": detail,
        "project_root": _rel(project_root, project_root),
    }


def build_packet(project_root: str | Path, chapter: int) -> Dict[str, Any]:
    """Project chapter N-1's accepted commit into an opening-bridge packet.

    Returns ``available: False`` rather than raising when the previous chapter has no
    durable accepted commit; that is a normal pre-write state (e.g. the previous
    chapter is still in review) and must not block the existing flow.
    """
    root = Path(project_root).expanduser().resolve()
    chapter = int(chapter)
    if chapter <= 1:
        return _unavailable(root, chapter, "no_previous_chapter")

    previous = chapter - 1
    commit_path = StoryContractPaths.from_project_root(root).commit_json(previous)
    try:
        payload = read_durable_commit(root, previous)
    except DurableCommitError as exc:
        return _unavailable(root, chapter, "previous_chapter_not_accepted", str(exc))

    meta = payload.get("meta") or {}
    if int(meta.get("chapter") or 0) != previous or meta.get("status") != "accepted":
        return _unavailable(
            root,
            chapter,
            "previous_chapter_not_accepted",
            f"commit chapter={meta.get('chapter')} status={meta.get('status')}",
        )

    extraction = payload.get("extraction_result") or {}
    names = _entity_names(extraction)

    facts: List[Dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for event in extraction.get("accepted_events") or []:
        if not isinstance(event, dict):
            continue
        fact = _fact_from_event(event, names)
        if not fact or not fact["text"]:
            continue
        key = (fact["kind"], fact["subject"], fact["text"])
        if key in seen:
            continue
        seen.add(key)
        facts.append(fact)
        if len(facts) >= MAX_FACTS:
            break

    scenes = [s for s in (extraction.get("scenes") or []) if isinstance(s, dict)]
    ending = ""
    if scenes:
        last = max(scenes, key=lambda s: int(s.get("index") or 0))
        ending = _clip(last.get("content"), ENDING_CHARS)

    raw = commit_path.read_bytes() if commit_path.is_file() else b""
    return {
        "schema_version": SCHEMA_VERSION,
        "chapter": chapter,
        "previous_chapter": previous,
        "available": True,
        "reason": "",
        "source": {
            "commit_path": _rel(root, commit_path),
            "commit_sha256": hashlib.sha256(raw).hexdigest(),
            "status": "accepted",
        },
        "previous_summary": _clip(extraction.get("summary_text"), SUMMARY_CHARS),
        "accepted_facts": facts,
        "previous_ending": ending,
        "constraints": [
            "只能使用本包列出的事实；不得引入未列出的机构、栏目、流程、登记簿、定量数据或新人物。",
            "开场只回应一件事：谁在上一章做了什么/决定了什么/知道了什么，以及这件事在本章开场立刻引起的当场回应。",
            "回应必须由一个上一章已经存在的问题角色做出，或由本章原任务书已经存在的角色承受。",
            "不得改写本章目标、阻力、代价、情节节点与结尾；完成开场回应后继续执行原任务书。",
            "若本包没有可承接的事实，不要生成开场承接。",
        ],
    }


def compose_brief(brief: str, bridge_body: str) -> str:
    """Prepend a sealed opening-bridge block to an unmodified Creative Brief.

    The original brief is copied verbatim after ``ORIGINAL_HEADER``; nothing inside it
    is rewritten, shortened, or re-ordered. ``split_composed_brief`` recovers it
    exactly, which is how the write flow and tests prove "brief unchanged".
    """
    original = str(brief or "")
    body = str(bridge_body or "").strip()
    if not original.strip():
        raise ValueError("creative brief must be non-empty before an opening bridge can be attached")
    if not body:
        raise ValueError("opening bridge body must be non-empty")
    _check_bridge_body(body)
    return f"{BRIDGE_HEADER}\n{body}\n\n{SCOPE_LINE}\n\n{ORIGINAL_HEADER}\n{original}"


def _check_bridge_body(body: str) -> None:
    """Reject a body that could act as a second brief rather than an opening beat.

    This is a shape check, not a content gate: it does not judge the story. It exists so
    "the bridge only affects the opening" is enforced by the seal instead of relying on the
    orchestrator's discipline (independent audit, 2026-11-17).
    """
    if BRIDGE_HEADER in body or ORIGINAL_HEADER in body:
        raise ValueError("opening bridge body must not contain a section header")
    if SCOPE_LINE in body:
        raise ValueError("opening bridge body must not repeat the scope line")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if len(lines) > 2:
        raise ValueError(
            f"opening bridge body must be exactly the two bridge lines (got {len(lines)} non-empty lines); "
            "it is an opening beat, not a chapter plan"
        )
    if len(body) > MAX_BRIDGE_CHARS:
        raise ValueError(
            f"opening bridge body must be at most {MAX_BRIDGE_CHARS} characters (got {len(body)})"
        )
    if not any(line.startswith(ACCEPTED_PREFIX) for line in lines):
        raise ValueError(f"opening bridge body must contain a line starting with {ACCEPTED_PREFIX!r}")
    if not any(line.startswith(OPENING_PREFIX) for line in lines):
        raise ValueError(f"opening bridge body must contain a line starting with {OPENING_PREFIX!r}")


def split_composed_brief(text: str) -> tuple[str, str]:
    """Return ``(bridge_body, original_brief)``; raises when the text is not composed."""
    value = str(text or "")
    marker = f"\n\n{ORIGINAL_HEADER}\n"
    if not value.startswith(BRIDGE_HEADER) or marker not in value:
        raise ValueError("text is not a composed opening-bridge brief")
    head, original = value.split(marker, 1)
    body = head[len(BRIDGE_HEADER):].strip()
    if body.endswith(SCOPE_LINE):
        body = body[: -len(SCOPE_LINE)].strip()
    return body, original


def format_packet_text(packet: Dict[str, Any]) -> str:
    """Render the packet for a human/model reader. Deterministic, no invented text."""
    if not packet.get("available"):
        return ""
    lines: List[str] = [
        f"开场承接包（第 {packet['previous_chapter']} 章 → 第 {packet['chapter']} 章）",
        f"来源：{packet['source']['commit_path']}（accepted，sha256={packet['source']['commit_sha256'][:16]}…）",
        "",
        "一、上一章 accepted 摘要",
        packet.get("previous_summary") or "（无）",
        "",
        "二、上一章 accepted 具名事实",
    ]
    for fact in packet.get("accepted_facts") or []:
        subject = f"{fact['subject']} · " if fact.get("subject") else ""
        field = f"[{fact['field']}] " if fact.get("field") else ""
        lines.append(f"- [{fact['kind']}] {subject}{field}{fact['text']}")
    if not packet.get("accepted_facts"):
        lines.append("- （无）")
    lines.extend(["", "三、上一章结尾（accepted 场景原文）", packet.get("previous_ending") or "（无）"])
    lines.extend(["", "四、约束"])
    lines.extend(f"- {item}" for item in packet.get("constraints") or [])
    return "\n".join(lines).strip() + "\n"
