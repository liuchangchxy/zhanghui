import pytest

"""Read-only CHANGES shadow measurement contract tests."""

import json
import importlib.util
from pathlib import Path

SHADOW_MODULE = Path(__file__).parents[1] / "changes_shadow_report.py"
MODULE_AVAILABLE = SHADOW_MODULE.is_file()
if MODULE_AVAILABLE:
    from data_modules.changes_shadow_report import analyze_phase2_files, aggregate_reports
else:
    analyze_phase2_files = aggregate_reports = None

SCHEMA = Path(__file__).parents[3] / "docs" / "changes-shadow-report.schema.json"


def _phase2_fixture(tmp_path, *, proposal_extra=None, extraction_extra=None):
    from data_modules.reconciliation import reconcile_changes

    proposed = {
        "character_state_changes": [{"entity_id": "hero", "field": "realm", "new": "筑基", "importance": "normal"}],
        "new_plot_points": [{"description": "a new opaque plot point", "importance": "normal"}],
        "foreshadowing_actions": [], "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    if proposal_extra:
        proposed.update(proposal_extra)
    chapter_text = "正文：主角突破。\n\n<chapter_changes>\n" + json.dumps(
        proposed, ensure_ascii=False, indent=2
    ) + "\n</chapter_changes>\n"
    extraction = {
        "accepted_events": [{"event_id": "scene-1", "event_type": "scene_change", "chapter": 1}],
        "state_deltas": [{"entity_id": "hero", "field": "realm", "old": "炼气", "new": "筑基"}],
        "entity_deltas": [], "entities_appeared": [], "scenes": [], "chapter_meta": {},
        "dominant_strand": "", "summary_text": "",
    }
    if extraction_extra:
        extraction.update(extraction_extra)
    reconciliation = reconcile_changes(proposed, extraction, chapter_text=chapter_text)
    chapter_path = tmp_path / "chapter.md"
    extraction_path = tmp_path / "extraction.json"
    reconciliation_path = tmp_path / "reconciliation.json"
    chapter_path.write_text(chapter_text, encoding="utf-8")
    extraction_path.write_text(json.dumps(extraction, ensure_ascii=False), encoding="utf-8")
    reconciliation_path.write_text(json.dumps(reconciliation, ensure_ascii=False), encoding="utf-8")
    originals = {path: path.read_bytes() for path in (chapter_path, extraction_path, reconciliation_path)}
    return chapter_path, extraction_path, reconciliation_path, originals, chapter_text, proposed, extraction, reconciliation


def test_shadow_consumes_real_phase2_artifacts_and_preserves_opaque_denominators(tmp_path):
    import data_modules.changes_shadow_report as module

    assert hasattr(module, "analyze_phase2_files"), "shadow analyzer must consume real Phase 2 inputs"
    chapter, extraction, reconciliation, originals, _text, _proposal, _observed, _audit = _phase2_fixture(tmp_path)
    report = module.analyze_phase2_files(
        chapter, extraction, reconciliation, project_id="opted-project", project_mode="story_system"
    )
    assert report["status"] == "INSUFFICIENT"
    assert report["denominators"] == {"proposed_claims": 2, "observed_facts": 2, "combined": 4}
    assert report["opaque_counts"] == {"proposed": 1, "observed": 1, "combined": 2}
    assert report["semantic_counts"]["matched"] == 1
    assert report["mapping_coverage"]["proposed_denominator"] == 2
    assert report["mapping_coverage"]["observed_denominator"] == 2
    assert set(report["input_sha256"]) == {"chapter", "proposed", "extraction", "reconciliation"}
    assert originals == {path: path.read_bytes() for path in originals}


def test_shadow_rejects_stale_phase2_reconciliation_and_keeps_denominators(tmp_path):
    import data_modules.changes_shadow_report as module

    assert hasattr(module, "analyze_phase2_files")
    chapter, extraction, reconciliation, _originals, *_ = _phase2_fixture(tmp_path)
    stale = json.loads(reconciliation.read_text(encoding="utf-8"))
    stale["chapter_sha256"] = "0" * 64
    reconciliation.write_text(json.dumps(stale), encoding="utf-8")
    report = module.analyze_phase2_files(chapter, extraction, reconciliation,
                                         project_id="opted-project", project_mode="legacy")
    assert report["status"] == "INSUFFICIENT"
    assert report["infrastructure_health"]["stale"] == 1
    assert report["denominators"] == {"proposed_claims": 2, "observed_facts": 2, "combined": 4}


def test_shadow_uses_extraction_result_schema_and_reports_invalid_artifact(tmp_path):
    import data_modules.changes_shadow_report as module

    assert hasattr(module, "analyze_phase2_files")
    chapter, extraction, reconciliation, _originals, *_ = _phase2_fixture(tmp_path)
    extraction.write_text(json.dumps({"state_deltas": []}), encoding="utf-8")
    report = module.analyze_phase2_files(chapter, extraction, reconciliation,
                                         project_id="opted-project", project_mode="story_system")
    assert report["status"] == "INSUFFICIENT"
    assert report["infrastructure_health"]["invalid"] == 1


def test_shadow_is_deterministic_and_keeps_opaque_fields_without_mutating_inputs(tmp_path):
    chapter, extraction, reconciliation, originals, *_ = _phase2_fixture(
        tmp_path, proposal_extra={"future_schema_field": [{"kind": "unknown"}]},
        extraction_extra={"future_extractor_field": [{"kind": "unknown"}]})
    first = analyze_phase2_files(chapter, extraction, reconciliation, project_id="p1", project_mode="legacy")
    second = analyze_phase2_files(chapter, extraction, reconciliation, project_id="p1", project_mode="legacy")
    assert first == second
    assert first["denominators"] == {"proposed_claims": 3, "observed_facts": 3, "combined": 6}
    assert first["opaque_counts"] == {"proposed": 2, "observed": 2, "combined": 4}
    assert originals == {path: path.read_bytes() for path in originals}


def test_shadow_report_schema_is_versioned_and_keeps_denominators_and_health_separate():
    assert SCHEMA.is_file()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("2020-12/schema")
    required = set(schema["required"])
    assert {"schema_version", "policy_version", "input_sha256", "denominators",
            "semantic_counts", "infrastructure_health"} <= required


def _eligible_reports(*, projects=3, chapters=60, low_category=None, low_rate=1.0, unhealthy=False):
    from data_modules.changes_shadow_report import REQUIRED_CATEGORIES
    rows = []
    for index in range(chapters):
        mode = "story_system" if index % 2 else "legacy"
        project = f"p{index % projects}"
        categories = {}
        for category in REQUIRED_CATEGORIES:
            rate = low_rate if category == low_category else 1.0
            categories[category] = {"proposed": 100, "observed": 100,
                                    "proposed_comparable": int(100 * rate),
                                    "observed_comparable": int(100 * rate)}
        rows.append({"project_id": project, "project_mode": mode, "chapter_id": str(index),
                     "categories": categories,
                     "denominators": {"proposed_claims": 200, "observed_facts": 200, "combined": 400},
                     "infrastructure_health": {"missing": int(unhealthy), "invalid": 0, "stale": 0, "extractor_failure": 0},
                     "hard_conflict_adjudication": {"unresolved": 0, "false_block": 0}})
    return rows


def test_sampling_categories_match_phase2_taxonomy():
    from data_modules.changes_shadow_report import REQUIRED_CATEGORIES
    from data_modules.reconciliation import REQUIRED_CHANGE_FIELDS
    assert REQUIRED_CATEGORIES == set(REQUIRED_CHANGE_FIELDS)


def test_candidate_category_gate_is_scoped_and_never_retires_automatically():
    from data_modules.changes_shadow_report import aggregate_reports
    reports = _eligible_reports(low_category="new_plot_points", low_rate=0.80)
    result = aggregate_reports(reports, candidate_categories=["character_state_changes"],
                               migration_evidence_complete=True, release_cohort_policy_present=True)
    assert result["status"] == "DISCUSSION_GATE_REQUIRES_HUMAN_REVIEW"
    assert result["retirement_discussion_threshold"]["automatic_retirement"] is False


@pytest.mark.parametrize("kwargs", [
    {"chapters": 59}, {"projects": 2}, {"unhealthy": True},
])
def test_candidate_gate_prerequisites_block_discussion(kwargs):
    from data_modules.changes_shadow_report import aggregate_reports
    reports = _eligible_reports(**kwargs)
    result = aggregate_reports(reports, candidate_categories=["character_state_changes"],
                               migration_evidence_complete=True, release_cohort_policy_present=True)
    assert result["status"] == "INSUFFICIENT"


def test_candidate_coverage_keeps_opaque_items_in_denominator():
    from data_modules.changes_shadow_report import aggregate_reports
    reports = _eligible_reports(low_category="character_state_changes", low_rate=0.94)
    result = aggregate_reports(reports, candidate_categories=["character_state_changes"],
                               migration_evidence_complete=True, release_cohort_policy_present=True)
    assert result["status"] == "INSUFFICIENT"
    assert result["retirement_discussion_threshold"]["candidate_category_coverage"]["character_state_changes"]["denominator"] == 12000


@pytest.mark.parametrize("failure", ["migration", "release_policy", "unresolved", "false_block", "missing_cell"])
def test_all_evidence_and_conflict_gates_block_discussion(failure):
    from data_modules.changes_shadow_report import aggregate_reports
    reports = _eligible_reports()
    migration, release = True, True
    if failure == "migration":
        migration = False
    elif failure == "release_policy":
        release = False
    elif failure in {"unresolved", "false_block"}:
        key = "unresolved" if failure == "unresolved" else "false_block"
        reports[0]["hard_conflict_adjudication"][key] = 1
    else:
        for row in reports:
            if row["project_mode"] == "legacy":
                row["categories"].pop("time_progression", None)
    result = aggregate_reports(reports, candidate_categories=["character_state_changes"],
                               migration_evidence_complete=migration, release_cohort_policy_present=release)
    assert result["status"] == "INSUFFICIENT"


def test_no_candidate_or_invalid_candidate_cannot_enter_discussion():
    from data_modules.changes_shadow_report import aggregate_reports
    reports = _eligible_reports()
    result = aggregate_reports(reports, migration_evidence_complete=True, release_cohort_policy_present=True)
    assert result["status"] == "INSUFFICIENT"
    with pytest.raises(ValueError, match="Phase 2 CHANGES"):
        aggregate_reports(reports, candidate_categories=["realm"], migration_evidence_complete=True,
                          release_cohort_policy_present=True)


def test_real_corpus_is_not_fabricated_for_retirement_discussion():
    from data_modules.changes_shadow_report import aggregate_reports
    result = aggregate_reports([], candidate_categories=["character_state_changes"],
                               migration_evidence_complete=False, release_cohort_policy_present=False)
    assert result["status"] == "INSUFFICIENT"
    assert result["sample_counts"] == {"chapters": 0, "projects": 0}
    assert result["retirement_discussion_threshold"]["automatic_retirement"] is False
