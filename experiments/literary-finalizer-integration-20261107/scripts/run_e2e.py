#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Short real E2E for the formal literary-subtraction finalizer (Step 2B).

For each of three real Zhanghui Writer chapters:
  1. build the production prompt through the new CLI (governed context + next outline);
  2. one editor call, mechanical retry only for truncation/empty;
  3. clean mechanically, then run the same host-judge round-trip the skill uses;
  4. run `prose literary-finalize-validate` and record accept/reject + reasons.

Rejected chapters fall back to the Writer raw. No prompt tuning, no second generation.
"""
from __future__ import annotations

import hashlib
import json
import re
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
EDITOR_MODEL = "group/mac-deepseek4.1-gpt[1m]"
JUDGE_MODEL = "codex/gpt-6.1-terra"
MIN_RATIO = 0.90


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-X", "utf8", str(SCRIPTS / "webnovel.py"), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean(raw: str, source: str) -> tuple[str, dict]:
    sys.path.insert(0, str(SCRIPTS))
    from data_modules.literary_finalizer import clean_finalizer_output

    return clean_finalizer_output(raw, source)


def _gate(source: str, candidate: str, raw: str, chapter: int, key: str) -> tuple[dict, int]:
    gate_file = ROOT / "outputs" / f"{key}_gate.json"
    proc = _run_cli(
        "--project-root", str(BENCH_PROJECT),
        "prose", "literary-finalize-validate",
        "--before-file", str(ROOT / "outputs" / f"{key}_source.md"),
        "--raw-draft-file", str(ROOT / "inputs" / f"{key}_raw.md"),
        "--after-file", str(ROOT / "outputs" / f"{key}_candidate.md"),
        "--chapter", str(chapter),
        "--judge-file", str(ROOT / "judge" / f"{key}_verdict.json"),
        "--output", str(gate_file),
        "--format", "json",
    )
    payload = json.loads(gate_file.read_text(encoding="utf-8")) if gate_file.exists() else {}
    if proc.returncode not in (0, 1):
        payload["cli_error"] = proc.stderr[-2000:]
    return payload, proc.returncode


def main() -> None:
    records: dict[str, dict] = {}
    for chapter, key in CHAPTERS.items():
        raw_path = ROOT / "inputs" / f"{key}_raw.md"
        prompt_path = ROOT / "outputs" / f"{key}_prompt.txt"
        source_path = ROOT / "outputs" / f"{key}_source.md"
        meta_path = ROOT / "outputs" / f"{key}_meta.json"

        proc = _run_cli(
            "--project-root", str(BENCH_PROJECT),
            "prose", "literary-finalize-prompt",
            "--chapter", str(chapter),
            "--draft-file", str(raw_path),
            "--output", str(prompt_path),
            "--source-output", str(source_path),
            "--meta-output", str(meta_path),
            "--format", "json",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"{key}: prompt CLI failed: {proc.stderr[-2000:]}")

        prompt = prompt_path.read_text(encoding="utf-8")
        source = source_path.read_text(encoding="utf-8")

        attempts = []
        cleaned = None
        for attempt in range(2):
            raw, call_meta = run_proxy(
                prompt,
                ROOT / "outputs" / f"{key}_editor_run",
                f"finalizer-{key}",
                model=EDITOR_MODEL,
                temperature=0.4,
                max_tokens=16000,
                retries=0,
            )
            candidate, notes = _clean(raw, source)
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "stop_reason": call_meta.get("stop_reason"),
                    "usage": call_meta.get("usage"),
                    "raw_sha256": _sha(raw),
                    "cleaned_chars": len(re.sub(r"\s", "", candidate)),
                }
            )
            truncated = call_meta.get("stop_reason") == "max_tokens"
            if truncated or len(re.sub(r"\s", "", candidate)) < 500:
                print(key, f"mechanical retry attempt {attempt + 1}", file=sys.stderr)
                continue
            cleaned = (raw, candidate, notes, call_meta)
            break
        if cleaned is None:
            records[key] = {"chapter": chapter, "status": "EDITOR_CALL_FAILED", "attempts": attempts}
            continue

        raw_response, candidate_text, clean_notes, editor_meta = cleaned
        (ROOT / "outputs" / f"{key}_editor_response.raw.txt").write_text(
            raw_response, encoding="utf-8"
        )
        (ROOT / "outputs" / f"{key}_candidate.md").write_text(candidate_text, encoding="utf-8")

        # Host-judge round-trip: request -> model answer -> bound verdict.
        request_file = ROOT / "judge" / f"{key}_request.json"
        judge_prompt_file = ROOT / "judge" / f"{key}_prompt.txt"
        proc = _run_cli(
            "--project-root", str(BENCH_PROJECT),
            "prose", "judge-request",
            "--before-file", str(source_path),
            "--after-file", str(ROOT / "outputs" / f"{key}_candidate.md"),
            "--chapter", str(chapter),
            "--output", str(request_file),
            "--prompt-output", str(judge_prompt_file),
            "--format", "json",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"{key}: judge-request failed: {proc.stderr[-2000:]}")
        request = json.loads(request_file.read_text(encoding="utf-8"))
        judge_raw, judge_meta = run_proxy(
            request["prompt"],
            ROOT / "judge" / f"{key}_judge_run",
            f"finalizer-judge-{key}",
            model=JUDGE_MODEL,
            temperature=0.2,
            max_tokens=8000,
            retries=0,
        )
        answer = parse_json(judge_raw)
        answer.setdefault("request_id", request["request_id"])
        answer.setdefault("before_sha256", request["before_sha256"])
        answer.setdefault("after_sha256", request["after_sha256"])
        response_file = ROOT / "judge" / f"{key}_response.json"
        response_file.write_text(json.dumps(answer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (ROOT / "judge" / f"{key}_judge_response.raw.txt").write_text(judge_raw, encoding="utf-8")

        verdict_file = ROOT / "judge" / f"{key}_verdict.json"
        proc = _run_cli(
            "--project-root", str(BENCH_PROJECT),
            "prose", "judge-bind",
            "--before-file", str(source_path),
            "--after-file", str(ROOT / "outputs" / f"{key}_candidate.md"),
            "--response-file", str(response_file),
            "--request-file", str(request_file),
            "--chapter", str(chapter),
            "--output", str(verdict_file),
            "--format", "json",
        )
        judge_binding = "ok" if proc.returncode == 0 else f"failed:{proc.stderr[-500:]}"

        gate, gate_code = _gate(source, candidate_text, raw_path.read_text(encoding="utf-8"), chapter, key)

        if gate.get("accepted") is True:
            final_text = candidate_text
            status = "ACCEPTED"
        else:
            final_text = raw_path.read_text(encoding="utf-8")
            status = "FALLBACK_RAW"
        (ROOT / "outputs" / f"{key}_final.md").write_text(final_text, encoding="utf-8")

        records[key] = {
            "chapter": chapter,
            "status": status,
            "gate_exit_code": gate_code,
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
            "judge_binding": judge_binding,
            "judge_outcome": answer.get("outcome"),
            "judge_changes": answer.get("changes", []),
            "editor_model": EDITOR_MODEL,
            "judge_model": JUDGE_MODEL,
            "editor_attempts": attempts,
            "editor_stop_reason": editor_meta.get("stop_reason"),
            "clean_notes": clean_notes,
            "source_sha256": _sha(source),
            "candidate_sha256": _sha(candidate_text),
            "prompt_sha256": _sha(prompt),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        print(key, status, gate.get("length_ratio"), gate.get("reasons"), flush=True)

    (ROOT / "results" / "run_records.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
