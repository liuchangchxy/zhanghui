#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Story Pressure — the missing bridge between accepted story state and next-chapter planning.

The planning pipeline used to have no step that asked *"what does this story currently owe?"*
before deciding what happens next. `/webnovel-plan` Step 7 could read state.json, entity state
and open loops, but nothing required it to turn them into "what should happen next", so the
first plausible idea won by default.

This module derives a **compact, deterministic** pressure digest from data that already exists:

  * ``story_craft.timed_locks``            — deadlines the volume has committed to
  * ``story_craft.foreshadow_chain``       — buried foreshadows with a planned payoff chapter
  * ``plot_threads.foreshadowing``         — accepted open loops not yet paid off
  * ``entity_state.<id>.stance/decision/belief/warning_status``
                                           — character commitments, unresolved decisions, risk
  * ``chapter_meta.<prev>.sequel_decision``— the consequence the previous chapter handed forward

No LLM, no scoring model, no new store. The digest is *input for the planner's judgement*, not
a checklist for the Writer: it is deliberately not rendered into the Writer prompt.

Design notes:

* **Compact by construction.** Each item is clipped and the list is capped, so the digest adds a
  few hundred characters rather than a Canon dump.
* **Ranked, not exhaustive.** Anything with a deadline near the current chapter, plus every
  character commitment/risk, outranks generic open loops. A pressure the planner ignores is
  fine — the goal explicitly allows deferring a pressure. What is *not* fine is planning a
  chapter that engages none of them while adding an unrelated event, and that is what
  ``plan_consistency`` can now notice.
* **Deterministic ids.** ``TL-001`` / ``FS-003`` / ``LO-<loop_id>`` / ``CH-<entity>-<kind>-<key>``
  / ``PREV-<n>`` are stable across runs, so a chapter outline can *declare* which pressure it
  engages and the checker can verify the declaration against the same derivation.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    from .state_validator import (
        FORESHADOWING_TARGET_KEYS,
        get_chapter_meta_entry,
        is_resolved_foreshadowing_status,
        resolve_chapter_field,
        to_positive_int,
    )
except ImportError:  # pragma: no cover
    from data_modules.state_validator import (
        FORESHADOWING_TARGET_KEYS,
        get_chapter_meta_entry,
        is_resolved_foreshadowing_status,
        resolve_chapter_field,
        to_positive_int,
    )

SCHEMA_VERSION = "story-pressure/v1"

# How many pressures a planner should be asked to consider. Small on purpose: the point is to
# help the planner decide, not to lengthen the prompt.
DEFAULT_LIMIT = 8

# Per-item text cap. Long evidence strings in entity_state run to thousands of characters and
# would defeat the "compact digest" requirement.
_ITEM_TEXT_CAP = 140

# A dated pressure counts as "due soon" when its payoff/deadline falls within this many chapters.
# Without this band, every dated foreshadow outranks every character obligation, and the digest
# silently loses exactly the material the planner most needs.
_DUE_SOON_CHAPTERS = 3

# Character sub-priority. `stance` is what the protagonist has *promised or owes another person*
# — the class of pressure the earlier experiment showed the planner never saw. Beliefs and
# procedural bookkeeping are context, not obligations, so they rank below and are capped harder.
_CHARACTER_FIELD_PRIORITY = {
    "stance": 0,
    "warning_status": 1,
    "decision": 2,
    "procedure_compliance": 3,
    "belief": 4,
}

# Per-kind slots in the digest. Without a cap one entity's `decision` dict can fill every slot
# and hide the previous chapter's hand-off entirely.
_KIND_QUOTA = {
    "previous_consequence": 1,
    "deadline": 2,
    "character": 4,
    "foreshadow": 2,
    "open_loop": 1,
}

