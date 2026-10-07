"""Read-only binding from Story Craft occurrence claims to effective Canon events."""
from __future__ import annotations

from typing import Any

from .story_event_schema import StoryEvent


_OCCURRENCE_FIELDS = {"buried_chapter", "payoff_chapter", "fulfilled_chapter"}


def resolve_story_craft_occurrences(story_craft: Any, snapshot: Any) -> dict[str, dict[str, Any]]:
    """Return exact Story Craft occurrence paths backed by one effective event.

    The snapshot is the only evidence input. Each link requires an accepted
    containing chapter, a schema-valid event bound to that chapter, a globally
    unique event ID, one explicit occurrence_ref, and exactly one chapter claim
    equal to the event chapter. Returned rows are evidence metadata, not authority.
    """
    chapters = getattr(snapshot, "chapters", {})
    event_counts: dict[str, int] = {}
    valid_events: dict[str, list[dict[str, Any]]] = {}
    for chapter_key, entry in sorted(chapters.items()):
        if getattr(entry, "status", None) != "accepted":
            continue
        try:
            containing_chapter = int(chapter_key)
        except (TypeError, ValueError):
            continue
        extraction = getattr(entry, "extraction_result", None) or {}
        raw_events = extraction.get("accepted_events", []) if isinstance(extraction, dict) else []
        if not isinstance(raw_events, list):
            continue
        for raw in raw_events:
            if not isinstance(raw, dict) or not isinstance(raw.get("event_id"), str):
                continue
            event_id = raw["event_id"]
            event_counts[event_id] = event_counts.get(event_id, 0) + 1
            try:
                event = StoryEvent.model_validate(raw)
            except Exception:
                continue
            if event.chapter != containing_chapter:
                continue
            valid_events.setdefault(event_id, []).append({
                "event_id": event.event_id,
                "event_type": event.event_type,
                "source_chapter": event.chapter,
                "source_relationship": "CANON_EVENT_EVIDENCE",
                "effective_revision_id": getattr(entry, "effective_revision_id", None),
                "effective_content_sha256": getattr(entry, "effective_content_sha256", None),
                "effective_history_digest": getattr(snapshot, "effective_history_digest", None),
                "generation_id": getattr(snapshot, "generation_id", None),
            })
    unique_events = {
        event_id: rows[0] for event_id, rows in valid_events.items()
        if event_counts.get(event_id) == 1 and len(rows) == 1
    }

    if not isinstance(story_craft, dict):
        return {}
    trusted: dict[str, dict[str, Any]] = {}
    for container in ("foreshadow_chain", "timed_locks", "thematic_echoes"):
        rows = story_craft.get(container)
        if not isinstance(rows, list):
            continue
        for index, item in enumerate(rows):
            if not isinstance(item, dict):
                continue
            item_path = f"story_craft.{container}.{index}"
            reference = item.get("occurrence_ref")
            if not isinstance(reference, dict) or set(reference) != {"event_id"}:
                continue
            event_id = reference.get("event_id")
            evidence = unique_events.get(event_id) if isinstance(event_id, str) else None
            if evidence is None:
                continue
            claims: list[tuple[str, Any]] = [
                (f"{item_path}.{name}", item[name])
                for name in _OCCURRENCE_FIELDS if name in item and item[name] is not None
            ]
            if container == "thematic_echoes":
                echoes = item.get("echoes")
                if isinstance(echoes, list):
                    claims.extend((f"{item_path}.echoes.{echo_index}.chapter", echo["chapter"])
                                  for echo_index, echo in enumerate(echoes)
                                  if isinstance(echo, dict) and echo.get("chapter") is not None)
            matching_claims = [(path, value) for path, value in claims
                               if type(value) is int and value == evidence["source_chapter"]]
            if len(matching_claims) != 1:
                continue
            trusted[f"{item_path}.occurrence_ref"] = dict(evidence)
            trusted[matching_claims[0][0]] = dict(evidence)
    return trusted
