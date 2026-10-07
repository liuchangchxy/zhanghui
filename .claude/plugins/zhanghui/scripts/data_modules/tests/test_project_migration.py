import json
import sqlite3
import shutil

import pytest

from data_modules.canon_correction_schema import (
    base_commit_digest, effective_content_digest, request_sha256,
)
from data_modules.canon_correction_store import append_correction_authorization, append_correction_request
from data_modules.effective_history import EffectiveHistoryStore
from data_modules.projection_generation import ProjectionGeneration
from data_modules.projection_rebuild import build_effective_generation
from data_modules.project_migration import (
    MigrationError, create_verified_backup, dry_run_migration, preflight_project,
)


def _commit(chapter=1):
    return {
        "meta": {"schema_version": "story-system/v1", "chapter": chapter, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": [],
                              "chapter_meta": {"title": "chapter"}},
    }


def _root_with_base(root):
    path = root / ".story-system/commits/chapter_001.commit.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_commit()), encoding="utf-8")
    webnovel = root / ".webnovel"
    webnovel.mkdir(parents=True)
    (webnovel / "state.json").write_text("{}", encoding="utf-8")
    db = sqlite3.connect(webnovel / "index.db")
    db.execute("CREATE TABLE chapters (chapter INTEGER)")
    db.execute("CREATE TABLE review_attempts (id INTEGER)")
    db.commit()
    db.close()
    return path


def _active_root(root):
    _root_with_base(root)
    snapshot = EffectiveHistoryStore().read_active_snapshot(root)
    built = build_effective_generation(root, snapshot)
    ProjectionGeneration(root).publish_generation(
        built["validated_generation"], None, snapshot.correction_lineage_digest)
    return root / ".story-system/commits/chapter_001.commit.json"


def _legacy_project(root):
    story = root / ".story-system"
    chapters = story / "chapters"
    chapters.mkdir(parents=True)
    (chapters / "chapter_001.json").write_text(json.dumps({
        "meta": {"schema_version": "story-system/v1", "contract_type": "CHAPTER_BRIEF", "chapter": 1},
        "override_allowed": {"chapter_focus": "TEST ONLY legacy brief"},
        "chapter_directive": {},
    }), encoding="utf-8")
    (chapters / "chapter_001.md").write_text("# TEST ONLY legacy brief\n", encoding="utf-8")
    prose = root / "正文/第0001章-TEST-ONLY.md"
    prose.parent.mkdir(parents=True)
    prose.write_text("# TEST ONLY chapter prose\n本文仅用于 legacy migration smoke。\n", encoding="utf-8")

    webnovel = root / ".webnovel"
    webnovel.mkdir(parents=True)
    (webnovel / "state.json").write_text(json.dumps({
        "project_info": {"title": "TEST ONLY", "genre": "玄幻", "core_selling_points": "planned"},
        "progress": {"current_chapter": 1, "total_words": 10, "last_updated": "2026-10-07",
                      "volumes_completed": []},
        "_migrated_to_sqlite": True,
        "_migration_timestamp": "2026-10-07T00:00:00Z",
        "state": {"_revision": 1, "_last_modified_by": "TEST ONLY", "_last_modified_at": "2026-10-07"},
        "plot_threads": {"active_threads": [], "foreshadowing": []},
        "relationships": {},
        "state_changes": [],
        "volumes": [],
        "world_settings": {"power_system": [], "factions": [], "locations": []},
    }), encoding="utf-8")
    db = sqlite3.connect(webnovel / "index.db")
    db.execute("CREATE TABLE chapters (chapter INTEGER PRIMARY KEY, title TEXT)")
    db.execute("INSERT INTO chapters VALUES (1, 'TEST ONLY derived row')")
    db.execute("CREATE TABLE state_changes (id INTEGER PRIMARY KEY, chapter INTEGER, value TEXT)")
    db.commit()
    db.close()
    return prose


def _tree_hashes(root):
    return {path.relative_to(root).as_posix(): __import__("hashlib").sha256(path.read_bytes()).hexdigest()
            for base in (root / ".story-system", root / ".webnovel") if base.exists()
            for path in base.rglob("*") if path.is_file()}


