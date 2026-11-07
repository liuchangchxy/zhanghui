#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Two model channels for the literary-gain experiment.

1. Local Anthropic-compatible proxy: used for the editor and one blind judge.
2. Antigravity agentapi (Gemini 3.8 Flash): independent second blind judge.

No production code imports this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

AGENTAPI_BIN = Path("/Users/chang/.gemini/antigravity/bin/agentapi")
APP_DATA_DIR = Path("/Users/chang/.gemini/antigravity")
AGENTAPI_PROJECT = "outside-of-project"


def _discover_ls() -> tuple[str, str]:
    out = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "language_server" not in line or "antigravity" not in line:
            continue
        pid = line.split(None, 1)[0]
        lsof = subprocess.run(["lsof", "-nP", "-p", pid], capture_output=True, text=True).stdout
        ports = re.findall(r"TCP\s+127\.0\.0\.1:(\d+)\s+\(LISTEN\)", lsof)
        token = re.search(r"--csrf_token[= ]([0-9a-f-]{36})", line)
        if not (ports and token):
            continue
        for port in ports:
            probe = subprocess.run(
                [str(AGENTAPI_BIN), "get-conversation-metadata", "probe"],
                capture_output=True, text=True, timeout=20,
                env={**os.environ, "ANTIGRAVITY_LS_ADDRESS": "127.0.0.1:" + port,
                     "ANTIGRAVITY_CSRF_TOKEN": token.group(1)},
            )
            if "Unavailable" in probe.stdout or "Unavailable" in probe.stderr:
                continue
            if "not_found" in probe.stdout or "not_found" in probe.stderr:
                return "127.0.0.1:" + port, token.group(1)
    raise RuntimeError("Could not find a live Antigravity language server.")


def run_agentapi(prompt: str, out_dir: str | Path, title: str,
                 max_wait: int = 1200, retries: int = 3) -> tuple[str, dict]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    address, csrf = _discover_ls()
    last = None
    for attempt in range(retries + 1):
        try:
            return _run_agentapi_once(prompt, out, title, address, csrf, max_wait, attempt + 1)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries:
                time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"agentapi failed after retries: {last}")


def _run_agentapi_once(prompt: str, out: Path, title: str,
                       address: str, csrf: str, max_wait: int, attempt: int) -> tuple[str, dict]:
    env = dict(os.environ, ANTIGRAVITY_LS_ADDRESS=address,
               ANTIGRAVITY_CSRF_TOKEN=csrf, ANTIGRAVITY_PROJECT_ID=AGENTAPI_PROJECT)
    started = time.time()
    proc = subprocess.run(
        [str(AGENTAPI_BIN), "new-conversation", "--model=flash", f"--title={title}", prompt],
        cwd=str(out), capture_output=True, text=True, env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"agentapi failed: {proc.stderr[:600]}")
    conv = json.loads(proc.stdout)["response"]["newConversation"]["conversationId"]
    brain = APP_DATA_DIR / "brain" / conv
    transcript = brain / ".system_generated/logs/transcript.jsonl"
    transcript_full = brain / ".system_generated/logs/transcript_full.jsonl"
    content, in_tok, out_tok = "", 0, 0
    while time.time() - started < max_wait:
        if transcript.exists():
            for line in transcript.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                step = json.loads(line)
                if step.get("type") == "ERROR_MESSAGE" or step.get("status") == "ERROR":
                    raise RuntimeError(f"Antigravity error: {step.get('error')}")
                if (step.get("source") == "MODEL" and step.get("type") == "PLANNER_RESPONSE"
                        and step.get("status") == "DONE"):
                    c = (step.get("content") or "").strip()
                    if "content" in (step.get("truncated_fields") or []) and transcript_full.exists():
                        for fl in transcript_full.read_text(encoding="utf-8").splitlines():
                            fl = fl.strip()
                            if not fl:
                                continue
                            f_step = json.loads(fl)
                            if f_step.get("step_index") == step.get("step_index"):
                                c = (f_step.get("content") or "").strip()
                                break
                    if c:
                        content, in_tok, out_tok = c, step.get("input_tokens", 0), step.get("output_tokens", 0)
            if content:
                break
        time.sleep(1.0)
    if not content:
        raise TimeoutError(f"no content after {max_wait}s")
    (out / "output.raw.txt").write_text(content, encoding="utf-8")
    meta = {
        "backend": "antigravity-agentapi",
        "model_flag": "flash",
        "human_runtime": "Gemini 3.8 Flash (Medium)",
        "machine_runtime": "MODEL_PLACEHOLDER_M322",
        "model_id_verifiability": "PARTIAL_INTERNAL_LABEL_ONLY",
        "project": AGENTAPI_PROJECT,
        "ls_address": address,
        "conversation_id": conv,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "elapsed_ms": int((time.time() - started) * 1000),
        "attempt": attempt,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (out / "runtime-metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return content, meta


def run_proxy(prompt: str, out_dir: str | Path, title: str,
              model: str | None = None, temperature: float = 0.2,
              max_tokens: int = 16000, retries: int = 3) -> tuple[str, dict]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    base = os.environ.get("ANTHROPIC_BASE_URL", "http://127.0.0.1:3425")
    key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
    model = model or os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL", "group/mac-deepseek4.1-gpt[1m]")
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    started = time.time()
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                f"{base}/v1/messages", data=body,
                headers={"content-type": "application/json", "x-api-key": key,
                         "anthropic-version": "2023-06-01"})
            with urllib.request.urlopen(req, timeout=1200) as resp:
                data = json.loads(resp.read())
            text = "".join(b.get("text", "") for b in data.get("content", [])
                           if b.get("type") == "text")
            meta = {
                "backend": "local-anthropic-proxy",
                "base_url": base,
                "requested_model": model,
                "response_model": data.get("model"),
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stop_reason": data.get("stop_reason"),
                "usage": data.get("usage"),
                "elapsed_ms": int((time.time() - started) * 1000),
                "attempt": attempt + 1,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            (out / "output.raw.txt").write_text(text, encoding="utf-8")
            (out / "runtime-metadata.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return text, meta
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"proxy failed after retries: {last}")


def parse_json(raw: str) -> dict:
    s = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.DOTALL)
    candidate = m.group(1) if m else s
    try:
        return json.loads(candidate)
    except Exception:
        m2 = re.search(r"\{.*\}", s, re.DOTALL)
        if not m2:
            raise
        return json.loads(m2.group(0))
