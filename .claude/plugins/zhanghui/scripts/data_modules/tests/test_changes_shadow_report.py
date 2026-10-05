"""Read-only CHANGES shadow measurement contract tests."""

import json
import importlib.util
from pathlib import Path

SHADOW_MODULE = Path(__file__).parents[1] / "changes_shadow_report.py"
MODULE_AVAILABLE = SHADOW_MODULE.is_file()
if MODULE_AVAILABLE:
    from data_modules.changes_shadow_report import analyze_files, aggregate_reports
else:
    analyze_files = aggregate_reports = None

SCHEMA = Path(__file__).parents[3] / "docs" / "changes-shadow-report.schema.json"


def write_artifact(path: Path, kind: str, items, mode="story_system", chapter="c1"):
    path.write_text(json.dumps({"schema_version": 1, "kind": kind, "project_mode": mode,
                                "chapter_id": chapter, "items": items}), encoding="utf-8")


def test_shadow_counts_match_one_sided_conflict_and_opaque_items_without_narrowing(tmp_path):
    assert MODULE_AVAILABLE, "read-only shadow analyzer is missing"
    proposal = tmp_path / "proposal.json"
    observed = tmp_path / "observed.json"
    reconciliation = tmp_path / "reconciliation.json"
    write_artifact(proposal, "proposed", [
        {"id": "a", "category": "character_state", "key": "x", "value": "alive"},
        {"id": "b", "category": "unsupported_custom", "key": "opaque", "value": "v"},
        {"id": "c", "category": "realm", "key": "hero.realm", "value": "2"},
    ])
    write_artifact(observed, "observed", [
        {"id": "a", "category": "character_state", "key": "x", "value": "alive"},
        {"id": "d", "category": "character_state", "key": "y", "value": "awake"},
        {"id": "c", "category": "realm", "key": "hero.realm", "value": "3"},
    ])
    write_artifact(reconciliation, "reconciliation", [])

    report = analyze_files(proposal, observed, reconciliation)
    assert report["status"] == "INSUFFICIENT"
    assert report["denominators"] == {"proposed_claims": 3, "observed_facts": 3, "combined": 6}
    assert report["semantic_counts"] == {
        "matched": 1, "proposed_only": 0, "observed_only": 1,
        "proposal_observation_conflict": 1, "observed_internal_conflict": 0, "opaque": 1,
    }
    assert report["infrastructure_health"] == {
        "missing": 0, "invalid": 0, "stale": 0, "extractor_failure": 0,
    }
    assert len(report["input_sha256"]) == 3


def test_aggregate_requires_chapter_project_and_mode_category_cells(tmp_path):
    assert MODULE_AVAILABLE, "read-only shadow analyzer is missing"
    proposal = tmp_path / "p.json"; observed = tmp_path / "o.json"; reconciliation = tmp_path / "r.json"
    reports = []
    for chapter in range(2):
        write_artifact(proposal, "proposed", [], chapter=f"c{chapter}")
        write_artifact(observed, "observed", [], chapter=f"c{chapter}")
        write_artifact(reconciliation, "reconciliation", [])
        reports.append(analyze_files(proposal, observed, reconciliation, project_id=f"p{chapter}"))
    aggregate = aggregate_reports(reports)
    assert aggregate["status"] == "INSUFFICIENT"
    assert aggregate["sample_counts"] == {"chapters": 2, "projects": 2}
    assert aggregate["missing_required_cells"]


def test_stale_schema_and_extraction_failures_are_infrastructure_not_semantic(tmp_path):
    assert MODULE_AVAILABLE, "read-only shadow analyzer is missing"
    proposal = tmp_path / "p.json"; observed = tmp_path / "o.json"; reconciliation = tmp_path / "r.json"
    write_artifact(proposal, "proposed", [])
    write_artifact(observed, "observed", [])
    write_artifact(reconciliation, "reconciliation", [])
    observed.write_text(observed.read_text().replace('"schema_version": 1', '"schema_version": 9'))
    report = analyze_files(proposal, observed, reconciliation, extractor_failed=True)
    assert report["status"] == "INSUFFICIENT"
    assert report["infrastructure_health"]["invalid"] == 1
    assert report["infrastructure_health"]["extractor_failure"] == 1
    assert report["semantic_counts"]["matched"] == 0


def test_shadow_analyzer_is_deterministic_and_does_not_mutate_inputs(tmp_path):
    assert MODULE_AVAILABLE, "read-only shadow analyzer is missing"
    proposal = tmp_path / "p.json"; observed = tmp_path / "o.json"; reconciliation = tmp_path / "r.json"
    write_artifact(proposal, "proposed", [{"id": "x", "category": "character_state", "key": "x", "value": 1}])
    write_artifact(observed, "observed", [{"id": "x", "category": "character_state", "key": "x", "value": 1}])
    write_artifact(reconciliation, "reconciliation", [])
    before = {p: p.read_bytes() for p in (proposal, observed, reconciliation)}
    first = analyze_files(proposal, observed, reconciliation)
    second = analyze_files(proposal, observed, reconciliation)
    assert first == second
    assert before == {p: p.read_bytes() for p in before}
    assert set(tmp_path.iterdir()) == {proposal, observed, reconciliation}


def test_shadow_report_schema_is_versioned_and_keeps_denominators_and_health_separate():
    assert SCHEMA.is_file()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("2020-12/schema")
    required = set(schema["required"])
    assert {"schema_version", "policy_version", "input_sha256", "denominators",
            "semantic_counts", "infrastructure_health"} <= required