def test_clean_base_only_preflight_and_dry_run_are_read_only_and_deterministic(tmp_path):
    _root_with_base(tmp_path)
    before = _tree_hashes(tmp_path)
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    assert report.ok is True
    assert report.active_status == "not_enrolled"
    assert report.active["mode"] == "base_only"
    assert any(row["path"] == ".webnovel/state-overlay.json" for row in plan.mutable_overlays)
    assert plan.canon_slices[0]["base_sha256"] == base_commit_digest(_commit())
    assert {path.split("/", 1)[0] for path in plan.output_hashes} == {
        "events", "state", "index", "summary", "memory", "vector", "intent_diagnostics",
    }
    assert all(len(digest) == 64 for digest in plan.output_hashes.values())
    assert _tree_hashes(tmp_path) == before
    assert dry_run_migration(tmp_path, report.report_digest).plan_digest == plan.plan_digest


def test_dry_run_rejects_stale_preflight_report(tmp_path):
    _root_with_base(tmp_path)
    report = preflight_project(tmp_path)
    (tmp_path / ".webnovel/state.json").write_text('{"story_craft":{}}', encoding="utf-8")
    with pytest.raises(MigrationError, match="PREFLIGHT_REPORT_STALE"):
        dry_run_migration(tmp_path, report.report_digest)


def test_candidate_corruption_does_not_poison_healthy_active_report(tmp_path):
    _active_root(tmp_path)
    candidate_dir = tmp_path / ".story-system/corrections/chapter_001/base/corrections"
    candidate_dir.mkdir(parents=True)
    (candidate_dir / "broken.correction.json").write_text("not-json", encoding="utf-8")
    report = preflight_project(tmp_path)
    assert report.active_status == "valid"
    assert report.active["semantic_activation_id"].startswith("semantic-")
    assert report.candidates[0]["status"] == "blocked"


def test_pending_and_rejected_candidates_do_not_change_active_status(tmp_path):
    _active_root(tmp_path)
    base = _commit()
    digest = base_commit_digest(base)
    request = {
        "schema_version": "canon-correction-request/v1", "request_id": "TEST-ONLY-pending",
        "chapter": 1, "base_commit_sha256": digest, "parent_revision_id": f"base:{digest}",
        "parent_effective_content_sha256": effective_content_digest("accepted", base["extraction_result"]),
        "operation": "RETRACT", "proposed_effective_status": "retracted",
        "proposed_effective_extraction_result": None,
        "proposed_effective_content_sha256": effective_content_digest("retracted", None),
        "changed_paths": [], "proposer_provenance": {"fixture": "TEST ONLY"}, "reason": "TEST ONLY",
    }
    append_correction_request(tmp_path, request)
    pending = preflight_project(tmp_path)
    assert pending.active_status == "valid"
    assert any(row["status"] == "pending" for row in pending.candidates)
    auth = {"schema_version": "canon-correction-authorization/v1",
            "authorization_id": "TEST-ONLY-rejected-auth", "request_id": request["request_id"],
            "request_sha256": request_sha256(request), "choice": "REJECT",
            "actor_ref": "TEST ONLY", "decision_provenance": {"fixture": "TEST ONLY"}}
    append_correction_authorization(tmp_path, auth)
    rejected = preflight_project(tmp_path)
    assert rejected.active_status == "valid"
    assert any(row["status"] == "rejected" for row in rejected.candidates)


def test_active_evidence_corruption_blocks_preflight_without_fallback(tmp_path):
    commit_path = _active_root(tmp_path)
    commit_path.write_text('{"tampered":true}', encoding="utf-8")
    report = preflight_project(tmp_path)
    assert report.active_status == "blocked"
    assert report.ok is False
    with pytest.raises(MigrationError, match="ACTIVE_HISTORY_BLOCKED"):
        dry_run_migration(tmp_path, report.report_digest)


def test_unknown_state_owner_and_mixed_memory_evidence_are_explicit_conflicts(tmp_path):
    _root_with_base(tmp_path)
    (tmp_path / ".webnovel/state.json").write_text(json.dumps({"mystery": {"x": 1}}))
    (tmp_path / ".webnovel/memory_scratchpad.json").write_text(json.dumps({
        "story_facts": [{"id": "mix", "evidence": ["state_change:chapter:1", "manual:note"]}]
    }))
    report = preflight_project(tmp_path)
    kinds = {item["kind"] for item in report.conflicts}
    assert "unmapped_state_root" in kinds
    assert "mixed_memory_evidence" in kinds


