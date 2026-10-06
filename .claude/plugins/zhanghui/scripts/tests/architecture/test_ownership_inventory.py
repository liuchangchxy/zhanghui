"""Contract tests for the Phase 7 ownership inventory."""

import json
import re
import copy
from pathlib import Path

import pytest

from tests.architecture.ownership_inventory_guard import (
    reader_coverage,
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
    ("readers", "read_edges"), ("readers", "lifecycle_status"),
    ("migrations", "backup"), ("migrations", "rollback"),
    ("migrations", "ambiguity_handling"),
])
def test_missing_required_ownership_fields_are_rejected(family, field):
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    broken = copy.deepcopy(inventory)
    broken[family][0].setdefault(field, "allowed")
    del broken[family][0][field]
    with pytest.raises(ValueError):
        validate_inventory(broken, ROOT)


@pytest.mark.parametrize("family,id_key", [("writers", "writer_id"), ("readers", "reader_id"),
                                            ("migrations", "migration_id")])
def test_duplicate_ids_are_rejected_per_record_family(family, id_key):
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    broken = copy.deepcopy(inventory)
    broken[family].append(copy.deepcopy(broken[family][0]))
    with pytest.raises(ValueError, match="duplicate"):
        validate_inventory(broken, ROOT)


def test_legacy_state_reader_cannot_claim_story_system_canon_authority():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    broken = copy.deepcopy(inventory)
    edge = broken["readers"][0]["read_edges"][0]
    edge["story_system"]["primary_source"] = "legacy state.json"
    edge["story_system"]["authority_claim"] = "CANON_AUTHORITY"
    with pytest.raises(ValueError, match="legacy source"):
        validate_inventory(broken, ROOT)


def test_inventory_records_resolve_and_cover_required_reader_families():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    assert validate_inventory(inventory, ROOT)
    assert writer_coverage(inventory, ROOT / ".claude/plugins/zhanghui") == []
    assert reader_coverage(inventory, ROOT / ".claude/plugins/zhanghui") == []
    assert reader_family_coverage(inventory) == []


def test_reader_inventory_coordinate_removal_exposes_protected_read():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    source = next(item for row in inventory["readers"] for item in row.get("source_coordinates", [])
                  if item["data_domain"] == "STATE_JSON")
    broken = copy.deepcopy(inventory)
    for row in broken["readers"]:
        row["source_coordinates"] = [item for item in row.get("source_coordinates", []) if item != source]
    assert (source["path"].removeprefix(".claude/plugins/zhanghui/"), source["symbol"], source["data_domain"], source["sink"]) in reader_coverage(
        broken, ROOT / ".claude/plugins/zhanghui")


def test_unregistered_protected_writer_candidate_fails_until_classified():
    import tests.architecture.ownership_inventory_guard as guard

    fixture_root = PLUGIN / "writer-coordinate-fixture"
    (fixture_root / "scripts").mkdir(parents=True)
    (fixture_root / "scripts/new_writer.py").write_text(
        "def write_story_state(state_path, payload):\n"
        "    atomic_write_json(state_path, payload)\n", encoding="utf-8")
    try:
        candidate = ("scripts/new_writer.py", "write_story_state", "STATE_JSON", "atomic_write_json")
        inventory = {"writers": [], "writer_exceptions": []}
        assert guard.writer_coverage(inventory, fixture_root) == [candidate]
        inventory["writers"].append({"writer_id": "new-owner", "implementation": {"path": candidate[0], "symbol": candidate[1]},
                                     "data_domains": [candidate[2]], "source_coordinates": [
                                         {"path": candidate[0], "symbol": candidate[1], "data_domain": candidate[2],
                                          "sink": candidate[3], "writer_id": "new-owner"}]})
        assert guard.writer_coverage(inventory, fixture_root) == []
    finally:
        import shutil
        shutil.rmtree(fixture_root)


def test_ast_scanner_discovers_new_state_writer_in_source(tmp_path):
    from tests.architecture.ownership_inventory_guard import discovered_writer_coordinates

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "new_writer.py").write_text(
        "def write_story_state(state_path, payload):\n"
        "    atomic_write_json(state_path, payload)\n",
        encoding="utf-8",
    )
    assert ("scripts/new_writer.py", "write_story_state") in discovered_writer_coordinates(tmp_path)


def test_ast_scanner_finds_actual_archive_and_memory_writers():
    from tests.architecture.ownership_inventory_guard import discovered_writer_coordinates

    found = discovered_writer_coordinates(PLUGIN)
    assert ("scripts/archive_manager.py", "ArchiveManager") in found
    assert ("scripts/project_memory.py", "add_pattern") in found


