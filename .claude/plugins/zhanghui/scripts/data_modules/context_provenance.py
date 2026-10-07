#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-time provenance and deterministic conflict handling for Writer context."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .durable_projection import discover_validated_chapter_commits


SEMANTIC_ROLES = {"CANON", "INTENT", "CRAFT", "OPERATIONAL", "UNKNOWN"}
SOURCE_ROLES = {
    "COMMIT", "PROJECTION", "CONTRACT", "OUTLINE", "USER", "LEGACY",
    "RETRIEVAL", "REVIEW", "SUMMARY", "CONFIG", "OWNER_STATE",
}
SOURCE_RELATIONSHIPS = {"AUTHORITATIVE_SOURCE", "SCOPED_AUTHORED_OVERRIDE",
                        "DERIVED_RUNTIME_COPY", "REFERENCE"}
SEMANTIC_CLASSES = {"CANON_FACT", "CANON_DERIVED_OBLIGATION", "PLANNER_INTENT",
                    "CRAFT_RECOMMENDATION", "DERIVED_REFERENCE", "UNKNOWN"}


@dataclass
class ContextItem:
    content: Any
    semantic_role: str
    source_role: str
    source_ref: str
    chapter: int | None = None
    provenance_status: str = "unknown"
    evidence: list[str] = field(default_factory=list)
    fact_key: tuple[str, ...] | None = None
    semantic_class: str | None = None
    owner: str | None = None
    source_relationship: str | None = None
    source_identity: str | None = None
    scope: str | None = None

    def __post_init__(self) -> None:
        self.semantic_role = self.semantic_role if self.semantic_role in SEMANTIC_ROLES else "UNKNOWN"
        self.source_role = self.source_role if self.source_role in SOURCE_ROLES else "LEGACY"
        self.source_ref = str(self.source_ref or "unknown")
        refs = [*self.evidence, self.source_ref]
        self.evidence = list(dict.fromkeys(str(ref) for ref in refs if ref))
        if self.source_role == "COMMIT" and self.provenance_status == "unknown":
            self.provenance_status = "verified"
        if self.semantic_class is None:
            self.semantic_class = ("CANON_FACT" if self.semantic_role == "CANON" else
                                   "PLANNER_INTENT" if self.semantic_role == "INTENT" else
                                   "CRAFT_RECOMMENDATION" if self.semantic_role == "CRAFT" else
                                   "UNKNOWN")
        if self.semantic_class not in SEMANTIC_CLASSES:
            self.semantic_class = "UNKNOWN"
        if self.owner is None:
            self.owner = self.source_role
        if self.source_relationship is None:
            self.source_relationship = "AUTHORITATIVE_SOURCE" if self.semantic_role in {"CANON", "INTENT"} else "DERIVED_RUNTIME_COPY" if self.source_role == "PROJECTION" else "REFERENCE"
        if self.source_relationship not in SOURCE_RELATIONSHIPS:
            self.source_relationship = "REFERENCE"
        if self.source_identity is None:
            self.source_identity = self.source_ref
        if self.scope is None and self.chapter is not None:
            self.scope = f"chapter:{self.chapter}"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.fact_key is not None:
            result["fact_key"] = list(self.fact_key)
        return result


def _describe(item: ContextItem) -> dict[str, Any]:
    return {
        "source_ref": item.source_ref,
        "source_role": item.source_role,
        "owner": item.owner,
        "semantic_class": item.semantic_class,
        "source_relationship": item.source_relationship,
        "source_identity": item.source_identity,
        "scope": item.scope,
        "chapter": item.chapter,
        "content": item.content,
    }


