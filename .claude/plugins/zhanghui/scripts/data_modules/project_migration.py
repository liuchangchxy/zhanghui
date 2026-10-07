"""Read-only Phase 9 migration preflight/dry run and verified backup helpers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import tempfile
from typing import Any

from .canon_correction_schema import artifact_sha256, canonical_json
from .config import DataModulesConfig
from .effective_history import EffectiveHistoryStore
from .owned_project_view import activation_health_report
from .projection_generation import ProjectionGeneration
from .story_event_schema import StoryEvent
from story_craft import classify_story_craft_field


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreflightReport:
    schema_version: str
    project_root: str
    ok: bool
    active_status: str
    active: dict[str, Any]
    candidates: list[dict[str, Any]]
    evidence_hashes: dict[str, str]
    owner_mappings: dict[str, Any]
    legacy_history: dict[str, Any]
    conflicts: list[dict[str, Any]]
    report_digest: str


@dataclass(frozen=True)
class MigrationPlan:
    schema_version: str
    project_root: str
    preflight_digest: str
    plan_digest: str
    canon_slices: list[dict[str, Any]]
    owner_dispositions: dict[str, Any]
    mutable_overlays: list[dict[str, Any]]
    preserved_sources: list[dict[str, Any]]
    output_hashes: dict[str, str]
    unresolved_decisions: list[dict[str, Any]]


@dataclass(frozen=True)
class BackupManifest:
    schema_version: str
    project_root: str
    backup_path: str
    plan_digest: str
    file_count: int
    files: list[dict[str, Any]]
    sqlite_integrity: dict[str, str]
    restore_verified: bool
    manifest_sha256: str


@dataclass(frozen=True)
class MigrationResult:
    schema_version: str
    project_root: str
    report_digest: str
    plan_digest: str
    backup_manifest_sha256: str
    publication: dict[str, Any]
    generation_id: str
    overlay_revision: int
    migration_owned_hashes: dict[str, str]


def _scoped_paths(root: Path) -> list[Path]:
    paths = []
    for relative in (".story-system", ".webnovel"):
        base = root / relative
        if base.exists():
            paths.extend(path for path in base.rglob("*")
                         if path.is_file() and ".story-system/backups/phase9" not in path.relative_to(root).as_posix())
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def _hash_files(root: Path, paths: list[Path] | None = None) -> dict[str, str]:
    result = {}
    for path in paths if paths is not None else _scoped_paths(root):
        if path.is_symlink():
            result[path.relative_to(root).as_posix()] = "SYMLINK_UNSUPPORTED"
        else:
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _json_file(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _owner_inventory(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    webnovel = root / ".webnovel"
    state = _json_file(webnovel / "state.json") or {}
    state_canon = {"entity_state", "protagonist_state", "strand_tracker"}
    owner_roots = {"story_craft", "planning", "promise_ledger", "review_checkpoints",
                   "workflow", "craft", "intent", "disambiguation_warnings", "disambiguation_pending",
                   "project_info", "volumes"}
    owner_paths = {"progress.volumes_planned", "progress.current_volume", "progress.total_volumes",
                   "progress.volumes_completed", "progress.last_updated"}
    known = state_canon | owner_roots | {"progress", "meta", "schema_version", "project_info", "state",
                                         "plot_threads", "relationships", "state_changes", "volumes",
                                         "world_settings", "chapter_meta", "_migrated_to_sqlite", "_migration_timestamp"}
    conflicts = []
    unknown = sorted(set(state) - known)
    for key in unknown:
        conflicts.append({"kind": "unmapped_state_root", "path": f".webnovel/state.json:{key}",
                          "requires": "explicit owner mapping"})
    progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
    progress_owner = sorted(set(progress) & {"volumes_planned", "current_volume", "total_volumes",
                                             "volumes_completed", "last_updated"})
    progress_canon = sorted(set(progress) & {"current_chapter", "total_words", "chapter_status"})
    unmapped_progress = sorted(set(progress) - set(progress_owner) - set(progress_canon) - {"chapter_meta"})
    for key in unmapped_progress:
        conflicts.append({"kind": "unmapped_progress_field", "path": f".webnovel/state.json:progress.{key}",
                          "requires": "explicit owner mapping"})

    field_classes = {}
    # Promise rows retain their original bytes. Validation is read-only and
    # exact: additive legacy omissions are accepted, unknown keys are not.
    promise_known = {"id", "type", "depth", "planted_chapter", "planted_volume",
                     "expected_payoff_chapter", "expected_payoff_volume", "status",
                     "created_at", "updated_at", "notes", "audit_log", "canon_event_ref"}
    promise_optional = {"created_at", "updated_at", "notes", "audit_log", "canon_event_ref"}
    def promise_conflict(kind, path):
        conflicts.append({"kind": kind, "path": f".webnovel/state.json:{path}",
                          "value_preserved": True, "requires": "preserve source; resolve exact Promise schema"})

    def validate_story_craft(value):
        prefix = ".webnovel/state.json:story_craft"
        if not isinstance(value, dict):
            conflicts.append({"kind": "malformed_story_craft_container", "path": prefix,
                              "value_preserved": True, "requires": "preserve source"})
            field_classes["story_craft"] = "UNKNOWN"
            return
        snapshot = EffectiveHistoryStore().read_active_snapshot(root)
        accepted_events_by_id: dict[str, list[StoryEvent]] = {}
        accepted_id_counts: dict[str, int] = {}
        for chapter_entry in snapshot.chapters.values():
            if chapter_entry.status != "accepted":
                continue
            for event in (chapter_entry.extraction_result or {}).get("accepted_events", []):
                if not isinstance(event, dict) or not isinstance(event.get("event_id"), str):
                    continue
                event_id = event["event_id"]
                accepted_id_counts[event_id] = accepted_id_counts.get(event_id, 0) + 1
                try:
                    validated_event = StoryEvent.model_validate(event)
                except Exception:
                    continue
                if validated_event.chapter != chapter_entry.chapter:
                    continue
                accepted_events_by_id.setdefault(event_id, []).append(validated_event)
        accepted_events_by_id = {
            event_id: events for event_id, events in accepted_events_by_id.items()
            if accepted_id_counts.get(event_id) == 1 and len(events) == 1
        }
        # Exact known shapes. Nested objects are allowlisted per container;
        # the classifier supplies semantic class for every leaf.
        schemas = {
            "rhythm_curve": {"last_emotion_peak_chapter", "chapters_since_peak", "warning_threshold", "block_threshold", "history"},
            "foreshadow_chain": {"id", "type", "depth", "content", "buried_chapter", "expected_payoff_chapter", "payoff_method", "linked_entities", "status", "buried_quality", "payoff_chapter", "payoff_quality", "occurrence_ref"},
            "timed_locks": {"id", "description", "trigger_chapter", "deadline_chapter", "status", "fulfilled_chapter", "occurrence_ref"},
            "thematic_echoes": {"id", "premise", "echoes"},
            "character_arc": {"name", "starting_state", "ending_state", "transformation", "key_moments", "desired_change", "milestones", "target", "quality", "evaluation", "structural_quality"},
            "volume_beat": {"volume", "total_chapters", "beats"},
            "volume_beats": None,
            "reader_contract": {"version", "expectation_debt", "causal_credits", "endgame_reserves", "swap_debts", "contract_fulfillment"},
            "volume_anchors": {"version", "anchors"},
            "event_matrix_state": {"version", "types", "history", "gentle_window", "max_consecutive_fast"},
            "pacing_history": {"version", "history", "rules"},
        }
        def bad(path, kind="unknown_story_craft_field"):
            field_classes[path] = "UNKNOWN"
            suffix = path.removeprefix("story_craft.")
            suffix = __import__("re").sub(r"\.(\d+)(?=\.)", r"[\1]", suffix)
            conflicts.append({"kind": kind, "path": f"{prefix}.{suffix}",
                              "value_preserved": True, "requires": "preserve source; exact field mapping required"})
        def classify(path, val, *, accepted_evidence_linked=False):
            cls = classify_story_craft_field(path, val, accepted_evidence_linked=accepted_evidence_linked)
            field_classes[path] = cls
            if path == "story_craft.reader_contract.endgame_reserves" and val == []:
                return  # inert legacy default: no authored reserve assertion
            if cls == "UNKNOWN": bad(path)
        def shape(path, value, expected):
            valid = (type(value) is int) if expected == "int" else (
                isinstance(value, str) if expected == "str" else (
                    isinstance(value, bool) if expected == "bool" else (
                        isinstance(value, list) if expected == "list" else isinstance(value, dict))))
            if not valid:
                bad(path, "malformed_story_craft_field")
        for key, val in value.items():
            path = f"story_craft.{key}"
            if key not in schemas:
                bad(path)
                continue
            allowed = schemas[key]
            if key == "volume_beats":
                if not isinstance(val, dict):
                    bad(path, "malformed_story_craft_container"); continue
                for vol, sheet in val.items():
                    if not isinstance(sheet, dict) or set(sheet) - schemas["volume_beat"]:
                        bad(f"{path}.{vol}", "malformed_story_craft_container"); continue
                    if not {"volume", "total_chapters", "beats"} <= set(sheet):
                        bad(f"{path}.{vol}", "malformed_story_craft_container")
                    for child, child_val in sheet.items():
                        child_path = f"{path}.{vol}.{child}"
                        if child == "volume" or child == "total_chapters": shape(child_path, child_val, "int")
                        elif child == "beats":
                            shape(child_path, child_val, "list")
                            if isinstance(child_val, list):
                                for idx, beat in enumerate(child_val):
                                    if not isinstance(beat, dict) or set(beat) - {"name", "chapter", "filled", "notes"}:
                                        bad(f"{child_path}.{idx}", "malformed_story_craft_container")
                                    else:
                                        if not {"name", "chapter", "filled"} <= set(beat):
                                            bad(f"{child_path}.{idx}", "malformed_story_craft_container")
                                        for leaf, leaf_value in beat.items():
                                            if leaf == "notes" and leaf_value is None: continue
                                            shape(f"{child_path}.{idx}.{leaf}", leaf_value,
                                                  {"name": "str", "chapter": "int", "filled": "bool", "notes": "str"}[leaf])
                        classify(f"{path}.{child}", child_val)
                continue
            if key in {"foreshadow_chain", "timed_locks", "thematic_echoes"}:
                if not isinstance(val, list):
                    bad(path, "malformed_story_craft_container"); continue
                allowed_child = schemas[key]
                for idx, item in enumerate(val):
                    if not isinstance(item, dict):
                        bad(f"{path}.{idx}", "malformed_story_craft_container"); continue
                    required_children = {"foreshadow_chain": {"id", "type", "depth"},
                                         "timed_locks": {"id", "description", "deadline_chapter"},
                                         "thematic_echoes": {"id", "premise", "echoes"}}[key]
                    if not required_children <= set(item):
                        bad(f"{path}.{idx}", "malformed_story_craft_container")
                    accepted_occurrence_link = False
                    linked_event = None
                    occurrence_ref = item.get("occurrence_ref")
                    if isinstance(occurrence_ref, dict) and set(occurrence_ref) == {"event_id"}:
                        event_id = occurrence_ref.get("event_id")
                        matches = accepted_events_by_id.get(event_id, []) if isinstance(event_id, str) else []
                        if len(matches) == 1:
                            accepted_occurrence_link = True
                            linked_event = matches[0]
                    def claim_has_link(field_name: str) -> bool:
                        if not linked_event:
                            return False
                        occurrence_fields = {"buried_chapter", "payoff_chapter", "fulfilled_chapter"}
                        claims = [name for name in occurrence_fields
                                  if item.get(name) is not None and item.get(name) == linked_event.chapter]
                        if len(claims) != 1 or claims[0] != field_name:
                            return False
                        return True
                    for child, child_val in item.items():
                        child_path = f"{path}.{idx}.{child}"
                        if child not in allowed_child: bad(child_path); continue
                        if child_val is None and child in {"buried_chapter", "payoff_chapter", "fulfilled_chapter", "occurrence_ref"}:
                            # Production writers use null as an unasserted placeholder.
                            # Preserve it without assigning semantic authority.
                            continue
                        types = {
                            "foreshadow_chain": {"id": "str", "type": "str", "depth": "str", "content": "str", "buried_chapter": "int", "expected_payoff_chapter": "int", "payoff_method": "str", "linked_entities": "list", "status": "str", "buried_quality": "str", "payoff_chapter": "int", "payoff_quality": "str"},
                            "timed_locks": {"id": "str", "description": "str", "trigger_chapter": "int", "deadline_chapter": "int", "status": "str", "fulfilled_chapter": "int"},
                            "thematic_echoes": {"id": "str", "premise": "str", "echoes": "list"},
                        }
                        if child in types[key] and child_val is not None:
                            shape(child_path, child_val, types[key][child])
                        if child == "occurrence_ref":
                            # Migration only trusts exact event IDs found in effective accepted history.
                            if not isinstance(child_val, dict) or set(child_val) != {"event_id"}:
                                bad(child_path, "malformed_story_craft_container"); continue
                            event_id = child_val.get("event_id")
                            field_classes[child_path] = classify_story_craft_field(
                                child_path, child_val, accepted_evidence_linked=accepted_occurrence_link)
                            if not accepted_occurrence_link: bad(child_path)
                        elif child == "echoes":
                            if not isinstance(child_val, list): bad(child_path, "malformed_story_craft_container"); continue
                            for ei, echo in enumerate(child_val):
                                if not isinstance(echo, dict): bad(f"{child_path}.{ei}", "malformed_story_craft_container"); continue
                                if not {"chapter", "manifestation"} <= set(echo):
                                    bad(f"{child_path}.{ei}", "malformed_story_craft_container")
                                for ec in echo:
                                    ep = f"{child_path}.{ei}.{ec}"
                                    if ec == "chapter": shape(ep, echo[ec], "int")
                                    elif ec == "manifestation": shape(ep, echo[ec], "str")
                                    classify(ep, echo[ec], accepted_evidence_linked=accepted_occurrence_link)
                        else: classify(child_path, child_val,
                                       accepted_evidence_linked=claim_has_link(child))
                continue
            if key == "rhythm_curve":
                if not isinstance(val, dict) or set(val) - allowed:
                    bad(path, "malformed_story_craft_container"); continue
                types = {"last_emotion_peak_chapter": "int", "chapters_since_peak": "int",
                         "warning_threshold": "int", "block_threshold": "int", "history": "list"}
                for child, child_val in val.items():
                    child_path = f"{path}.{child}"
                    shape(child_path, child_val, types[child])
                    if child == "history" and isinstance(child_val, list):
                        for idx, item in enumerate(child_val):
                            if not isinstance(item, dict) or set(item) - {"chapter", "intensity", "type"}:
                                bad(f"{child_path}.{idx}", "malformed_story_craft_container")
                            else:
                                if not {"chapter", "intensity", "type"} <= set(item):
                                    bad(f"{child_path}.{idx}", "malformed_story_craft_container")
                                for leaf, leaf_value in item.items(): shape(f"{child_path}.{idx}.{leaf}", leaf_value,
                                    {"chapter": "int", "intensity": "int", "type": "str"}[leaf])
                    else:
                        classify(child_path, child_val)
                    if child == "history":
                        classify(child_path, child_val)
                continue
            if key in {"character_arc", "volume_beat"} and val is None:
                field_classes[path] = "INTENT"; continue
            if key in {"character_arc", "volume_beat", "reader_contract", "volume_anchors", "event_matrix_state", "pacing_history"}:
                if not isinstance(val, dict) or set(val) - allowed:
                    bad(path, "malformed_story_craft_container"); continue
                nested_types = {
                    "character_arc": {"name": "str", "starting_state": "str", "ending_state": "str", "transformation": "str", "key_moments": "list", "desired_change": "str", "milestones": "list", "target": "str", "quality": "str", "evaluation": "str", "structural_quality": "str"},
                    "volume_beat": {"volume": "int", "total_chapters": "int", "beats": "list"},
                    "reader_contract": {"version": "int", "expectation_debt": "list", "causal_credits": "dict", "endgame_reserves": "list", "swap_debts": "list", "contract_fulfillment": "list"},
                    "volume_anchors": {"version": "int", "anchors": "list"},
                    "event_matrix_state": {"version": "int", "types": "dict", "history": "list", "gentle_window": "int", "max_consecutive_fast": "int"},
                    "pacing_history": {"version": "int", "history": "list", "rules": "dict"},
                }
                for child, child_val in val.items():
                    child_path = f"{path}.{child}"
                    shape(child_path, child_val, nested_types[key][child])
                    classify(child_path, child_val)
                    if key == "volume_beat" and child == "beats" and isinstance(child_val, list):
                        for idx, beat in enumerate(child_val):
                            bp = f"{child_path}.{idx}"
                            if not isinstance(beat, dict) or set(beat) - {"name", "chapter", "filled", "notes"}:
                                bad(bp, "malformed_story_craft_container"); continue
                            if not {"name", "chapter", "filled"} <= set(beat):
                                bad(bp, "malformed_story_craft_container")
                            for field, item_value in beat.items():
                                if field == "notes" and item_value is None: continue
                                shape(f"{bp}.{field}", item_value,
                                      {"name": "str", "chapter": "int", "filled": "bool", "notes": "str"}[field])
                    if key == "reader_contract" and child == "causal_credits" and isinstance(child_val, dict):
                        if set(child_val) - {"protagonist_actions_used_without_setup"}:
                            bad(child_path, "unknown_story_craft_field")
                        actions = child_val.get("protagonist_actions_used_without_setup", [])
                        if not isinstance(actions, list) or any(not isinstance(action, str) for action in actions):
                            bad(f"{child_path}.protagonist_actions_used_without_setup", "malformed_story_craft_container")
                    if key == "character_arc" and child in {"key_moments", "milestones"} and isinstance(child_val, list):
                        if any(not isinstance(item, str) for item in child_val):
                            bad(child_path, "malformed_story_craft_container")
                    if key == "reader_contract" and child in {"expectation_debt", "endgame_reserves", "swap_debts", "contract_fulfillment"} and isinstance(child_val, list):
                        row_keys = {
                            "expectation_debt": {"id", "description", "expected", "expected_chapter", "created_chapter", "satisfied_chapter", "status", "source"},
                            "endgame_reserves": {"id", "name", "used", "used_chapter", "status"},
                            "swap_debts": {"risk", "description", "chapter", "status"},
                            "contract_fulfillment": {"promise_id", "status", "chapter_promised", "chapter_satisfied"},
                        }[child]
                        for idx, row in enumerate(child_val):
                            rp = f"{child_path}.{idx}"
                            if isinstance(row, dict) and set(row) - row_keys:
                                bad(rp, "unknown_story_craft_field")
                            elif isinstance(row, dict):
                                required = {"expectation_debt": {"description"},
                                            "endgame_reserves": {"name"},
                                            "swap_debts": {"risk"},
                                            "contract_fulfillment": {"promise_id", "status"}}[child]
                                if not required <= set(row): bad(rp, "malformed_story_craft_container")
                                for field, item_value in row.items():
                                    if field in {"id", "description", "expected", "source", "name", "risk", "promise_id", "status"} and not isinstance(item_value, str):
                                        bad(f"{rp}.{field}", "malformed_story_craft_field")
                                    elif field.endswith("chapter") and item_value is not None and type(item_value) is not int:
                                        bad(f"{rp}.{field}", "malformed_story_craft_field")
                            elif not isinstance(row, (dict, str)):
                                bad(rp, "malformed_story_craft_container")
                    if key == "event_matrix_state" and child == "types" and isinstance(child_val, dict):
                        for type_key, type_value in child_val.items():
                            if not isinstance(type_key, str) or not isinstance(type_value, (str, int, bool)):
                                bad(f"{child_path}.{type_key}", "malformed_story_craft_container")
                    if key == "volume_anchors" and child == "anchors" and isinstance(child_val, list):
                        for idx, anchor in enumerate(child_val):
                            ap = f"{child_path}.{idx}"
                            if not isinstance(anchor, dict) or set(anchor) - {"volume", "total_chapters", "current_chapter", "must_not_reveal"}:
                                bad(ap, "malformed_story_craft_container"); continue
                            if not {"volume", "total_chapters"} <= set(anchor):
                                bad(ap, "malformed_story_craft_container")
                            for field, item in anchor.items():
                                expected = "list" if field == "must_not_reveal" else "int"
                                shape(f"{ap}.{field}", item, expected)
                                if field == "must_not_reveal" and isinstance(item, list) and any(not isinstance(x, str) for x in item):
                                    bad(f"{ap}.{field}", "malformed_story_craft_container")
                    if key == "event_matrix_state" and child == "history" and isinstance(child_val, list):
                        for idx, record in enumerate(child_val):
                            if not isinstance(record, dict) or set(record) - {"primary"}:
                                bad(f"{child_path}.{idx}", "malformed_story_craft_container")
                            elif "primary" not in record or not isinstance(record["primary"], str):
                                bad(f"{child_path}.{idx}.primary", "malformed_story_craft_field")
                    if key == "pacing_history" and child == "rules" and isinstance(child_val, dict):
                        if set(child_val) - {"max_consecutive_fast", "slow_per_4_chapters_min"}:
                            bad(child_path, "unknown_story_craft_field")
                        for rule, rule_value in child_val.items(): shape(f"{child_path}.{rule}", rule_value, "int")
                    if key == "pacing_history" and child == "history" and isinstance(child_val, list):
                        for idx, record in enumerate(child_val):
                            if not isinstance(record, dict) or set(record) - {"tier", "chapter", "type"}:
                                bad(f"{child_path}.{idx}", "malformed_story_craft_container")
                            else:
                                if not {"tier", "chapter"} <= set(record):
                                    bad(f"{child_path}.{idx}", "malformed_story_craft_container")
                                for field, item in record.items(): shape(f"{child_path}.{idx}.{field}", item,
                                    "int" if field == "chapter" else "str")

    if "story_craft" in state:
        validate_story_craft(state["story_craft"])
    chapter_meta = state.get("chapter_meta")
    if chapter_meta is not None:
        # Exact field names only. No accepted evidence binding is established
        # by this legacy state migration, so occurrence flags remain UNKNOWN.
        craft_fields = {"hook_type", "beat_position", "scene_goal", "scene_conflict",
                        "scene_setback", "scene_resolution", "sequel_reaction",
                        "sequel_dilemma", "sequel_decision"}
        intent_fields_meta = {"must_cover", "forbidden", "CBN", "CPNs", "CEN",
                              "strand", "coolpoint", "time_anchor", "villain_tier"}
        reference_fields = {"title", "word_count", "summary"}
        if not isinstance(chapter_meta, dict):
            conflicts.append({"kind": "malformed_chapter_meta", "path": ".webnovel/state.json:chapter_meta",
                              "requires": "preserve source; field semantics unavailable"})
        else:
            for chapter_key, fields in chapter_meta.items():
                prefix = f"chapter_meta.{chapter_key}"
                if not isinstance(fields, dict):
                    field_classes[prefix] = "UNKNOWN"
                    conflicts.append({"kind": "malformed_chapter_meta_entry",
                                      "path": f".webnovel/state.json:{prefix}",
                                      "requires": "preserve source; explicit field mapping required"})
                    continue
                for field_name, value in fields.items():
                    path = f"{prefix}.{field_name}"
                    if field_name in craft_fields:
                        semantic = "CRAFT"
                    elif field_name in intent_fields_meta:
                        semantic = "INTENT"
                    elif field_name in reference_fields:
                        semantic = "DERIVED_REFERENCE"
                    else:
                        semantic = "UNKNOWN"
                    field_classes[path] = semantic
                    if semantic == "UNKNOWN":
                        conflicts.append({"kind": "unknown_chapter_meta_field",
                                          "path": f".webnovel/state.json:{path}",
                                          "value_preserved": True,
                                          "requires": "explicit field and evidence mapping"})
    for key in ("_migrated_to_sqlite", "_migration_timestamp"):
        if key in state:
            field_classes[key] = "PRESERVED_COMPATIBILITY_METADATA"
    for key in progress_owner:
        field_classes[f"progress.{key}"] = "OWNER_WORKFLOW_METADATA"
    for key in progress_canon:
        field_classes[f"progress.{key}"] = "LEGACY_DERIVED_CANON_PROJECTION"
    intent_fields = {"title", "genre", "genre_label", "genre_tags", "tags", "core_selling_points",
                     "target_reader", "target_words", "target_chapters", "story_pitch", "story_premise",
                     "characters", "world_setting", "outline", "theme", "golden_finger_name",
                     "golden_finger_type", "golden_finger_style", "protagonist_structure", "heroine_config",
                     "heroine_names", "heroine_role", "co_protagonists", "co_protagonist_roles",
                     "antagonist_tiers", "world_scale", "factions", "power_system_type", "social_class",
                     "resource_distribution", "gf_visibility", "gf_irreversible_cost", "currency_system",
                     "currency_exchange", "sect_hierarchy", "cultivation_chain", "cultivation_subtiers",
                     "later_volumes_status", "confirmed_through_volume", "cross_volume_beat_map"}
    # The ledger is planner-owned Intent. Keep its bytes in the existing
    # project_info owner; malformed rows remain preserved and diagnostic.
    intent_fields.add("promise_ledger")
    config_fields = {"author", "language", "output_dir", "project_id", "platform", "created_at"}
    project_info = state.get("project_info") if isinstance(state.get("project_info"), dict) else {}
    for key in sorted(project_info):
        if key in intent_fields:
            field_classes[f"project_info.{key}"] = "OWNER_INTENT"
            if key == "promise_ledger":
                ledger = project_info[key]
                if not isinstance(ledger, list):
                    conflicts.append({"kind": "malformed_planner_promise_ledger",
                                      "path": ".webnovel/state.json:project_info.promise_ledger",
                                      "requires": "preserve source and explicitly map ledger shape"})
                else:
                    for index, entry in enumerate(ledger):
                        required = {"id", "type", "depth", "planted_chapter", "planted_volume",
                                    "expected_payoff_chapter", "expected_payoff_volume", "status"}
                        if not isinstance(entry, dict) or not required <= set(entry):
                            conflicts.append({"kind": "malformed_planner_promise_entry",
                                              "path": f".webnovel/state.json:project_info.promise_ledger[{index}]",
                                              "requires": "preserve source row and explicitly map its schema"})
                            continue
                        for extra in sorted(set(entry) - promise_known):
                            promise_conflict("unknown_planner_promise_field",
                                             f"project_info.promise_ledger[{index}].{extra}")
                        for missing in sorted((promise_known - promise_optional) - set(entry)):
                            promise_conflict("malformed_planner_promise_field",
                                             f"project_info.promise_ledger[{index}].{missing}")
                        try:
                            from .promise_ledger import ForeshadowEntry
                            if not isinstance(entry["id"], str) or not entry["id"]: raise ValueError("id")
                            if entry["status"] not in {"pending", "advanced", "paid_off", "overdue"}:
                                promise_conflict("invalid_planner_promise_field", f"project_info.promise_ledger[{index}].status")
                            if entry["type"] not in {"foreshadow", "promise", "callback"}:
                                promise_conflict("invalid_planner_promise_field", f"project_info.promise_ledger[{index}].type")
                            for num in ("depth", "planted_chapter", "planted_volume", "expected_payoff_chapter", "expected_payoff_volume"):
                                if type(entry[num]) is not int: raise ValueError(num)
                            if entry.get("created_at", "") is not None and not isinstance(entry.get("created_at", ""), str): raise ValueError("created_at")
                            if entry.get("updated_at", "") is not None and not isinstance(entry.get("updated_at", ""), str): raise ValueError("updated_at")
                            if entry.get("notes", "") is not None and not isinstance(entry.get("notes", ""), str): raise ValueError("notes")
                            if not isinstance(entry.get("audit_log", []), list): raise ValueError("audit_log")
                            for audit in entry.get("audit_log", []):
                                if (not isinstance(audit, dict) or set(audit) - {"action", "chapter", "ts"}
                                        or audit.get("action") not in {"advance", "payoff", "mark_overdue", "defer", "cancel"}
                                        or type(audit.get("chapter")) is not int or not isinstance(audit.get("ts"), str)):
                                    raise ValueError("audit_log")
                            if entry.get("canon_event_ref") is not None and not isinstance(entry["canon_event_ref"], str): raise ValueError("canon_event_ref")
                            ForeshadowEntry.from_dict(entry)
                        except (ValueError, TypeError, KeyError) as exc:
                            message = str(exc)
                            invalid_field = next((name for name in ("expected_payoff_chapter", "planted_chapter", "planted_volume", "depth", "status", "type", "audit_log", "canon_event_ref", "created_at", "updated_at", "notes") if name in message), "row")
                            promise_conflict("invalid_planner_promise_field",
                                             f"project_info.promise_ledger[{index}].{invalid_field}")
        elif key in config_fields:
            field_classes[f"project_info.{key}"] = "OWNER_PROJECT_CONFIG"
        else:
            conflicts.append({"kind": "unmapped_legacy_field", "path": f".webnovel/state.json:project_info.{key}",
                              "requires": "explicit owner mapping"})
    legacy_root_classes = {
        "state_changes": "LEGACY_DERIVED_CANON_PROJECTION",
        "relationships": "LEGACY_DERIVED_CANON_PROJECTION",
        "plot_threads": "LEGACY_AMBIGUOUS_CANON_OR_INTENT",
        "world_settings": "LEGACY_AMBIGUOUS_CANON_OR_INTENT",
        "volumes": "OWNER_INTENT_PLANNING",
    }
    for root_name, classification in legacy_root_classes.items():
        value = state.get(root_name)
        field_classes[root_name] = classification
        if value not in (None, {}, []):
            if root_name == "volumes":
                field_classes[root_name] = "OWNER_INTENT_PLANNING"
            elif root_name in {"plot_threads", "world_settings"}:
                def leaves(item, prefix):
                    if item == {} or item == []:
                        return
                    if isinstance(item, dict) and item:
                        for child_key, child_value in item.items():
                            yield from leaves(child_value, f"{prefix}.{child_key}")
                    elif isinstance(item, list) and item:
                        for index, child_value in enumerate(item):
                            yield from leaves(child_value, f"{prefix}[{index}]")
                    else:
                        yield prefix
                for field_path in leaves(value, root_name):
                    conflicts.append({"kind": "ambiguous_legacy_semantics",
                                      "path": f".webnovel/state.json:{field_path}",
                                      "classification": classification,
                                      "requires": "explicit field-level import decision"})
    state_blob = state.get("state") if isinstance(state.get("state"), dict) else {}
    for key in sorted(state_blob):
        if key in {"_revision", "_last_modified_by", "_last_modified_at"}:
            field_classes[f"state.{key}"] = "PRESERVED_COMPATIBILITY_METADATA"
        else:
            conflicts.append({"kind": "unmapped_legacy_field", "path": f".webnovel/state.json:state.{key}",
                              "requires": "explicit owner mapping"})

    table_owners = {
        "chapters": "LEGACY_DERIVED_CANON_PROJECTION", "scenes": "LEGACY_DERIVED_CANON_PROJECTION",
        "appearances": "LEGACY_DERIVED_CANON_PROJECTION", "state_changes": "LEGACY_DERIVED_CANON_PROJECTION",
        "entities": "LEGACY_DERIVED_CANON_PROJECTION", "relationships": "LEGACY_DERIVED_CANON_PROJECTION",
        "story_events": "LEGACY_DERIVED_CANON_PROJECTION",
    }
    index_path = webnovel / "index.db"
    index_tables = []
    if index_path.is_file():
        try:
            with sqlite3.connect(f"{index_path.resolve().as_uri()}?mode=ro", uri=True) as conn:
                index_tables = [row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        except sqlite3.Error as exc:
            conflicts.append({"kind": "index_db_unreadable", "path": str(index_path), "detail": str(exc)})
    table_owners.update({name: "OWNER_OPERATIONAL" for name in index_tables if name not in table_owners})

    memory_path = webnovel / "memory_scratchpad.json"
    memory = _json_file(memory_path) or {}
    canon_prefixes = ("state_change:", "entity_new:", "relationship:", "chapter_meta:hook:",
                      "memory_facts:timeline:", "memory_facts:world_rule:",
                      "memory_facts:open_loop:", "memory_facts:reader_promise:")
    memory_rows = 0
    ambiguous_memory_rows = []
    for bucket, rows in memory.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            memory_rows += 1
            evidence = row.get("evidence", [])
            evidence = [evidence] if isinstance(evidence, str) else evidence
            has_canon = any(str(item).startswith(canon_prefixes) for item in evidence or [])
            has_owner = any(not str(item).startswith(canon_prefixes) for item in evidence or [])
            if has_canon and has_owner:
                ambiguous_memory_rows.append({"bucket": bucket, "id": row.get("id")})
    for row in ambiguous_memory_rows:
        conflicts.append({"kind": "mixed_memory_evidence", **row,
                          "requires": "separate Canon and owner evidence before migration"})

    for conflict in conflicts:
        path = str(conflict.get("path") or "")
        prefix = ".webnovel/state.json:"
        if path.startswith(prefix):
            field_classes.setdefault(path[len(prefix):], "UNCLASSIFIED_CONFLICT")
    field_dispositions = {}
    for path, classification in field_classes.items():
        if path.startswith("chapter_meta.") and classification in {"CRAFT", "INTENT"}:
            disposition = {"destination": "owner_overlay." + path, "copied": True,
                           "visible_in_activation_runtime": True, "conflict_required": False}
        elif classification in {"OWNER_INTENT", "OWNER_PROJECT_CONFIG"}:
            disposition = {"destination": "owner_overlay.project_info", "copied": True,
                           "visible_in_activation_runtime": True, "conflict_required": False}
        elif classification == "OWNER_INTENT_PLANNING":
            disposition = {"destination": "owner_overlay.volumes", "copied": True,
                           "visible_in_activation_runtime": True, "conflict_required": False}
        elif classification == "OWNER_WORKFLOW_METADATA":
            disposition = {"destination": "owner_overlay." + path, "copied": True,
                           "visible_in_activation_runtime": True, "conflict_required": False}
        elif classification == "LEGACY_DERIVED_CANON_PROJECTION":
            root_name = path.split(".", 1)[0]
            destination = {"relationships": "generation.relationships",
                           "state_changes": "generation.state_changes",
                           "progress": "generation.materialized_state"}.get(
                               root_name, "generation." + root_name)
            disposition = {"destination": destination, "copied": False,
                           "visible_in_activation_runtime": True, "conflict_required": False}
        elif classification == "LEGACY_AMBIGUOUS_CANON_OR_INTENT":
            disposition = {"destination": "legacy_preserved_source", "copied": False,
                           "visible_in_activation_runtime": False, "conflict_required": True}
        elif classification == "UNCLASSIFIED_CONFLICT":
            disposition = {"destination": "legacy_preserved_source", "copied": False,
                           "visible_in_activation_runtime": False, "conflict_required": True}
        else:
            disposition = {"destination": "legacy_preserved_source", "copied": False,
                           "visible_in_activation_runtime": False, "conflict_required": False}
        field_dispositions[path] = disposition
    table_dispositions = {}
    for table, classification in table_owners.items():
        if classification == "LEGACY_DERIVED_CANON_PROJECTION":
            table_dispositions[table] = {"destination": "generation." + table, "copied": False,
                                         "visible_in_activation_runtime": True, "conflict_required": False}
        else:
            table_dispositions[table] = {"destination": ".webnovel/index.db", "copied": False,
                                         "visible_in_activation_runtime": True, "conflict_required": False}
    mappings = {
        "state": {"canon_roots": sorted(state_canon), "owner_roots": sorted(owner_roots),
                  "owner_progress_paths": sorted(owner_paths), "observed_owner_progress_fields": progress_owner,
                  "observed_canon_progress_fields": progress_canon, "field_classifications": field_classes,
                  "field_dispositions": field_dispositions,
                  "owner_field_paths": sorted(path for path, owner in field_classes.items()
                                               if owner.startswith("OWNER_")),
                  "overlay_compatible_owner_field_paths": sorted(
                      (set(progress_owner) & set(owner_paths)) | {"project_info", "volumes"})},
        "index_tables": table_owners,
        "index_table_dispositions": table_dispositions,
        "memory": {"observed_rows": memory_rows, "canon_evidence_prefixes": list(canon_prefixes),
                   "ambiguous_mixed_rows": ambiguous_memory_rows},
        "vector_store_paths": [path.relative_to(root).as_posix() for path in _scoped_paths(root)
                               if path.name.startswith(("vectors.db", "rag.db"))],
    }
    return mappings, conflicts


def _candidate_report(root: Path) -> list[dict[str, Any]]:
    store = EffectiveHistoryStore()
    candidates = []
    correction_request_hashes = set()
    for path in sorted((root / ".story-system/corrections").glob("chapter_*/*/corrections/*.correction.json")):
        body = _json_file(path) or {}
        correction_id = str(body.get("correction_id") or "")
        correction_request_hashes.add(body.get("request_sha256"))
        candidate = store.resolve_candidate(root, correction_id) if correction_id else None
        candidates.append({"correction_id": correction_id,
                           "status": "ready" if candidate and candidate.ok else "blocked",
                           "diagnostics": list(candidate.diagnostics) if candidate else ["INVALID_CORRECTION_ARTIFACT"]})
    for path in sorted((root / ".story-system/corrections").glob("chapter_*/*/requests/*.request.json")):
        body = _json_file(path) or {}
        request_id = str(body.get("request_id") or path.stem)
        if artifact_sha256(body) in correction_request_hashes:
            continue
        auth_files = list(path.parents[1].joinpath("authorizations").glob("*.authorization.json"))
        decision = None
        for auth_path in auth_files:
            auth = _json_file(auth_path) or {}
            if auth.get("request_id") == request_id:
                decision = auth.get("choice")
                break
        candidates.append({"request_id": request_id,
                           "status": "rejected" if decision == "REJECT" else "staged" if decision == "APPROVE" else "pending",
                           "diagnostics": []})
    return candidates


def _report_body(root: Path) -> dict[str, Any]:
    active = activation_health_report(root)
    mappings, conflicts = _owner_inventory(root)
    legacy_state_path = root / ".webnovel/state.json"
    overlay_path = root / ".webnovel/state-overlay.json"
    legacy_state = _json_file(legacy_state_path) or {}
    overlay = _json_file(overlay_path) or {}
    owner_roots = {"story_craft", "planning", "promise_ledger", "review_checkpoints",
                   "workflow", "craft", "intent", "disambiguation_warnings",
                   "disambiguation_pending", "project_info", "volumes"}
    legacy_mutable_roots = sorted(owner_roots.intersection(legacy_state))
    overlay_roots = sorted(set((overlay.get("values") or {})).intersection(owner_roots))
    active["owner_path_compatibility"] = {
        "status": "base_only_compatibility" if active.get("mode") == "base_only" else "activation_managed_health",
        "effective_authority": "state.json" if active.get("mode") == "base_only" else "OwnedProjectView/state-overlay.json",
        "legacy_state_sha256": hashlib.sha256(legacy_state_path.read_bytes()).hexdigest() if legacy_state_path.is_file() else None,
        "owner_overlay_sha256": hashlib.sha256(overlay_path.read_bytes()).hexdigest() if overlay_path.is_file() else None,
        "legacy_mutable_roots": legacy_mutable_roots,
        "overlay_roots": overlay_roots,
        "unresolved_legacy_fields": list(conflicts),
        "writer_retirement": {"ready": False, "status": "guarded_pending_independent_review",
                              "requires": ["base-only compatibility", "owner-route coverage",
                                           "effective-reader coverage", "read-after-write tests",
                                           "exact migration mapping", "rollback evidence",
                                           "unknown-field fail-closed tests"]},
        "repeat_enrollment_supported": False,
    }
    history = EffectiveHistoryStore().read_active_snapshot(root)
    if active.get("mode") == "base_only":
        active["base_history_status"] = "valid" if history.ok else "blocked"
        if not history.ok:
            conflicts.append({"kind": "base_history_invalid", "diagnostics": list(history.diagnostics)})
    commit_paths = sorted((root / ".story-system/commits").glob("*.commit.json"))
    chapter_paths = sorted((root / ".story-system/chapters").glob("chapter_*.json"))
    structured_paths = set(chapter_paths)
    for pattern in (".story-system/reviews/chapter_*.review.json",
                    ".story-system/volumes/volume_*.json",
                    "99_归档/**/chapter_*.json"):
        structured_paths.update(root.glob(pattern))
    structured_paths = sorted(path for path in structured_paths if path.is_file()
                              and "/backups/" not in path.relative_to(root).as_posix())
    prose_paths = sorted(path for path in root.rglob("*.md") if path.is_file()
                         and not any(part.startswith(".") for part in path.relative_to(root).parts)
                         and __import__("re").search(r"第\d{4,}章", path.name)
                         and not any(token in path.name for token in ("审查报告", "质量检查表")))
    durable_history_valid = bool(commit_paths and history.ok and history.chapters)
    legacy_history = {"status": "durable_history_available" if durable_history_valid else
                      "invalid_durable_history" if commit_paths else "no_durable_history",
                      "durable_commit_count": len(commit_paths),
                      "legacy_chapter_artifact_count": len(chapter_paths),
                      "chapter_artifacts": [{"path": p.relative_to(root).as_posix(),
                                             "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                                             "contract_type": (_json_file(p) or {}).get("meta", {}).get("contract_type")}
                                            for p in chapter_paths],
                      "legacy_structured_artifacts": [{"path": p.relative_to(root).as_posix(),
                                                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                                                        "contract_type": (_json_file(p) or {}).get("meta", {}).get("contract_type"),
                                                        "archived": "99_归档" in p.relative_to(root).parts}
                                                       for p in structured_paths],
                      "legacy_prose_count": len(prose_paths),
                      "prose_artifacts": [{"path": p.relative_to(root).as_posix(),
                                           "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in prose_paths],
                      "accepted_evidence_found": durable_history_valid, "safe_to_auto_import": False}
    if not commit_paths and (chapter_paths or prose_paths):
        legacy_history["status"] = "requires_explicit_import_decision"
        conflicts.append({"kind": "legacy_history_requires_explicit_import_decision",
                          "path": ".story-system/commits", "legacy_prose_count": len(prose_paths),
                          "legacy_chapter_artifact_count": len(chapter_paths),
                          "requires": "human-confirmed accepted legacy history and field-level Canon import"})
    evidence_hashes = _hash_files(root)
    candidates = _candidate_report(root)
    return {"schema_version": "phase9-migration-preflight/v1", "project_root": str(root),
            "active_status": active.get("active_status", "unknown"), "active": active,
            "candidates": candidates, "evidence_hashes": evidence_hashes,
            "owner_mappings": mappings, "legacy_history": legacy_history, "conflicts": conflicts}


def preflight_project(project_root: str | Path) -> PreflightReport:
    root = Path(project_root).expanduser().resolve()
    before = _hash_files(root)
    body = _report_body(root)
    after = _hash_files(root)
    if before != after:
        raise MigrationError("PREFLIGHT_MUTATED_PROJECT")
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    active_status = body["active_status"]
    ok = active_status != "blocked" and not body["conflicts"]
    return PreflightReport(**body, ok=ok, report_digest=digest)


def dry_run_migration(project_root: str | Path, report_digest: str) -> MigrationPlan:
    root = Path(project_root).expanduser().resolve()
    before = _hash_files(root)
    report = preflight_project(root)
    if report.report_digest != report_digest:
        raise MigrationError("PREFLIGHT_REPORT_STALE")
    history = EffectiveHistoryStore().read_active_snapshot(root)
    if not history.ok:
        raise MigrationError("ACTIVE_HISTORY_BLOCKED:" + ";".join(history.diagnostics))
    canon_slices = []
    for chapter, entry in sorted(history.chapters.items()):
        canon_slices.append({"chapter": chapter, "base_sha256": entry.base_sha256,
                             "effective_revision_id": entry.effective_revision_id,
                             "effective_content_sha256": entry.effective_content_sha256,
                             "status": entry.status, "applied_correction_ids": list(entry.applied_correction_ids)})
    mappings = report.owner_mappings
    owner_dispositions = {
        "state_fields": mappings["state"]["field_dispositions"],
        "index_tables": mappings["index_table_dispositions"],
    }
    mutable_overlays = [
        {"path": ".webnovel/state-overlay.json", "fields": sorted(set(
            mappings["state"]["owner_roots"] + mappings["state"]["owner_progress_paths"]))},
        {"path": ".webnovel/index.db", "tables": sorted(name for name, owner in mappings["index_tables"].items()
                                                           if owner == "OWNER_OPERATIONAL")},
        {"path": ".webnovel/memory_scratchpad.json", "classification": "non-Canon rows; Canon evidence rows regenerated from effective history"},
    ]
    preserved = []
    for path in _scoped_paths(root):
        relative = path.relative_to(root).as_posix()
        if relative.endswith(".commit.json") or relative in {".webnovel/state.json", ".webnovel/index.db"}:
            preserved.append({"path": relative, "sha256": before[relative], "reason": "preserved source/compatibility snapshot"})
    from .chapter_commit_service import ChapterCommitService
    from .event_projection_router import EventProjectionRouter
    from .projection_generation import ProjectionGeneration

    output_hashes = {}
    history_store = EffectiveHistoryStore()
    with tempfile.TemporaryDirectory(prefix="phase9-migration-dry-run-") as staging_name:
        protocol = ProjectionGeneration(staging_name)
        handle = protocol.begin(history)
        service = ChapterCommitService(root)
        for chapter in sorted(history.chapters):
            effective_input = history_store.projection_input(history, chapter)
            service.apply_effective_projection(effective_input, handle)
        domains = {domain: {} for domain in EventProjectionRouter.PROJECTION_MANIFEST}
        for path in sorted(item for item in handle.staging_root.rglob("*") if item.is_file()):
            relative = path.relative_to(handle.staging_root).as_posix()
            domain = relative.split("/", 1)[0]
            if domain in domains:
                domains[domain][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        validated = protocol.validate_generation(handle, {"domains": domains})
        for domain, files in validated.manifest["domains"].items():
            output_hashes.update(files)
    unresolved = list(report.conflicts)
    body = {"schema_version": "phase9-migration-plan/v1", "project_root": str(root),
            "preflight_digest": report.report_digest, "canon_slices": canon_slices,
            "owner_dispositions": owner_dispositions,
            "mutable_overlays": mutable_overlays, "preserved_sources": preserved,
            "output_hashes": output_hashes, "unresolved_decisions": unresolved}
    after = _hash_files(root)
    if before != after:
        raise MigrationError("DRY_RUN_MUTATED_PROJECT")
    plan_digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    return MigrationPlan(**body, plan_digest=plan_digest)


def _integrity_check(path: Path) -> str:
    try:
        with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True) as conn:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "no_result"
    except sqlite3.Error as exc:
        return f"ERROR:{exc}"


def create_verified_backup(project_root: str | Path, plan: MigrationPlan) -> BackupManifest:
    root = Path(project_root).expanduser().resolve()
    if plan.project_root != str(root):
        raise MigrationError("BACKUP_PLAN_ROOT_MISMATCH")
    current = dry_run_migration(root, plan.preflight_digest)
    if current.plan_digest != plan.plan_digest:
        raise MigrationError("BACKUP_PLAN_STALE")
    sources = _scoped_paths(root)
    before = _hash_files(root, sources)
    story_root = root / ".story-system"
    target_parent = story_root / "backups" / "phase9"
    target_parent.mkdir(parents=True, exist_ok=True)
    target = target_parent / plan.plan_digest
    if target.exists():
        raise MigrationError("BACKUP_ALREADY_EXISTS")
    temp_parent = target_parent / f".{plan.plan_digest}.tmp"
    if temp_parent.exists():
        shutil.rmtree(temp_parent)
    temp_parent.mkdir(parents=True)
    file_rows = []
    sqlite_checks = {}
    try:
        for source in sources:
            relative = source.relative_to(root)
            destination = temp_parent / "files" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            expected = before[relative.as_posix()]
            if digest != expected:
                raise MigrationError(f"BACKUP_HASH_MISMATCH:{relative}")
            file_rows.append({"path": relative.as_posix(), "file_type": "regular_file",
                              "size_bytes": destination.stat().st_size, "sha256": digest})
            if source.suffix.lower() == ".db":
                integrity = _integrity_check(source)
                restore_integrity = _integrity_check(destination)
                if integrity != "ok" or restore_integrity != "ok":
                    raise MigrationError(f"SQLITE_INTEGRITY_FAILED:{relative}:{integrity}:{restore_integrity}")
                sqlite_checks[relative.as_posix()] = integrity
        manifest_body = {"schema_version": "phase9-backup/v1", "project_root": str(root),
                         "plan_digest": plan.plan_digest, "files": file_rows,
                         "sqlite_integrity": sqlite_checks}
        manifest_hash = hashlib.sha256(canonical_json(manifest_body).encode("utf-8")).hexdigest()
        manifest = {**manifest_body, "manifest_sha256": manifest_hash}
        manifest_path = temp_parent / "manifest.json"
        manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
        reread_manifest = _json_file(manifest_path)
        if reread_manifest != manifest:
            raise MigrationError("BACKUP_MANIFEST_REREAD_MISMATCH")
        reread_body = {key: value for key, value in reread_manifest.items() if key != "manifest_sha256"}
        reread_hash = hashlib.sha256(canonical_json(reread_body).encode("utf-8")).hexdigest()
        if reread_hash != reread_manifest.get("manifest_sha256"):
            raise MigrationError("BACKUP_MANIFEST_DIGEST_MISMATCH")
        for row in reread_manifest["files"]:
            copied = temp_parent / "files" / row["path"]
            if (not copied.is_file() or copied.stat().st_size != row["size_bytes"]
                    or hashlib.sha256(copied.read_bytes()).hexdigest() != row["sha256"]):
                raise MigrationError(f"BACKUP_MANIFEST_FILE_MISMATCH:{row['path']}")
        with tempfile.TemporaryDirectory(prefix="phase9-backup-restore-") as restore_name:
            restore_root = Path(restore_name)
            for row in file_rows:
                copied = temp_parent / "files" / row["path"]
                restored = restore_root / row["path"]
                restored.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(copied, restored)
                if hashlib.sha256(restored.read_bytes()).hexdigest() != row["sha256"]:
                    raise MigrationError(f"BACKUP_RESTORE_HASH_MISMATCH:{row['path']}")
                if restored.suffix.lower() == ".db" and _integrity_check(restored) != "ok":
                    raise MigrationError(f"BACKUP_RESTORE_SQLITE_FAILED:{row['path']}")
        if _hash_files(root, sources) != before:
            raise MigrationError("BACKUP_SOURCE_CHANGED")
        os.replace(temp_parent, target)
        return BackupManifest("phase9-backup/v1", str(root), str(target), plan.plan_digest,
                             len(file_rows), file_rows, sqlite_checks, True, manifest_hash)
    except Exception:
        if temp_parent.exists():
            shutil.rmtree(temp_parent, ignore_errors=True)
        raise


def _validated_backup(root: Path, plan: MigrationPlan,
                      supplied: BackupManifest | dict[str, Any] | None) -> BackupManifest:
    root = root.expanduser().resolve()
    if supplied is None:
        raise MigrationError("VERIFIED_BACKUP_REQUIRED")
    backup = supplied if isinstance(supplied, BackupManifest) else BackupManifest(**supplied)
    if (backup.project_root != str(root) or backup.plan_digest != plan.plan_digest
            or not backup.restore_verified):
        raise MigrationError("VERIFIED_BACKUP_REQUIRED")
    backup_root = Path(backup.backup_path).resolve()
    expected_parent = (root / ".story-system/backups/phase9").resolve()
    if (backup_root.parent != expected_parent or backup_root.name != plan.plan_digest
            or not backup_root.is_dir()):
        raise MigrationError("VERIFIED_BACKUP_REQUIRED")
    manifest_path = backup_root / "manifest.json"
    manifest = _json_file(manifest_path)
    if not manifest:
        raise MigrationError("BACKUP_MANIFEST_INVALID")
    manifest_body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    digest = hashlib.sha256(canonical_json(manifest_body).encode("utf-8")).hexdigest()
    if (digest != backup.manifest_sha256 or digest != manifest.get("manifest_sha256")
            or manifest.get("plan_digest") != plan.plan_digest):
        raise MigrationError("BACKUP_MANIFEST_INVALID")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != backup.file_count:
        raise MigrationError("BACKUP_MANIFEST_INVALID")
    verified = {}
    restore_rows = []
    for row in rows:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts or row.get("file_type") != "regular_file":
            raise MigrationError("BACKUP_MANIFEST_INVALID")
        copied = backup_root / "files" / relative
        if (not copied.is_file() or copied.stat().st_size != row.get("size_bytes")
                or hashlib.sha256(copied.read_bytes()).hexdigest() != row.get("sha256")):
            raise MigrationError(f"BACKUP_FILE_INVALID:{row['path']}")
        verified[row["path"]] = row["sha256"]
        restore_rows.append(row)
    current = _hash_files(root)
    if current != verified:
        raise MigrationError("POST_BACKUP_SOURCE_CONFLICT")
    with tempfile.TemporaryDirectory(prefix="phase9-backup-verify-") as restore_name:
        restore_root = Path(restore_name)
        for row in restore_rows:
            copied = backup_root / "files" / row["path"]
            restored = restore_root / row["path"]
            restored.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copied, restored)
            if hashlib.sha256(restored.read_bytes()).hexdigest() != row["sha256"]:
                raise MigrationError(f"BACKUP_RESTORE_HASH_MISMATCH:{row['path']}")
        for row in restore_rows:
            restored = restore_root / row["path"]
            if restored.suffix.lower() == ".db" and _integrity_check(restored) != "ok":
                raise MigrationError(f"BACKUP_RESTORE_SQLITE_FAILED:{row['path']}")
    return backup


def _prepare_owner_overlay(root: Path) -> int:
    from .owned_project_view import OwnedStateStore

    state = _json_file(root / ".webnovel/state.json") or {}
    _, inventory_conflicts = _owner_inventory(root)
    unsafe_story_craft = [item["path"] for item in inventory_conflicts
                          if item.get("path", "").startswith(".webnovel/state.json:story_craft")]
    if unsafe_story_craft:
        raise MigrationError(f"UNCLASSIFIED_STORY_CRAFT:{sorted(unsafe_story_craft)}")
    store = OwnedStateStore(root)
    overlay = store._overlay()
    values = overlay["values"]
    additions = {}
    owner_roots = {"story_craft", "planning", "promise_ledger", "review_checkpoints",
                   "workflow", "craft", "intent", "disambiguation_warnings",
                   "disambiguation_pending", "project_info", "volumes"}
    allowed_overlay_paths = owner_roots | {"progress.volumes_planned", "progress.current_volume",
                                           "progress.total_volumes", "progress.chapter_status",
                                           "progress.volumes_completed", "progress.last_updated"}
    unknown_overlay_paths = set(overlay["values"]) - allowed_overlay_paths
    if unknown_overlay_paths:
        raise MigrationError(f"UNMAPPED_EXISTING_OVERLAY:{sorted(unknown_overlay_paths)}")
    for key in owner_roots:
        if key in state:
            additions[key] = state[key]
    progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
    for key in ("volumes_planned", "current_volume", "total_volumes", "volumes_completed", "last_updated"):
        if key in progress:
            additions[f"progress.{key}"] = progress[key]
    for key, value in additions.items():
        if key in values and values[key] != value:
            raise MigrationError(f"OWNER_OVERLAY_CONFLICT:{key}")
    new_values = {**values, **additions}
    if new_values == values and store.overlay_path.exists():
        return int(overlay.get("revision", 0))
    overlay = {**overlay, "values": new_values,
               "revision": int(overlay.get("revision", 0)) + 1}
    store.overlay_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = store.overlay_path.with_name(f".{store.overlay_path.name}.{secrets.token_hex(8)}.tmp")
    data = (canonical_json(overlay) + "\n").encode("utf-8")
    with temp_path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, store.overlay_path)
    directory_fd = os.open(store.overlay_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return overlay["revision"]


def migrate_project(project_root: str | Path, expected_report_digest: str,
                    reviewed_plan_digest: str,
                    backup_manifest: BackupManifest | dict[str, Any] | None) -> MigrationResult:
    root = Path(project_root).expanduser().resolve()
    report = preflight_project(root)
    if report.report_digest != expected_report_digest:
        raise MigrationError("PREFLIGHT_REPORT_STALE")
    plan = dry_run_migration(root, expected_report_digest)
    if plan.plan_digest != reviewed_plan_digest:
        raise MigrationError("MIGRATION_PLAN_STALE")
    if plan.unresolved_decisions:
        raise MigrationError("MIGRATION_CONFLICTS_UNRESOLVED")
    if report.active.get("mode") != "base_only":
        raise MigrationError("PROJECT_ALREADY_ENROLLED")
    backup = _validated_backup(root, plan, backup_manifest)
    snapshot = EffectiveHistoryStore().read_active_snapshot(root)
    if not snapshot.ok:
        raise MigrationError("ACTIVE_HISTORY_BLOCKED:" + ";".join(snapshot.diagnostics))
    from .projection_rebuild import build_effective_generation

    built = build_effective_generation(root, snapshot)
    overlay_revision = _prepare_owner_overlay(root)
    protocol = ProjectionGeneration(root)
    try:
        publication = protocol.publish_generation(
            built["validated_generation"], None, snapshot.correction_lineage_digest)
    except Exception:
        # An unreferenced generation/overlay is inert before enrollment. Enrollment
        # is created atomically with the publication attempt and remains fail-closed.
        raise
    if not publication.record_sha256:
        raise MigrationError("PUBLICATION_FAILED")
    return MigrationResult("phase9-migration-result/v1", str(root), report.report_digest,
                           plan.plan_digest, backup.manifest_sha256,
                           {"publication_record_id": publication.publication_record_id,
                            "record_sha256": publication.record_sha256,
                            "body": publication.body},
                           built["generation_id"], overlay_revision,
                           {".webnovel/state-overlay.json": hashlib.sha256(
                               (root / ".webnovel/state-overlay.json").read_bytes()).hexdigest()})


def replace_generation(project_root: str | Path, generation_id: str):
    """Publish an already validated generation only for the active semantics."""
    root = Path(project_root).expanduser().resolve()
    protocol = ProjectionGeneration(root)
    try:
        active = protocol.latest_publication_for_recovery()
    except Exception as exc:
        raise MigrationError("ACTIVE_PUBLICATION_BLOCKED") from exc
    if active is None:
        raise MigrationError("ACTIVE_GENERATION_REQUIRED")
    generation_root = protocol.generations_root / generation_id
    if not generation_root.is_dir() or generation_root.parent != protocol.generations_root:
        raise MigrationError("REPLACEMENT_GENERATION_NOT_FOUND")
    manifest = _json_file(generation_root / "generation-manifest.json")
    if not manifest:
        raise MigrationError("REPLACEMENT_GENERATION_INVALID")
    from .projection_generation import ValidatedGeneration, _file_manifest

    snapshot = EffectiveHistoryStore().read_active_snapshot(
        root, allow_unhealthy_generation_for_recovery=True)
    if not snapshot.ok:
        raise MigrationError("ACTIVE_HISTORY_BLOCKED:" + ";".join(snapshot.diagnostics))
    if (manifest.get("generation_id") != generation_id
            or manifest.get("effective_history_digest") != active.body["effective_history_digest"]
            or manifest.get("effective_history_digest") != snapshot.effective_history_digest
            or manifest.get("base_set_digest") != snapshot.base_set_digest
            or manifest.get("correction_lineage_digest") != snapshot.correction_lineage_digest
            or _file_manifest(generation_root) != manifest.get("domains")):
        raise MigrationError("REPLACEMENT_SEMANTIC_MISMATCH")
    validated = ValidatedGeneration(generation_id, generation_root, manifest,
                                    artifact_sha256(manifest), snapshot)
    try:
        publication = protocol.publish_generation(
            validated, active.record_sha256, snapshot.correction_lineage_digest)
    except Exception as exc:
        raise MigrationError(f"REPLACEMENT_PUBLICATION_REJECTED:{exc}") from exc
    if publication.body["semantic_activation_id"] != active.body["semantic_activation_id"]:
        raise MigrationError("REPLACEMENT_SEMANTIC_ID_CHANGED")
    return publication


def restore_mutable_layout(project_root: str | Path,
                           backup_manifest: BackupManifest | dict[str, Any],
                           post_backup_conflict_report: dict[str, Any], *,
                           expected_semantic_activation_id: str,
                           expected_effective_history_digest: str) -> dict[str, Any]:
    """Restore the owner overlay only when its exact migration output is unchanged.

    Canon commits, corrections, enrollment, publications, and generations are never
    restored or removed by this filesystem-layout rollback.
    """
    root = Path(project_root).expanduser().resolve()
    if (not isinstance(post_backup_conflict_report, dict)
            or post_backup_conflict_report.get("ok") is not True
            or post_backup_conflict_report.get("conflicts")
            or not isinstance(post_backup_conflict_report.get("expected_current_hashes"), dict)):
        raise MigrationError("POST_BACKUP_CONFLICT_REPORT_REQUIRED")
    protocol = ProjectionGeneration(root)
    try:
        active = protocol.pin_active_generation()
    except Exception as exc:
        raise MigrationError("ACTIVE_GENERATION_BLOCKED") from exc
    if (active is None or active.semantic_activation_id != expected_semantic_activation_id
            or active.record_body.get("effective_history_digest") != expected_effective_history_digest):
        raise MigrationError("ACTIVE_SEMANTIC_HISTORY_CHANGED")
    backup = backup_manifest if isinstance(backup_manifest, BackupManifest) else BackupManifest(**backup_manifest)
    backup_root = Path(backup.backup_path).expanduser().resolve()
    if (backup.project_root != str(root)
            or backup_root.parent != (root / ".story-system/backups/phase9").resolve()
            or backup_root.name != backup.plan_digest):
        raise MigrationError("BACKUP_MANIFEST_INVALID")
    manifest_path = backup_root / "manifest.json"
    manifest = _json_file(manifest_path) or {}
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    if (digest != backup.manifest_sha256 or digest != manifest.get("manifest_sha256")
            or manifest.get("project_root") != str(root)):
        raise MigrationError("BACKUP_MANIFEST_INVALID")
    relative = ".webnovel/state-overlay.json"
    expected_hashes = post_backup_conflict_report["expected_current_hashes"]
    current_path = root / relative
    current_hash = hashlib.sha256(current_path.read_bytes()).hexdigest() if current_path.is_file() else None
    if current_hash != expected_hashes.get(relative):
        return {"ok": False, "conflicts": [{"path": relative, "kind": "post_backup_edit"}],
                "restored": []}
    backup_row = next((row for row in manifest.get("files", []) if row.get("path") == relative), None)
    if backup_row:
        source = backup_root / "files" / relative
        if (not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != backup_row["sha256"]):
            raise MigrationError("BACKUP_FILE_INVALID:" + relative)
        destination = current_path.with_name(f".{current_path.name}.{secrets.token_hex(8)}.restore")
        current_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        os.replace(destination, current_path)
        directory_fd = os.open(current_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    elif current_path.exists():
        current_path.unlink()
    return {"ok": True, "conflicts": [], "restored": [relative],
            "semantic_activation_id": active.semantic_activation_id,
            "effective_history_digest": active.record_body["effective_history_digest"]}
