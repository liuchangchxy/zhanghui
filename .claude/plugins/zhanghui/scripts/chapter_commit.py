#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio

from data_modules.chapter_commit_service import ChapterCommitService
from data_modules.gate_finding_adapters import adapt_changes_gate_result, adapt_legacy_artifacts
from data_modules.story_runtime_sources import load_runtime_sources


def _read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Chapter commit CLI")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--review-result", required=True)
    parser.add_argument("--fulfillment-result", required=True)
    parser.add_argument("--disambiguation-result", required=True)
    parser.add_argument("--extraction-result", required=True)
    parser.add_argument("--reconciliation-result", required=True)
    parser.add_argument("--chapter-file", required=True, help="Final chapter file bound to reconciliation")
    parser.add_argument("--resolve-attempt", default=None, help="Prior pending GateDecision attempt ID")
    parser.add_argument("--resolve-finding", default=None, help="Finding ID resolved by the human response")
    parser.add_argument("--human-choice", default=None, help="Structured human choice recorded in workflow audit")
    parser.add_argument("--human-actor-ref", default=None, help="Accountable actor reference")
    parser.add_argument("--response-id", default=None, help="Unique ID for the new reevaluation attempt")
    parser.add_argument(
        "--on-conflict",
        choices=["overwrite", "skip"],
        default=None,
        help="已有 canonical chapter commit 时拒绝 overwrite；skip 只从磁盘上的既有 commit 重试投影。"
        "append/ask 不支持 (chapter commit 是不可变的 point-in-time snapshot)。",
    )
    args = parser.parse_args()

    # The durable chapter transaction is stored before any projection writer runs.
    service = ChapterCommitService(Path(args.project_root))
    from data_modules.reconciliation import split_chapter_and_changes
    reconciliation_result = _read_json(args.reconciliation_result)
    chapter_text = Path(args.chapter_file).read_text(encoding="utf-8")
    gate = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("changes_gate.py")),
         "--chapter-file", args.chapter_file, "--db", str(Path(args.project_root) / ".webnovel" / "index.db"), "--json"],
        capture_output=True, text=True, check=False,
    )
    try:
        gate_result = json.loads(gate.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"changes_gate did not return valid JSON: {exc}") from exc
    _, proposed_changes = split_chapter_and_changes(chapter_text)
    review_result = _read_json(args.review_result)
    fulfillment_result = _read_json(args.fulfillment_result)
    disambiguation_result = _read_json(args.disambiguation_result)
    extraction_result = _read_json(args.extraction_result)
    findings = adapt_legacy_artifacts(
        chapter=args.chapter, review=review_result, fulfillment=fulfillment_result,
        disambiguation=disambiguation_result,
        contract_payloads=load_runtime_sources(Path(args.project_root), args.chapter).contracts,
    )
    findings.extend(adapt_changes_gate_result(gate_result, chapter=args.chapter))
    attempt_kwargs = {
        "policy_version": "phase6a-v1", "scope": {"chapter": args.chapter},
        "review_result": review_result, "fulfillment_result": fulfillment_result,
        "disambiguation_result": disambiguation_result, "extraction_result": extraction_result,
        "chapter_text": chapter_text, "proposed_changes": proposed_changes,
        "reconciliation_result": reconciliation_result, "on_conflict": args.on_conflict,
    }
    response_values = (args.resolve_attempt, args.resolve_finding, args.human_choice, args.human_actor_ref)
    if any(response_values):
        if not all(response_values):
            raise ValueError("human resolution requires --resolve-attempt, --resolve-finding, --human-choice, and --human-actor-ref")
        attempt = service.evaluate_after_human_response(
            args.chapter, findings, prior_attempt_id=args.resolve_attempt,
            response_id=args.response_id or f"cli-{uuid.uuid4().hex}",
            finding_id=args.resolve_finding, choice=args.human_choice,
            actor_ref=args.human_actor_ref, **attempt_kwargs,
        )
    else:
        attempt = service.evaluate_attempt(
            chapter=args.chapter, findings=findings,
            attempt_id=f"cli-{uuid.uuid4().hex}", **attempt_kwargs,
        )
    if attempt.chapter_outcome is None:
        print(json.dumps({
            "workflow_status": attempt.attempt_status,
            "action": attempt.action.value,
            "attempt_id": attempt.attempt_id,
            "gate_decision_ref": attempt.gate_decision_ref,
        }, ensure_ascii=False))
    else:
        print(json.dumps(attempt.chapter_outcome.commit_payload, ensure_ascii=False))


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
