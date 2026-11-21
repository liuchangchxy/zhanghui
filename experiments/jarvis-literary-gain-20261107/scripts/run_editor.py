#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the frozen literary editor on the four frozen A-arm chapters.

One prompt, one model, one temperature. Retries only for mechanical failures
(empty output, truncation, missing body), never to improve the result.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CHAPTERS, input_path, outline_path, output_path, prompt_path  # noqa: E402
from llm_channels import run_proxy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "prompts/editor_zh.md").read_text(encoding="utf-8")
MODEL = "group/mac-deepseek4.1-gpt[1m]"
TEMPERATURE = 0.4
MAX_TOKENS = 16000


def clean_output(raw: str, source: str) -> str:
    text = raw.replace("\r\n", "\n").strip()
    text = re.sub(r"^```(?:markdown|md)?\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    text = text.strip()
    first = source.splitlines()[0].strip()
    if not text.startswith(first):
        # Drop a leading meta line such as "以下是修订稿：".
        lines = text.splitlines()
        while lines and (lines[0].strip().startswith(("以下是", "修订稿", "【修订", "---"))):
            lines.pop(0)
        text = "\n".join(lines).strip()
        if not text.startswith(first):
            text = first + "\n\n" + text
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return text


def body_chars(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def main() -> None:
    chapters = [int(x) for x in sys.argv[1:]] or sorted(CHAPTERS)
    records = {}
    for ch in chapters:
        meta = CHAPTERS[ch]
        source = input_path(ch).read_text(encoding="utf-8")
        outline = outline_path(ch).read_text(encoding="utf-8").strip()
        prompt = TEMPLATE.replace("{outline}", outline).replace("{source}", source)
        out_dir = ROOT / f"outputs/{meta['key']}_run"
        last_err = None
        for attempt in range(2):
            raw, call_meta = run_proxy(
                prompt, out_dir, f"lit-editor-{meta['key']}",
                model=MODEL, temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
            )
            cleaned = clean_output(raw, source)
            ratio = body_chars(cleaned) / max(1, body_chars(source))
            truncated = call_meta.get("stop_reason") == "max_tokens"
            empty = body_chars(cleaned) < 500
            if not truncated and not empty:
                output_path(ch).write_text(cleaned, encoding="utf-8")
                prompt_path(ch).write_text(prompt, encoding="utf-8")
                records[meta["key"]] = {
                    "chapter": ch,
                    "model": MODEL,
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                    "output_sha256": hashlib.sha256(cleaned.encode()).hexdigest(),
                    "source_chars": body_chars(source),
                    "output_chars": body_chars(cleaned),
                    "length_ratio": round(ratio, 4),
                    "attempt": attempt + 1,
                    "stop_reason": call_meta.get("stop_reason"),
                    "usage": call_meta.get("usage"),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                print(meta["key"], "ok", body_chars(source), "->", body_chars(cleaned),
                      f"{ratio:.3f}")
                last_err = None
                break
            last_err = f"truncated={truncated} empty={empty} ratio={ratio:.3f}"
            print(meta["key"], "retry:", last_err, file=sys.stderr)
        if last_err:
            raise RuntimeError(f"{meta['key']} failed: {last_err}")

    p = ROOT / "outputs/RUN_RECORDS.json"
    existing = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    existing.update(records)
    p.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