# How many slots one *sub-field* of `entity_state` may take inside the `character` quota.
# A protagonist with three `stance` entries would otherwise consume the whole character budget
# and hide every `decision` — including the one that says what he plans to do next, which is the
# most actionable pressure in the file. Two keeps the most important stances visible while
# guaranteeing that a different field can still surface.
_CHARACTER_FIELD_QUOTA = 2

# Timed-lock statuses that are *not* covered by the foreshadow resolver above. A lock also has
# domain-specific settlement words (`paid`, `fulfilled`) that the foreshadow vocabulary lacks, so
# the two are checked together in `_is_active`.
_LOCK_SETTLED_STATUSES = frozenset(
    {"paid", "paid_off", "paid-off", "fulfilled", "closed", "回收", "已兑现", "已支付"}
)

# Fields of entity_state that describe an *obligation carried forward* rather than a fact.
_CHARACTER_PRESSURE_FIELDS = ("stance", "decision", "belief", "warning_status", "procedure_compliance")


@dataclass
class StoryPressure:
    """One thing the story currently owes, in planner-facing language."""

    id: str
    kind: str
    text: str
    source: str
    planted_chapter: Optional[int] = None
    deadline_chapter: Optional[int] = None
    remaining: Optional[int] = None
    related_chapters: List[int] = field(default_factory=list)
    priority: int = 0
    # Which sub-field of `entity_state` this came from (`stance` / `decision` / ...). Used only to
    # stop one sub-field from monopolising the character quota; empty for non-character pressures.
    sub_field: str = ""
    # True when the deadline sits at or before the last accepted chapter but the source record is
    # still marked active. Whatever happened, happened in prose that is already frozen, so a future
    # chapter cannot act on it. We do **not** decide whether the obligation was met — that is a
    # semantic judgement this module refuses to make. The flag only says "this record has not been
    # updated", which is a fact about the data, and it keeps the item from being rendered as a
    # live "已逾期" debt the planner must now discharge.
    stale: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "source": self.source,
            "planted_chapter": self.planted_chapter,
            "deadline_chapter": self.deadline_chapter,
            "remaining": self.remaining,
            "related_chapters": list(self.related_chapters),
            "priority": self.priority,
            "stale": self.stale,
            "sub_field": self.sub_field,
        }


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


_ID_UNSAFE_RE = re.compile(r"[^A-Za-z0-9_.\-]")


def _clip_id(text: Any, cap: int = 60) -> str:
    """Bound an id built from user-supplied strings, and keep it in the charset ids are read in.

    `LO-<loop_id>` / `CH-<entity>-<field>-<key>` interpolate arbitrary project data straight into
    an id, and ids reach the `plan-check` report and the outline declaration. A pathological key
    would otherwise propagate unbounded. The cap is far above any real entity or field name.

    The charset matters as much as the length: `plan_consistency` reads declared ids with a
    latin-only pattern (`CH-xu_zhiyuan-stance-liang_mu`). A Chinese entity id or a full-width
    parenthesis would emit an id the parser could never match, so the planner's *correct*
    declaration would come back as "declared nothing" — or, worse, as a truncated bogus id.
    Latin runs are kept readable; anything else is folded to `_` and pinned with a short digest
    of the original so two different Chinese names cannot collapse onto one declaration id.
    """
    raw = str(text or "").strip()
    value = re.sub(r"\s+", "_", raw)
    if _ID_UNSAFE_RE.search(value):
        cleaned = re.sub(r"_{2,}", "_", _ID_UNSAFE_RE.sub("_", value)).strip("_")
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]
        value = f"{cleaned[: cap - 7]}-{digest}" if cleaned else digest
    return value[:cap]


