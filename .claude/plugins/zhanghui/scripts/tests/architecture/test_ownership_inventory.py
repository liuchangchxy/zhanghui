"""Contract tests for the Phase 7 ownership inventory."""

import json
import re
import copy
from pathlib import Path

import pytest

from tests.architecture.ownership_inventory_guard import (
    reader_family_coverage,
    runtime_inventory_references,
    validate_inventory,
    writer_coverage,
)


ROOT = Path(__file__).resolve().parents[6]
PLUGIN = Path(__file__).resolve().parents[3]
DOCS = PLUGIN / "docs"
SCHEMA_PATH = DOCS / "ownership-inventory.schema.json"
INVENTORY_PATH = DOCS / "ownership-inventory.json"


def test_inventory_schema_and_records_exist():
    assert SCHEMA_PATH.is_file(), "ownership inventory schema is missing"
    assert INVENTORY_PATH.is_file(), "ownership inventory is missing"


def test_schema_declares_draft_2020_12_and_separate_record_families():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema.get("$schema", "").endswith("2020-12/schema")
    required = set(schema.get("required", []))
    assert {"writers", "readers", "migrations"} <= required


def test_invalid_domains_and_missing_reader_authority_are_rejected():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    broken = json.loads(json.dumps(inventory))
    broken["writers"][0]["data_domains"] = ["UNKNOWN_DOMAIN"]
    with pytest.raises(ValueError, match="data_domains"):
        validate_inventory(broken, ROOT)


@pytest.mark.parametrize("family,field", [
    ("writers", "owner"), ("writers", "replacement"), ("writers", "retirement_criterion"),
    ("writers", "evidence"), ("writers", "active_consumers"),
    ("readers", "read_edges"), ("migrations", "backup"), ("migrations", "rollback"),
    ("migrations", "ambiguity_handling"),
])
def test_missing_required_ownership_fields_are_rejected(family, field):
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    broken = copy.deepcopy(inventory)
    del broken[family][0][field]
    with pytest.raises(ValueError):
        validate_inventory(broken, ROOT)


def test_inventory_records_resolve_and_cover_required_reader_families():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    assert validate_inventory(inventory, ROOT)
    assert writer_coverage(inventory, ROOT / ".claude/plugins/zhanghui") == []
    assert reader_family_coverage(inventory) == []


def test_unregistered_protected_writer_candidate_fails_until_classified(monkeypatch):
    import tests.architecture.ownership_inventory_guard as guard

    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    candidate = ("scripts/new_writer.py", "write_story_state")
    monkeypatch.setattr(guard, "discovered_writer_coordinates", lambda _root: {candidate})
    assert guard.writer_coverage(inventory, PLUGIN) == [candidate]
    inventory["writers"].append({"implementation": {"path": ".claude/plugins/zhanghui/scripts/new_writer.py",
                                                       "symbol": "write_story_state"}})
    assert guard.writer_coverage(inventory, PLUGIN) == []


def test_production_runtime_does_not_consult_inventory():
    assert runtime_inventory_references(ROOT / ".claude/plugins/zhanghui") == []

    broken = json.loads(json.dumps(inventory))
    del broken["readers"][0]["read_edges"][0]["story_system"]["authority_claim"]
    with pytest.raises(ValueError, match="authority_claim"):
        validate_inventory(broken, ROOT)


def test_inventory_has_required_domains_and_unique_stable_ids():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    expected = {
        "CANON_COMMIT", "EVENTS", "STATE_JSON", "INDEX_DB", "SUMMARIES",
        "MEMORY", "VECTORS", "INTENT", "CRAFT", "WORKFLOW_METADATA",
        "MIGRATION", "COMPATIBILITY",
    }
    domains = {domain for writer in inventory["writers"] for domain in writer["data_domains"]}
    assert expected <= domains
    option_groups = {row.get("selector") for row in inventory["writers"] if row["implementation"]["path"].endswith("update_state.py")}
    assert {"canon-state-options", "foreshadowing-and-strand-options", "volume-planning-options", "review-metadata-option"} <= option_groups
    for records, key in ((inventory["writers"], "writer_id"),
                         (inventory["readers"], "reader_id"),
                         (inventory["migrations"], "migration_id")):
        values = [record[key] for record in records]
        assert len(values) == len(set(values)), f"duplicate {key}"


def test_inventory_has_mode_aware_records_and_resolvable_evidence():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    for writer in inventory["writers"]:
        assert writer["story_system_mode"]["behavior"]
        assert writer["legacy_mode"]["behavior"]
        assert writer["active_consumers"]
        assert writer["retirement_criterion"]
        for evidence in writer["evidence"]:
            assert (ROOT / evidence["path"]).exists(), evidence["path"]
    for reader in inventory["readers"]:
        for edge in reader["read_edges"]:
            for mode in ("story_system", "legacy"):
                assert edge[mode]["primary_source"]
                assert edge[mode]["authority_claim"]
                assert edge[mode]["condition"]
                assert "fallback" in edge[mode]


def test_production_runtime_does_not_consult_inventory():
    assert runtime_inventory_references(PLUGIN) == []


def test_compatibility_contract_separates_version_axes_and_project_modes():
    contract = PLUGIN / "docs/compatibility-contract.md"
    assert contract.is_file()
    text = contract.read_text(encoding="utf-8")
    for phrase in ("Git/source-tree identity", "plugin package version", "marketplace catalog version",
                   "installed host plugin version", "project data schema version",
                   "new Story System", "existing Story System", "legacy", "mixed/partial",
                   "non-destructive", "dry-run", "rollback"):
        assert phrase.lower() in text.lower(), phrase


def test_marketplace_source_and_repository_versions_resolve_without_snapshot_activation():
    marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    plugin = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    source = ROOT / marketplace["plugins"][0]["source"]
    assert source.resolve() == PLUGIN.resolve()
    assert marketplace["plugins"][0]["version"] == plugin["version"]
    assert not (PLUGIN / "6.4.0/docs/ownership-inventory.json").exists()
