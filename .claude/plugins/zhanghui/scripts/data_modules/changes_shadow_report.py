"""Read-only shadow comparison for frozen ProposedChanges/ObservedChanges artifacts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
POLICY_VERSION = "changes-shadow-v1"
CATEGORIES = {
    "character_state", "character_state_changes", "realm", "power_breakthrough",
    "new_plot_points", "foreshadowing_actions", "location_state_changes",
    "faction_state_changes", "time_progression", "item_transfers", "unresolved_questions",
}
REQUIRED_CATEGORIES = {
    "character_state_changes", "new_plot_points", "foreshadowing_actions",
    "location_state_changes", "faction_state_changes", "time_progression",
    "item_transfers", "unresolved_questions", "realm", "power_breakthrough",
}


def _load(path: Path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _validated(artifact: dict, kind: str):
    if artifact.get("schema_version") != SCHEMA_VERSION or artifact.get("kind") != kind:
        raise ValueError(f"invalid {kind} artifact schema or kind")
    if artifact.get("project_mode") not in {"story_system", "legacy"}:
        raise ValueError(f"invalid {kind} project_mode")
    if not artifact.get("chapter_id") or not isinstance(artifact.get("items"), list):
        raise ValueError(f"invalid {kind} chapter/items")
    for item in artifact["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("category"), str) or not item.get("key") or "value" not in item:
            raise ValueError(f"invalid atomic item in {kind}")


def analyze_files(proposed_path, observed_path, reconciliation_path, *, project_id="unknown", extractor_failed=False):
    """Read three explicit artifacts and return an aggregate-only report; never writes inputs."""
    paths = [Path(proposed_path), Path(observed_path), Path(reconciliation_path)]
    health = {"missing": 0, "invalid": 0, "stale": 0, "extractor_failure": int(extractor_failed)}
    loaded, hashes = [], []
    for path in paths:
        try:
            artifact, digest = _load(path)
            loaded.append(artifact); hashes.append(digest)
        except FileNotFoundError:
            health["missing"] += 1; loaded.append(None); hashes.append(None)
        except (json.JSONDecodeError, UnicodeDecodeError):
            health["invalid"] += 1; loaded.append(None); hashes.append(None)
    if any(item is None for item in loaded):
        return _empty_report(project_id, health, hashes)
    proposal, observed, reconciliation = loaded
    try:
        _validated(proposal, "proposed"); _validated(observed, "observed")
        _validated(reconciliation, "reconciliation")
    except ValueError:
        health["invalid"] += 1
        return _empty_report(project_id, health, hashes)
    identity = (proposal["chapter_id"], proposal["project_mode"])
    if any((row["chapter_id"], row["project_mode"]) != identity for row in loaded[1:]):
        health["stale"] += 1
    expected_hashes = reconciliation.get("source_sha256")
    if expected_hashes and expected_hashes != {"proposed": hashes[0], "observed": hashes[1]}:
        health["stale"] += 1
    if health["stale"] or health["invalid"] or health["extractor_failure"]:
        return _empty_report(project_id, health, hashes, proposal, observed)

    proposed_items, observed_items = proposal["items"], observed["items"]
    opaque_p = [x for x in proposed_items if x.get("category") not in CATEGORIES]
    opaque_o = [x for x in observed_items if x.get("category") not in CATEGORIES]
    pmap, omap = _item_map(proposed_items, opaque_p), _item_map(observed_items, opaque_o)
    matched = conflicts = 0
    for key in pmap.keys() & omap.keys():
        if pmap[key] == omap[key]: matched += 1
        else: conflicts += 1
    comparable_p = len(pmap)
    comparable_o = len(omap)
    p_only = len(pmap.keys() - omap.keys())
    o_only = len(omap.keys() - pmap.keys())
    internal = sum(1 for key, values in _value_sets(observed_items, opaque_o).items() if len(values) > 1)
    categories = sorted({x.get("category", "opaque") for x in proposed_items + observed_items})
    category_counts = {}
    for category in categories:
        p_items = [x for x in proposed_items if x.get("category") == category]
        o_items = [x for x in observed_items if x.get("category") == category]
        p_comparable = sum(1 for x in p_items if category in CATEGORIES)
        o_comparable = sum(1 for x in o_items if category in CATEGORIES)
        category_counts[category] = {"proposed": len(p_items), "observed": len(o_items),
                                     "proposed_comparable": p_comparable, "observed_comparable": o_comparable}
    adjudication_rows = reconciliation.get("conflict_adjudication", [])
    true_count = sum(1 for row in adjudication_rows if row.get("decision") == "true_conflict")
    false_count = sum(1 for row in adjudication_rows if row.get("decision") == "false_block")
    unresolved_count = max(0, conflicts - true_count - false_count)
    return {
        "schema_version": SCHEMA_VERSION, "policy_version": POLICY_VERSION,
        "status": "INSUFFICIENT", "project_id": project_id, "project_mode": identity[1],
        "chapter_id": identity[0], "input_sha256": {"proposed": hashes[0], "observed": hashes[1], "reconciliation": hashes[2]},
        "denominators": {"proposed_claims": len(proposed_items), "observed_facts": len(observed_items), "combined": len(proposed_items)+len(observed_items)},
        "mapping_coverage": {"proposed_comparable": comparable_p, "proposed_denominator": len(proposed_items), "observed_comparable": comparable_o, "observed_denominator": len(observed_items), "combined_comparable": comparable_p+comparable_o, "combined_denominator": len(proposed_items)+len(observed_items)},
        "semantic_counts": {"matched": matched, "proposed_only": p_only, "observed_only": o_only, "proposal_observation_conflict": conflicts, "observed_internal_conflict": internal, "opaque": len(opaque_p)+len(opaque_o)},
        "categories": category_counts,
        "hard_conflict_adjudication": {"candidates": conflicts, "confirmed_true": true_count, "false_block": false_count, "unresolved": unresolved_count},
        "infrastructure_health": health,
        "compatibility": {"sampled_chapters": 1, "parseable_current_and_legacy": 0},
    }


def _item_map(items, opaque):
    opaque_ids = {id(row) for row in opaque}
    result = {}
    for row in items:
        if id(row) in opaque_ids: continue
        result[(row["category"], row["key"])] = row.get("value")
    return result


def _value_sets(items, opaque):
    opaque_ids = {id(row) for row in opaque}; result = defaultdict(set)
    for row in items:
        if id(row) not in opaque_ids: result[(row["category"], row["key"])].add(json.dumps(row.get("value"), sort_keys=True))
    return result


def _empty_report(project_id, health, hashes, proposal=None, observed=None):
    proposal_items = proposal.get("items", []) if proposal else []
    observed_items = observed.get("items", []) if observed else []
    return {"schema_version": SCHEMA_VERSION, "policy_version": POLICY_VERSION, "status": "INSUFFICIENT", "project_id": project_id,
            "input_sha256": {"proposed": hashes[0], "observed": hashes[1], "reconciliation": hashes[2]},
            "denominators": {"proposed_claims": len(proposal_items), "observed_facts": len(observed_items), "combined": len(proposal_items)+len(observed_items)},
            "semantic_counts": {"matched": 0, "proposed_only": 0, "observed_only": 0, "proposal_observation_conflict": 0, "observed_internal_conflict": 0, "opaque": 0},
            "infrastructure_health": health}


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
