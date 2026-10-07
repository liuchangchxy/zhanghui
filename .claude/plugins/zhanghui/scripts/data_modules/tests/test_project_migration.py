import json
import sqlite3

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
