#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the frozen held-out literary editor, once per chapter.

One prompt, one model, one temperature. Retries only for mechanical failures
(empty output, truncation), never to improve the result and never after a
length-guard rejection.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (CHAPTERS, constraints_path, input_path,  # noqa: E402
                    next_opening_path, outline_path, output_path,
                    prompt_path, rejected_path)
from llm_channels import run_proxy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "prompts/editor_zh_heldout.md").read_text(encoding="utf-8")
MODEL = "group/mac-deepseek4.1-gpt[1m]"
TEMPERATURE = 0.4
MAX_TOKENS = 16000
MIN_RATIO = 0.90


def build_prompt(ch: int) -> str:
    return (TEMPLATE
            .replace("{outline}", outline_path(ch).read_text(encoding="utf-8").strip())
            .replace("{constraints}", constraints_path(ch).read_text(encoding="utf-8").strip())
            .replace("{next_opening}", next_opening_path(ch).read_text(encoding="utf-8").strip())
            .replace("{source}", input_path(ch).read_text(encoding="utf-8")))


def _heading_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def body_prose(text: str) -> str:
    """Whitespace-free prose body, excluding a leading chapter-heading line."""
    lines = text.replace("\r\n", "\n").splitlines()
    if lines and re.match(r"^#{0,4}\s*第\s*[0-9零一二三四五六七八九十百千两]+章", lines[0].strip()):
        lines = lines[1:]
    return re.sub(r"\s", "", "\n".join(lines))


def clean_output(raw: str, source: str) -> tuple[str, dict]:
    text = raw.replace("\r\n", "\n").strip()
    text = re.sub(r"^```(?:markdown|md)?\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    lines = text.splitlines()
    while lines and re.match(r"^(以下是|修订稿|【修订|---+\s*$|好的[，,])", lines[0].strip()):
        lines.pop(0)
    text = "\n".join(lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    notes = {"heading_prepended": False, "dedup_removed_chars": 0}
    heading = _heading_line(source)
    if not text.startswith(heading):
        text = heading + "\n\n" + text
        notes["heading_prepended"] = True

    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(parts) >= 3 and parts[1] == parts[2] and len(parts[1]) > 20:
        notes["dedup_removed_chars"] = len(parts[2])
        parts.pop(2)
    text = "\n\n".join(parts).strip() + "\n"
    return text, notes


def main() -> None:
    chapters = [int(x) for x in sys.argv[1:]] or sorted(CHAPTERS)
    records_path = ROOT / "outputs/RUN_RECORDS.json"
    records = json.loads(records_path.read_text(encoding="utf-8")) if records_path.exists() else {}

    for ch in chapters:
        meta = CHAPTERS[ch]
        source = input_path(ch).read_text(encoding="utf-8")
        prompt = build_prompt(ch)
        prompt_path(ch).parent.mkdir(parents=True, exist_ok=True)
        prompt_path(ch).write_text(prompt, encoding="utf-8")
        out_dir = ROOT / f"outputs/{meta['key']}_run"

        attempts = []
        cleaned = None
        final_note = None
        status = "EDITOR_CALL_FAILED"
        for attempt in range(2):
            raw, call_meta = run_proxy(
                prompt, out_dir, f"heldout-editor-{meta['key']}",
                model=MODEL, temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
                retries=0,
            )
            attempts.append({
                "attempt": attempt + 1,
                "stop_reason": call_meta.get("stop_reason"),
                "usage": call_meta.get("usage"),
                "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "elapsed_ms": call_meta.get("elapsed_ms"),
            })
            candidate, notes = clean_output(raw, source)
            src_chars, out_chars = len(body_prose(source)), len(body_prose(candidate))
            ratio = out_chars / max(1, src_chars)
            truncated = call_meta.get("stop_reason") == "max_tokens"
            empty = out_chars < 500
            if truncated or empty:
                print(meta["key"], f"attempt{attempt + 1} mechanical retry:",
                      f"truncated={truncated} empty={empty} ratio={ratio:.3f}", file=sys.stderr)
                continue
            cleaned, final_note = candidate, notes
            status = "EDITOR_REJECT_LENGTH" if ratio < MIN_RATIO else "ACCEPTED"
            break

        record = {
            "chapter": ch,
            "key": meta["key"],
            "title": meta["title"],
            "model": MODEL,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "attempts": attempts,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if cleaned is not None:
            src_chars, out_chars = len(body_prose(source)), len(body_prose(cleaned))
            ratio = out_chars / max(1, src_chars)
            record.update({
                "source_body_chars": src_chars,
                "output_body_chars": out_chars,
                "length_ratio": round(ratio, 4),
                "output_sha256": hashlib.sha256(cleaned.encode()).hexdigest(),
                "cleanup_notes": final_note,
            })
            if status == "ACCEPTED":
                output_path(ch).write_text(cleaned, encoding="utf-8")
                if rejected_path(ch).exists():
                    rejected_path(ch).unlink()
            else:
                rejected_path(ch).parent.mkdir(parents=True, exist_ok=True)
                rejected_path(ch).write_text(cleaned, encoding="utf-8")
                if output_path(ch).exists():
                    output_path(ch).unlink()
        records[meta["key"]] = record
        print(meta["key"], status, record.get("length_ratio"),
              [a["stop_reason"] for a in attempts])

    records_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
