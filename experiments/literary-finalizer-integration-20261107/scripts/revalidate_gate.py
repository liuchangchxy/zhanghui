#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-run only the acceptance gate on the PR #68 candidates.

The prose candidates are reused byte-for-byte; no chapter is generated again.
What changes is the judge rubric (finalizer-only `--state-impact`) and the
acceptance rule (only story-state changes block). Evidence goes to
`results/run_records_v2.json` and `outputs/{key}_gate_v2.json`.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SCRIPTS = REPO / ".claude" / "plugins" / "zhanghui" / "scripts"
sys.path.insert(0, str(ROOT / "scripts"))
from llm_channels import parse_json, run_proxy  # noqa: E402

BENCH_PROJECT = Path(
    "/Users/chang/Desktop/Code/zhanghui-benchmark/runs/"
    "clean-e2e-jarvis-vs-zhanghui-2026-10-29/e2e/zhanghui/project"
)
CHAPTERS = {3: "ch03", 5: "ch05", 7: "ch07"}
JUDGE_MODEL = "codex/gpt-6.1-terra"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-X", "utf8", str(SCRIPTS / "webnovel.py"), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    records: dict[str, dict] = {}
    for chapter, key in CHAPTERS.items():
        source = ROOT / "outputs" / f"{key}_source.md"
        candidate = ROOT / "outputs" / f"{key}_candidate.md"
        raw = ROOT / "inputs" / f"{key}_raw.md"
        request_file = ROOT / "judge" / f"{key}_request_v2.json"
        prompt_file = ROOT / "judge" / f"{key}_prompt_v2.txt"
        context_file = ROOT / "judge" / f"{key}_context_v2.json"

        proc = _run_cli(
            "--project-root", str(BENCH_PROJECT),
            "prose", "literary-finalize-prompt",
            "--chapter", str(chapter),
            "--draft-file", str(raw),
            "--output", str(ROOT / "judge" / f"{key}_editor_prompt_v2.txt"),
            "--source-output", str(source),
            "--context-output", str(context_file),
            "--format", "json",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"{key}: prompt CLI failed: {proc.stderr[-2000:]}")

        proc = _run_cli(
            "--project-root", str(BENCH_PROJECT),
            "prose", "judge-request",
            "--before-file", str(source),
            "--after-file", str(candidate),
            "--chapter", str(chapter),
            "--constraints-file", str(context_file),
            "--state-impact",
            "--output", str(request_file),
            "--prompt-output", str(prompt_file),
            "--format", "json",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"{key}: judge-request failed: {proc.stderr[-2000:]}")

        request = json.loads(request_file.read_text(encoding="utf-8"))
        judge_raw, judge_meta = run_proxy(
            request["prompt"],
            ROOT / "judge" / f"{key}_judge_v2_run",
            f"finalizer-judge-v2-{key}",
            model=JUDGE_MODEL,
            temperature=0.2,
            max_tokens=8000,
            retries=0,
        )
        answer = parse_json(judge_raw)
        answer.setdefault("request_id", request["request_id"])
        answer.setdefault("before_sha256", request["before_sha256"])
        answer.setdefault("after_sha256", request["after_sha256"])
        response_file = ROOT / "judge" / f"{key}_response_v2.json"
        response_file.write_text(
            json.dumps(answer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (ROOT / "judge" / f"{key}_judge_response_v2.raw.txt").write_text(
            judge_raw, encoding="utf-8"
        )

        verdict_file = ROOT / "judge" / f"{key}_verdict_v2.json"
        proc = _run_cli(
            "--project-root", str(BENCH_PROJECT),
            "prose", "judge-bind",
            "--before-file", str(source),
            "--after-file", str(candidate),
            "--response-file", str(response_file),
            "--request-file", str(request_file),
            "--chapter", str(chapter),
            "--output", str(verdict_file),
            "--format", "json",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"{key}: judge-bind failed: {proc.stderr[-2000:]}")

        gate_file = ROOT / "outputs" / f"{key}_gate_v2.json"
        proc = _run_cli(
            "--project-root", str(BENCH_PROJECT),
            "prose", "literary-finalize-validate",
            "--before-file", str(source),
            "--raw-draft-file", str(raw),
            "--after-file", str(candidate),
            "--chapter", str(chapter),
            "--judge-file", str(verdict_file),
            "--output", str(gate_file),
            "--format", "json",
        )
        gate = json.loads(gate_file.read_text(encoding="utf-8")) if gate_file.exists() else {}
        if proc.returncode not in (0, 1):
            gate["cli_error"] = proc.stderr[-2000:]

        raw_text = raw.read_text(encoding="utf-8")
        if gate.get("accepted") is True:
            final_text = candidate.read_text(encoding="utf-8")
            status = "ACCEPTED"
        else:
            final_text = raw_text
            status = "FALLBACK_RAW"
        (ROOT / "outputs" / f"{key}_final_v2.md").write_text(final_text, encoding="utf-8")

        records[key] = {
            "chapter": chapter,
            "status": status,
            "gate_exit_code": proc.returncode,
            "accepted": gate.get("accepted"),
            "reasons": gate.get("reasons", []),
            "length_ratio": gate.get("length_ratio"),
            "before_body_chars": gate.get("before_body_chars"),
            "after_body_chars": gate.get("after_body_chars"),
            "missing_numbers": gate.get("missing_numbers", []),
            "added_numbers": gate.get("added_numbers", []),
            "missing_dates": gate.get("missing_dates", []),
            "added_dates": gate.get("added_dates", []),
            "missing_codes": gate.get("missing_codes", []),
            "added_codes": gate.get("added_codes", []),
            "semantic_outcome": gate.get("semantic_outcome"),
            "gate_status": gate.get("gate_status"),
            "gate_details": gate.get("gate_details", {}),
            "judge_outcome": answer.get("outcome"),
            "judge_changes": answer.get("changes", []),
            "judge_model": JUDGE_MODEL,
            "judge_stop_reason": judge_meta.get("stop_reason"),
            "source_sha256": _sha(source.read_text(encoding="utf-8")),
            "candidate_sha256": _sha(candidate.read_text(encoding="utf-8")),
            "request_id": request["request_id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        print(
            key,
            status,
            gate.get("length_ratio"),
            "discourse_only=" + str(gate.get("gate_details", {}).get("discourse_only")),
            "blocking=" + str(len(gate.get("gate_details", {}).get("blocking_changes", []))),
            flush=True,
        )

    (ROOT / "results" / "run_records_v2.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
