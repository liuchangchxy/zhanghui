"""Normal user-mediated review and persistence flow for Phase 9 corrections."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from .canon_correction_schema import CanonCorrectionRequest, artifact_sha256
from .canon_correction_store import (
    CorrectionStoreError,
    activate_correction,
    build_correction_review_package,
    record_interactive_correction_decision,
)


def _load_request(root: Path, request_id: str) -> tuple[CanonCorrectionRequest, Path]:
    paths = list((root / ".story-system/corrections").glob(
        f"chapter_*/*/requests/{request_id}.request.json"
    ))
    if len(paths) != 1:
        raise CorrectionStoreError("REQUEST_NOT_FOUND_OR_AMBIGUOUS")
    try:
        body = json.loads(paths[0].read_text(encoding="utf-8"))
        request = CanonCorrectionRequest.model_validate(body)
    except Exception as exc:
        raise CorrectionStoreError("INVALID_PERSISTED_REQUEST") from exc
    if request.request_id != request_id or artifact_sha256(request) != artifact_sha256(body):
        raise CorrectionStoreError("REQUEST_DIGEST_MISMATCH")
    return request, paths[0]


def prepare_review(root: str | Path, request_id: str, parent_state: dict) -> dict:
    request, _ = _load_request(Path(root).expanduser().resolve(), request_id)
    if set(parent_state) != {"status", "extraction_result"}:
        raise CorrectionStoreError("INVALID_PARENT_STATE")
    return build_correction_review_package(
        request,
        parent_status=parent_state["status"],
        parent_extraction=parent_state["extraction_result"],
    )


def record_decision(
    root: str | Path,
    request_id: str,
    review_package: dict,
    choice: str | None,
):
    project_root = Path(root).expanduser().resolve()
    request, _ = _load_request(project_root, request_id)
    return record_interactive_correction_decision(
        project_root,
        request,
        review_package,
        choice=choice,
        authorization_id=f"phase9-{secrets.token_hex(12)}",
        interaction_id=f"phase9-{secrets.token_hex(16)}",
        interaction_surface="host interactive user input",
        confirmed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 9 interactive correction confirmation")
    parser.add_argument("--project-root", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("review-package")
    prepare.add_argument("--request-id", required=True)
    prepare.add_argument("--parent-state-file", required=True)
    decide = sub.add_parser("record-decision")
    decide.add_argument("--request-id", required=True)
    decide.add_argument("--review-package-file", required=True)
    decide.add_argument("--choice", choices=["APPROVE", "REJECT"], required=True)
    activate = sub.add_parser("activate")
    activate.add_argument("--correction-id", required=True)
    activate.add_argument("--authorization-file", required=True)
    args = parser.parse_args(argv)
    root = Path(args.project_root).expanduser().resolve()
    try:
        if args.action == "review-package":
            state = json.loads(Path(args.parent_state_file).read_text(encoding="utf-8"))
            result = prepare_review(root, args.request_id, state)
        elif args.action == "record-decision":
            package = json.loads(Path(args.review_package_file).read_text(encoding="utf-8"))
            result = record_decision(root, args.request_id, package, args.choice).model_dump(mode="json")
        else:
            authorization = json.loads(Path(args.authorization_file).read_text(encoding="utf-8"))
            result = asdict(activate_correction(root, args.correction_id, authorization))
    except (OSError, json.JSONDecodeError, CorrectionStoreError) as exc:
        parser.exit(2, f"correction confirmation failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