def test_legacy_brief_and_prose_require_explicit_import_decision(tmp_path):
    prose = _legacy_project(tmp_path)

    report = preflight_project(tmp_path)

    assert report.ok is False
    assert report.legacy_history["status"] == "requires_explicit_import_decision"
    assert report.legacy_history["durable_commit_count"] == 0
    assert report.legacy_history["legacy_chapter_artifact_count"] == 1
    assert report.legacy_history["legacy_prose_count"] == 1
    assert report.legacy_history["legacy_structured_artifacts"][0]["contract_type"] == "CHAPTER_BRIEF"
    assert report.legacy_history["accepted_evidence_found"] is False
    assert report.legacy_history["prose_artifacts"][0]["sha256"] == __import__("hashlib").sha256(prose.read_bytes()).hexdigest()
    assert any(item["kind"] == "legacy_history_requires_explicit_import_decision"
               for item in report.conflicts)
    assert not any(item["kind"] == "ambiguous_legacy_semantics" for item in report.conflicts)
    assert report.owner_mappings["state"]["field_classifications"]["_migrated_to_sqlite"] == "OWNER_OPERATIONAL_METADATA"
    assert report.owner_mappings["state"]["field_classifications"]["progress.volumes_completed"] == "OWNER_WORKFLOW_METADATA"
    assert report.owner_mappings["state"]["field_classifications"]["project_info.core_selling_points"] == "OWNER_INTENT"
    classifications = report.owner_mappings["state"]["field_classifications"]
    assert classifications["_migration_timestamp"] == "OWNER_OPERATIONAL_METADATA"
    assert classifications["relationships"] == "LEGACY_DERIVED_CANON_PROJECTION"
    assert classifications["state_changes"] == "LEGACY_DERIVED_CANON_PROJECTION"
    assert classifications["state._revision"] == "OWNER_OPERATIONAL_METADATA"
    assert classifications["volumes"] == "OWNER_INTENT_PLANNING"
    assert classifications["plot_threads"] == "LEGACY_AMBIGUOUS_CANON_OR_INTENT"
    assert classifications["world_settings"] == "LEGACY_AMBIGUOUS_CANON_OR_INTENT"
    assert classifications["progress.current_chapter"] == "LEGACY_DERIVED_CANON_PROJECTION"
    assert report.owner_mappings["index_tables"]["chapters"] == "LEGACY_DERIVED_CANON_PROJECTION"

    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    from data_modules.project_migration import migrate_project
    with pytest.raises(MigrationError, match="MIGRATION_CONFLICTS_UNRESOLVED"):
        migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)
    assert not (tmp_path / ".story-system/effective-history/enrollment.json").exists()
    assert not (tmp_path / ".story-system/publications/active.json").exists()


def test_nonempty_ambiguous_legacy_roots_remain_field_level_conflicts(tmp_path):
    _legacy_project(tmp_path)
    state_path = tmp_path / ".webnovel/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["plot_threads"]["active_threads"] = [{"id": "TEST ONLY", "description": "ambiguous"}]
    state["relationships"]["林川"] = {"ally": "陈默"}
    state["world_settings"]["locations"] = [{"name": "TEST ONLY", "source": "unknown"}]
    state["project_info"]["unclassified_future_field"] = "ambiguous"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    report = preflight_project(tmp_path)

    paths = {item.get("path") for item in report.conflicts}
    assert any(path.startswith(".webnovel/state.json:plot_threads.active_threads") for path in paths)
    assert any(path.startswith(".webnovel/state.json:relationships.林川") for path in paths)
    assert any(path.startswith(".webnovel/state.json:world_settings.locations") for path in paths)
    assert ".webnovel/state.json:project_info.unclassified_future_field" in paths
    assert report.ok is False


def test_verified_backup_copies_sqlite_and_all_sidecars_and_restores_hashes(tmp_path):
    _root_with_base(tmp_path)
    vector_db = sqlite3.connect(tmp_path / ".webnovel/vectors.db")
    vector_db.execute("CREATE TABLE vectors (id TEXT)")
    vector_db.commit()
    vector_db.close()
    (tmp_path / ".webnovel/vectors.db-wal").write_bytes(b"test-sidecar")
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    assert backup.restore_verified is True
    assert backup.sqlite_integrity[".webnovel/index.db"] == "ok"
    assert backup.sqlite_integrity[".webnovel/vectors.db"] == "ok"
    assert any(row["path"] == ".webnovel/vectors.db-wal" for row in backup.files)
    manifest_path = tmp_path / ".story-system/backups/phase9" / plan.plan_digest / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifest_sha256"] == backup.manifest_sha256
    assert all(row["file_type"] == "regular_file" and isinstance(row["size_bytes"], int)
               for row in manifest["files"])