def test_reader_scanner_detects_new_protected_file_reader():
    from tests.architecture.ownership_inventory_guard import reader_coverage

    scripts = PLUGIN / "scripts"
    fixture_root = PLUGIN / "reader-scan-fixture"
    fixture_root.mkdir()
    (fixture_root / "scripts").mkdir()
    (fixture_root / "scripts" / "new_state_reader.py").write_text(
        "def read_state(project_root):\n"
        "    state_path = project_root / '.webnovel' / 'state.json'\n"
        "    return json.loads(state_path.read_text(encoding='utf-8'))\n",
        encoding="utf-8",
    )
    try:
        assert ("scripts/new_state_reader.py", "read_state", "STATE_JSON", "read_text") in reader_coverage(
            {"readers": [], "reader_exceptions": []}, fixture_root
        )
    finally:
        import shutil
        shutil.rmtree(fixture_root)


def test_unresolved_protected_reader_source_requires_exact_classification():
    from tests.architecture.ownership_inventory_guard import reader_coverage

    fixture_root = PLUGIN / "reader-dynamic-fixture"
    (fixture_root / "scripts" / "data_modules").mkdir(parents=True)
    (fixture_root / "scripts" / "data_modules" / "dynamic_reader.py").write_text(
        "def read_state(source):\n"
        "    return load_json(source)\n",
        encoding="utf-8",
    )
    try:
        candidate = ("scripts/data_modules/dynamic_reader.py", "read_state", "STATE_JSON", "load_json")
        inventory = {"readers": [], "reader_exceptions": []}
        assert candidate in reader_coverage(inventory, fixture_root)
        inventory["reader_exceptions"].append({
            "family": "reader", "path": candidate[0], "symbol": candidate[1], "domain": candidate[2],
            "sink": candidate[3], "target_expression": "source",
            "reason_code": "DYNAMIC_TARGET_REVIEWED",
            "rationale": "fixture source is explicitly reviewed as a non-Canon compatibility read",
        })
        assert candidate not in reader_coverage(inventory, fixture_root)
    finally:
        import shutil
        shutil.rmtree(fixture_root)


def test_writer_scanner_detects_new_protected_sql_mutator():
    from tests.architecture.ownership_inventory_guard import writer_coverage

    fixture_root = PLUGIN / "writer-scan-fixture"
    fixture_root.mkdir()
    (fixture_root / "scripts").mkdir()
    (fixture_root / "scripts" / "new_index_writer.py").write_text(
        "def persist_entity(conn, entity):\n"
        "    sql = 'INSERT INTO entities (id) VALUES (?)'\n"
        "    conn.execute(sql, (entity,))\n",
        encoding="utf-8",
    )
    try:
        assert ("scripts/new_index_writer.py", "persist_entity", "INDEX_DB", "SQL:entities") in writer_coverage(
            {"writers": [], "writer_exceptions": []}, fixture_root
        )
    finally:
        import shutil
        shutil.rmtree(fixture_root)


def test_unresolved_protected_writer_target_requires_exact_reason_coded_exception():
    from tests.architecture.ownership_inventory_guard import writer_coverage

    fixture_root = PLUGIN / "writer-dynamic-fixture"
    fixture_root.mkdir()
    (fixture_root / "scripts" / "data_modules").mkdir(parents=True)
    (fixture_root / "scripts" / "data_modules" / "dynamic_writer.py").write_text(
        "def write_state(target, payload):\n"
        "    atomic_write_json(target, payload)\n",
        encoding="utf-8",
    )
    try:
        inventory = {"writers": [], "writer_exceptions": []}
        candidate = ("scripts/data_modules/dynamic_writer.py", "write_state", "STATE_JSON", "atomic_write_json")
        assert candidate in writer_coverage(inventory, fixture_root)
        inventory["writer_exceptions"].append({
            "family": "writer", "path": candidate[0], "symbol": candidate[1], "domain": candidate[2],
            "sink": candidate[3], "reason_code": "DYNAMIC_TARGET_REVIEWED",
            "target_expression": "target",
            "rationale": "fixture proves this parameter is outside protected roots",
        })
        assert candidate not in writer_coverage(inventory, fixture_root)
    finally:
        import shutil
        shutil.rmtree(fixture_root)


def test_production_runtime_does_not_consult_inventory():
    assert runtime_inventory_references(ROOT / ".claude/plugins/zhanghui") == []


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
        for mode in (writer["story_system_mode"], writer["legacy_mode"]):
            assert mode["mode"] in {"allowed", "guarded", "rejected", "projection_only", "not_applicable"}
            assert mode["behavior"]
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

