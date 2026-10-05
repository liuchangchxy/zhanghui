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
