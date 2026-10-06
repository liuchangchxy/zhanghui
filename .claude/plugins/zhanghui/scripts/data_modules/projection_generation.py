"""Immutable Canon projection generation and monotonic publication protocol."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
from typing import Any
from uuid import uuid4

from filelock import FileLock

from .canon_correction_schema import artifact_sha256, canonical_json
from .event_projection_router import EventProjectionRouter


GENERATION_SCHEMA = "story-system-projection-generation/v1"
PUBLICATION_SCHEMA = "story-system-effective-history-publication/v1"
ENROLLMENT_SCHEMA = "story-system-effective-history/v1"
CANON_DOMAINS = EventProjectionRouter.CANON_GENERATION_DOMAINS


class GenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class BuildHandle:
    root: Path
    staging_root: Path
    generation_id: str
    snapshot: Any
    previous_generation_id: str | None

    @staticmethod
    def digest_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def write_domain_file(self, domain: str, relative_path: str, data: bytes) -> str:
        if domain not in CANON_DOMAINS:
            raise GenerationError("MUTABLE_OR_UNKNOWN_DOMAIN")
        relative = PurePosixPath(relative_path)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != domain:
            raise GenerationError("INVALID_GENERATION_PATH")
        target = self.staging_root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_bytes_atomic(target, data)
        return self.digest_bytes(data)

    def record_writer(self, chapter: int, writer: str, result: dict[str, Any]) -> None:
        if chapter < 0 or not writer:
            raise GenerationError("INVALID_WRITER_RECORD")
        path = self.staging_root / ".writer-records.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {"chapter": chapter, "writer": writer, "result": result,
               "snapshot_digest": self.snapshot.effective_history_digest,
               "generation_id": self.generation_id}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "ab") as handle:
            handle.write((canonical_json(row) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())


@dataclass(frozen=True)
class ValidatedGeneration:
    generation_id: str
    generation_root: Path
    manifest: dict[str, Any]
    manifest_sha256: str
    snapshot: Any


@dataclass(frozen=True)
class PublicationRecord:
    publication_record_id: str
    record_sha256: str
    path: Path
    body: dict[str, Any]


@dataclass(frozen=True)
class PinnedGeneration:
    publication_record_id: str
    publication_record_sha256: str
    semantic_activation_id: str
    generation_id: str
    generation_root: Path
    manifest: dict[str, Any]
    record_body: dict[str, Any]


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _atomic_create_json(path: Path, body: dict[str, Any]) -> str:
    data = (canonical_json(body) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise GenerationError("PUBLICATION_ID_CONFLICT") from exc
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return hashlib.sha256(data.rstrip(b"\n")).hexdigest()


def _file_manifest(root: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {domain: {} for domain in CANON_DOMAINS}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative.startswith(".") or relative == "generation-manifest.json":
            continue
        domain = relative.split("/", 1)[0]
        if domain not in result:
            raise GenerationError("NON_CANON_DATA_IN_GENERATION")
        result[domain][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _namespace_digest(root: Path, namespace: dict[str, str]) -> str:
    directory = root / namespace["path"]
    if not directory.exists():
        paths = []
    elif namespace["kind"] == "base_set":
        paths = sorted(directory.glob("chapter_*.commit.json"))
    else:
        paths = sorted(path for path in directory.rglob("*.json") if path.is_file())
    rows = [{"path": path.relative_to(root).as_posix(),
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in paths]
    return artifact_sha256(rows)


class ProjectionGeneration:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).expanduser().resolve()
        self.story_root = self.project_root / ".story-system"
        self.generations_root = self.story_root / "projection-generations"
        self.publications_root = self.story_root / "publications"
        self.enrollment_path = self.story_root / "effective-history" / "enrollment.json"
        self.lock_path = self.story_root / "activation.lock"

    def begin(self, snapshot: Any, previous_generation: str | None = None) -> BuildHandle:
        if not getattr(snapshot, "effective_history_digest", None):
            raise GenerationError("INVALID_SNAPSHOT")
        generation_id = f"generation-{uuid4().hex}"
        staging = self.generations_root / f".staging-{generation_id}"
        final = self.generations_root / generation_id
        staging.mkdir(parents=True, exist_ok=False)
        return BuildHandle(final, staging, generation_id, snapshot, previous_generation)

    def validate_generation(self, handle: BuildHandle,
                            expected_manifest: dict[str, Any]) -> ValidatedGeneration:
        if not isinstance(handle, BuildHandle) or not handle.staging_root.is_dir():
            raise GenerationError("STAGING_NOT_FOUND")
        expected_domains = expected_manifest.get("domains")
        if not isinstance(expected_domains, dict) or set(expected_domains) != set(CANON_DOMAINS):
            raise GenerationError("DOMAIN_SET_MISMATCH")
        actual = _file_manifest(handle.staging_root)
        if set(actual) != set(CANON_DOMAINS):
            raise GenerationError("DOMAIN_SET_MISMATCH")
        if actual != expected_domains:
            raise GenerationError("OUTPUT_DIGEST_MISMATCH")
        manifest = {
            "schema_version": GENERATION_SCHEMA,
            "generation_id": handle.generation_id,
            "snapshot_id": handle.snapshot.effective_history_digest,
            "effective_history_digest": handle.snapshot.effective_history_digest,
            "base_set_digest": handle.snapshot.base_set_digest,
            "correction_lineage_digest": handle.snapshot.correction_lineage_digest,
            "previous_generation_id": handle.previous_generation_id,
            "domains": actual,
        }
        manifest_path = handle.staging_root / "generation-manifest.json"
        _write_bytes_atomic(manifest_path, (canonical_json(manifest) + "\n").encode("utf-8"))
        _fsync_directory(handle.staging_root)
        if handle.root.exists():
            raise GenerationError("GENERATION_ID_CONFLICT")
        os.replace(handle.staging_root, handle.root)
        _fsync_directory(self.generations_root)
        manifest_digest = artifact_sha256(manifest)
        return ValidatedGeneration(handle.generation_id, handle.root, manifest,
                                   manifest_digest, handle.snapshot)

    def _records(self) -> list[PublicationRecord]:
        if not self.publications_root.exists():
            return []
        paths = sorted(self.publications_root.glob("publication-*.json"))
        records = []
        prior = None
        for sequence, path in enumerate(paths, start=1):
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise GenerationError("PUBLICATION_CHAIN_CORRUPT") from exc
            record_id = f"publication-{sequence:08d}"
            if (body.get("publication_record_id") != record_id
                    or body.get("sequence") != sequence
                    or body.get("previous_record_sha256") != prior):
                raise GenerationError("PUBLICATION_CHAIN_CORRUPT")
            digest = artifact_sha256(body)
            records.append(PublicationRecord(record_id, digest, path, body))
            prior = digest
        return records

    def latest_publication(self) -> PublicationRecord | None:
        records = self._records()
        return records[-1] if records else None

    def publish_generation(self, validated: ValidatedGeneration,
                           expected_previous_publication: str | None,
                           expected_lineage_digest: str) -> PublicationRecord:
        if not isinstance(validated, ValidatedGeneration):
            raise GenerationError("GENERATION_NOT_VALIDATED")
        if expected_lineage_digest != validated.snapshot.correction_lineage_digest:
            raise GenerationError("LINEAGE_CHANGED")
        self.publications_root.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.lock_path)):
            for dependency in getattr(validated.snapshot, "dependencies", ()):
                path = self.project_root / dependency["path"]
                try:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError as exc:
                    raise GenerationError("LINEAGE_CHANGED") from exc
                if digest != dependency["sha256"]:
                    raise GenerationError("LINEAGE_CHANGED")
            for namespace in getattr(validated.snapshot, "lineage_namespace_checks", ()):
                if _namespace_digest(self.project_root, namespace) != namespace["sha256"]:
                    raise GenerationError("LINEAGE_CHANGED")
            records = self._records()
            current = records[-1] if records else None
            current_digest = current.record_sha256 if current else None
            if current_digest != expected_previous_publication:
                raise GenerationError("PUBLICATION_HEAD_CHANGED")
            seen_semantics = {row.body["effective_history_digest"] for row in records}
            history_digest = validated.manifest["effective_history_digest"]
            if current and history_digest != current.body["effective_history_digest"] and history_digest in seen_semantics:
                raise GenerationError("SEMANTIC_ROLLBACK_REJECTED")
            semantic_id = (
                current.body["semantic_activation_id"]
                if current and history_digest == current.body["effective_history_digest"]
                else f"semantic-{uuid4().hex}"
            )
            sequence = len(records) + 1
            record_id = f"publication-{sequence:08d}"
            body = {
                "schema_version": PUBLICATION_SCHEMA,
                "publication_record_id": record_id,
                "sequence": sequence,
                "publication_kind": (
                    "same_semantics_generation_replacement"
                    if current and history_digest == current.body["effective_history_digest"]
                    else "semantic_activation"
                ),
                "semantic_activation_id": semantic_id,
                "effective_history_digest": history_digest,
                "base_set_digest": validated.manifest["base_set_digest"],
                "correction_lineage_digest": validated.manifest["correction_lineage_digest"],
                "generation_id": validated.generation_id,
                "generation_manifest_sha256": validated.manifest_sha256,
                "generation_manifest": validated.manifest,
                "dependency_closure": getattr(validated.snapshot, "dependencies", ()),
                "chapter_closure": [
                    {"chapter": number, "base_sha256": entry.base_sha256,
                     "effective_revision_id": entry.effective_revision_id,
                     "status": entry.status,
                     "effective_content_sha256": entry.effective_content_sha256,
                     "applied_correction_ids": list(entry.applied_correction_ids)}
                    for number, entry in sorted(getattr(validated.snapshot, "chapters", {}).items())
                ],
                "previous_record_sha256": current_digest,
            }
            path = self.publications_root / f"{record_id}.json"
            if not self.enrollment_path.exists():
                enrollment = {"schema_version": ENROLLMENT_SCHEMA,
                              "mode": "activation_managed"}
                self.enrollment_path.parent.mkdir(parents=True, exist_ok=True)
                _atomic_create_json(self.enrollment_path, enrollment)
            digest = _atomic_create_json(path, body)
            pointer = self.publications_root / "current-head.json"
            _write_bytes_atomic(pointer, (canonical_json({"publication_record_id": record_id,
                                                          "record_sha256": digest}) + "\n").encode())
            return PublicationRecord(record_id, digest, path, body)

    def pin_active_generation(self) -> PinnedGeneration | None:
        if self.enrollment_path.exists() and not any(self.publications_root.glob("publication-*.json")):
            raise GenerationError("ENROLLED_PUBLICATION_MISSING")
        current = self.latest_publication()
        if current is None:
            return None
        if self.enrollment_path.exists():
            try:
                enrollment = json.loads(self.enrollment_path.read_text(encoding="utf-8"))
                self._records()[0]
            except Exception as exc:
                raise GenerationError("ENROLLMENT_CORRUPT") from exc
            if (enrollment.get("schema_version") != ENROLLMENT_SCHEMA
                    or enrollment.get("mode") != "activation_managed"):
                raise GenerationError("ENROLLMENT_CORRUPT")
        body = current.body
        generation_root = self.generations_root / body["generation_id"]
        try:
            manifest = json.loads((generation_root / "generation-manifest.json").read_text(encoding="utf-8"))
        except Exception as exc:
            raise GenerationError("ACTIVE_GENERATION_CORRUPT") from exc
        if (manifest != body.get("generation_manifest")
                or artifact_sha256(manifest) != body.get("generation_manifest_sha256")
                or _file_manifest(generation_root) != manifest.get("domains")):
            raise GenerationError("ACTIVE_GENERATION_CORRUPT")
        for dependency in body.get("dependency_closure", []):
            path = self.project_root / dependency["path"]
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except (KeyError, OSError) as exc:
                raise GenerationError("ACTIVE_DEPENDENCY_CORRUPT") from exc
            if digest != dependency.get("sha256"):
                raise GenerationError("ACTIVE_DEPENDENCY_CORRUPT")
        return PinnedGeneration(current.publication_record_id, current.record_sha256,
                                body["semantic_activation_id"], body["generation_id"],
                                generation_root, manifest, body)
