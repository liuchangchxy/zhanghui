#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic Canon fact guard.

The shared gate policy already knows how to turn a *proven* Canon contradiction into a
hard `REJECT` — but until now nothing produced one. Reviewer prose allegations were the
only source, and they necessarily stayed advisory (they are model judgement, not proof).

This module is the missing producer. It rebuilds the hard-fact layer from the accepted
chapter commits that already exist (no new ledger), compares it with the facts the final
prose's own extraction declares, and emits a contradiction only when the prose asserts a
value that cannot coexist with accepted Canon.

What counts as a *hard* fact is deliberately narrow:

* confirmed item custody        (holder / artifact owner)
* confirmed injury / health     (present vs absent, not wording)
* confirmed time relation       (elapsed years / year numbers)
* confirmed realm / cultivation level
* confirmed current location    (only the `old` side of a move)

Everything else — knowledge, attitude, plot summaries, relationship nuance, wording — is
allowed to evolve. A paraphrase is never a contradiction: values are compared after
normalization, with explicit time and injury semantics.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .reconciliation import classify_fact_kind, normalize_field, values_conflict, values_equivalent

VALIDATOR_ID = "canon_fact_validator.v1"

# Only these fields can carry a hard contradiction. Knowledge, mood, plans and attitude are
# expected to change; treating them as immutable would block legitimate story progression.
HARD_FIELD_NAMES = {
    "realm", "holder", "injury", "time", "location.current",
}
_HARD_FIELD_RE = re.compile(
    r"(持有|归属|所有|保管|owner|holder|custody|伤势|伤情|受伤|健康|health|时间|年代|日期|"
    r"location\.current|所在地|境界|修为|realm)",
    re.IGNORECASE,
)
_INJURY_VALUE_RE = re.compile(r"(烫伤|烧伤|骨折|受伤|擦伤|割伤|伤口|渗血|渗液|红肿|淤青|中毒|昏迷|残疾|重伤|轻伤|裂伤|创面|虎口|无伤|完好|痊愈|伤愈|康复|愈合)")


def _key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold().replace("_", " "))


def _is_hard_field(field: str, value: Any = "") -> bool:
    field_key = normalize_field(field)
    if field_key in HARD_FIELD_NAMES:
        return True
    if _HARD_FIELD_RE.search(field_key):
        return True
    return bool(_INJURY_VALUE_RE.search(str(value or "")))


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else event


def _facts_from_extraction(extraction: dict[str, Any], *, chapter: int, source: str) -> list[dict[str, Any]]:
    """Flatten one extraction into canonical `(entity, field, value)` facts."""
    facts: list[dict[str, Any]] = []
    for index, item in enumerate(extraction.get("state_deltas") or []):
        entity = item.get("entity_id") or item.get("entity")
        field = item.get("field") or item.get("field_name")
        value = item.get("new") if "new" in item else item.get("new_value")
        if entity and field and value is not None:
            facts.append({
                "entity": _key(entity), "field": normalize_field(field), "value": str(value),
                "old": "" if item.get("old") is None else str(item.get("old")),
                "kind": classify_fact_kind(str(field), value),
                "source": f"{source}:state_deltas:{index}",
                "event_id": str(item.get("event_id") or f"commit-{chapter}-state-{index}"),
                "chapter": chapter,
            })
    for index, item in enumerate(extraction.get("entity_deltas") or []):
        entity = item.get("entity_id") or item.get("entity")
        patch = item.get("patch") if isinstance(item.get("patch"), dict) else {}
        current = item.get("current") if isinstance(item.get("current"), dict) else {}
        nested = patch.get("current") if isinstance(patch.get("current"), dict) else {}
        value = patch.get("realm", patch.get("current.realm", nested.get("realm", current.get("realm"))))
        if entity and value is not None:
            facts.append({
                "entity": _key(entity), "field": "realm", "value": str(value), "old": "",
                "kind": "realm", "source": f"{source}:entity_deltas:{index}",
                "event_id": f"commit-{chapter}-entity-{index}", "chapter": chapter,
            })
    for index, event in enumerate(extraction.get("accepted_events") or []):
        event_type = _key(event.get("event_type") or event.get("type")).replace(" ", "_")
        payload = _event_payload(event)
        subject = event.get("subject") or event.get("entity_id") or event.get("entity")
        event_id = str(event.get("event_id") or f"commit-{chapter}-event-{index}")
        if event_type in {"character_state_changed", "state_changed"} and subject:
            field = payload.get("field") or payload.get("field_name")
            value = payload.get("new") if "new" in payload else payload.get("new_value")
            if field and value is not None:
                facts.append({
                    "entity": _key(subject), "field": normalize_field(field), "value": str(value),
                    "old": "" if payload.get("old") is None else str(payload.get("old")),
                    "kind": classify_fact_kind(str(field), value), "source": f"{source}:events:{index}",
                    "event_id": event_id, "chapter": chapter,
                })
        elif event_type == "power_breakthrough" and subject:
            value = payload.get("realm") or payload.get("new_realm") or payload.get("new")
            if value is not None:
                facts.append({
                    "entity": _key(subject), "field": "realm", "value": str(value), "old": "",
                    "kind": "realm", "source": f"{source}:events:{index}",
                    "event_id": event_id, "chapter": chapter,
                })
        elif event_type == "artifact_obtained" and subject:
            artifact = payload.get("artifact_id") or payload.get("name") or subject
            owner = payload.get("owner") or payload.get("to_holder")
            if artifact and owner:
                facts.append({
                    "entity": _key(artifact), "field": "holder", "value": str(owner), "old": "",
                    "kind": "ownership", "source": f"{source}:events:{index}",
                    "event_id": event_id, "chapter": chapter,
                })
    return facts