def test_explicit_migration_requires_verified_backup_and_publishes_complete_generation(tmp_path):
    from data_modules.project_migration import migrate_project

    commit_path = _root_with_base(tmp_path)
    original_commit = commit_path.read_bytes()
    expected_history_digest = EffectiveHistoryStore().read_active_snapshot(tmp_path).effective_history_digest
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    with pytest.raises(MigrationError, match="VERIFIED_BACKUP_REQUIRED"):
        migrate_project(tmp_path, report.report_digest, plan.plan_digest, None)

    backup = create_verified_backup(tmp_path, plan)
    result = migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)
    assert result.publication["body"]["publication_kind"] == "semantic_activation"
    assert result.publication["body"]["effective_history_digest"] == expected_history_digest
    assert result.backup_manifest_sha256 == backup.manifest_sha256
    assert commit_path.read_bytes() == original_commit
    assert (tmp_path / ".story-system/effective-history/enrollment.json").is_file()
    assert (tmp_path / ".webnovel/state-overlay.json").is_file()
    pinned = ProjectionGeneration(tmp_path).pin_active_generation()
    assert pinned is not None
    from data_modules.projection_generation import CANON_DOMAINS
    assert set(pinned.manifest["domains"]) == set(CANON_DOMAINS)


def test_migration_rejects_stale_source_digest_and_unresolved_owner_conflicts(tmp_path):
    from data_modules.project_migration import migrate_project

    _root_with_base(tmp_path)
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    (tmp_path / ".webnovel/state.json").write_text('{"mystery":true}', encoding="utf-8")
    with pytest.raises(MigrationError, match="PREFLIGHT_REPORT_STALE"):
        migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)

    conflict = preflight_project(tmp_path)
    conflicted_plan = dry_run_migration(tmp_path, conflict.report_digest)
    conflict_backup = create_verified_backup(tmp_path, conflicted_plan)
    with pytest.raises(MigrationError, match="MIGRATION_CONFLICTS_UNRESOLVED"):
        migrate_project(tmp_path, conflict.report_digest, conflicted_plan.plan_digest, conflict_backup)
    assert not (tmp_path / ".story-system/effective-history/enrollment.json").exists()


def test_same_semantic_replacement_publishes_monotonically_and_rejects_other_generation(tmp_path):
    from data_modules.project_migration import migrate_project, replace_generation

    _root_with_base(tmp_path)
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    first = migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup).publication["body"]
    snapshot = EffectiveHistoryStore().read_active_snapshot(tmp_path)
    replacement = build_effective_generation(tmp_path, snapshot,
                                             previous_generation_id=first["generation_id"])
    second = replace_generation(tmp_path, replacement["generation_id"])
    assert second.body["sequence"] == first["sequence"] + 1
    assert second.body["semantic_activation_id"] == first["semantic_activation_id"]
    assert second.body["effective_history_digest"] == first["effective_history_digest"]
    with pytest.raises(MigrationError, match="REPLACEMENT_GENERATION_NOT_FOUND"):
        replace_generation(tmp_path, "generation-unknown")

    other_root = tmp_path / "other-project"
    other_commit = _root_with_base(other_root)
    other_body = _commit()
    other_body["extraction_result"]["chapter_meta"]["title"] = "different semantic history"
    other_commit.write_text(json.dumps(other_body), encoding="utf-8")
    other_snapshot = EffectiveHistoryStore().read_active_snapshot(other_root)
    other_generation = build_effective_generation(other_root, other_snapshot)
    foreign_id = other_generation["generation_id"]
    shutil.copytree(other_generation["validated_generation"].generation_root,
                    ProjectionGeneration(tmp_path).generations_root / foreign_id)
    with pytest.raises(MigrationError, match="REPLACEMENT_SEMANTIC_MISMATCH"):
        replace_generation(tmp_path, foreign_id)


def test_migration_moves_known_owner_state_to_overlay_without_rewriting_legacy_state(tmp_path):
    from data_modules.project_migration import migrate_project
    from data_modules.owned_project_view import OwnedStateStore

    _root_with_base(tmp_path)
    state_path = tmp_path / ".webnovel/state.json"
    original = {"story_craft": {"voice": "warm"},
                "progress": {"current_volume": 4, "current_chapter": 1,
                             "volumes_completed": [1, 2], "last_updated": "2026-10-07"}}
    state_path.write_text(json.dumps(original), encoding="utf-8")
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    result = migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)
    overlay = json.loads((tmp_path / ".webnovel/state-overlay.json").read_text(encoding="utf-8"))
    assert overlay["values"]["story_craft"] == {"voice": "warm"}
    assert overlay["values"]["progress.current_volume"] == 4
    assert overlay["values"]["progress.volumes_completed"] == [1, 2]
    assert overlay["values"]["progress.last_updated"] == "2026-10-07"
    assert state_path.read_text(encoding="utf-8") == json.dumps(original)
    assert result.overlay_revision == overlay["revision"]


