"""Shared provenance checks for projections derived from chapter commits."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

from .chapter_commit_schema import (
    DisambiguationResult,
    ExtractionResult,
    FulfillmentResult,
    ReviewResult,
)


class DurableCommitError(RuntimeError):
    """Raised when a projection payload has no matching durable chapter commit."""

    def __init__(self, message: str, *, chapter: int | None = None):
        super().__init__(message)
        self.chapter = chapter


_COMMIT_NAME = re.compile(r"^chapter_(\d+)\.commit\.json$")


def _meta(payload: Dict[str, Any], *, label: str) -> Dict[str, Any]:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise DurableCommitError(f"{label} metadata is not an object")
    return meta


def commit_path(project_root: str | Path, chapter: int) -> Path:
    try:
        chapter_number = int(chapter)
    except (TypeError, ValueError) as exc:
        raise DurableCommitError(f"Invalid chapter number for durable commit: {chapter!r}") from exc
    if chapter_number < 1:
        raise DurableCommitError(f"Invalid chapter number for durable commit: {chapter_number}")
    return (
        Path(project_root).expanduser().resolve()
        / ".story-system"
        / "commits"
        / f"chapter_{chapter_number:03d}.commit.json"
    )


def canonical_commit_json(payload: Dict[str, Any]) -> str:
    """Serialize canonical identity, excluding mutable projection run metadata."""
    if not isinstance(payload, dict):
        raise DurableCommitError("Chapter commit payload must be an object")
    canonical = dict(payload)
    canonical.pop("projection_status", None)
    return json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def read_durable_commit(project_root: str | Path, chapter: int) -> Dict[str, Any]:
    path = commit_path(project_root, chapter)
    if not path.is_file():
        raise DurableCommitError(f"Durable chapter commit is missing: {path}")
    return read_validated_chapter_commit(path, expected_chapter=int(chapter))


def read_commit_file(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise DurableCommitError(f"Durable chapter commit is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DurableCommitError(f"Durable chapter commit cannot be read: {exc}") from exc
    if not isinstance(payload, dict):
        raise DurableCommitError(f"Durable chapter commit is not an object: {path}")
    return payload


def read_validated_chapter_commit(
    path: str | Path, *, expected_chapter: int | None = None
) -> Dict[str, Any]:
    """Read and validate the canonical durable Story System v1 chapter record."""
    path = Path(path)
    match = _COMMIT_NAME.fullmatch(path.name)
    if not match:
        raise DurableCommitError(f"unexpected file in canonical commit directory: {path}")
    filename_chapter = int(match.group(1))
    if filename_chapter < 1 or path.name != f"chapter_{filename_chapter:03d}.commit.json":
        raise DurableCommitError(f"non-canonical durable commit filename: {path}")
    if expected_chapter is not None and filename_chapter != int(expected_chapter):
        raise DurableCommitError(
            f"durable commit filename chapter {filename_chapter} does not match expected chapter {expected_chapter}"
        )
    payload = read_commit_file(path)
    meta = _meta(payload, label="Durable chapter commit")
    chapter = meta.get("chapter")
    if isinstance(chapter, bool) or not isinstance(chapter, int) or chapter != filename_chapter:
        raise DurableCommitError(
            f"invalid durable commit {path}: meta.chapter does not match filename chapter {filename_chapter}"
        )
    if meta.get("schema_version") != "story-system/v1":
        raise DurableCommitError(
            f"invalid durable commit {path}: unsupported schema version {meta.get('schema_version')!r}"
        )
    if meta.get("status") not in {"accepted", "rejected"}:
        raise DurableCommitError(
            f"invalid durable commit {path}: unsupported commit status {meta.get('status')!r}"
        )
    binding = payload.get("gate_decision_binding")
    if binding is not None:
        if not isinstance(binding, dict) or set(binding) != {
            "gate_decision_ref", "input_fingerprint", "policy_version", "final_action"
        }:
            raise DurableCommitError(f"invalid durable commit {path}: malformed GateDecision binding")
        ref = binding.get("gate_decision_ref")
        fingerprint = binding.get("input_fingerprint")
        policy_version = binding.get("policy_version")
        final_action = binding.get("final_action")
        if not isinstance(ref, str) or not ref or ref.startswith("/") or ".." in Path(ref).parts:
            raise DurableCommitError(f"invalid durable commit {path}: invalid GateDecision reference")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise DurableCommitError(f"invalid durable commit {path}: invalid GateDecision input fingerprint")
        if not isinstance(policy_version, str) or not policy_version.strip():
            raise DurableCommitError(f"invalid durable commit {path}: invalid GateDecision policy version")
        expected_action = "REJECT" if meta.get("status") == "rejected" else "ALLOW_WITH_ADVISORY"
        if final_action != expected_action:
            raise DurableCommitError(
                f"invalid durable commit {path}: final_action {final_action!r} does not match status {meta.get('status')!r}"
            )
    try:
        ReviewResult.model_validate(payload.get("review_result"))
        FulfillmentResult.model_validate(payload.get("fulfillment_result"))
        DisambiguationResult.model_validate(payload.get("disambiguation_result"))
        ExtractionResult.model_validate(payload.get("extraction_result"))
    except Exception as exc:
        raise DurableCommitError(f"invalid durable commit {path}: {exc}") from exc
    return payload


def discover_validated_chapter_commits(project_root: str | Path) -> list[dict[str, Any]]:
    """Discover the canonical commit set and validate every durable file."""
    directory = Path(project_root).expanduser().resolve() / ".story-system" / "commits"
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise DurableCommitError(f"commit path is not a directory: {directory}")
    result = []
    for path in sorted(item for item in directory.iterdir() if item.is_file()):
        if path.name.endswith(".lock") and _COMMIT_NAME.fullmatch(path.name[:-5]):
            continue
        try:
            payload = read_validated_chapter_commit(path)
        except DurableCommitError as exc:
            if exc.chapter is None and _COMMIT_NAME.fullmatch(path.name):
                exc.chapter = int(_COMMIT_NAME.fullmatch(path.name).group(1))
            raise
        result.append({"chapter": payload["meta"]["chapter"], "path": path, "payload": payload})
    return sorted(result, key=lambda item: item["chapter"])


def require_durable_commit_match(
    project_root: str | Path,
    commit_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Return the disk commit only when it canonically matches the projection input."""
    if not isinstance(commit_payload, dict):
        raise DurableCommitError("Projection payload must be a chapter commit object")
    try:
        chapter = int(_meta(commit_payload, label="Projection payload").get("chapter") or 0)
    except (TypeError, ValueError) as exc:
        raise DurableCommitError("Projection payload has an invalid chapter number") from exc
    if chapter < 1:
        raise DurableCommitError(f"Projection payload has an invalid chapter number: {chapter}")

    durable_payload = read_durable_commit(project_root, chapter)
    incoming_status = str(_meta(commit_payload, label="Projection payload").get("status") or "")
    if incoming_status not in {"accepted", "rejected"}:
        raise DurableCommitError(f"Projection payload has unsupported status: {incoming_status!r}")
    if canonical_commit_json(durable_payload) != canonical_commit_json(commit_payload):
        path = commit_path(project_root, chapter)
        raise DurableCommitError(
            f"Projection payload does not match durable chapter commit: {path}"
        )
    return durable_payload