def _commits(project_root: Path, chapter: int) -> Iterable[tuple[int, dict[str, Any]]]:
    commit_dir = project_root / ".story-system" / "commits"
    if not commit_dir.is_dir():
        return []
    found: list[tuple[int, dict[str, Any]]] = []
    for path in sorted(commit_dir.glob("chapter_*.commit.json")):
        match = re.search(r"chapter_(\d+)\.commit\.json$", path.name)
        if not match:
            continue
        number = int(match.group(1))
        if number >= chapter:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("meta", {}).get("status") != "accepted":
            continue
        extraction = payload.get("extraction_result")
        if isinstance(extraction, dict):
            found.append((number, extraction))
    return found


def build_canon_facts(project_root: str | Path, chapter: int) -> dict[tuple[str, str], dict[str, Any]]:
    """Latest accepted hard fact per `(entity, field)`, rebuilt from canonical commits."""
    canon: dict[tuple[str, str], dict[str, Any]] = {}
    for number, extraction in _commits(Path(project_root), chapter):
        for fact in _facts_from_extraction(extraction, chapter=number, source=f"commit{number}"):
            if not _is_hard_field(fact["field"], fact["value"]):
                continue
            canon[(fact["entity"], fact["field"])] = fact
    return canon


def _current_claims(extraction_result: dict[str, Any], chapter: int,
                    proposed_changes: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    claims = _facts_from_extraction(extraction_result, chapter=chapter, source="current")
    if isinstance(proposed_changes, dict):
        for index, item in enumerate(proposed_changes.get("item_transfers") or []):
            if not isinstance(item, dict):
                continue
            item_id = item.get("item_id") or item.get("item_name") or item.get("item")
            holder = (item.get("to_holder") or item.get("to_character") or item.get("to")
                      or item.get("new_holder"))
            if item_id and holder:
                claims.append({
                    "entity": _key(item_id), "field": "holder", "value": str(holder),
                    "old": str(item.get("from_holder") or item.get("from_character") or ""),
                    "kind": "ownership", "source": f"current:item_transfers:{index}",
                    "event_id": f"proposal-item-transfer-{index}", "chapter": chapter,
                })
    return [claim for claim in claims if _is_hard_field(claim["field"], claim["value"])]


def validate_canon_facts(
    project_root: str | Path,
    chapter: int,
    extraction_result: dict[str, Any],
    proposed_changes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare the chapter's hard facts with accepted Canon. Returns an audit artifact."""
    canon = build_canon_facts(project_root, chapter)
    if not canon:
        return {
            "schema_version": "canon-validation/v1", "validator_id": VALIDATOR_ID,
            "status": "passed", "canon_fact_count": 0, "contradictions": [],
            "reason": "no accepted Canon commits before this chapter",
        }
    claims = _current_claims(extraction_result, chapter, proposed_changes)
    contradictions: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def _record(claim, canon_fact, reason):
        key = (claim["entity"], claim["field"], claim["value"])
        if key in seen:
            return
        seen.add(key)
        contradictions.append({
            "entity": claim["entity"],
            "field": claim["field"],
            "kind": claim["kind"],
            "canon_value": canon_fact["value"],
            "canon_source": canon_fact["source"],
            "canon_event_id": canon_fact["event_id"],
            "canon_chapter": canon_fact["chapter"],
            "observed_value": claim["value"],
            "observed_old": claim.get("old") or "",
            "observed_source": claim["source"],
            "reason": reason,
        })

    for claim in claims:
        key = (claim["entity"], claim["field"])
        canon_fact = canon.get(key)
        if not canon_fact:
            continue
        old = str(claim.get("old") or "")
        value = str(claim["value"])

        # 1. The prose asserts a prior state that Canon never held. This is the clean
        #    "stale old value" contradiction (十年前 vs 十四年前 / 无伤 vs 烫伤).
        if old and not values_equivalent(old, canon_fact["value"]):
            _record(claim, canon_fact, "asserted prior value contradicts accepted Canon")
            continue

        # 2. A documented transition (old matches Canon) is legitimate: healing, moving,
        #    handing an item over. But a *time* fact is retroactive and cannot "transition".
        if old and values_equivalent(old, canon_fact["value"]):
            if claim["kind"] != "time":
                continue
            if not values_conflict(value, canon_fact["value"], kind=claim["kind"]):
                continue

        # 3. No documented transition, and the new value is provably incompatible with the
        #    accepted fact (injury present vs absent; different holder; different elapsed
        #    time; different realm). Paraphrases are excluded by `values_conflict`.
        if values_conflict(value, canon_fact["value"], kind=claim["kind"]):
            _record(claim, canon_fact, "value contradicts accepted Canon without a documented transition")

    return {
        "schema_version": "canon-validation/v1", "validator_id": VALIDATOR_ID,
        "status": "conflict" if contradictions else "passed",
        "canon_fact_count": len(canon),
        "checked_claim_count": len(claims),
        "contradictions": contradictions,
    }
