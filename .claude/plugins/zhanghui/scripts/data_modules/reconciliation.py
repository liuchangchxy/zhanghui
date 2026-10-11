"""Deterministically align writer declarations with final-prose extraction."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any

from .chapter_commit_schema import ExtractionResult

REQUIRED_CHANGE_FIELDS = {
    "character_state_changes", "new_plot_points", "foreshadowing_actions",
    "location_state_changes", "faction_state_changes", "time_progression",
    "item_transfers", "unresolved_questions",
}
FIELD_ALIASES = {"修为": "realm", "境界": "realm", "realm": "realm"}
VALUE_ALIASES = {
    "foundation establishment": "筑基", "foundation_establishment": "筑基",
    "foundation-establishment": "筑基", "筑基期": "筑基",
}
SUPPORTED_MAPPINGS = [
    "character_state_changes -> state_deltas",
    "realm entity_delta patch/current",
    "power_breakthrough event realm",
]
OPAQUE_CATEGORIES = [
    "new_plot_points", "foreshadowing_actions", "location_state_changes",
    "faction_state_changes", "time_progression", "item_transfers",
    "unresolved_questions", "non-realm entity_deltas", "unmapped accepted_events",
]


def _digest(value: Any) -> str:
    raw = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _key(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("_", " ")
    return re.sub(r"\s+", " ", text)


def _field(value: Any) -> str:
    normalized = _key(value)
    return FIELD_ALIASES.get(normalized, normalized)


def _value(value: Any) -> str:
    normalized = _key(value)
    return VALUE_ALIASES.get(normalized, normalized)


def _changes_document(chapter_text: str):
    # Parser owns format recognition and the corresponding removal spans.
    from changes_gate import parse_changes_document

    return parse_changes_document(chapter_text)


def validate_proposed_changes(proposed: Any) -> dict[str, Any]:
    if not isinstance(proposed, dict):
        raise ValueError("CHANGES must be a JSON object")
    missing = REQUIRED_CHANGE_FIELDS - proposed.keys()
    if missing:
        raise ValueError("CHANGES missing required fields: " + ", ".join(sorted(missing)))
    for name in REQUIRED_CHANGE_FIELDS:
        value = proposed[name]
        if name == "time_progression":
            if value is not None and not isinstance(value, dict):
                raise ValueError("CHANGES.time_progression must be an object or null")
        elif not isinstance(value, list):
            raise ValueError(f"CHANGES.{name} must be a list")
        elif any(not isinstance(item, dict) for item in value):
            raise ValueError(f"CHANGES.{name} items must be objects")
    return proposed


def split_chapter_and_changes(chapter_text: str) -> tuple[str, dict[str, Any]]:
    """Parse the proposal and return prose with the parser-selected source removed."""
    document = _changes_document(chapter_text)
    if document.error or document.proposed_changes is None:
        raise ValueError(f"invalid CHANGES: {document.error or 'missing parsed value'}")
    return document.prose_only, validate_proposed_changes(document.proposed_changes)


def _proposal_facts(proposed: dict[str, Any]) -> list[dict[str, Any]]:
    facts = []
    for index, item in enumerate(proposed["character_state_changes"]):
        entity = item.get("entity_id") or item.get("character_id")
        raw_value = item.get("new") or item.get("new_value") or item.get("new_state")
        raw_field = item.get("field") or item.get("field_name")
        if not raw_field and isinstance(raw_value, str):
            match = re.match(r"\s*([^:=：]+)\s*[:=：]\s*(.+)\s*$", raw_value)
            if match:
                raw_field, raw_value = match.group(1), match.group(2)
            elif _value(raw_value.removeprefix("突破")) in {"筑基", "炼气", "金丹", "元婴"}:
                raw_field, raw_value = "realm", raw_value.removeprefix("突破")
        if entity and raw_field and raw_value is not None:
            facts.append({"entity": _key(entity), "field": _field(raw_field), "value": _value(raw_value),
                          "source_type": "character_state_changes", "source_index": index})
    return facts


def _event_fact(event: dict[str, Any], index: int) -> dict[str, Any] | None:
    event_type = _key(event.get("event_type") or event.get("type")).replace(" ", "_")
    if event_type != "power_breakthrough":
        return None
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else event
    entity = event.get("subject") or event.get("entity_id") or event.get("entity")
    value = payload.get("realm") or payload.get("new_realm") or payload.get("new")
    if entity and value is not None:
        return {"entity": _key(entity), "field": "realm", "value": _value(value),
                "source_type": "accepted_events", "source_index": index}
    return None


def _entity_realm_fact(delta: dict[str, Any], index: int) -> dict[str, Any] | None:
    entity = delta.get("entity_id") or delta.get("entity")
    patch = delta.get("patch") if isinstance(delta.get("patch"), dict) else {}
    current = delta.get("current") if isinstance(delta.get("current"), dict) else {}
    nested_patch = patch.get("current") if isinstance(patch.get("current"), dict) else {}
    value = patch.get("realm", patch.get("current.realm", nested_patch.get("realm", current.get("realm"))))
    if entity and value is not None:
        return {"entity": _key(entity), "field": "realm", "value": _value(value),
                "source_type": "entity_deltas", "source_index": index}
    return None


def _observed_facts(observed: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for index, item in enumerate(observed["state_deltas"]):
        entity, field = item.get("entity_id"), item.get("field")
        value = item.get("new")
        if entity and field and value is not None:
            facts.append({"entity": _key(entity), "field": _field(field), "value": _value(value),
                          "source_type": "state_deltas", "source_index": index})
    for index, item in enumerate(observed["entity_deltas"]):
        fact = _entity_realm_fact(item, index)
        if fact:
            facts.append(fact)
    for index, event in enumerate(observed["accepted_events"]):
        fact = _event_fact(event, index)
        if fact:
            facts.append(fact)
    return facts


def reconcile_changes(proposed_changes: Any, observed_changes: Any, *, chapter_text: str) -> dict[str, Any]:
    """Return derived audit data. A conflict anywhere blocks the whole payload."""
    proposed = validate_proposed_changes(proposed_changes)
    observed = ExtractionResult.model_validate(observed_changes).model_dump()
    declarations = _proposal_facts(proposed)
    normalized_proposal_sources = {(item["source_type"], item["source_index"]) for item in declarations}
    facts = _observed_facts(observed)
    observed_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    proposals_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        observed_by_key[(fact["entity"], fact["field"])].append(fact)
    for fact in declarations:
        proposals_by_key[(fact["entity"], fact["field"])].append(fact)

    conflicts: list[dict[str, Any]] = []
    for key, evidence in observed_by_key.items():
        values = sorted({item["value"] for item in evidence})
        if len(values) > 1:
            conflicts.append({"type": "observed_internal_conflict", "entity": key[0], "field": key[1],
                              "values": values, "evidence": evidence})
    for key, evidence in proposals_by_key.items():
        values = sorted({item["value"] for item in evidence})
        if len(values) > 1:
            conflicts.append({"type": "proposal_internal_conflict", "entity": key[0], "field": key[1],
                              "values": values, "evidence": evidence})

    matched, proposed_not_observed, unproposed_observed = [], [], []
    for key, declarations_for_key in proposals_by_key.items():
        evidence = observed_by_key.get(key, [])
        proposal_values = {item["value"] for item in declarations_for_key}
        observed_values = {item["value"] for item in evidence}
        if not evidence:
            for item in declarations_for_key:
                proposed_not_observed.append({"proposed": {"source": item["source_type"], "index": item["source_index"]},
                                              "reason": "no matching observed entity/field"})
        elif proposal_values & observed_values:
            for item in declarations_for_key:
                matched.append({"proposed": {"source": item["source_type"], "index": item["source_index"]},
                                "observed": [{"source": fact["source_type"], "index": fact["source_index"]}
                                             for fact in evidence if fact["value"] == item["value"]],
                                "reason": "normalized entity, field, and value match"})
            if proposal_values != observed_values:
                conflicts.append({"type": "proposal_observed_conflict", "entity": key[0], "field": key[1],
                                  "proposed_values": sorted(proposal_values), "observed_values": sorted(observed_values),
                                  "evidence": evidence})
        else:
            conflicts.append({"type": "proposal_observed_conflict", "entity": key[0], "field": key[1],
                              "proposed_values": sorted(proposal_values), "observed_values": sorted(observed_values),
                              "evidence": evidence})

    for field in REQUIRED_CHANGE_FIELDS:
        value = proposed[field]
        items = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
        for index, _ in enumerate(items):
            if field != "character_state_changes" or (field, index) not in normalized_proposal_sources:
                proposed_not_observed.append({"proposed": {"source": field, "index": index},
                                              "reason": "no deterministic proposal fact mapping" if field == "character_state_changes" else "no deterministic observed mapping"})
    deterministic_sources = {(fact["source_type"], fact["source_index"]) for fact in facts}
    for source, index in deterministic_sources:
        if not any(entry.get("observed") and any(ref == {"source": source, "index": index}
                                                   for ref in (entry["observed"] if isinstance(entry["observed"], list) else [entry["observed"]]))
                   for entry in matched):
            unproposed_observed.append({"observed": {"source": source, "index": index},
                                        "reason": "final-prose observation has no deterministic proposal match"})
    mapped = deterministic_sources
    for source, field in (("state_deltas", observed["state_deltas"]),
                          ("entity_deltas", observed["entity_deltas"]),
                          ("accepted_events", observed["accepted_events"])):
        for index, _ in enumerate(field):
            if (source, index) not in mapped:
                unproposed_observed.append({"observed": {"source": source, "index": index},
                                            "reason": "opaque final-prose observation retained"})

    status = "conflict" if conflicts else "passed"
    return {
        "schema_version": "story-reconciliation/v1", "status": status,
        "coverage": {"deterministic_mappings": SUPPORTED_MAPPINGS, "opaque_categories": OPAQUE_CATEGORIES},
        "matched": matched, "proposed_not_observed": proposed_not_observed,
        "unproposed_observed": unproposed_observed, "conflicts": conflicts,
        "accepted_payload": {key: observed[key] for key in ("accepted_events", "state_deltas", "entity_deltas")},
        "accepted_sources": [
            {"accepted": {"field": field, "index": index}, "observed": {"source": field, "index": index},
             "prose_sha256": _digest(_changes_document(chapter_text).prose_only)}
            for field in ("accepted_events", "state_deltas", "entity_deltas")
            for index, _ in enumerate(observed[field])
        ],
        "proposed_sha256": _digest(proposed),
        "observed_sha256": _digest(observed), "chapter_sha256": _digest(chapter_text),
        "prose_sha256": _digest(_changes_document(chapter_text).prose_only),
    }


def verify_reconciliation_freshness(result: dict[str, Any], *, chapter_text: str) -> None:
    if result.get("status") != "passed":
        raise ValueError("reconciliation has not passed")
    if result.get("chapter_sha256") != _digest(chapter_text):
        raise ValueError("stale reconciliation: final chapter changed after reconciliation")


def verify_observed_payload(result: dict[str, Any], observed_changes: Any) -> dict[str, list[dict[str, Any]]]:
    """Compatibility validator for audit readers; never grants commit authority."""
    if not isinstance(result, dict) or result.get("schema_version") != "story-reconciliation/v1":
        raise ValueError("missing or invalid reconciliation_result")
    if result.get("status") != "passed" or result.get("conflicts"):
        raise ValueError("reconciliation did not pass; chapter commit is blocked")
    observed = ExtractionResult.model_validate(observed_changes).model_dump()
    if result.get("observed_sha256") != _digest(observed):
        raise ValueError("stale reconciliation: extraction_result changed after reconciliation")
    accepted = result.get("accepted_payload")
    fields = ("accepted_events", "state_deltas", "entity_deltas")
    if not isinstance(accepted, dict) or any(accepted.get(field) != observed[field] for field in fields):
        raise ValueError("reconciliation accepted payload does not match observed extraction")
    return {field: observed[field] for field in fields}
