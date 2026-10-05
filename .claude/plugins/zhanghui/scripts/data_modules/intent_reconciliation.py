"""Deterministically reconcile Canon create/resolution events into Intent rows."""
from __future__ import annotations

from typing import Any


def _content(event: dict[str, Any]) -> str:
    payload = event.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    for key in ("content", "unanswered_question", "description"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(event.get("subject") or "").strip()


def _link_id(event: dict[str, Any], keys: tuple[str, ...]) -> str:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _diagnostic(event: dict[str, Any], reason: str, candidates: list[str]) -> dict[str, Any]:
    return {
        "event_id": str(event.get("event_id") or ""),
        "chapter": int(event.get("chapter") or 0),
        "reason": reason,
        "candidate_ids": sorted(candidates),
        "link_status": "unlinked",
    }


def _resolve(
    rows: list[dict[str, Any]], event: dict[str, Any], *, explicit_keys: tuple[str, ...],
    close_type: str, diagnostics: list[dict[str, Any]],
) -> None:
    content = _content(event)
    explicit_id = _link_id(event, explicit_keys)
    if explicit_id:
        candidates = [row for row in rows if row["identity_id"] == explicit_id]
        if not candidates:
            diagnostics.append(_diagnostic(event, "orphan_close", []))
            return
        target = candidates[0]
        if target["status"] != "active":
            diagnostics.append(_diagnostic(event, "duplicate_resolution", [explicit_id]))
            return
        link_status = "linked"
    else:
        candidate_rows = [
            row for row in rows
            if row["status"] == "active" and row["content"].strip() == content and content
        ]
        if not candidate_rows:
            diagnostics.append(_diagnostic(event, "orphan_close", []))
            return
        if len(candidate_rows) != 1:
            diagnostics.append(
                _diagnostic(event, "ambiguous_legacy_close", [row["identity_id"] for row in candidate_rows])
            )
            return
        target = candidate_rows[0]
        link_status = "legacy_exact_unique"

    target["status"] = "resolved" if close_type == "open_loop_closed" else "paid_off"
    target["resolution_event_id"] = str(event.get("event_id") or "")
    target["resolved_chapter"] = int(event.get("chapter") or 0)
    target["link_status"] = link_status


def reconcile_intent_events(
    events: list[dict[str, Any]],
    *,
    initial_open_loops: list[dict[str, Any]] | None = None,
    initial_reader_promises: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return Open Loop and reader Promise lifecycles plus unlinked diagnostics.

    Caller supplies accepted events in canonical chapter/event order. This function
    uses only explicit IDs and exact-content unique legacy compatibility; it performs
    no semantic matching and never mutates source events.
    """
    open_loops: list[dict[str, Any]] = [dict(row) for row in (initial_open_loops or [])]
    reader_promises: list[dict[str, Any]] = [dict(row) for row in (initial_reader_promises or [])]
    diagnostics: list[dict[str, Any]] = []

    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("event_type") or "").strip()
        content = _content(event)
        event_id = str(event.get("event_id") or "")
        chapter = int(event.get("chapter") or 0)
        if event_type == "open_loop_created":
            if not event_id:
                diagnostics.append(_diagnostic(event, "missing_source_event_id", []))
                continue
            if any(row["identity_id"] == event_id for row in open_loops):
                continue
            open_loops.append({
                "identity_id": event_id,
                "source_event_id": event_id,
                "source_chapter": chapter,
                "content": content,
                "status": "active",
                "link_status": "linked",
                "source_kind": "canonical_event",
                "target_chapter": (event.get("payload") or {}).get("target_chapter"),
                "tier": (event.get("payload") or {}).get("tier"),
                "urgency": (event.get("payload") or {}).get("urgency"),
                "expected_payoff": (event.get("payload") or {}).get("expected_payoff"),
            })
        elif event_type == "open_loop_closed":
            _resolve(
                open_loops, event,
                explicit_keys=("loop_id", "source_event_id"),
                close_type=event_type, diagnostics=diagnostics,
            )
        elif event_type == "promise_created":
            if not event_id:
                diagnostics.append(_diagnostic(event, "missing_source_event_id", []))
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if any(row["identity_id"] == event_id for row in reader_promises):
                continue
            reader_promises.append({
                "identity_id": event_id,
                "source_event_id": event_id,
                "source_chapter": chapter,
                "content": content,
                "status": "active",
                "link_status": "linked",
                "source_kind": "canonical_event",
                "promise_id": payload.get("promise_id"),
                "promise_type": payload.get("type"),
                "target": payload.get("target"),
            })
        elif event_type == "promise_paid_off":
            before = len(diagnostics)
            _resolve(
                reader_promises, event,
                explicit_keys=("promise_id", "source_event_id", "promise_event_id"),
                close_type=event_type, diagnostics=diagnostics,
            )
            if len(diagnostics) > before and diagnostics[-1]["reason"] == "orphan_close":
                diagnostics[-1]["reason"] = "unlinked_payoff"

    return {
        "open_loops": open_loops,
        "reader_promises": reader_promises,
        "diagnostics": diagnostics,
    }