@pytest.mark.parametrize("call,expected", [
    ("path.open('a')", "write"), ("path.open('w')", "write"),
    ("path.open('r')", "read"), ("path.open()", "read"),
    ("path.open(mode='a')", "write"), ("open(path, 'a')", "write"),
    ("open(path, mode='r')", "read"), ("open(path)", "read"),
])
def test_open_scanner_uses_target_and_mode_separately(tmp_path, call, expected):
    from tests.architecture.ownership_inventory_guard import _protected_candidates
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "state_io.py").write_text(
        "from pathlib import Path\ndef access(root):\n    path = root / 'state.json'\n    " + call + "\n", encoding="utf-8")
    writes, _ = _protected_candidates(tmp_path, writers=True)
    reads, _ = _protected_candidates(tmp_path, writers=False)
    selected, rejected = (writes, reads) if expected == "write" else (reads, writes)
    assert any(row[2] == "STATE_JSON" and row[3] in {"open", "Path.open"} for row in selected)
    assert not any(row[2] == "STATE_JSON" for row in rejected)
    assert all(row[3] not in {"'a'", "'r'"} for row in selected)


def test_source_coordinate_cannot_be_attached_to_wrong_same_domain_owner():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    broken = copy.deepcopy(inventory)
    source = next(row["source_coordinates"][0] for row in broken["writers"] if row.get("source_coordinates"))
    wrong_owner = next(row for row in broken["writers"] if row["writer_id"] != source["writer_id"]
                       and source["data_domain"] in row.get("data_domains", []))
    moved = copy.deepcopy(source)
    wrong_owner["source_coordinates"].append(moved)
    with pytest.raises(ValueError, match="source owner linkage mismatch"):
        validate_inventory(broken, ROOT)


def test_state_manager_cannot_have_conflicting_shadow_writer_contract():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    broken = copy.deepcopy(inventory)
    owner = next(row for row in broken["writers"] if row["writer_id"] == "state-manager")
    coordinate = {
        "path": ".claude/plugins/zhanghui/scripts/data_modules/state_manager.py",
        "symbol": "StateManager", "data_domain": "STATE_JSON", "sink": "atomic_write_json",
        "writer_id": "generic-shadow",
    }
    owner["source_coordinates"].append({**coordinate, "writer_id": "state-manager"})
    shadow = copy.deepcopy(owner)
    shadow["writer_id"] = "generic-shadow"
    shadow["implementation"] = {"path": coordinate["path"], "symbol": coordinate["symbol"]}
    shadow["owner"] = "Direct source owner StateManager"
    shadow["story_system_mode"] = {"mode": "allowed", "behavior": "Direct source owner allows writing"}
    shadow["source_coordinates"] = [coordinate]
    broken["writers"].append(shadow)
    with pytest.raises(ValueError, match="conflicting Story System ownership"):
        validate_inventory(broken, ROOT)


def test_conflicting_same_implementation_domain_requires_distinct_selector():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    assert validate_inventory(inventory, ROOT)
    broken = copy.deepcopy(inventory)
    for row in broken["writers"]:
        if row["writer_id"].startswith("update-state-"):
            row.pop("selector", None)
    with pytest.raises(ValueError, match="distinct selectors required"):
        validate_inventory(broken, ROOT)


def test_inventory_has_no_mechanically_generated_source_records():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    assert not [row["writer_id"] for row in inventory["writers"]
                if row["writer_id"].startswith("source-writer-")]
    assert not [row["reader_id"] for row in inventory["readers"]
                if row["reader_id"].startswith("source-reader-")]


@pytest.mark.parametrize("reader_id,domain", [
    ("plan-reader", "INTENT"),
    ("state-reader", "STATE_JSON"),
    ("review-reader", "WORKFLOW_METADATA"),
    ("index-reader", "INDEX_DB"),
])
def test_non_commit_reader_edges_cannot_claim_canon_authority(reader_id, domain):
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    broken = copy.deepcopy(inventory)
    record = next(row for row in broken["readers"] if row["reader_id"] == reader_id)
    edge = next(row for row in record["read_edges"] if row["data_domain"] == domain)
    edge["story_system"].update(primary_source=".story-system/commits", authority_claim="CANON_AUTHORITY")
    with pytest.raises(ValueError, match="CANON_COMMIT"):
        validate_inventory(broken, ROOT)


def test_style_samples_table_is_not_misclassified_as_index_db():
    from tests.architecture.ownership_inventory_guard import _sql_resources

    assert _sql_resources("SELECT content FROM samples") == [("CRAFT", "samples", "read")]


