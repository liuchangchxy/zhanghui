"""Validated active and candidate snapshots over immutable Canon correction artifacts."""
from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class CandidateEffectiveHistorySnapshot:
    ok: bool
    target_correction_id: str
    chapters: dict[int, EffectiveHistoryEntry]
    candidate_digest: str | None
    diagnostics: tuple[str, ...] = ()


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


class EffectiveHistoryStore:
    def read_active_snapshot(self, project_root: str | Path) -> ActiveEffectiveHistorySnapshot:
        root = Path(project_root).expanduser().resolve()
        publication_root = root / ".story-system" / "publications"
        if publication_root.exists() and any(publication_root.iterdir()):
            return ActiveEffectiveHistorySnapshot(False, {}, None, "", "", "", None,
                                                  ("ACTIVATION_PROTOCOL_UNAVAILABLE",))
        try:
            records = discover_validated_chapter_commits(root)
            entries = {
                row["chapter"]: _entry(row["chapter"], row["payload"])
                for row in records if row["payload"].get("meta", {}).get("status") == "accepted"
            }
            base_digest, lineage_digest, history_digest = _snapshot_digests(entries)
            return ActiveEffectiveHistorySnapshot(True, entries, None, base_digest,
                                                  lineage_digest, history_digest, None)
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
            return CandidateEffectiveHistorySnapshot(True, target_correction_id,
                                                    candidate_chapters, digest)
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
    if (disk_digest != entry.base_sha256
            or base_commit_digest(value.base_commit) != entry.base_sha256
            or base_commit_digest(value.base_commit) != disk_digest):
        raise DurableCommitError("BASE_COMMIT_MISMATCH")
    if effective_content_digest(entry.status, entry.extraction_result) != entry.effective_content_sha256:
        raise DurableCommitError("EFFECTIVE_CONTENT_MISMATCH")
    if value.snapshot_digest != value.snapshot_id or not value.snapshot_id:
        raise DurableCommitError("EFFECTIVE_SNAPSHOT_BINDING_MISMATCH")
    return value