def resolve_fact_items(items: Iterable[ContextItem]) -> tuple[list[ContextItem], list[dict[str, Any]]]:
    """Choose current deterministic facts; never promote a projection by itself."""
    grouped: dict[tuple[str, ...], list[ContextItem]] = {}
    passthrough: list[ContextItem] = []
    diagnostics: list[dict[str, Any]] = []
    for item in items:
        if item.fact_key:
            grouped.setdefault(tuple(item.fact_key), []).append(item)
        else:
            passthrough.append(item)

    selected = list(passthrough)
    for fact_key, group in grouped.items():
        commits = [x for x in group if x.source_role == "COMMIT" and x.provenance_status == "verified"]
        if commits:
            latest_chapter = max(x.chapter or 0 for x in commits)
            latest = [x for x in commits if (x.chapter or 0) == latest_chapter]
            values = {repr(x.content) for x in latest}
            if len(values) > 1:
                raise ValueError(f"canonical fact conflict at chapter {latest_chapter}: {fact_key!r}")
            winner = latest[0]
            evidence = list(dict.fromkeys(ref for x in latest for ref in x.evidence))
            for item in group:
                if item in latest:
                    continue
                same_fact = item.content == winner.content and (item.chapter is None or item.chapter == latest_chapter)
                if same_fact and item.source_role == "PROJECTION":
                    evidence.extend(ref for ref in item.evidence if ref not in evidence)
                    diagnostics.append({"type": "duplicate_suppressed", "fact_key": list(fact_key), "suppressed": [_describe(item)]})
                elif item.source_role == "COMMIT" and (item.chapter or 0) < latest_chapter:
                    diagnostics.append({"type": "historical_fact", "fact_key": list(fact_key), "suppressed": [_describe(item)]})
                elif item.content != winner.content:
                    diagnostics.append({"type": "source_conflict", "fact_key": list(fact_key), "winner": _describe(winner), "suppressed": [_describe(item)]})
                elif item.source_role not in {"COMMIT", "PROJECTION"}:
                    diagnostics.append({"type": "duplicate_suppressed", "fact_key": list(fact_key), "suppressed": [_describe(item)]})
            winner.evidence = evidence
            selected.append(winner)
        else:
            # A projection label is not proof of commit lineage.
            for item in group:
                if item.source_role == "PROJECTION" and item.semantic_role == "CANON":
                    item.semantic_role = "UNKNOWN"
                    item.provenance_status = "unverified"
                    diagnostics.append({"type": "legacy_unknown", "fact_key": list(fact_key), "suppressed": [_describe(item)]})
                selected.append(item)

    return selected, diagnostics


def classify_rag_hit(project_root: Path, hit: dict[str, Any], *, target_chapter: int | None = None) -> dict[str, Any]:
    """Preserve retrieval metadata while keeping similarity separate from authority."""
    result = dict(hit)
    source_file = str(result.get("source_file") or "")
    try:
        chapter = int(result.get("chapter") or 0)
    except (TypeError, ValueError):
        chapter = 0
    verified = False
    if source_file.startswith("commit:"):
        match = re.search(r"chapter[_-]?(\d+)", source_file)
        if match:
            commit_chapter = int(match.group(1))
            path = Path(project_root) / ".story-system" / "commits" / f"chapter_{commit_chapter:03d}.commit.json"
            try:
                commit = json.loads(path.read_text(encoding="utf-8"))
                try:
                    metadata_chapter = int((commit.get("meta") or {}).get("chapter") or 0)
                except (TypeError, ValueError):
                    metadata_chapter = 0
                verified = (
                    (commit.get("meta") or {}).get("status") == "accepted"
                    and metadata_chapter == commit_chapter
                    and (commit.get("provenance") or {}).get("write_fact_role") == "chapter_commit"
                    and (target_chapter is None or commit_chapter < target_chapter)
                )
            except (OSError, json.JSONDecodeError):
                verified = False
            if verified:
                chapter = commit_chapter
    result.update({
        "chapter": chapter,
        "source_type": str(result.get("chunk_type") or result.get("source") or "retrieval"),
        "presentation_role": "REFERENCE",
        "semantic_role": "CANON" if verified else "UNKNOWN",
        "source_role": "PROJECTION" if verified else "LEGACY",
        "provenance_status": "commit_evidenced" if verified else "unknown",
        "similarity_is_authority": False,
    })
    return result


