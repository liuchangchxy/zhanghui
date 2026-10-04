"""Shared provenance checks for projections derived from chapter commits."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class DurableCommitError(RuntimeError):
    """Raised when a projection payload has no matching durable chapter commit."""


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
    payload = read_commit_file(path)
    status = str(_meta(payload, label="Durable chapter commit").get("status") or "")
    if status not in {"accepted", "rejected"}:
        raise DurableCommitError(f"Durable chapter commit has unsupported status: {status!r}")
    return payload


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
