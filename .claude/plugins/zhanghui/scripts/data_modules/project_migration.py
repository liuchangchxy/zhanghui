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
    conflicts: list[dict[str, Any]]
    report_digest: str


@dataclass(frozen=True)
class MigrationPlan:
    schema_version: str
    project_root: str
    preflight_digest: str
    plan_digest: str
    canon_slices: list[dict[str, Any]]
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
    state_canon = {"entity_state", "protagonist_state", "strand_tracker", "chapter_meta"}
    owner_roots = {"story_craft", "planning", "promise_ledger", "review_checkpoints",
                   "workflow", "craft", "intent", "disambiguation_warnings", "disambiguation_pending"}
    owner_paths = {"progress.volumes_planned", "progress.current_volume", "progress.total_volumes"}
    known = state_canon | owner_roots | {"progress", "meta", "schema_version"}
    conflicts = []
    unknown = sorted(set(state) - known)
    for key in unknown:
        conflicts.append({"kind": "unmapped_state_root", "path": f".webnovel/state.json:{key}",
                          "requires": "explicit owner mapping"})
    progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
    progress_owner = sorted(set(progress) & {"volumes_planned", "current_volume", "total_volumes"})
    progress_canon = sorted(set(progress) & {"current_chapter", "total_words", "chapter_status", "last_updated"})
    unmapped_progress = sorted(set(progress) - set(progress_owner) - set(progress_canon) - {"chapter_meta"})
    for key in unmapped_progress:
        conflicts.append({"kind": "unmapped_progress_field", "path": f".webnovel/state.json:progress.{key}",
                          "requires": "explicit owner mapping"})

    table_owners = {
        "chapters": "CANON_COMMIT", "scenes": "CANON_COMMIT", "appearances": "CANON_COMMIT",
        "state_changes": "CANON_COMMIT", "entities": "CANON_COMMIT", "relationships": "CANON_COMMIT",
        "story_events": "CANON_COMMIT",
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

    mappings = {
        "state": {"canon_roots": sorted(state_canon), "owner_roots": sorted(owner_roots),
                  "owner_progress_paths": sorted(owner_paths), "observed_owner_progress_fields": progress_owner,
                  "observed_canon_progress_fields": progress_canon},
        "index_tables": table_owners,
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
    history = EffectiveHistoryStore().read_active_snapshot(root)
    if active.get("mode") == "base_only":
        active["base_history_status"] = "valid" if history.ok else "blocked"
        if not history.ok:
            conflicts.append({"kind": "base_history_invalid", "diagnostics": list(history.diagnostics)})
    evidence_hashes = _hash_files(root)
    candidates = _candidate_report(root)
    return {"schema_version": "phase9-migration-preflight/v1", "project_root": str(root),
            "active_status": active.get("active_status", "unknown"), "active": active,
            "candidates": candidates, "evidence_hashes": evidence_hashes,
            "owner_mappings": mappings, "conflicts": conflicts}


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
    mutable_overlays = [
        {"path": ".webnovel/state-overlay.json", "fields": mappings["state"]["owner_roots"] + mappings["state"]["owner_progress_paths"]},
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
    store = OwnedStateStore(root)
    overlay = store._overlay()
    values = overlay["values"]
    additions = {}
    owner_roots = {"story_craft", "planning", "promise_ledger", "review_checkpoints",
                   "workflow", "craft", "intent", "disambiguation_warnings",
                   "disambiguation_pending"}
    allowed_overlay_paths = owner_roots | {"progress.volumes_planned", "progress.current_volume",
                                           "progress.total_volumes", "progress.chapter_status"}
    unknown_overlay_paths = set(overlay["values"]) - allowed_overlay_paths
    if unknown_overlay_paths:
        raise MigrationError(f"UNMAPPED_EXISTING_OVERLAY:{sorted(unknown_overlay_paths)}")
    for key in owner_roots:
        if key in state:
            additions[key] = state[key]
    progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
    for key in ("volumes_planned", "current_volume", "total_volumes"):
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