def test_migration_detects_post_backup_file_edits_before_enrollment(tmp_path):
    from data_modules.project_migration import _validated_backup, migrate_project

    _root_with_base(tmp_path)
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    state_path = tmp_path / ".webnovel/state.json"
    state_path.write_text('{"planning":{"changed":true}}', encoding="utf-8")
    with pytest.raises(MigrationError, match="POST_BACKUP_SOURCE_CONFLICT"):
        _validated_backup(tmp_path, plan, backup)
    with pytest.raises(MigrationError, match="PREFLIGHT_REPORT_STALE"):
        migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)
    assert not (tmp_path / ".story-system/effective-history/enrollment.json").exists()


def test_failed_generation_build_does_not_create_enrollment_or_overlay(tmp_path, monkeypatch):
    from data_modules import projection_rebuild
    from data_modules.project_migration import migrate_project

    _root_with_base(tmp_path)
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    def fail_build(*_args, **_kwargs):
        raise RuntimeError("synthetic writer failure")
    monkeypatch.setattr(projection_rebuild, "build_effective_generation", fail_build)
    with pytest.raises(RuntimeError, match="synthetic writer failure"):
        migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)
    assert not (tmp_path / ".story-system/effective-history/enrollment.json").exists()
    assert not (tmp_path / ".webnovel/state-overlay.json").exists()


def test_layout_restore_requires_conflict_report_and_preserves_active_semantics(tmp_path):
    from data_modules.project_migration import migrate_project, restore_mutable_layout

    _root_with_base(tmp_path)
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    result = migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)
    publication = result.publication["body"]
    conflict_report = {"ok": True, "conflicts": [],
                       "expected_current_hashes": result.migration_owned_hashes}
    restored = restore_mutable_layout(
        tmp_path, backup, conflict_report,
        expected_semantic_activation_id=publication["semantic_activation_id"],
        expected_effective_history_digest=publication["effective_history_digest"])
    assert restored["ok"] is True
    assert not (tmp_path / ".webnovel/state-overlay.json").exists()
    pinned = ProjectionGeneration(tmp_path).pin_active_generation()
    assert pinned.semantic_activation_id == publication["semantic_activation_id"]
    assert pinned.record_body["effective_history_digest"] == publication["effective_history_digest"]


def test_layout_restore_blocks_post_migration_owner_edits(tmp_path):
    from data_modules.project_migration import migrate_project, restore_mutable_layout

    _root_with_base(tmp_path)
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    result = migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)
    publication = result.publication["body"]
    overlay = tmp_path / ".webnovel/state-overlay.json"
    overlay.write_text('{"schema_version":"owner-state-overlay/v1","revision":9,"values":{}}', encoding="utf-8")
    after_edit = overlay.read_bytes()
    correction = tmp_path / ".story-system/corrections/chapter_001/base/corrections/POST-BACKUP.correction.json"
    correction.parent.mkdir(parents=True, exist_ok=True)
    correction.write_bytes(b'{"post_backup_candidate":true}')
    restored = restore_mutable_layout(
        tmp_path, backup,
        {"ok": True, "conflicts": [], "expected_current_hashes": result.migration_owned_hashes},
        expected_semantic_activation_id=publication["semantic_activation_id"],
        expected_effective_history_digest=publication["effective_history_digest"])
    assert restored["ok"] is False
    assert restored["conflicts"][0]["kind"] == "post_backup_edit"
    assert overlay.read_bytes() == after_edit
    assert correction.read_bytes() == b'{"post_backup_candidate":true}'


def test_publication_failure_before_enrollment_keeps_base_mode_readable(tmp_path, monkeypatch):
    from data_modules.projection_generation import ProjectionGeneration
    from data_modules.project_migration import migrate_project

    _root_with_base(tmp_path)
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    def fail_before_publish(*_args, **_kwargs):
        raise RuntimeError("synthetic pre-publication crash")
    monkeypatch.setattr(ProjectionGeneration, "publish_generation", fail_before_publish)
    with pytest.raises(RuntimeError, match="pre-publication crash"):
        migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)
    assert not (tmp_path / ".story-system/effective-history/enrollment.json").exists()
    assert ProjectionGeneration(tmp_path).pin_active_generation() is None


