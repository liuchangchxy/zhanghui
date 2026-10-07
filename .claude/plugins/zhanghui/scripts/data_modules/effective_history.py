"""Validated active and candidate snapshots over immutable Canon correction artifacts."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

from .canon_correction_resolver import EffectiveHistoryResult, resolve_effective_history
from .canon_correction_schema import (
    CanonCorrectionAuthorization, CanonCorrectionRequest, artifact_sha256,
    base_commit_digest, effective_content_digest,
)
from .canon_correction_store import (
    CorrectionStoreError, VerifiedCorrectionDecision, build_correction_review_package,
    correction_target_dir, verify_phase9_correction_decision,
)
from .durable_projection import (
    DurableCommitError, discover_validated_chapter_commits, read_durable_commit,
)
from .projection_generation import GenerationError, ProjectionGeneration


@dataclass(frozen=True)
class EffectiveHistoryEntry:
    chapter: int
    base_commit: dict[str, Any]
    base_sha256: str
    status: str
    extraction_result: dict[str, Any] | None
    effective_revision_id: str
    effective_content_sha256: str
    applied_correction_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActiveEffectiveHistorySnapshot:
    ok: bool
    chapters: dict[int, EffectiveHistoryEntry]
    activation_record_id: str | None
    base_set_digest: str
    correction_lineage_digest: str
    effective_history_digest: str
    generation_id: str | None
    diagnostics: tuple[str, ...] = ()
    dependencies: tuple[dict[str, str], ...] = ()
    lineage_namespace_checks: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class CandidateEffectiveHistorySnapshot:
    ok: bool
    target_correction_id: str
    chapters: dict[int, EffectiveHistoryEntry]
    candidate_digest: str | None
    diagnostics: tuple[str, ...] = ()
    dependencies: tuple[dict[str, str], ...] = ()
    base_set_digest: str = ""
    correction_lineage_digest: str = ""
    effective_history_digest: str = ""
    lineage_namespace_checks: tuple[dict[str, str], ...] = ()


_PROJECTION_SEAL = object()


@dataclass(frozen=True)
class EffectiveProjectionInput:
    base_commit: dict[str, Any]
    effective_entry: EffectiveHistoryEntry
    snapshot_id: str
    snapshot_digest: str
    _seal: object = field(repr=False, compare=False, default=None)


def _read_json_artifacts(directory: Path, pattern: str) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise CorrectionStoreError("INVALID_ARTIFACT_STORE")
    result = []
    for path in sorted(directory.glob(pattern)):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CorrectionStoreError(f"INVALID_ARTIFACT: {path.name}") from exc
        if not isinstance(value, dict):
            raise CorrectionStoreError(f"INVALID_ARTIFACT: {path.name}")
        result.append(value)
    return result


def _entry(chapter: int, base: dict[str, Any], result: EffectiveHistoryResult | None = None):
    base_digest = base_commit_digest(base)
    if result is None:
        status = "accepted"
        extraction = base["extraction_result"]
        revision = f"base:{base_digest}"
        content_digest = effective_content_digest(status, extraction)
        applied = ()
    else:
        if not result.ok or result.base_commit_sha256 != base_digest:
            raise CorrectionStoreError("EFFECTIVE_HISTORY_INVALID")
        status = result.effective_status
        extraction = result.effective_extraction_result
        revision = result.effective_revision_id
        content_digest = result.effective_content_sha256
        applied = result.applied_correction_ids
    return EffectiveHistoryEntry(chapter, dict(base), base_digest, status, extraction,
                                 revision, content_digest, tuple(applied))


def _snapshot_digests(entries: dict[int, EffectiveHistoryEntry]):
    base_rows = [{"chapter": number, "base_sha256": entry.base_sha256}
                 for number, entry in sorted(entries.items())]
    lineage_rows = [{"chapter": number, "revision": entry.effective_revision_id,
                     "corrections": list(entry.applied_correction_ids)}
                    for number, entry in sorted(entries.items())]
    effective_rows = [{"chapter": number, "base_sha256": entry.base_sha256,
                       "status": entry.status,
                       "content_sha256": entry.effective_content_sha256,
                       "revision": entry.effective_revision_id}
                      for number, entry in sorted(entries.items())]
    return artifact_sha256(base_rows), artifact_sha256(lineage_rows), artifact_sha256(effective_rows)


def _namespace_digest(root: Path, relative: str, kind: str) -> str:
    directory = root / relative
    if not directory.exists():
        paths = []
    elif kind == "base_set":
        paths = sorted(directory.glob("chapter_*.commit.json"))
    else:
        paths = sorted(path for path in directory.rglob("*.json") if path.is_file())
    rows = [{"path": path.relative_to(root).as_posix(),
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in paths]
    return artifact_sha256(rows)


class EffectiveHistoryStore:
    def read_active_snapshot(self, project_root: str | Path, *,
                             allow_unhealthy_generation_for_recovery: bool = False) -> ActiveEffectiveHistorySnapshot:
        root = Path(project_root).expanduser().resolve()
        generation_protocol = ProjectionGeneration(root)
        publication_records_exist = any(generation_protocol.publications_root.glob("publication-*.json"))
        if generation_protocol.enrollment_path.exists() or publication_records_exist:
            try:
                try:
                    pinned = generation_protocol.pin_active_generation()
                except Exception:
                    if not allow_unhealthy_generation_for_recovery:
                        raise
                    from types import SimpleNamespace
                    publication = generation_protocol.latest_publication_for_recovery()
                    pinned = SimpleNamespace(
                        record_body=publication.body,
                        publication_record_id=publication.publication_record_id,
                        generation_id=publication.body["generation_id"],
                    )
                if pinned is None:
                    raise GenerationError("ENROLLED_PUBLICATION_MISSING")
                record = pinned.record_body
                dependencies = tuple(record.get("dependency_closure", ()))
                for dependency in dependencies:
                    relative = Path(dependency.get("path", ""))
                    if relative.is_absolute() or ".." in relative.parts:
                        raise GenerationError("ACTIVE_DEPENDENCY_CLOSURE_INVALID")
                    try:
                        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
                    except OSError as exc:
                        raise GenerationError("ACTIVE_DEPENDENCY_CORRUPT") from exc
                    if actual != dependency.get("sha256"):
                        raise GenerationError("ACTIVE_DEPENDENCY_CORRUPT")
                namespace_checks = [{"path": ".story-system/commits", "sha256": _namespace_digest(
                    root, ".story-system/commits", "base_set"), "kind": "base_set"}]
                correction_namespaces = sorted({
                    (root / dependency["path"]).parent.parent.relative_to(root).as_posix()
                    for dependency in dependencies if dependency.get("kind") == "correction"
                })
                namespace_checks.extend({"path": namespace, "sha256": _namespace_digest(
                    root, namespace, "correction_namespace"), "kind": "correction_namespace"}
                    for namespace in correction_namespaces)
                dependency_bodies: dict[str, list[dict[str, Any]]] = {}
                for dependency in dependencies:
                    if dependency.get("kind") not in {"request", "authorization", "correction"}:
                        continue
                    path = root / dependency["path"]
                    dependency_bodies.setdefault(dependency["kind"], []).append(
                        json.loads(path.read_text(encoding="utf-8")))
                entries: dict[int, EffectiveHistoryEntry] = {}
                bases = {row["chapter"]: read_durable_commit(root, row["chapter"])
                         for row in record.get("chapter_closure", [])}
                for row in record.get("chapter_closure", []):
                    chapter = row["chapter"]
                    base = bases[chapter]
                    if base_commit_digest(base) != row["base_sha256"]:
                        raise GenerationError("ACTIVE_DEPENDENCY_CORRUPT")
                    chapter_corrections = [item for item in dependency_bodies.get("correction", [])
                                           if item.get("chapter") == chapter]
                    if chapter_corrections:
                        correction_ids = list(row.get("applied_correction_ids", []))
                        if set(correction_ids) != {item.get("correction_id") for item in chapter_corrections}:
                            raise GenerationError("ACTIVE_DEPENDENCY_CLOSURE_MISMATCH")
                        requests = [item for item in dependency_bodies.get("request", [])
                                    if item.get("chapter") == chapter]
                        authorizations = [item for item in dependency_bodies.get("authorization", [])
                                          if item.get("request_id") in {req.get("request_id") for req in requests}]
                        verified = []
                        current = _entry(chapter, base)
                        ordered_corrections = []
                        for correction_id in correction_ids:
                            correction = next(item for item in chapter_corrections
                                              if item.get("correction_id") == correction_id)
                            req = next(item for item in requests
                                       if artifact_sha256(item) == correction.get("request_sha256"))
                            auth = next(item for item in authorizations
                                        if item.get("authorization_id") == correction.get("authorization_ref")
                                        and artifact_sha256(item) == correction.get("authorization_sha256"))
                            package = build_correction_review_package(
                                req, parent_status=current.status, parent_extraction=current.extraction_result,
                            )
                            verified.append(verify_phase9_correction_decision(req, auth, package))
                            ordered_corrections.append(correction)
                            partial = resolve_effective_history(base, ordered_corrections, requests,
                                                               authorizations, verified)
                            if not partial.ok:
                                raise GenerationError("ACTIVE_LINEAGE_INVALID")
                            current = _entry(chapter, base, partial)
                        result = resolve_effective_history(base, chapter_corrections, requests,
                                                           authorizations, verified)
                        entry = _entry(chapter, base, result)
                    else:
                        entry = _entry(chapter, base)
                    if (entry.effective_revision_id != row.get("effective_revision_id")
                            or entry.status != row.get("status")
                            or entry.effective_content_sha256 != row.get("effective_content_sha256")
                            or list(entry.applied_correction_ids) != row.get("applied_correction_ids")):
                        raise GenerationError("ACTIVE_HISTORY_DIGEST_MISMATCH")
                    entries[chapter] = entry
                base_digest, lineage_digest, history_digest = _snapshot_digests(entries)
                if (base_digest != record.get("base_set_digest")
                        or history_digest != record.get("effective_history_digest")):
                    raise GenerationError("ACTIVE_HISTORY_DIGEST_MISMATCH")
                artifact_dependencies = [item for item in dependencies
                                         if item.get("kind") in {"correction", "request", "authorization"}]
                exact_lineage_digest = artifact_sha256({
                    "effective_lineage_digest": lineage_digest,
                    "artifacts": artifact_dependencies,
                })
                if exact_lineage_digest != record.get("correction_lineage_digest"):
                    raise GenerationError("ACTIVE_HISTORY_DIGEST_MISMATCH")
                return ActiveEffectiveHistorySnapshot(
                    True, entries, pinned.publication_record_id, base_digest, exact_lineage_digest,
                    history_digest, pinned.generation_id, (), dependencies, tuple(namespace_checks),
                )
            except Exception as exc:
                return ActiveEffectiveHistorySnapshot(False, {}, None, "", "", "", None,
                                                      (f"ACTIVE_HISTORY_INVALID:{exc}",))
        try:
            records = discover_validated_chapter_commits(root)
            entries = {
                row["chapter"]: _entry(row["chapter"], row["payload"])
                for row in records if row["payload"].get("meta", {}).get("status") == "accepted"
            }
            base_digest, lineage_digest, history_digest = _snapshot_digests(entries)
            lineage_digest = artifact_sha256({"effective_lineage_digest": lineage_digest,
                                              "artifacts": []})
            dependencies = tuple(
                {"path": row["path"].relative_to(root).as_posix(),
                 "sha256": hashlib.sha256(row["path"].read_bytes()).hexdigest(),
                 "kind": "base_commit"}
                for row in records if row["payload"].get("meta", {}).get("status") == "accepted"
            )
            namespace_checks = ({"path": ".story-system/commits",
                                 "sha256": _namespace_digest(root, ".story-system/commits", "base_set"),
                                 "kind": "base_set"},)
            return ActiveEffectiveHistorySnapshot(True, entries, None, base_digest,
                                                  lineage_digest, history_digest, None, (), dependencies,
                                                  namespace_checks)
        except Exception as exc:
            return ActiveEffectiveHistorySnapshot(False, {}, None, "", "", "", None,
                                                  (f"ACTIVE_HISTORY_INVALID:{exc}",))

    def resolve_candidate(self, project_root: str | Path,
                          target_correction_id: str) -> CandidateEffectiveHistorySnapshot:
        root = Path(project_root).expanduser().resolve()
        matches = list((root / ".story-system/corrections").glob(
            f"chapter_*/*/corrections/{target_correction_id}.correction.json"
        ))
        if len(matches) != 1:
            return CandidateEffectiveHistorySnapshot(False, target_correction_id, {}, None,
                                                     ("TARGET_CORRECTION_NOT_FOUND_OR_AMBIGUOUS",))
        target = matches[0].parents[1]
        try:
            chapter = int(target.parent.name.removeprefix("chapter_"))
            base_digest = target.name
            base = read_durable_commit(root, chapter)
            if base_commit_digest(base) != base_digest or base["meta"]["status"] != "accepted":
                raise CorrectionStoreError("INVALID_CORRECTION_BASE")
            corrections = _read_json_artifacts(target / "corrections", "*.correction.json")
            requests = _read_json_artifacts(target / "requests", "*.request.json")
            authorizations = _read_json_artifacts(target / "authorizations", "*.authorization.json")
            by_correction = {item.get("correction_id"): item for item in corrections}
            requested = by_correction[target_correction_id]
            chain = []
            cursor = requested
            seen = set()
            while cursor["correction_id"] not in seen:
                seen.add(cursor["correction_id"])
                chain.append(cursor)
                parent_id = cursor.get("parent_revision_id", "")
                if parent_id == f"base:{base_digest}":
                    break
                parent_correction_id = parent_id.rsplit(":", 1)[-1]
                cursor = by_correction.get(parent_correction_id)
                if cursor is None:
                    raise CorrectionStoreError("LINEAGE_PARENT_NOT_FOUND")
            else:
                raise CorrectionStoreError("LINEAGE_CYCLE")
            chain.reverse()
            verified: list[VerifiedCorrectionDecision] = []
            prefix: list[dict[str, Any]] = []
            current = _entry(chapter, base)
            for correction in chain:
                req = next((item for item in requests
                            if artifact_sha256(item) == correction.get("request_sha256")), None)
                auth = next((item for item in authorizations
                             if item.get("authorization_id") == correction.get("authorization_ref")
                             and artifact_sha256(item) == correction.get("authorization_sha256")), None)
                if req is None or auth is None:
                    raise CorrectionStoreError("REQUEST_OR_AUTHORIZATION_NOT_FOUND")
                package = build_correction_review_package(
                    req, parent_status=current.status, parent_extraction=current.extraction_result,
                )
                decision = verify_phase9_correction_decision(req, auth, package)
                verified.append(decision)
                prefix.append(correction)
                partial = resolve_effective_history(base, prefix, requests, authorizations, verified)
                if not partial.ok:
                    code = partial.diagnostics[0].code if partial.diagnostics else "LINEAGE_INVALID"
                    raise CorrectionStoreError(code)
                current = _entry(chapter, base, partial)
            # Validate every staged artifact and conflict in this exact namespace.
            resolved = resolve_effective_history(base, corrections, requests, authorizations, verified)
            if not resolved.ok or target_correction_id not in resolved.applied_correction_ids:
                code = resolved.diagnostics[0].code if resolved.diagnostics else "CANDIDATE_NOT_EFFECTIVE"
                raise CorrectionStoreError(code)
            entry = _entry(chapter, base, resolved)
            candidate_chapters = {
                row["chapter"]: _entry(row["chapter"], row["payload"])
                for row in discover_validated_chapter_commits(root)
                if row["payload"].get("meta", {}).get("status") == "accepted"
            }
            candidate_chapters[chapter] = entry
            _, _, digest = _snapshot_digests(candidate_chapters)
            dependencies = []
            for row in discover_validated_chapter_commits(root):
                if row["payload"].get("meta", {}).get("status") == "accepted":
                    path = row["path"]
                    dependencies.append({"path": path.relative_to(root).as_posix(),
                                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                         "kind": "base_commit"})
            for path in sorted((target / "corrections").glob("*.correction.json")):
                dependencies.append({"path": path.relative_to(root).as_posix(),
                                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                     "kind": "correction"})
            for path in sorted((target / "requests").glob("*.request.json")):
                dependencies.append({"path": path.relative_to(root).as_posix(),
                                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                     "kind": "request"})
            for path in sorted((target / "authorizations").glob("*.authorization.json")):
                dependencies.append({"path": path.relative_to(root).as_posix(),
                                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                     "kind": "authorization"})
            artifact_dependencies = [item for item in dependencies
                                     if item.get("kind") in {"correction", "request", "authorization"}]
            exact_lineage_digest = artifact_sha256({
                "effective_lineage_digest": _snapshot_digests(candidate_chapters)[1],
                "artifacts": artifact_dependencies,
            })
            candidate_base_digest, _, candidate_history_digest = _snapshot_digests(candidate_chapters)
            namespace_checks = (
                {"path": ".story-system/commits", "sha256": _namespace_digest(root, ".story-system/commits", "base_set"), "kind": "base_set"},
                {"path": target.relative_to(root).as_posix(), "sha256": _namespace_digest(root, target.relative_to(root).as_posix(), "correction_namespace"), "kind": "correction_namespace"},
            )
            return CandidateEffectiveHistorySnapshot(True, target_correction_id,
                                                    candidate_chapters, digest, (),
                                                    tuple(dependencies), candidate_base_digest,
                                                    exact_lineage_digest, candidate_history_digest,
                                                    namespace_checks)
        except Exception as exc:
            return CandidateEffectiveHistorySnapshot(False, target_correction_id, {}, None,
                                                     (str(exc) or type(exc).__name__,))

    def projection_input(self, snapshot: ActiveEffectiveHistorySnapshot,
                         chapter: int) -> EffectiveProjectionInput:
        if not snapshot.ok or chapter not in snapshot.chapters:
            raise CorrectionStoreError("ACTIVE_SNAPSHOT_UNAVAILABLE")
        entry = snapshot.chapters[chapter]
        return EffectiveProjectionInput(entry.base_commit, entry, snapshot.effective_history_digest,
                                        snapshot.effective_history_digest, _PROJECTION_SEAL)

    def candidate_projection_input(self, snapshot: CandidateEffectiveHistorySnapshot,
                                   chapter: int) -> EffectiveProjectionInput:
        if not snapshot.ok or chapter not in snapshot.chapters or not snapshot.effective_history_digest:
            raise CorrectionStoreError("CANDIDATE_SNAPSHOT_UNAVAILABLE")
        entry = snapshot.chapters[chapter]
        return EffectiveProjectionInput(entry.base_commit, entry, snapshot.effective_history_digest,
                                        snapshot.effective_history_digest, _PROJECTION_SEAL)


def validate_effective_projection_input(project_root: str | Path,
                                        value: EffectiveProjectionInput) -> EffectiveProjectionInput:
    if not isinstance(value, EffectiveProjectionInput) or value._seal is not _PROJECTION_SEAL:
        raise TypeError("EffectiveProjectionInput must come from EffectiveHistoryStore")
    entry = value.effective_entry
    try:
        disk_base = read_durable_commit(project_root, entry.chapter)
        disk_digest = base_commit_digest(disk_base)
    except Exception as exc:
        raise DurableCommitError("BASE_COMMIT_MISMATCH") from exc
    try:
        supplied_digest = base_commit_digest(value.base_commit)
    except Exception as exc:
        raise DurableCommitError("BASE_COMMIT_MISMATCH") from exc
    if disk_digest != entry.base_sha256 or supplied_digest != entry.base_sha256 or supplied_digest != disk_digest:
        raise DurableCommitError("BASE_COMMIT_MISMATCH")
    if effective_content_digest(entry.status, entry.extraction_result) != entry.effective_content_sha256:
        raise DurableCommitError("EFFECTIVE_CONTENT_MISMATCH")
    if value.snapshot_digest != value.snapshot_id or not value.snapshot_id:
        raise DurableCommitError("EFFECTIVE_SNAPSHOT_BINDING_MISMATCH")
    return value


def write_effective_projection(project_root: str | Path, value: EffectiveProjectionInput,
                               build_handle: Any, domain: str, writer: str,
                               projection: dict[str, Any]) -> dict[str, Any]:
    """Write a typed effective slice into one isolated Canon generation."""
    validate_effective_projection_input(project_root, value)
    snapshot = build_handle.snapshot
    if (value.snapshot_id != snapshot.effective_history_digest
            or value.snapshot_digest != snapshot.effective_history_digest
            or value.effective_entry.chapter not in snapshot.chapters
            or snapshot.chapters[value.effective_entry.chapter] != value.effective_entry):
        raise DurableCommitError("EFFECTIVE_GENERATION_BINDING_MISMATCH")
    entry = value.effective_entry
    document = {
        "schema_version": "story-system-effective-projection/v1",
        "chapter": entry.chapter,
        "writer": writer,
        "base_sha256": entry.base_sha256,
        "effective_revision_id": entry.effective_revision_id,
        "effective_content_sha256": entry.effective_content_sha256,
        "effective_status": entry.status,
        "effective_history_digest": value.snapshot_digest,
        "projection": projection,
    }
    path = f"{domain}/chapter_{entry.chapter:03d}.json"
    from .canon_correction_schema import canonical_json
    digest = build_handle.write_domain_file(domain, path,
                                            (canonical_json(document) + "\n").encode("utf-8"))
    return {"applied": True, "writer": writer, "base_sha256": entry.base_sha256,
            "effective_revision_id": entry.effective_revision_id,
            "effective_content_sha256": entry.effective_content_sha256,
            "generation_id": build_handle.generation_id, "output_sha256": digest}