def load_commit_fact_items(project_root: Path, chapter: int, owned_view=None) -> tuple[list[ContextItem], int | None, str | None]:
    items: list[ContextItem] = []
    latest_chapter = None
    latest_hash = None
    validated_commits = (owned_view.effective_commits_before(chapter) if owned_view is not None
                         else discover_validated_chapter_commits(project_root))
    for commit in validated_commits:
        path = commit.get("path")
        commit_chapter = commit["chapter"]
        payload = commit["payload"]
        # The requested chapter is the next writing target. Its existing commit,
        # when revising, must not become evidence about its own prewrite context.
        if commit_chapter >= chapter or payload["meta"]["status"] != "accepted":
            continue
        ref = (f"active:{owned_view.pinned.semantic_activation_id}:chapter:{commit_chapter}"
               if owned_view is not None else f"commit:{commit_chapter}")
        digest = (payload.get("effective_content_sha256") if owned_view is not None
                  else hashlib.sha256(path.read_bytes()).hexdigest())
        if latest_chapter is None or commit_chapter >= latest_chapter:
            latest_chapter, latest_hash = commit_chapter, digest
        extraction = payload["extraction_result"]
        chapter_meta = extraction.get("chapter_meta")
        if isinstance(chapter_meta, dict):
            from story_craft import classify_story_craft_field
            for field_name, value in chapter_meta.items():
                role = classify_story_craft_field(f"chapter_meta.{field_name}")
                semantic_role = role if role in {"INTENT", "CRAFT"} else "UNKNOWN"
                items.append(ContextItem(
                    content={"field": field_name, "value": value}, semantic_role=semantic_role,
                    source_role="COMMIT", source_ref=ref, chapter=commit_chapter,
                    provenance_status="commit_snapshot", evidence=["commit_chapter_meta"],
                    semantic_class="PLANNER_INTENT" if role == "INTENT" else "CRAFT_RECOMMENDATION" if role == "CRAFT" else "UNKNOWN",
                    source_relationship="DERIVED_RUNTIME_COPY", source_identity=ref,
                    scope=f"chapter:{commit_chapter}",
                ))
        for delta in extraction.get("entity_deltas", []) or []:
            if not isinstance(delta, dict):
                continue
            entity = str(delta.get("entity_id") or delta.get("id") or "").strip()
            if not entity:
                continue
            values = {}
            for name in ("canonical_name", "name", "aliases"):
                if name in delta:
                    values[name] = delta[name]
            values.update(delta.get("current") or {})
            values.update(delta.get("patch") or {})
            for field_name, value in values.items():
                items.append(ContextItem(
                    content={"entity_id": entity, "field": str(field_name), "value": value},
                    semantic_role="CANON", source_role="COMMIT", source_ref=ref,
                    chapter=commit_chapter, provenance_status="verified",
                    fact_key=(entity, str(field_name)),
                ))
        for delta in extraction.get("state_deltas", []) or []:
            if not isinstance(delta, dict):
                continue
            entity = str(delta.get("entity_id") or delta.get("entity") or "").strip()
            field_name = str(delta.get("field") or delta.get("field_path") or "").strip()
            if not entity or not field_name:
                continue
            value = delta.get("new", delta.get("new_value"))
            items.append(ContextItem(
                content={"entity_id": entity, "field": field_name, "value": value},
                semantic_role="CANON", source_role="COMMIT", source_ref=ref,
                chapter=commit_chapter, provenance_status="verified",
                fact_key=(entity, field_name),
            ))
        for event_index, event in enumerate(extraction.get("accepted_events", []) or []):
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("event_type") or "")
            body = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if event_type == "relationship_changed":
                left = str(body.get("from_entity") or event.get("subject") or "").strip()
                right = str(body.get("to_entity") or body.get("to") or "").strip()
                relation = body.get("relationship_type", body.get("relation_type", body.get("type")))
                if left and right and relation is not None:
                    items.append(ContextItem(
                        content={"from_entity": left, "to_entity": right, "relationship": relation},
                        semantic_role="CANON", source_role="COMMIT", source_ref=ref,
                        chapter=commit_chapter, provenance_status="verified",
                        fact_key=("relationship", left, right),
                    ))
                    continue
            entity = str(body.get("entity_id") or event.get("subject") or "").strip()
            field_name = str(body.get("field") or body.get("field_path") or ("relationship" if event_type == "relationship_changed" else "")).strip()
            if event_type in {"promise_created", "open_loop_created", "promise_paid_off", "open_loop_closed", "world_rule_revealed", "world_rule_broken", "artifact_obtained"}:
                event_id = str(event.get("event_id") or f"{commit_chapter}:{event_index}")
                items.append(ContextItem(
                    content={"event_type": event_type, "subject": event.get("subject", ""), "payload": body},
                    semantic_role="CANON", source_role="COMMIT", source_ref=ref,
                    chapter=commit_chapter, provenance_status="verified",
                    fact_key=("event", event_id),
                ))
                continue
            if event_type not in {"character_state_changed", "power_breakthrough", "relationship_changed"} or not entity or not field_name:
                continue
            value = body.get("new", body.get("to", body.get("new_value", body.get("new_state"))))
            items.append(ContextItem(
                content={"entity_id": entity, "field": field_name, "value": value},
                semantic_role="CANON", source_role="COMMIT", source_ref=ref,
                chapter=commit_chapter, provenance_status="verified",
                fact_key=(entity, field_name),
            ))
    return items, latest_chapter, latest_hash


def _flatten_projection(value: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_projection(child, child_prefix)
    else:
        yield prefix, value


def _max_chapter(db_path: Path, table: str) -> int | None:
    if not db_path.is_file() or table not in {"chapters", "vectors"}:
        return None
    try:
        with sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True) as conn:
            row = conn.execute(f"SELECT MAX(chapter) FROM {table}").fetchone()
            return int(row[0]) if row and row[0] is not None else None
    except (sqlite3.Error, ValueError):
        return None