def test_crash_after_publication_is_detected_as_published_not_retried(tmp_path, monkeypatch):
    from data_modules.projection_generation import ProjectionGeneration
    from data_modules.project_migration import migrate_project

    _root_with_base(tmp_path)
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    publish = ProjectionGeneration.publish_generation
    def publish_then_crash(self, *args, **kwargs):
        publish(self, *args, **kwargs)
        raise RuntimeError("synthetic post-publication crash")
    monkeypatch.setattr(ProjectionGeneration, "publish_generation", publish_then_crash)
    with pytest.raises(RuntimeError, match="post-publication crash"):
        migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)
    monkeypatch.setattr(ProjectionGeneration, "publish_generation", publish)
    pinned = ProjectionGeneration(tmp_path).pin_active_generation()
    assert pinned is not None
    assert len(ProjectionGeneration(tmp_path)._records()) == 1
    retry_report = preflight_project(tmp_path)
    retry_plan = dry_run_migration(tmp_path, retry_report.report_digest)
    retry_backup = create_verified_backup(tmp_path, retry_plan)
    with pytest.raises(MigrationError, match="PROJECT_ALREADY_ENROLLED"):
        migrate_project(tmp_path, retry_report.report_digest, retry_plan.plan_digest, retry_backup)


def test_corrupt_active_generation_recovers_from_publication_closure_only(tmp_path):
    from data_modules.projections import _active_generation_recovery
    from data_modules.projection_generation import GenerationError
    from data_modules.project_migration import migrate_project

    _root_with_base(tmp_path)
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    first = migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup).publication["body"]
    protocol = ProjectionGeneration(tmp_path)
    damaged_file = protocol.generations_root / first["generation_id"] / "events/chapter_001.json"
    damaged_file.write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(GenerationError, match="ACTIVE_GENERATION_CORRUPT"):
        protocol.pin_active_generation()

    recovered = _active_generation_recovery(tmp_path)
    assert recovered["ok"] is True
    assert recovered["semantic_activation_id"] == first["semantic_activation_id"]
    assert recovered["effective_history_digest"] == first["effective_history_digest"]
    assert recovered["generation_id"] != first["generation_id"]
    assert protocol.pin_active_generation().generation_id == recovered["generation_id"]


def test_source_change_during_generation_build_fails_publication_recheck(tmp_path, monkeypatch):
    from data_modules.projection_generation import GenerationError, ProjectionGeneration
    from data_modules.project_migration import migrate_project

    commit_path = _root_with_base(tmp_path)
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    publish = ProjectionGeneration.publish_generation
    def mutate_source_then_publish(self, *args, **kwargs):
        commit_path.write_text('{"changed_during_build":true}', encoding="utf-8")
        return publish(self, *args, **kwargs)
    monkeypatch.setattr(ProjectionGeneration, "publish_generation", mutate_source_then_publish)
    with pytest.raises(GenerationError, match="LINEAGE_CHANGED"):
        migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)
    assert not (tmp_path / ".story-system/effective-history/enrollment.json").exists()
    assert ProjectionGeneration(tmp_path).latest_publication() is None


def test_owner_overlay_collision_blocks_without_promoting_craft_or_enrolling(tmp_path):
    from data_modules.project_migration import migrate_project

    _root_with_base(tmp_path)
    state_path = tmp_path / ".webnovel/state.json"
    state_path.write_text(json.dumps({"story_craft": {"tone": "legacy"}}), encoding="utf-8")
    overlay_path = tmp_path / ".webnovel/state-overlay.json"
    original_overlay = {"schema_version": "owner-state-overlay/v1", "revision": 3,
                        "values": {"story_craft": {"tone": "newer-owner-value"}}}
    overlay_path.write_text(json.dumps(original_overlay), encoding="utf-8")
    report = preflight_project(tmp_path)
    plan = dry_run_migration(tmp_path, report.report_digest)
    backup = create_verified_backup(tmp_path, plan)
    with pytest.raises(MigrationError, match="OWNER_OVERLAY_CONFLICT:story_craft"):
        migrate_project(tmp_path, report.report_digest, plan.plan_digest, backup)
    assert json.loads(state_path.read_text(encoding="utf-8"))["story_craft"]["tone"] == "legacy"
    assert json.loads(overlay_path.read_text(encoding="utf-8")) == original_overlay
    assert not (tmp_path / ".story-system/effective-history/enrollment.json").exists()