def test_override_proposals_and_style_samples_have_distinct_owner_contracts():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    override = next(row for row in inventory["writers"] if row["writer_id"] == "override-ledger")
    samples = next(row for row in inventory["writers"] if row["writer_id"] == "style-samples")
    assert override["implementation"]["symbol"] == "persist_amend_proposals"
    assert "WORKFLOW_METADATA" in override["data_domains"]
    assert samples["implementation"]["symbol"] == "StyleSampler"
    assert "CRAFT" in samples["data_domains"]


def test_state_manager_state_json_reader_is_discovered_and_bound_to_projection_edge():
    from tests.architecture.ownership_inventory_guard import _protected_candidates

    discovered, _ = _protected_candidates(PLUGIN, writers=False)
    candidate = ("scripts/data_modules/state_manager.py", "StateManager", "STATE_JSON", "read_json_safe")
    assert candidate in discovered
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    state_reader = next(row for row in inventory["readers"] if row["reader_id"] == "state-reader")
    assert any(row["path"].endswith("/state_manager.py") and row["symbol"] == "StateManager"
               and row["data_domain"] == "STATE_JSON" for row in state_reader["source_coordinates"])


def test_consistency_runner_intent_reader_uses_intent_authority():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    plan_reader = next(row for row in inventory["readers"] if row["reader_id"] == "plan-reader")
    coordinate = next(row for row in plan_reader["source_coordinates"]
                      if row["path"].endswith("/consistency/core/runner.py")
                      and row["symbol"] == "ConsistencyRunner" and row["data_domain"] == "INTENT")
    edge = next(row for row in plan_reader["read_edges"] if row["read_edge_id"] == coordinate["read_edge_id"])
    assert edge["story_system"]["authority_claim"] == "INTENT"
    assert edge["story_system"]["primary_source"] != ".story-system/commits"


@pytest.mark.parametrize("reader_id,domain,source_fragment,expected_claim", [
    ("state-reader", "STATE_JSON", "/state_manager.py", "VERIFIED_PROJECTION"),
    ("review-reader", "WORKFLOW_METADATA", "/review_pipeline.py", "WORKFLOW"),
    ("index-reader", "INDEX_DB", "/sql_state_manager.py", "VERIFIED_PROJECTION"),
])
def test_discovered_projection_readers_keep_domain_authority(reader_id, domain, source_fragment, expected_claim):
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    record = next(row for row in inventory["readers"] if row["reader_id"] == reader_id)
    assert any(source_fragment in coordinate["path"] and coordinate["data_domain"] == domain
               for coordinate in record["source_coordinates"])
    edge = next(row for row in record["read_edges"] if row["data_domain"] == domain)
    assert edge["story_system"]["authority_claim"] == expected_claim
    assert edge["story_system"]["primary_source"] != ".story-system/commits"


def test_non_story_exceptions_have_distinct_target_specific_rationales():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    for family in ("writer_exceptions", "reader_exceptions"):
        rationales = [row["rationale"] for row in inventory[family]
                     if row["reason_code"] == "NON_STORY_STORE"]
        assert len(rationales) == len(set(rationales)), family
        assert all(len(value.split()) >= 12 for value in rationales)


def test_dynamic_protected_exception_requires_owner_link_and_classification():
    from tests.architecture.ownership_inventory_guard import writer_coverage
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    exception = next(row for row in inventory["writer_exceptions"] if row.get("writer_id"))
    broken = copy.deepcopy(inventory)
    broken_exception = next(row for row in broken["writer_exceptions"] if row.get("writer_id"))
    broken_exception.pop("writer_id", None)
    with pytest.raises(ValueError, match="owner"):
        validate_inventory(broken, ROOT)
    assert writer_coverage(inventory, PLUGIN) == []


def test_projection_log_append_is_not_misclassified_as_reader():
    from tests.architecture.ownership_inventory_guard import _protected_candidates
    writes, _ = _protected_candidates(PLUGIN, writers=True)
    reads, _ = _protected_candidates(PLUGIN, writers=False)
    assert any(p.endswith("projection_log.py") and s == "append_projection_run" for p, s, *_ in writes)
    assert not any(p.endswith("projection_log.py") and s == "append_projection_run" for p, s, *_ in reads)


def test_dynamic_reader_exception_requires_owner_and_exact_read_edge():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    protected = next(row for row in inventory["reader_exceptions"] if row.get("reader_id"))
    broken = copy.deepcopy(inventory)
    target = next(row for row in broken["reader_exceptions"] if row.get("reader_id"))
    target.pop("reader_id")
    with pytest.raises(ValueError, match="owner"):
        validate_inventory(broken, ROOT)
    broken = copy.deepcopy(inventory)
    target = next(row for row in broken["reader_exceptions"] if row.get("reader_id"))
    target.pop("read_edge_id", None)
    with pytest.raises(ValueError, match="read edge"):
        validate_inventory(broken, ROOT)
    assert protected["read_edge_id"]