def _clip(text: Any, cap: int = _ITEM_TEXT_CAP) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= cap:
        return value
    return value[: cap - 1].rstrip() + "…"


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _section(state: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    """Walk a nested mapping, tolerating any malformed level.

    `state.json` is author- and agent-written, so a key can hold a string, a list, or null where a
    mapping is expected. Planning checks run on every chapter prepare, so a `AttributeError` here
    would take down the write flow over a bookkeeping typo. Anything unusable reads as empty.
    """
    current: Any = state
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _is_active(status: Any) -> bool:
    """Whether a record still represents something the story owes.

    Delegates to the project's own canonical predicate so a status written as `已解决`, `完成`,
    `complete`, or `已回收（第12章）` is recognised as resolved here too. A hand-maintained
    denylist in this module would drift from `state_validator` and resurrect settled threads as
    live pressures forever.
    """
    text = str(status or "").strip().lower()
    if text in _LOCK_SETTLED_STATUSES:
        return False
    return not is_resolved_foreshadowing_status(status)


def _load_state(project_root: Path) -> Dict[str, Any]:
    path = Path(project_root) / ".webnovel" / "state.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # `ValueError` covers both `json.JSONDecodeError` and `UnicodeDecodeError` (a GBK or
        # UTF-16 state.json). Planning checks run on every chapter prepare; a mis-encoded file
        # must degrade to "no pressures", not traceback out of `plan-check`.
        return {}
    return data if isinstance(data, dict) else {}


def _accepted_through(state: Dict[str, Any]) -> int:
    """Highest chapter the project has actually committed (0 when unknown)."""
    status = _section(state, "progress").get("chapter_status") or {}
    if isinstance(status, list):
        # Some writers store `["1", "2"]` rather than `{"1": "chapter_committed"}`.
        status = {str(item): "chapter_committed" for item in status}
    if not isinstance(status, dict):
        status = {}
    committed = []
    for key, value in status.items():
        if str(value or "").strip().lower() in {"chapter_committed", "accepted", "committed"}:
            number = _as_int(key)
            if number:
                committed.append(number)
    if committed:
        return max(committed)
    return _as_int(_section(state, "progress").get("current_chapter")) or 0


# --------------------------------------------------------------------------- #
# derivation
# --------------------------------------------------------------------------- #


def _timed_lock_pressures(state: Dict[str, Any], chapter: int) -> List[StoryPressure]:
    out: List[StoryPressure] = []
    locks = _section(state, "story_craft").get("timed_locks") or []
    for index, lock in enumerate(locks if isinstance(locks, list) else [], start=1):
        if not isinstance(lock, dict) or not _is_active(lock.get("status")):
            continue
        deadline = _as_int(lock.get("deadline_chapter"))
        description = _clip(lock.get("description"))
        if not description:
            continue
        out.append(
            StoryPressure(
                # Number from the *source* position, not from how many rows survived filtering:
                # `len(out) + 1` restarts the count after a resolved lock and can mint an id that
                # a later explicit `TL-002` already owns, which then silently dedupes away.
                id=_clip_id(lock.get("id") or f"TL-{index:03d}"),
                kind="deadline",
                text=description,
                source="state.json:story_craft.timed_locks",
                deadline_chapter=deadline,
                remaining=(deadline - chapter) if deadline else None,
            )
        )
    return out


def _mark_stale(items: List[StoryPressure], accepted_through: int) -> None:
    """Flag dated items whose deadline has already passed into accepted prose.

    A lock or foreshadow whose deadline is at or before the last committed chapter cannot be
    planned around any more — the chapter that owed it is frozen. Leaving it rendered as
    "已逾期 N 章" tells the planner a debt is live when nothing can be done about it, and, worse,
    implies the promise went unkept when the prose may well have kept it. The flag is about the
    *record*, not the story.
    """
    if accepted_through <= 0:
        return
    for item in items:
        if item.deadline_chapter is not None and item.deadline_chapter <= accepted_through:
            item.stale = True


def _foreshadow_pressures(state: Dict[str, Any], chapter: int) -> List[StoryPressure]:
    out: List[StoryPressure] = []
    chain = _section(state, "story_craft").get("foreshadow_chain") or []
    for row in chain if isinstance(chain, list) else []:
        if not isinstance(row, dict) or not _is_active(row.get("status")):
            continue
        planted = _as_int(row.get("buried_chapter"))
        # A foreshadow buried in a *later* chapter is not yet a pressure on this one.
        if planted is not None and planted > chapter:
            continue
        content = _clip(row.get("content"))
        if not content:
            continue
        deadline = _as_int(row.get("expected_payoff_chapter"))
        out.append(
            StoryPressure(
                id=str(row.get("id") or f"FS-{len(out) + 1:03d}"),
                kind="foreshadow",
                text=content,
                source="state.json:story_craft.foreshadow_chain",
                planted_chapter=planted,
                deadline_chapter=deadline,
                remaining=(deadline - chapter) if deadline else None,
            )
        )
    return out


def _open_loop_pressures(state: Dict[str, Any], chapter: int) -> List[StoryPressure]:
    out: List[StoryPressure] = []
    rows = _section(state, "plot_threads").get("foreshadowing") or []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not _is_active(row.get("status")):
            continue
        planted = _as_int(row.get("source_chapter") or row.get("planted_chapter"))
        if planted is not None and planted > chapter:
            continue
        content = _clip(row.get("content"))
        if not content:
            continue
        loop_id = _clip_id(row.get("loop_id") or row.get("source_event_id") or f"loop-{len(out) + 1}")
        # An open loop's due chapter lives under one of the canonical target keys. Without reading
        # it every loop ranks as undated, so the single open-loop slot goes to whichever id sorts
        # first rather than to the one that is most overdue.
        target = resolve_chapter_field(row, FORESHADOWING_TARGET_KEYS)
        out.append(
            StoryPressure(
                id=f"LO-{loop_id}",
                kind="open_loop",
                text=content,
                source="state.json:plot_threads.foreshadowing",
                planted_chapter=planted,
                deadline_chapter=target,
                remaining=(target - chapter) if target else None,
            )
        )
    return out


def _character_pressures(state: Dict[str, Any]) -> List[StoryPressure]:
    """Commitments, unresolved decisions, belief shifts and standing risk carried by characters.

    This is the class of pressure the earlier experiment showed mattered most: the planner could
    see the plot threads but never the protagonist's own promises and exposure.
    """
    out: List[StoryPressure] = []
    entities = state.get("entity_state") or {}
    if not isinstance(entities, dict):
        return out
    for entity_id, entity in entities.items():
        if not isinstance(entity, dict):
            continue
        for field_name in _CHARACTER_PRESSURE_FIELDS:
            value = entity.get(field_name)
            if value in (None, "", [], {}):
                continue
            priority = _CHARACTER_FIELD_PRIORITY.get(field_name, 9)
            if isinstance(value, dict):
                for key, sub in value.items():
                    text = _clip(sub)
                    if not text:
                        continue
                    out.append(
                        StoryPressure(
                            id=f"CH-{_clip_id(entity_id)}-{field_name}-{_clip_id(key)}",
                            kind="character",
                            text=f"{key}：{text}",
                            source=f"state.json:entity_state.{entity_id}.{field_name}",
                            priority=priority,
                            sub_field=field_name,
                        )
                    )
            else:
                text = _clip(value)
                if text:
                    out.append(
                        StoryPressure(
                            id=f"CH-{_clip_id(entity_id)}-{field_name}",
                            kind="character",
                            text=text,
                            source=f"state.json:entity_state.{entity_id}.{field_name}",
                            priority=priority,
                            sub_field=field_name,
                        )
                    )
    return out


def _previous_consequence_pressures(state: Dict[str, Any], chapter: int) -> List[StoryPressure]:
    """What the previous chapter handed forward (its sequel decision / open question)."""
    out: List[StoryPressure] = []
    # Use the project's canonical lookup: `chapter_meta` keys are written zero-padded
    # (`"0006"`) by `state_manager`, and a plain `str(chapter)` lookup silently loses the previous
    # chapter's hand-off for every such project.
    previous = chapter - 1
    row = get_chapter_meta_entry(state, previous)
    if not row:
        return out
    decision = _clip(row.get("sequel_decision"))
    if decision:
        out.append(
            StoryPressure(
                id=f"PREV-{previous}",
                kind="previous_consequence",
                text=decision,
                source=f"state.json:chapter_meta.{previous}.sequel_decision",
                planted_chapter=previous,
                related_chapters=[previous],
            )
        )
    return out


def build_story_pressures(
    project_root: str | Path,
    chapter: int,
    *,
    limit: int = DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """Derive the ranked, compact pressure digest for planning `chapter`."""
    root = Path(project_root)
    return build_pressures_from_state(root, _load_state(root), chapter, limit=limit)


def build_pressures_from_state(
    project_root: str | Path,
    state: Dict[str, Any],
    chapter: int,
    *,
    limit: int = DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """Same as :func:`build_story_pressures`, but reuses an already-loaded state.

    `plan-check` walks every chapter of a volume; re-reading state.json per chapter would be
    both slow and non-atomic (the file can change mid-walk). Callers that already hold the
    state should use this entry point.
    """
    root = Path(project_root)
    state = state if isinstance(state, dict) else {}
    chapter = int(chapter)

    collected: List[StoryPressure] = []
    collected.extend(_previous_consequence_pressures(state, chapter))
    collected.extend(_character_pressures(state))
    collected.extend(_timed_lock_pressures(state, chapter))
    collected.extend(_foreshadow_pressures(state, chapter))
    collected.extend(_open_loop_pressures(state, chapter))
    _mark_stale(collected, _accepted_through(state))

    # Rank, in this order:
    #   1. deadlines that actually fall due soon (a foreshadow/lock whose payoff is near);
    #   2. character obligations — the planner cannot plan *people* without them, and the
    #      experiment showed their absence was the real gap;
    #   3. the previous chapter's hand-off;
    #   4. undated open loops.
    # Inside the deadline band, sort by remaining chapters. Ties break on the stable id so the
    # digest is reproducible.
    def sort_key(item: StoryPressure) -> tuple:
        remaining = item.remaining
        # A stale record is bookkeeping, not a live obligation: it must never outrank a pressure
        # the planner can still act on, whatever its deadline says.
        if item.stale:
            return (9, 0, item.id)
        due_soon = remaining is not None and 0 <= remaining <= _DUE_SOON_CHAPTERS
        if due_soon:
            band, urgency = 0, remaining
        elif item.kind == "character":
            band, urgency = 1, item.priority
        elif item.kind == "previous_consequence":
            band, urgency = 2, 0
        elif item.kind == "deadline":
            band, urgency = 3, remaining if remaining is not None else 10**6
        elif item.kind == "foreshadow":
            band, urgency = 4, remaining if remaining is not None else 10**6
        else:
            band, urgency = 5, remaining if remaining is not None else 10**6
        return (band, urgency, item.id)

    collected.sort(key=sort_key)

    # Two records can derive the same id (a duplicated lock entry, or an auto-numbered fallback
    # colliding with an explicit id). Downstream code keys by id — the `reported` set, the
    # declaration checker, the outline's `**承接压力**` — so a duplicate would silently shadow a
    # real pressure. Dedupe *after* ranking so the surviving one is the most urgent, not the one
    # that happened to be collected first.
    unique: List[StoryPressure] = []
    seen_ids: set[str] = set()
    for item in collected:
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        unique.append(item)
    collected = unique

    # Apply a per-kind quota so one rich entity cannot crowd out every other class of pressure.
    # Character pressures get a second, per-sub-field cap: without it a protagonist's `stance`
    # dict fills every character slot and the planner never sees `decision` — the field that says
    # what he intends to do next. Whatever the quotas drop stays counted in `total_available`.
    selected: List[StoryPressure] = []
    used: Dict[str, int] = {}
    used_sub: Dict[str, int] = {}
    for item in collected:
        quota = _KIND_QUOTA.get(item.kind, 1)
        if used.get(item.kind, 0) >= quota:
            continue
        if item.sub_field:
            sub_key = f"{item.kind}:{item.sub_field}"
            if used_sub.get(sub_key, 0) >= _CHARACTER_FIELD_QUOTA:
                continue
        used[item.kind] = used.get(item.kind, 0) + 1
        if item.sub_field:
            used_sub[f"{item.kind}:{item.sub_field}"] = used_sub.get(f"{item.kind}:{item.sub_field}", 0) + 1
        selected.append(item)
        if len(selected) >= max(0, int(limit)):
            break
    # Backfill with the best remaining items if quotas left room (e.g. a project with no loops).
    if len(selected) < max(0, int(limit)):
        chosen = {item.id for item in selected}
        for item in collected:
            if item.id in chosen:
                continue
            selected.append(item)
            if len(selected) >= max(0, int(limit)):
                break
    selected.sort(key=sort_key)
    # Stale records are rendered (the planner should know the ledger is out of date) but they are
    # not plannable debt. `actionable_available` is what a "you must engage something" check may
    # key on: otherwise a project whose every derivable pressure is stale is nagged every chapter
    # to engage entries the same digest labels 不可再规划.
    actionable = [item for item in collected if not item.stale]

    return {
        "schema_version": SCHEMA_VERSION,
        "project_root": str(root),
        "chapter": chapter,
        "accepted_through": _accepted_through(state),
        "pressures": [item.to_dict() for item in selected],
        "total_available": len(collected),
        "actionable_available": len(actionable),
        "truncated": len(collected) > len(selected),
        "source_note": (
            "自动从 state.json（story_craft / plot_threads / entity_state / chapter_meta）派生；"
            "只读，不写回任何来源。"
        ),
    }


def format_pressure_block(digest: Dict[str, Any]) -> str:
    """Render the digest as a compact block for the planner (never for the Writer)."""
    chapter = digest.get("chapter")
    lines = [
        f"## 当前故事压力（第 {chapter} 章规划前自动派生）",
        "",
        "这些是故事**现在欠着**的东西。不是每一条都要在本章处理；但本章应当从其中至少一条"
        "自然长出来，并留下不能被本章内抹平的后果。",
        "",
    ]
    pressures = digest.get("pressures") or []
    if not pressures:
        lines.append("（未从 state.json 派生出可用压力：可能是项目尚未提交任何章节，或缺少 story_craft / entity_state。）")
        return "\n".join(lines)
    for item in pressures:
        badge = item["id"]
        remaining = item.get("remaining")
        if item.get("stale"):
            badge += " · 记录未更新（截止章已 accepted，不可再规划）"
        elif remaining is not None:
            if remaining < 0:
                badge += f" · 已逾期 {abs(remaining)} 章"
            elif remaining == 0:
                badge += " · 本章到期"
            else:
                badge += f" · 剩 {remaining} 章"
        lines.append(f"- **{badge}**（{item['kind']}）{item['text']}")
    if digest.get("truncated"):
        lines.append("")
        lines.append(
            f"（另有 {digest.get('total_available', 0) - len(pressures)} 条较低优先级压力未列出；"
            "需要时可用 --limit 提高。）"
        )
    stale_count = sum(1 for item in pressures if item.get("stale"))
    if stale_count:
        lines.append("")
        lines.append(
            f"（其中 {stale_count} 条标着「记录未更新」：它们的截止章已 accepted，是本卷台账没跟着"
            "正文更新，不是本章要还的债。）"
        )
    lines.append("")
    lines.append("规划时：写明本章承接了哪些压力 ID、为什么是现在、章末什么状态真的变了。")
    return "\n".join(lines)


def pressure_ids(digest: Dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in (digest.get("pressures") or []) if item.get("id")}
