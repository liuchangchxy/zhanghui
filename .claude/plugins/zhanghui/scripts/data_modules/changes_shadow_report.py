"""Read-only shadow comparison for frozen ProposedChanges/ObservedChanges artifacts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .chapter_commit_schema import ExtractionResult
from .reconciliation import (
    REQUIRED_CHANGE_FIELDS,
    _observed_facts,
    _proposal_facts,
    reconcile_changes,
    validate_proposed_changes,
)

SCHEMA_VERSION = 1
POLICY_VERSION = "changes-shadow-v1"
REQUIRED_CATEGORIES = {
    "character_state_changes", "new_plot_points", "foreshadowing_actions",
    "location_state_changes", "faction_state_changes", "time_progression",
    "item_transfers", "unresolved_questions", "realm", "power_breakthrough",
}


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _proposal_atoms(proposed: dict[str, Any]):
    atoms = []
    for field in REQUIRED_CHANGE_FIELDS:
        value = proposed[field]
        if isinstance(value, list):
            atoms.extend((field, index, item) for index, item in enumerate(value))
        elif isinstance(value, dict):
            atoms.append((field, 0, value))
    for field, value in proposed.items():
        if field in REQUIRED_CHANGE_FIELDS:
            continue
        rows = value if isinstance(value, list) else [value]
        atoms.extend((field, index, row) for index, row in enumerate(rows) if row not in (None, [], {}))
    return atoms


def _extraction_atoms(extraction: dict[str, Any]):
    atoms = []
    list_fields = ("accepted_events", "state_deltas", "entity_deltas", "entities_appeared", "scenes")
    for field in list_fields:
        atoms.extend((field, index, row) for index, row in enumerate(extraction.get(field, [])))
    for field in ("chapter_meta", "dominant_strand", "summary_text"):
        value = extraction.get(field)
        if value not in (None, "", {}):
            atoms.append((field, 0, value))
    for field, value in extraction.items():
        if field in list_fields or field in {"chapter_meta", "dominant_strand", "summary_text"}:
            continue
        rows = value if isinstance(value, list) else [value]
        atoms.extend((field, index, row) for index, row in enumerate(rows) if row not in (None, [], {}))
    return atoms


def _blank_report(project_id, project_mode, chapter_id, hashes, health, proposal=None, extraction=None):
    proposals = _proposal_atoms(proposal) if proposal else []
    observations = _extraction_atoms(extraction) if extraction else []
    return {
        "schema_version": SCHEMA_VERSION, "policy_version": POLICY_VERSION, "status": "INSUFFICIENT",
        "project_id": project_id, "project_mode": project_mode, "chapter_id": chapter_id,
        "input_sha256": hashes,
        "denominators": {"proposed_claims": len(proposals), "observed_facts": len(observations),
                         "combined": len(proposals) + len(observations)},
        "mapping_coverage": {"proposed_comparable": 0, "proposed_denominator": len(proposals),
                             "observed_comparable": 0, "observed_denominator": len(observations),
                             "combined_comparable": 0, "combined_denominator": len(proposals) + len(observations)},
        "semantic_counts": {"matched": 0, "proposed_only": 0, "observed_only": 0,
                             "proposal_observation_conflict": 0, "observed_internal_conflict": 0, "opaque": 0},
        "opaque_counts": {"proposed": len(proposals), "observed": len(observations),
                          "combined": len(proposals) + len(observations)},
        "categories": {}, "hard_conflict_adjudication": {"candidates": 0, "confirmed_true": 0,
        "false_block": 0, "unresolved": 0}, "infrastructure_health": health,
    }


def analyze_phase2_files(chapter_path, extraction_path, reconciliation_path, *, project_id, project_mode,
                         extractor_failed=False):
    """Measure existing Phase 2 artifacts through their production parsers and validators."""
    paths = {"chapter": Path(chapter_path), "extraction": Path(extraction_path),
             "reconciliation": Path(reconciliation_path)}
    hashes: dict[str, str | None] = {key: None for key in paths}
    health = {"missing": 0, "invalid": 0, "stale": 0, "extractor_failure": int(extractor_failed)}
    raw = {}
    for key, path in paths.items():
        try:
            data = path.read_bytes()
            raw[key] = data
            hashes[key] = hashlib.sha256(data).hexdigest()
        except FileNotFoundError:
            health["missing"] += 1
        except OSError:
            health["invalid"] += 1
    if project_mode not in {"story_system", "legacy"}:
        health["invalid"] += 1
        return _blank_report(project_id, None, None, hashes, health)
    chapter_text = None
    proposed = None
    extraction = None
    reconciliation = None
    chapter_id = Path(chapter_path).stem
    if "chapter" in raw:
        try:
            chapter_text = raw["chapter"].decode("utf-8")
            from changes_gate import check_r01_protocol, check_r02_enums, parse_changes_document
            document = parse_changes_document(chapter_text)
            if document.error or document.proposed_changes is None:
                raise ValueError(document.error or "CHANGES is missing")
            proposed = validate_proposed_changes(document.proposed_changes)
            failures = check_r01_protocol(proposed) + check_r02_enums(proposed)
            if failures:
                raise ValueError("ProposedChanges violates Phase 2 validation: " + "; ".join(f.message for f in failures))
            hashes["proposed"] = _canonical_digest(proposed)
        except (UnicodeDecodeError, ValueError, TypeError):
            health["invalid"] += 1
    if "extraction" in raw:
        try:
            extraction_json = json.loads(raw["extraction"])
            extraction = ExtractionResult.model_validate(extraction_json).model_dump()
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            health["invalid"] += 1
    if "reconciliation" in raw:
        try:
            reconciliation = json.loads(raw["reconciliation"])
            if not isinstance(reconciliation, dict):
                raise ValueError("reconciliation must be an object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            health["invalid"] += 1
    if chapter_text is None or proposed is None or extraction is None or reconciliation is None:
        return _blank_report(project_id, project_mode, chapter_id, hashes, health, proposed, extraction)

    expected = reconcile_changes(proposed, extraction, chapter_text=chapter_text)
    if reconciliation != expected:
        health["stale"] += 1
    proposal_atoms = _proposal_atoms(proposed)
    extraction_atoms = _extraction_atoms(extraction)
    proposal_fact_indexes = {fact["source_index"] for fact in _proposal_facts(proposed)}
    observed_facts = _observed_facts(extraction)
    observed_fact_refs = {(fact["source_type"], fact["source_index"]) for fact in observed_facts}
    proposed_comparable = sum(field == "character_state_changes" and index in proposal_fact_indexes
                              for field, index, _value in proposal_atoms)
    observed_comparable = min(len(extraction_atoms), len(observed_facts))
    conflicts = expected["conflicts"]
    counts = {
        "matched": len(expected["matched"]),
        "proposed_only": len(expected["proposed_not_observed"]),
        "observed_only": len(expected["unproposed_observed"]),
        "proposal_observation_conflict": sum(row.get("type") == "proposal_observed_conflict" for row in conflicts),
        "observed_internal_conflict": sum(row.get("type") == "observed_internal_conflict" for row in conflicts),
        "opaque": max(0, len(proposal_atoms) - proposed_comparable) + max(0, len(extraction_atoms) - observed_comparable),
    }
    opaque_proposed = max(0, len(proposal_atoms) - proposed_comparable)
    opaque_observed = max(0, len(extraction_atoms) - observed_comparable)
    category_counts: dict[str, dict[str, int]] = {}
    for category in sorted({row[0] for row in proposal_atoms} | {row[0] for row in extraction_atoms}):
        p_count = sum(row[0] == category for row in proposal_atoms)
        o_count = sum(row[0] == category for row in extraction_atoms)
        p_map = sum(field == category and index in proposal_fact_indexes for field, index, _value in proposal_atoms)
        o_map = sum(field == category and (field, index) in observed_fact_refs
                    for field, index, _value in extraction_atoms)
        category_counts[category] = {"proposed": p_count, "observed": o_count,
                                     "proposed_comparable": p_map, "observed_comparable": o_map}
    report = _blank_report(project_id, project_mode, chapter_id, hashes, health, proposed, extraction)
    report.update({
        "denominators": {"proposed_claims": len(proposal_atoms), "observed_facts": len(extraction_atoms),
                         "combined": len(proposal_atoms) + len(extraction_atoms)},
        "mapping_coverage": {"proposed_comparable": proposed_comparable, "proposed_denominator": len(proposal_atoms),
                             "observed_comparable": observed_comparable, "observed_denominator": len(extraction_atoms),
                             "combined_comparable": proposed_comparable + observed_comparable,
                             "combined_denominator": len(proposal_atoms) + len(extraction_atoms)},
        "semantic_counts": counts,
        "opaque_counts": {"proposed": opaque_proposed, "observed": opaque_observed,
                          "combined": opaque_proposed + opaque_observed},
        "categories": category_counts,
        "hard_conflict_adjudication": {"candidates": len(conflicts), "confirmed_true": 0,
                                       "false_block": 0, "unresolved": len(conflicts)},
        "source_contract": {"proposal_parser": "changes_gate.parse_changes_document",
                            "proposal_validator": "reconciliation.validate_proposed_changes + R1/R2",
                            "observation_validator": "ExtractionResult",
                            "reconciliation": "reconciliation.reconcile_changes"},
    })
    return report


def aggregate_reports(reports, *, migration_evidence_complete=False, release_cohort_policy_present=False):
    """Apply the frozen minimum cohort and report missing project-mode/category cells."""
    projects = {row.get("project_id") for row in reports if row.get("project_id") != "unknown"}
    chapters = {(row.get("project_id"), row.get("chapter_id")) for row in reports}
    required_modes = {"story_system", "legacy"}
    present_modes = {row.get("project_mode") for row in reports}
    categories = REQUIRED_CATEGORIES
    cells = {(row.get("project_mode"), category) for row in reports for category, counts in row.get("categories", {}).items()
             if counts.get("proposed", 0) or counts.get("observed", 0)}
    missing_cells = sorted(f"{mode}:{category}" for mode in required_modes for category in categories if (mode, category) not in cells)
    total_health = Counter()
    for report in reports: total_health.update(report.get("infrastructure_health", {}))
    category_totals = defaultdict(lambda: Counter())
    totals = Counter()
    for report in reports:
        mode = report.get("project_mode", "unknown")
        totals.update(report.get("denominators", {}))
        for category, counts in report.get("categories", {}).items():
            for key, value in counts.items(): category_totals[(mode, category)][key] += value
    coverage_values = []
    for counts in category_totals.values():
        for numerator, denominator in ((counts["proposed_comparable"], counts["proposed"]),
                                       (counts["observed_comparable"], counts["observed"])):
            if denominator:
                coverage_values.append(numerator / denominator)
    unresolved = sum(row.get("hard_conflict_adjudication", {}).get("unresolved", 0) for row in reports)
    false_blocks = sum(row.get("hard_conflict_adjudication", {}).get("false_block", 0) for row in reports)
    sufficient = (len(chapters) >= 60 and len(projects) >= 3 and required_modes <= present_modes
                  and bool(categories) and not missing_cells and not any(total_health.values())
                  and bool(coverage_values) and min(coverage_values) >= 0.95 and unresolved == 0
                  and false_blocks == 0 and migration_evidence_complete and release_cohort_policy_present)
    per_mode = {}
    for (mode, category), counts in sorted(category_totals.items()):
        row = dict(counts)
        row["proposed_mapping_rate"] = counts["proposed_comparable"] / counts["proposed"] if counts["proposed"] else None
        row["observed_mapping_rate"] = counts["observed_comparable"] / counts["observed"] if counts["observed"] else None
        per_mode[f"{mode}:{category}"] = row
    health = {key: total_health[key] for key in ("missing", "invalid", "stale", "extractor_failure")}
    report_hashes = [hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest() for row in reports]
    return {"schema_version": SCHEMA_VERSION, "policy_version": POLICY_VERSION,
            "status": "DISCUSSION_GATE_REQUIRES_HUMAN_REVIEW" if sufficient else "INSUFFICIENT",
            "input_sha256": {"report_set": report_hashes},
            "sample_counts": {"chapters": len(chapters), "projects": len(projects)},
            "denominators": {"proposed_claims": totals["proposed_claims"], "observed_facts": totals["observed_facts"], "combined": totals["combined"]},
            "per_mode_category": per_mode,
            "missing_required_cells": missing_cells, "infrastructure_health": health,
            "retirement_discussion_threshold": {"chapters": 60, "projects": 3, "category_mapping_coverage": 0.95,
                                                  "migration_evidence_complete": migration_evidence_complete,
                                                  "release_cohort_policy_present": release_cohort_policy_present,
                                                  "unresolved_conflicts": unresolved, "known_false_blocks": false_blocks,
                                                  "automatic_retirement": False}}