def build_governed_context(
    *, project_root: Path, chapter: int, state: dict[str, Any], source_sections: dict[str, Any],
    owned_view=None,
) -> dict[str, Any]:
    """Produce explicit Writer-facing roles and diagnostics without mutating sources."""
    commits, latest_chapter, latest_hash = load_commit_fact_items(project_root, chapter, owned_view)
    try:
        state_chapter = int(((state.get("progress") or {}).get("current_chapter") or 0))
    except (TypeError, ValueError):
        state_chapter = 0
    stale_state = latest_chapter is not None and state_chapter < latest_chapter
    state_ahead = latest_chapter is not None and state_chapter > latest_chapter
    projections: list[ContextItem] = []
    entity_state = state.get("entity_state") or {}
    for entity_id, fields in entity_state.items() if isinstance(entity_state, dict) else []:
        if not isinstance(fields, dict):
            continue
        for field_name, value in _flatten_projection(fields):
            projections.append(ContextItem(
                content={"entity_id": str(entity_id), "field": field_name, "value": value},
                semantic_role="CANON", source_role="PROJECTION", source_ref=f"state:{state_chapter or 'unknown'}",
                chapter=state_chapter or None, provenance_status="unverified",
                fact_key=(str(entity_id), field_name),
            ))
    protagonist = state.get("protagonist_state") or {}
    protagonist_id = str(protagonist.get("entity_id") or "").strip() if isinstance(protagonist, dict) else ""
    for field_name, value in _flatten_projection(protagonist):
        if field_name == "entity_id":
            continue
        key_entity = protagonist_id or "protagonist"
        projections.append(ContextItem(
            content={"entity_id": key_entity, "field": field_name, "value": value},
            semantic_role="CANON", source_role="PROJECTION", source_ref=f"state:{state_chapter or 'unknown'}",
            chapter=state_chapter or None, provenance_status="unverified",
            fact_key=(key_entity, field_name),
        ))
    if stale_state or state_ahead:
        for item in projections:
            item.semantic_role = "UNKNOWN"
            item.provenance_status = "stale" if stale_state else "ahead_of_canon"

    diagnostics: list[dict[str, Any]] = []
    if stale_state:
        diagnostics.append({"type": "stale_projection", "source_ref": "state.json", "projection_chapter": state_chapter, "latest_commit_chapter": latest_chapter})
    elif state_ahead:
        diagnostics.append({"type": "projection_ahead_of_canon", "source_ref": "state.json", "projection_chapter": state_chapter, "latest_commit_chapter": latest_chapter})
    if latest_chapter is None:
        diagnostics.append({"type": "missing_canonical_source", "chapter": chapter})

    # Structured, low-risk source groupings. Raw legacy projections remain clearly
    # labeled references; they are never inserted into the Canon list.
    intent: list[ContextItem] = []
    for key in ("outline", "story_contract"):
        value = source_sections.get(key)
        if value:
            is_authored_source = key == "outline"
            intent.append(ContextItem(value, "INTENT", "OUTLINE" if is_authored_source else "CONTRACT", key,
                                      chapter=chapter, provenance_status="authoritative" if is_authored_source else "derived_copy",
                                      semantic_class="PLANNER_INTENT",
                                      source_relationship="AUTHORITATIVE_SOURCE" if is_authored_source else "DERIVED_RUNTIME_COPY",
                                      source_identity=str(source_sections.get(f"{key}_source_identity") or ""),
                                      owner="authored_outline" if is_authored_source else "runtime_contract"))
    for key in ("urgent_loops", "promise_intent"):
        value = source_sections.get(key)
        if value:
            intent.append(ContextItem(value, "INTENT", "PROJECTION", key, provenance_status="unverified_plan"))
    for row in source_sections.get("intent_facts", []) or []:
        if not isinstance(row, dict) or not row.get("fact_key"):
            continue
        intent.append(ContextItem(
            row.get("content"), "INTENT", str(row.get("source_role") or "CONTRACT"),
            str(row.get("source_ref") or "intent_fact"), chapter=row.get("chapter"),
            provenance_status="authoritative", fact_key=tuple(str(x) for x in row["fact_key"]),
            source_relationship=str(row.get("source_relationship") or "AUTHORITATIVE_SOURCE"),
            source_identity=str(row.get("source_identity") or row.get("source_ref") or "intent_fact"),
            scope=str(row.get("scope") or (f"chapter:{row['chapter']}" if row.get("chapter") is not None else "project")),
        ))
    project_info = state.get("project_info") or {}
    promise_ledger = project_info.get("promise_ledger") if isinstance(project_info, dict) else None
    if isinstance(promise_ledger, list):
        for index, row in enumerate(promise_ledger):
            if not isinstance(row, dict):
                reference.append(ContextItem(row, "UNKNOWN", "OWNER_STATE", f"state.project_info.promise_ledger[{index}]", provenance_status="unverified"))
                continue
            promise_id = str(row.get("id") or f"row:{index}")
            intent.append(ContextItem(row, "INTENT", "OWNER_STATE", f"state.project_info.promise_ledger[{index}]",
                                      provenance_status="authoritative", fact_key=("planner_promise", promise_id),
                                      semantic_class="PLANNER_INTENT", owner="promise_ledger",
                                      source_relationship="AUTHORITATIVE_SOURCE", source_identity=promise_id,
                                      scope=str(row.get("scope") or row.get("expected_payoff_volume") or "project")))
    volume_rows = state.get("volumes")
    if isinstance(volume_rows, list):
        for index, row in enumerate(volume_rows):
            if isinstance(row, dict):
                volume_id = str(row.get("index") or f"row:{index}")
                intent.append(ContextItem(row, "INTENT", "OWNER_STATE", f"state.volumes[{index}]",
                                          provenance_status="authoritative", fact_key=("volume_plan", volume_id),
                                          semantic_class="PLANNER_INTENT", owner="volumes",
                                          source_relationship="AUTHORITATIVE_SOURCE", source_identity=volume_id,
                                          scope=f"volume:{volume_id}"))
    story_craft = state.get("story_craft") or {}
    craft: list[ContextItem] = []
    reference: list[ContextItem] = []
    for row in source_sections.get("craft_facts", []) or []:
        if not isinstance(row, dict) or not row.get("fact_key"):
            continue
        craft.append(ContextItem(
            row.get("content"), "CRAFT", str(row.get("source_role") or "REVIEW"),
            str(row.get("source_ref") or "craft_recommendation"), chapter=row.get("chapter"),
            provenance_status="advisory", fact_key=tuple(str(x) for x in row["fact_key"]),
            semantic_class="CRAFT_RECOMMENDATION", source_relationship="DERIVED_RUNTIME_COPY",
            source_identity=str(row.get("source_identity") or row.get("source_ref") or "craft_recommendation"),
            scope=str(row.get("scope") or (f"chapter:{row['chapter']}" if row.get("chapter") is not None else "project")),
        ))
    for key in ("writing_guidance", "genre_profile", "reader_signal", "preferences", "author_style_patterns", "style_contract", "genre_profile_excerpt"):
        value = source_sections.get(key)
        if value:
            role = "REVIEW" if key == "reader_signal" else "CONFIG"
            craft.append(ContextItem(value, "CRAFT", role, key, provenance_status="advisory"))
    if isinstance(story_craft, dict):
        from story_craft import classify_story_craft_field

        categorized: dict[str, list[dict[str, Any]]] = {"INTENT": [], "CRAFT": [], "UNKNOWN": [], "DERIVED_REFERENCE": []}

        def visit(value: Any, path: str) -> None:
            if isinstance(value, dict):
                if not value:
                    categorized[classify_story_craft_field(path)].append({"path": path, "value": value})
                for key, child in value.items():
                    visit(child, f"{path}.{key}")
            elif isinstance(value, list):
                if not value:
                    categorized[classify_story_craft_field(path)].append({"path": path, "value": value})
                for child in value:
                    visit(child, f"{path}[]")
            else:
                role = classify_story_craft_field(path)
                categorized[role if role in categorized else "UNKNOWN"].append({"path": path, "value": value})

        for key, value in story_craft.items():
            visit(value, f"story_craft.{key}")
        for role, fields in categorized.items():
            if not fields:
                continue
            item = ContextItem(fields, role if role in {"INTENT", "CRAFT"} else "UNKNOWN",
                               "PROJECTION", f"state.story_craft.{role.lower()}",
                               provenance_status="advisory" if role == "CRAFT" else "unverified_plan",
                               semantic_class="PLANNER_INTENT" if role == "INTENT" else "CRAFT_RECOMMENDATION" if role == "CRAFT" else "UNKNOWN",
                               owner="story_craft", source_relationship="AUTHORITATIVE_SOURCE" if role in {"INTENT", "CRAFT"} else "REFERENCE",
                               source_identity=f"owner-overlay:story_craft:{role.lower()}")
            (intent if role == "INTENT" else craft if role == "CRAFT" else reference).append(item)
    chapter_meta = state.get("chapter_meta")
    if isinstance(chapter_meta, dict):
        from story_craft import classify_story_craft_field
        for chapter_key, metadata in chapter_meta.items():
            if not isinstance(metadata, dict):
                continue
            buckets: dict[str, dict[str, Any]] = {"INTENT": {}, "CRAFT": {}, "UNKNOWN": {}, "DERIVED_REFERENCE": {}}
            for field_name, value in metadata.items():
                role = classify_story_craft_field(f"chapter_meta.{chapter_key}.{field_name}")
                buckets[role if role in buckets else "UNKNOWN"][field_name] = value
            for role, values in buckets.items():
                if values:
                    try:
                        chapter_number = int(chapter_key)
                    except (TypeError, ValueError):
                        chapter_number = None
                    item = ContextItem(values, role if role in {"INTENT", "CRAFT"} else "UNKNOWN",
                                       "PROJECTION", f"state.chapter_meta.{chapter_key}.{role.lower()}",
                                       chapter=chapter_number,
                                       semantic_class="PLANNER_INTENT" if role == "INTENT" else "CRAFT_RECOMMENDATION" if role == "CRAFT" else "UNKNOWN",
                                       source_relationship="DERIVED_RUNTIME_COPY")
                    (intent if role == "INTENT" else craft if role == "CRAFT" else reference).append(item)
    for key in ("recent_summaries", "story_skeleton", "memory", "scene", "rag_assist", "plot_structure", "fulfillment_result"):
        value = source_sections.get(key)
        if value:
            source_role = "RETRIEVAL" if key == "rag_assist" else "SUMMARY" if key in {"recent_summaries", "story_skeleton"} else "REVIEW" if key == "fulfillment_result" else "LEGACY"
            if source_role == "SUMMARY" and isinstance(value, (list, dict)):
                rows = value.items() if isinstance(value, dict) else enumerate(value)
                for ref, row in rows:
                    row_chapter = row.get("chapter") if isinstance(row, dict) else None
                    summary_content = row.get("summary", row.get("content", row)) if isinstance(row, dict) else row
                    reference.append(ContextItem(summary_content, "OPERATIONAL", "SUMMARY", f"summary:{ref}", chapter=row_chapter, provenance_status="unverified"))
            else:
                reference.append(ContextItem(value, "UNKNOWN" if source_role == "LEGACY" else "OPERATIONAL", source_role, key, provenance_status="retrieval_only" if key == "rag_assist" else "intent_satisfaction_record" if key == "fulfillment_result" else "unverified"))
    if latest_chapter is not None:
        if owned_view is not None:
            latest_rows = owned_view.effective_commits_before(chapter)
            latest_payload = next((row["payload"] for row in latest_rows
                                   if row["chapter"] == latest_chapter), {})
        else:
            latest_path = Path(project_root) / ".story-system" / "commits" / f"chapter_{latest_chapter:03d}.commit.json"
            try:
                latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                latest_payload = {}
        fulfillment = latest_payload.get("fulfillment_result")
        if fulfillment:
            reference.append(ContextItem(fulfillment, "OPERATIONAL", "REVIEW", f"commit:{latest_chapter}:fulfillment_result", chapter=latest_chapter, provenance_status="intent_satisfaction_record"))
        review_result = latest_payload.get("review_result")
        if review_result:
            craft.append(ContextItem(review_result, "CRAFT", "REVIEW", f"commit:{latest_chapter}:review_result", chapter=latest_chapter, provenance_status="historical_advisory"))

    memory_pack = source_sections.get("memory_pack") or source_sections.get("long_term_memory") or {}
    represented_memory_refs: set[str] = set()
    for memory in (memory_pack.get("semantic_memory") or []) if isinstance(memory_pack, dict) else []:
        if not isinstance(memory, dict):
            continue
        evidence = memory.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        for marker in evidence:
            parts = str(marker).split(":")
            evidence_type = parts[0] if parts else ""
            if len(parts) != 4 or evidence_type not in {"state_change", "relationship"}:
                continue
            entity, field_name, chapter_text = parts[1], parts[2], parts[3]
            try:
                evidence_chapter = int(chapter_text)
            except ValueError:
                continue
            if evidence_type == "state_change":
                matching_commit = any(x.source_role == "COMMIT" and x.chapter == evidence_chapter and x.fact_key == (entity, field_name) and str((x.content or {}).get("value")) == str(memory.get("value")) for x in commits if isinstance(x.content, dict))
                fact_key = (entity, field_name)
                content = {"entity_id": entity, "field": field_name, "value": memory.get("value")}
            else:
                matching_commit = any(x.source_role == "COMMIT" and x.chapter == evidence_chapter and x.fact_key == ("relationship", entity, field_name) and str((x.content or {}).get("relationship")) == str(memory.get("value")) for x in commits if isinstance(x.content, dict))
                fact_key = ("relationship", entity, field_name)
                content = {"from_entity": entity, "to_entity": field_name, "relationship": memory.get("value")}
            represented_memory_refs.add(str(memory.get("id", marker)))
            projections.append(ContextItem(
                content=content,
                semantic_role="CANON", source_role="PROJECTION", source_ref=f"memory:{memory.get('id', marker)}",
                chapter=evidence_chapter, provenance_status="commit_evidenced" if matching_commit else "unverified",
                evidence=[str(marker)], fact_key=fact_key,
            ))
    for memory in (memory_pack.get("semantic_memory") or []) if isinstance(memory_pack, dict) else []:
        if not isinstance(memory, dict) or str(memory.get("id", "")) in represented_memory_refs:
            continue
        category = str(memory.get("category") or "")
        if category in {"open_loop", "reader_promise"}:
            intent.append(ContextItem(memory, "INTENT", "PROJECTION", f"memory:{memory.get('id', 'unknown')}", chapter=memory.get("source_chapter"), provenance_status="unverified_plan"))
        else:
            reference.append(ContextItem(memory, "UNKNOWN", "LEGACY", f"memory:{memory.get('id', 'unknown')}", chapter=memory.get("source_chapter"), provenance_status="unverified", evidence=[str(x) for x in (memory.get("evidence") or [])]))
    if isinstance(memory_pack, dict):
        for layer in ("working_memory", "episodic_memory"):
            for index, memory in enumerate(memory_pack.get(layer) or []):
                if not isinstance(memory, dict):
                    continue
                source = str(memory.get("source") or "")
                role = "INTENT" if source == "outline" else "UNKNOWN"
                source_role = "OUTLINE" if source == "outline" else "SUMMARY" if source == "summary" else "LEGACY"
                target = intent if role == "INTENT" else reference
                represented_by_fact = False
                if source == "relationship":
                    row = memory.get("content") or {}
                    if isinstance(row, dict):
                        left = str(row.get("from_entity") or row.get("from") or "").strip()
                        right = str(row.get("to_entity") or row.get("to") or "").strip()
                        value = row.get("relationship_type", row.get("relation_type", row.get("type")))
                        if left and right and value is not None:
                            represented_by_fact = True
                            projections.append(ContextItem(
                                {"from_entity": left, "to_entity": right, "relationship": value},
                                "CANON", "PROJECTION", f"index_relationship:{left}:{right}",
                                chapter=memory.get("chapter"), provenance_status="unverified",
                                fact_key=("relationship", left, right),
                            ))
                if not represented_by_fact:
                    target.append(ContextItem(memory, role, source_role, f"{layer}:{source}:{index}", chapter=memory.get("chapter"), provenance_status="authoritative" if role == "INTENT" else "unverified"))
    derived_obligations = []
    retained_commits = []
    for item in commits:
        if "commit_chapter_meta" in item.evidence:
            if item.semantic_role == "INTENT":
                intent.append(item)
            elif item.semantic_role == "CRAFT":
                craft.append(item)
            else:
                reference.append(item)
            continue
        payload = item.content if isinstance(item.content, dict) else {}
        event_type = payload.get("event_type")
        if event_type in {"promise_created", "open_loop_created", "promise_paid_off", "open_loop_closed"}:
            event_id = (item.fact_key or ("event", "unknown"))[-1]
            derived_obligations.append(ContextItem(
                item.content, "INTENT", "COMMIT", item.source_ref, chapter=item.chapter,
                provenance_status="commit_evidenced", evidence=item.evidence,
                fact_key=item.fact_key, semantic_class="CANON_DERIVED_OBLIGATION",
                source_relationship="AUTHORITATIVE_SOURCE", source_identity=str(event_id),
                scope=str(payload.get("subject") or "story"),
            ))
        else:
            retained_commits.append(item)
    intent.extend(derived_obligations)
    facts, projection_diagnostics = resolve_fact_items([*retained_commits, *projections])
    diagnostics.extend(projection_diagnostics)
    canon_by_key = {tuple(item.fact_key): item for item in facts if item.semantic_role == "CANON" and item.fact_key}
    intents_by_key: dict[tuple[str, ...], list[ContextItem]] = {}
    for item in intent:
        if item.fact_key:
            intents_by_key.setdefault(tuple(item.fact_key), []).append(item)
            canon_item = canon_by_key.get(tuple(item.fact_key))
            if canon_item is not None and item.content != canon_item.content:
                diagnostics.append({"type": "intent_canon_ambiguity", "fact_key": list(item.fact_key), "canon": _describe(canon_item), "intent": _describe(item)})
    for fact_key, rows in intents_by_key.items():
        scoped: dict[str, list[ContextItem]] = {}
        for row in rows:
            scoped.setdefault(row.scope or "project", []).append(row)
        for exact_scope, scoped_rows in scoped.items():
            sources = [row for row in scoped_rows if row.source_relationship in {"AUTHORITATIVE_SOURCE", "SCOPED_AUTHORED_OVERRIDE"}]
            copies = [row for row in scoped_rows if row.source_relationship == "DERIVED_RUNTIME_COPY"]
            source_ids = {row.source_identity for row in sources}
            for copy in copies:
                matching = [row for row in sources if row.source_identity == copy.source_identity]
                if matching and any(row.content != copy.content for row in matching):
                    diagnostics.append({"type": "stale_runtime_copy", "source_identity": copy.source_identity,
                                        "copy_identity": copy.source_ref, "scope": exact_scope,
                                        "source_value": matching[0].content, "copy_value": copy.content,
                                        "source_ref": matching[0].source_ref, "copy_ref": copy.source_ref})
            independent = [row for row in sources if row.semantic_class != "CANON_DERIVED_OBLIGATION"]
            if len({repr(row.content) for row in independent}) > 1:
                diagnostics.append({"type": "intent_conflict", "fact_key": list(fact_key),
                                    "scope": exact_scope, "sources": [_describe(row) for row in independent]})
            exact_craft = [row for row in craft if row.fact_key == fact_key and (row.scope or "project") == exact_scope]
            for recommendation in exact_craft:
                if any(source.content != recommendation.content for source in scoped_rows):
                    diagnostics.append({"type": "craft_recommendation_differs_from_intent",
                                        "fact_key": list(fact_key), "scope": exact_scope,
                                        "intent": [_describe(row) for row in scoped_rows],
                                        "craft_recommendation": _describe(recommendation),
                                        "blocking": False})
    for copy in intent:
        if copy.source_relationship != "DERIVED_RUNTIME_COPY":
            continue
        exact_sources = [row for row in intent
                         if row.source_relationship in {"AUTHORITATIVE_SOURCE", "SCOPED_AUTHORED_OVERRIDE"}
                         and (row.scope or "project") == (copy.scope or "project")]
        if copy.source_identity:
            exact_matches = [row for row in exact_sources if row.source_identity == copy.source_identity]
            for source in exact_matches:
                # Root outline/contract sections have no fact_key, so compare only
                # their explicit identity and exact scope. Never infer a link.
                if source.fact_key or copy.fact_key:
                    continue
                if source.content != copy.content:
                    diagnostics.append({"type": "stale_runtime_copy", "source_identity": copy.source_identity,
                                        "copy_identity": copy.source_ref, "scope": copy.scope or "project",
                                        "source_value": source.content, "copy_value": copy.content,
                                        "source_ref": source.source_ref, "copy_ref": copy.source_ref})
            continue
        if exact_sources:
            diagnostics.append({"type": "source_relationship_unresolved",
                                "copy_ref": copy.source_ref, "scope": copy.scope,
                                "candidate_sources": [_describe(row) for row in exact_sources],
                                "requires": "exact semantic identity and source relationship; values were not merged"})
    for item in facts:
        if item.semantic_role == "UNKNOWN":
            reference.append(ContextItem(
                item.content, "UNKNOWN", item.source_role, item.source_ref,
                chapter=item.chapter, provenance_status=item.provenance_status,
                evidence=item.evidence, fact_key=item.fact_key,
            ))
    for key in ("active_rules", "protagonist", "progress", "urgent_loops"):
        value = source_sections.get(key)
        if value and key != "urgent_loops":
            reference.append(ContextItem(value, "UNKNOWN", "LEGACY", key, provenance_status="unverified"))

    index_chapter = _max_chapter(Path(project_root) / ".webnovel" / "index.db", "chapters")
    vector_chapter = _max_chapter(Path(project_root) / ".webnovel" / "vectors.db", "vectors")
    projection_freshness = {"state": state_chapter, "index": index_chapter, "vector": vector_chapter}
    if latest_chapter is not None:
        for name, source_chapter in (("index", index_chapter), ("vector", vector_chapter)):
            if source_chapter is not None and source_chapter < latest_chapter:
                diagnostics.append({"type": "stale_projection", "source_ref": name, "projection_chapter": source_chapter, "latest_commit_chapter": latest_chapter})
            elif source_chapter is not None and source_chapter > latest_chapter:
                diagnostics.append({"type": "projection_ahead_of_canon", "source_ref": name, "projection_chapter": source_chapter, "latest_commit_chapter": latest_chapter})

    return {
        "canon": [item.to_dict() for item in facts if item.semantic_role == "CANON"],
        "intent": [item.to_dict() for item in intent],
        "craft": [item.to_dict() for item in craft],
        "reference": [item.to_dict() for item in reference],
        "diagnostics": diagnostics,
        "snapshot": {
            "latest_commit": {"chapter": latest_chapter, "sha256": latest_hash} if latest_chapter is not None else None,
            "projection_chapter": state_chapter,
            "projection_freshness": projection_freshness,
            "semantic_activation_id": owned_view.pinned.semantic_activation_id if owned_view is not None else None,
            "generation_id": owned_view.pinned.generation_id if owned_view is not None else None,
            "publication_record_id": owned_view.pinned.publication_record_id if owned_view is not None else None,
        },
    }