def test_generic_dynamic_exception_rationale_does_not_replace_ownership():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    broken = copy.deepcopy(inventory)
    target = next(row for row in broken["writer_exceptions"] if row.get("writer_id"))
    target.pop("writer_id")
    target["rationale"] = "dynamic target reviewed"
    with pytest.raises(ValueError, match="owner"):
        validate_inventory(broken, ROOT)


def test_writer_coverage_requires_exact_sink_coordinate(tmp_path, monkeypatch):
    import tests.architecture.ownership_inventory_guard as guard

    monkeypatch.setitem(guard.SQL_DOMAINS, "INDEX_DB", guard.SQL_DOMAINS["INDEX_DB"] | {"table_a", "table_b"})
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "foo.py").write_text(
        "def foo(conn):\n"
        "    conn.execute('INSERT INTO table_a (id) VALUES (1)')\n"
        "    conn.execute('INSERT INTO table_b (id) VALUES (1)')\n",
        encoding="utf-8",
    )
    owner = {"writer_id": "foo-owner", "implementation": {"path": "scripts/foo.py", "symbol": "foo"},
             "data_domains": ["INDEX_DB"], "source_coordinates": [
                 {"path": "scripts/foo.py", "symbol": "foo", "data_domain": "INDEX_DB",
                  "sink": "SQL:table_a", "writer_id": "foo-owner"}]}
    inventory = {"writers": [owner], "writer_exceptions": []}
    assert guard.writer_coverage(inventory, tmp_path) == [
        ("scripts/foo.py", "foo", "INDEX_DB", "SQL:table_b")]
    owner["source_coordinates"].append(
        {"path": "scripts/foo.py", "symbol": "foo", "data_domain": "INDEX_DB",
         "sink": "SQL:table_b", "writer_id": "foo-owner"})
    assert guard.writer_coverage(inventory, tmp_path) == []


def test_reader_coverage_requires_exact_sink_coordinate(tmp_path, monkeypatch):
    import tests.architecture.ownership_inventory_guard as guard

    monkeypatch.setitem(guard.SQL_DOMAINS, "INDEX_DB", guard.SQL_DOMAINS["INDEX_DB"] | {"table_a", "table_b"})
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "foo.py").write_text(
        "def foo(conn):\n"
        "    conn.execute('SELECT id FROM table_a')\n"
        "    conn.execute('SELECT id FROM table_b')\n",
        encoding="utf-8",
    )
    owner = {"reader_id": "foo-reader", "implementation": {"path": "scripts/foo.py", "symbol": "foo"},
             "read_edges": [{"data_domain": "INDEX_DB", "read_edge_id": "foo-index-edge"}],
             "source_coordinates": [{"path": "scripts/foo.py", "symbol": "foo", "data_domain": "INDEX_DB",
                                     "sink": "SQL:table_a", "reader_id": "foo-reader",
                                     "read_edge_id": "foo-index-edge"}]}
    inventory = {"readers": [owner], "reader_exceptions": []}
    assert guard.reader_coverage(inventory, tmp_path) == [
        ("scripts/foo.py", "foo", "INDEX_DB", "SQL:table_b")]
    owner["source_coordinates"].append(
        {"path": "scripts/foo.py", "symbol": "foo", "data_domain": "INDEX_DB",
         "sink": "SQL:table_b", "reader_id": "foo-reader", "read_edge_id": "foo-index-edge"})
    assert guard.reader_coverage(inventory, tmp_path) == []


def test_stale_dynamic_exception_is_rejected():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    broken = copy.deepcopy(inventory)
    broken["writer_exceptions"].append({
        "path": ".claude/plugins/zhanghui/scripts/data_modules/projection_log.py",
        "symbol": "append_projection_run", "domain": "WORKFLOW_METADATA", "sink": "open",
        "target_expression": "'a'", "reason_code": "DYNAMIC_TARGET_REVIEWED",
        "rationale": "Old append-mode exception retained after the scanner began resolving Path.open sinks.",
        "evidence": [{"path": ".claude/plugins/zhanghui/scripts/data_modules/projection_log.py",
                      "anchor": "append_projection_run"}], "writer_id": "projection-run-log"})
    with pytest.raises(ValueError, match="stale exception"):
        validate_inventory(broken, ROOT)
