#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Host-driven Semantic Judge wiring (task F).

The Semantic Judge contract already existed (`build_semantic_judge_prompt`,
`parse_semantic_judge_response`, `--judge-result` / `--judge-file`), but the normal host
call chain was incomplete:

* the Skill was told to "call the Semantic Judge" without any command that produces the
  judge's input, so a correctly fail-closed pipeline rolled every substantial edit back and
  Step 2B / Step 4 became no-ops;
* an external judge result could be replayed against *different* prose — nothing tied a
  verdict to the text it judged.

This module closes both gaps **without requiring an extra API key**: the host model
(Claude Code itself) is the judge. The round trip is

    prose judge-request  ->  <prompt file>       (bound to before/after sha256)
    <host model answers> ->  <response file>     (must carry the same two sha256)
    prose validate --judge-file <response file>

and every judge verdict is bound to the exact before/after text it was produced for.

Fail-closed behaviour is preserved: a missing, unbound, mismatched or malformed verdict
still resolves to UNCERTAIN, and UNCERTAIN still rolls back.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from .prose_semantic_diff import (
    SEMANTIC_JUDGE_DIMENSIONS,
    build_semantic_judge_prompt,
    parse_semantic_judge_response,
)


SCHEMA_VERSION = "semantic-judge/v1"

BINDING_FIELDS = ("before_sha256", "after_sha256")


class JudgeBindingError(ValueError):
    """Raised when a judge verdict is not bound to the prose it is being applied to."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def build_judge_request(
    before_text: str,
    after_text: str,
    *,
    chapter: int = 0,
    canon_constraints: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build the host-facing judge request: prompt + binding + the exact answer schema."""
    prompt = build_semantic_judge_prompt(before_text, after_text, canon_constraints=canon_constraints)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "request",
        "chapter": int(chapter or 0),
        "before_sha256": sha256_text(before_text),
        "after_sha256": sha256_text(after_text),
        "dimensions": list(SEMANTIC_JUDGE_DIMENSIONS),
        "response_schema": {
            "outcome": "STYLE_ONLY_SAFE | SEMANTIC_CHANGE_PROPOSED | UNCERTAIN",
            "changes": [
                {"dimension": "<one of dimensions>", "before": "...", "after": "...", "reason": "..."}
            ],
            "before_sha256": "<copy from this request>",
            "after_sha256": "<copy from this request>",
        },
        "prompt": prompt,
        "instructions": [
            "把 prompt 交给宿主模型（当前 Claude Code），不要调用任何外部付费 API。",
            "把模型回答的 JSON 原样写入响应文件，并回填 before_sha256 / after_sha256。",
            "无法判断时输出 UNCERTAIN —— 系统会安全回滚，不会放行。",
        ],
    }


def _coerce_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            raise JudgeBindingError("empty judge payload")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # maybe it is a path
            path = Path(text)
            if path.is_file():
                return _coerce_payload(path.read_text(encoding="utf-8"))
            raise JudgeBindingError("judge payload is neither JSON nor an existing file")
        if not isinstance(data, dict):
            raise JudgeBindingError("judge payload must be a JSON object")
        return data
    raise JudgeBindingError(f"unsupported judge payload type: {type(payload)}")


def bind_judge_response(
    payload: Any,
    before_text: str,
    after_text: str,
    *,
    chapter: int = 0,
) -> Dict[str, Any]:
    """Validate a raw host answer and return a verdict bound to this exact prose pair."""
    data = _coerce_payload(payload)
    # A nested prompt-style wrapper is tolerated: `{"response": {...}}`
    for key in ("response", "verdict", "result"):
        if key in data and isinstance(data[key], dict):
            data = {**data, **data.pop(key)}
            break

    parsed = parse_semantic_judge_response(
        {k: v for k, v in data.items() if k in {"outcome", "changes"}}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "verdict",
        "chapter": int(data.get("chapter") or chapter or 0),
        "outcome": parsed["outcome"],
        "changes": parsed["changes"],
        "before_sha256": sha256_text(before_text),
        "after_sha256": sha256_text(after_text),
        "source": str(data.get("source") or "host"),
    }


def validate_binding(
    verdict: Any,
    before_text: str,
    after_text: str,
    *,
    chapter: Optional[int] = None,
) -> Dict[str, Any]:
    """Validate a *previously produced* verdict against the prose it is applied to.

    Raises `JudgeBindingError` when the verdict is unbound, bound to different text, or
    bound to a different chapter. Callers translate that into UNCERTAIN (fail-closed).
    """
    data = _coerce_payload(verdict)
    if str(data.get("kind") or "") != "verdict":
        raise JudgeBindingError("judge verdict is not bound (missing kind=verdict)")

    missing = [field for field in BINDING_FIELDS if not data.get(field)]
    if missing:
        raise JudgeBindingError(
            "judge verdict is not bound to its prose "
            f"(missing {', '.join(missing)}); regenerate it with `prose judge-request`"
        )

    expected_before = sha256_text(before_text)
    expected_after = sha256_text(after_text)
    if data["before_sha256"] != expected_before:
        raise JudgeBindingError(
            "stale judge verdict: before_sha256 does not match the prose being validated "
            f"(verdict={str(data['before_sha256'])[:12]}, actual={expected_before[:12]})"
        )
    if data["after_sha256"] != expected_after:
        raise JudgeBindingError(
            "stale judge verdict: after_sha256 does not match the prose being validated "
            f"(verdict={str(data['after_sha256'])[:12]}, actual={expected_after[:12]})"
        )
    if chapter:
        verdict_chapter = int(data.get("chapter") or 0)
        if verdict_chapter and verdict_chapter != int(chapter):
            raise JudgeBindingError(
                f"judge verdict belongs to chapter {verdict_chapter}, not chapter {chapter}"
            )
    return data


def make_bound_judge_callable(
    payload: Any,
    before_text: str,
    after_text: str,
    *,
    chapter: int = 0,
    require_binding: bool = True,
):
    """Return a `semantic_judge` callable for `compare_semantic_facts`.

    The callable re-validates on every invocation, and refuses when it is asked to judge
    *different* prose than the verdict was bound to. `require_binding=False` is the
    compatibility path for an inline `--judge-result` supplied in the same invocation.
    """

    def _judge(call_before: str, call_after: str) -> Dict[str, Any]:
        if sha256_text(call_before) != sha256_text(before_text) or sha256_text(call_after) != sha256_text(after_text):
            raise JudgeBindingError(
                "judge callable was handed different prose than it was bound to"
            )
        if require_binding:
            verdict = validate_binding(payload, call_before, call_after, chapter=chapter or None)
        else:
            verdict = bind_judge_response(payload, call_before, call_after, chapter=chapter)
        return {"outcome": verdict["outcome"], "changes": verdict["changes"]}

    return _judge


def format_request_text(request: Dict[str, Any]) -> str:
    lines = [
        "=== Semantic Judge 请求（由宿主模型裁决，无需额外 API Key）===",
        f"chapter: {request.get('chapter')}",
        f"before_sha256: {request.get('before_sha256')}",
        f"after_sha256: {request.get('after_sha256')}",
        "",
        "请把下面 prompt 交给宿主模型，并将回答 JSON 保存为响应文件后回填：",
        f"  before_sha256={request.get('before_sha256')}",
        f"  after_sha256={request.get('after_sha256')}",
        "",
        "---- prompt ----",
        str(request.get("prompt") or ""),
    ]
    return "\n".join(lines)
