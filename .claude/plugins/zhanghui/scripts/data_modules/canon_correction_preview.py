"""Read-only staged inspection API for one immutable chapter/base namespace."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from .canon_correction_resolver import (
    CorrectionDiagnostic, EffectiveHistoryResult, resolve_effective_history,
)
from .canon_correction_schema import base_commit_digest
from .canon_correction_store import VerifiedCorrectionDecision, correction_target_dir
from .durable_projection import read_durable_commit


def _failed(chapter: int, base_digest: str | None, code: str, detail: str = "") -> EffectiveHistoryResult:
    return EffectiveHistoryResult(False, chapter, base_digest, None, None, None, (), None,
                                 (CorrectionDiagnostic(code, detail=detail),))


def _read_artifacts(directory: Path) -> tuple[list[dict], str | None]:
    artifacts = []
    if not directory.exists():
        return artifacts, None
    if not directory.is_dir():
        return artifacts, f"artifact path is not a directory: {directory}"
    for path in sorted(directory.glob("*.json")):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return artifacts, f"cannot read {path.name}: {exc}"
        artifacts.append(payload)
    return artifacts, None


def preview_chapter_corrections(
    project_root: str | Path,
    chapter: int,
    base_commit_sha256: str,
    decision_verifications: Sequence[VerifiedCorrectionDecision] = (),
) -> EffectiveHistoryResult:
    """Resolve the exact accepted base and its staged artifacts without writing."""
    try:
        root = Path(project_root).expanduser().resolve()
        base = read_durable_commit(root, chapter)
        actual_digest = base_commit_digest(base)
    except Exception as exc:
        return _failed(chapter, None, "INVALID_BASE", str(exc))
    if actual_digest != base_commit_sha256:
        return _failed(chapter, actual_digest, "CROSS_BASE_REFERENCE")
    try:
        target = correction_target_dir(root, chapter, base_commit_sha256)
    except Exception as exc:
        return _failed(chapter, actual_digest, "INVALID_TARGET", str(exc))
    requests, error = _read_artifacts(target / "requests")
    if error:
        return _failed(chapter, actual_digest, "INVALID_REQUEST_STORE", error)
    authorizations, error = _read_artifacts(target / "authorizations")
    if error:
        return _failed(chapter, actual_digest, "INVALID_AUTHORIZATION_STORE", error)
    corrections, error = _read_artifacts(target / "corrections")
    if error:
        return _failed(chapter, actual_digest, "INVALID_CORRECTION_STORE", error)
    return resolve_effective_history(base, corrections, requests, authorizations, decision_verifications)
