"""Deterministically align writer declarations with final-prose extraction."""
from __future__ import annotations

import hashlib
import json
import re
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


def _state_proposals(proposed: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for index, item in enumerate(proposed["character_state_changes"]):
        entity = item.get("entity_id") or item.get("character_id")
        state = item.get("new") or item.get("new_value") or item.get("new_state")
        field = item.get("field") or item.get("field_name")
        if not field and isinstance(state, str):
            match = re.match(r"\s*([^:=：]+)\s*[:=：]\s*(.+)\s*$", state)
            if match:
                field, state = match.group(1), match.group(2)
            elif _value(state.removeprefix("突破")) in {"筑基", "炼气", "金丹", "元婴"}:
                field, state = "realm", state.removeprefix("突破")
        if entity and field and state is not None:
            result.append({"index": index, "source": "character_state_changes", "entity": _key(entity), "field": _field(field), "value": _value(state)})
    return result


def reconcile_changes(
    proposed_changes: Any,
    observed_changes: Any,
    *,
    chapter_text: str,
) -> dict[str, Any]:
    """Return an auditable result; only observed facts enter accepted_payload."""
    proposed = validate_proposed_changes(proposed_changes)
    observed = ExtractionResult.model_validate(observed_changes).model_dump()
    declarations = _state_proposals(proposed)
    state_deltas = observed["state_deltas"]
    matched: list[dict[str, Any]] = []
    proposed_not_observed: list[dict[str, Any]] = []
    unproposed_observed: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    consumed: set[int] = set()
    accounted_proposals: set[tuple[str, int]] = set()

    for declaration in declarations:
        targets = [
            (index, item) for index, item in enumerate(state_deltas)
            if _key(item.get("entity_id")) == declaration["entity"]
            and _field(item.get("field")) == declaration["field"]
        ]
        if not targets:
            proposed_not_observed.append({"proposed": {"source": declaration["source"], "index": declaration["index"]}, "reason": "no matching observed entity/field"})
            accounted_proposals.add((declaration["source"], declaration["index"]))
            continue
        index, item = targets[0]
        consumed.add(index)
        evidence = {"source": "state_deltas", "index": index}
        if _value(item.get("new")) == declaration["value"]:
            matched.append({"proposed": {"source": declaration["source"], "index": declaration["index"]}, "observed": evidence, "reason": "normalized entity, field, and value match"})
            accounted_proposals.add((declaration["source"], declaration["index"]))
        else:
            conflicts.append({"proposed": {"source": declaration["source"], "index": declaration["index"]}, "observed": evidence, "proposed_value": declaration["value"], "observed_value": _value(item.get("new")), "reason": "same normalized entity and field have different values"})
            accounted_proposals.add((declaration["source"], declaration["index"]))

    for field, value in proposed.items():
        items = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
        for index, _ in enumerate(items):
            if (field, index) not in accounted_proposals:
                proposed_not_observed.append({"proposed": {"source": field, "index": index}, "reason": "no deterministic observed mapping"})

    for index, item in enumerate(state_deltas):
        if index not in consumed:
            unproposed_observed.append({"observed": {"source": "state_deltas", "index": index}, "reason": "final-prose observation has no deterministic proposal match"})
    for field in ("accepted_events", "entity_deltas"):
        for index, _ in enumerate(observed[field]):
            unproposed_observed.append({"observed": {"source": field, "index": index}, "reason": "final-prose observation retained; no deterministic CHANGES mapping"})

    status = "conflict" if conflicts else "passed"
    return {
        "schema_version": "story-reconciliation/v1",
        "status": status,
        "matched": matched,
        "proposed_not_observed": proposed_not_observed,
        "unproposed_observed": unproposed_observed,
        "conflicts": conflicts,
        "accepted_payload": {key: observed[key] for key in ("accepted_events", "state_deltas", "entity_deltas")},
        "accepted_sources": [
            {
                "accepted": {"field": field, "index": index},
                "observed": {"source": field, "index": index},
                **({"proposed": next(
                    item["proposed"] for item in matched
                    if item["observed"] == {"source": field, "index": index}
                )} if any(item["observed"] == {"source": field, "index": index} for item in matched) else {}),
                "prose_sha256": _digest(chapter_text),
            }
            for field in ("accepted_events", "state_deltas", "entity_deltas")
            for index, _ in enumerate(observed[field])
        ],
        "observed_sha256": _digest(observed),
        "chapter_sha256": _digest(chapter_text),
    }


def verify_reconciliation_freshness(result: dict[str, Any], *, chapter_text: str) -> None:
    if result.get("status") != "passed":
        raise ValueError("reconciliation has not passed")
    if result.get("chapter_sha256") != _digest(chapter_text):
        raise ValueError("stale reconciliation: final chapter changed after reconciliation")


def verify_observed_payload(result: dict[str, Any], observed_changes: Any) -> dict[str, list[dict[str, Any]]]:
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
    return {field: accepted[field] for field in fields}
