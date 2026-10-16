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

Binding has two layers, and the second one is what makes rebinding impossible:

* **content binding** — the verdict carries `before_sha256` / `after_sha256`;
* **request binding** — `judge-request` writes a `request_id` derived from (chapter, before
  hash, after hash), and `judge-bind --request-file` requires the raw answer to be associated
  with that exact request.

Without the request layer, `judge-bind` could take a raw answer produced for prose A and stamp
it with the hashes of prose B — "binding" it to text it never judged. Now a declared hash or
request id that disagrees with the original request is **refused**, not overwritten.

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


def judge_request_id(chapter: int, before_hash: str, after_hash: str) -> str:
    """Stable id for one (chapter, before, after) judging request."""
    payload = f"{SCHEMA_VERSION}|request|{int(chapter or 0)}|{before_hash}|{after_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_judge_request(
    before_text: str,
    after_text: str,
    *,
    chapter: int = 0,
    canon_constraints: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build the host-facing judge request: prompt + binding + the exact answer schema."""
    prompt = build_semantic_judge_prompt(before_text, after_text, canon_constraints=canon_constraints)
    before_hash = sha256_text(before_text)
    after_hash = sha256_text(after_text)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "request",
        "chapter": int(chapter or 0),
        "request_id": judge_request_id(chapter, before_hash, after_hash),
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "dimensions": list(SEMANTIC_JUDGE_DIMENSIONS),
        "response_schema": {
            "outcome": "STYLE_ONLY_SAFE | SEMANTIC_CHANGE_PROPOSED | UNCERTAIN",
            "changes": [
                {"dimension": "<one of dimensions>", "before": "...", "after": "...", "reason": "..."}
            ],
            "before_sha256": "<copy from this request>",
            "after_sha256": "<copy from this request>",
            "request_id": "<copy from this request>",
        },
        "prompt": prompt,
        "instructions": [
            "把 prompt 交给宿主模型（当前 Claude Code），不要调用任何外部付费 API。",
            "把模型回答的 JSON 原样写入响应文件，并回填 request_id 与 before_sha256 / after_sha256。",
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


def _declared_binding(data: Dict[str, Any]) -> Dict[str, str]:
    """Binding fields the raw answer itself carries (empty string when not declared)."""
    declared: Dict[str, str] = {}
    for key in (*BINDING_FIELDS, "request_id"):
        value = data.get(key)
        declared[key] = str(value).strip() if value is not None else ""
    return declared


def _request_binding(request: Any, before_text: str, after_text: str) -> Dict[str, str]:
    """Read and validate an original `judge-request` against the prose being bound."""
    data = _coerce_payload(request)
    if str(data.get("kind") or "") != "request":
        raise JudgeBindingError("--request-file is not a judge request (missing kind=request)")
    before_hash = str(data.get("before_sha256") or "")
    after_hash = str(data.get("after_sha256") or "")
    if not before_hash or not after_hash:
        raise JudgeBindingError("judge request has no before/after hashes")
    actual_before = sha256_text(before_text)
    actual_after = sha256_text(after_text)
    if before_hash != actual_before or after_hash != actual_after:
        raise JudgeBindingError(
            "judge request does not describe this prose: the request was issued for different "
            f"before/after text (request={before_hash[:12]}/{after_hash[:12]}, "
            f"actual={actual_before[:12]}/{actual_after[:12]})"
        )
    return {
        "request_id": str(data.get("request_id") or ""),
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "chapter": str(data.get("chapter") or ""),
    }


def bind_judge_response(
    payload: Any,
    before_text: str,
    after_text: str,
    *,
    chapter: int = 0,
    request: Any = None,
) -> Dict[str, Any]:
    """Validate a raw host answer and bind it to this prose pair.

    When the original `judge-request` is supplied, the answer must be *associated* with it:
    every binding field the answer declares (`request_id` / `before_sha256` / `after_sha256`)
    has to agree with the request, and at least one has to be declared. A declared value that
    disagrees is refused — never overwritten with the current prose's hashes.
    """
    data = _coerce_payload(payload)
    # A nested prompt-style wrapper is tolerated: `{"response": {...}}`
    for key in ("response", "verdict", "result"):
        if key in data and isinstance(data[key], dict):
            data = {**data, **data.pop(key)}
            break

    declared = _declared_binding(data)
    expected_before = sha256_text(before_text)
    expected_after = sha256_text(after_text)
    request_binding: Optional[Dict[str, str]] = None

    if request is not None:
        request_binding = _request_binding(request, before_text, after_text)
        if not any(declared.values()):
            raise JudgeBindingError(
                "raw judge answer declares no binding (request_id / before_sha256 / "
                "after_sha256); it cannot be associated with the judge request it came from. "
                "让宿主模型按 judge-request 的 response_schema 回填这些字段。"
            )
        if declared["before_sha256"] and declared["before_sha256"] != request_binding["before_sha256"]:
            raise JudgeBindingError(
                "judge answer was produced for different before text than the request "
                f"(answer={declared['before_sha256'][:12]}, request={request_binding['before_sha256'][:12]})"
            )
        if declared["after_sha256"] and declared["after_sha256"] != request_binding["after_sha256"]:
            raise JudgeBindingError(
                "judge answer was produced for different after text than the request "
                f"(answer={declared['after_sha256'][:12]}, request={request_binding['after_sha256'][:12]})"
            )
        if declared["request_id"]:
            expected_request_id = request_binding["request_id"] or judge_request_id(
                int(request_binding["chapter"] or 0),
                request_binding["before_sha256"],
                request_binding["after_sha256"],
            )
            if declared["request_id"] != expected_request_id:
                raise JudgeBindingError(
                    "judge answer belongs to a different judge request "
                    f"(answer={declared['request_id'][:12]}, request={expected_request_id[:12]})"
                )
    else:
        # No request supplied (legacy inline path). Still refuse to *ignore* hashes the answer
        # declares: a mismatching hash means the answer is about other prose.
        if declared["before_sha256"] and declared["before_sha256"] != expected_before:
            raise JudgeBindingError(
                "judge answer declares a before_sha256 for different prose "
                f"(answer={declared['before_sha256'][:12]}, actual={expected_before[:12]})"
            )
        if declared["after_sha256"] and declared["after_sha256"] != expected_after:
            raise JudgeBindingError(
                "judge answer declares an after_sha256 for different prose "
                f"(answer={declared['after_sha256'][:12]}, actual={expected_after[:12]})"
            )

    parsed = parse_semantic_judge_response(
        {k: v for k, v in data.items() if k in {"outcome", "changes"}}
    )
    verdict = {
        "schema_version": SCHEMA_VERSION,
        "kind": "verdict",
        "chapter": int(data.get("chapter") or chapter or 0),
        "outcome": parsed["outcome"],
        "changes": parsed["changes"],
        "before_sha256": expected_before,
        "after_sha256": expected_after,
        "request_id": (
            request_binding["request_id"]
            if request_binding and request_binding["request_id"]
            else judge_request_id(int(data.get("chapter") or chapter or 0), expected_before, expected_after)
        ),
        "source": str(data.get("source") or "host"),
        "association": (
            "request" if request_binding is not None
            else ("declared_hashes" if any(declared.values()) else "inline_unbound")
        ),
    }
    return verdict


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
    declared_request_id = str(data.get("request_id") or "")
    if declared_request_id:
        expected_request_id = judge_request_id(
            int(data.get("chapter") or chapter or 0), expected_before, expected_after
        )
        if declared_request_id != expected_request_id:
            raise JudgeBindingError(
                "stale judge verdict: request_id does not match this prose pair "
                f"(verdict={declared_request_id[:12]}, expected={expected_request_id[:12]})"
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
    request: Any = None,
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
            verdict = bind_judge_response(
                payload, call_before, call_after, chapter=chapter, request=request
            )
        return {"outcome": verdict["outcome"], "changes": verdict["changes"]}

    return _judge


def format_request_text(request: Dict[str, Any]) -> str:
    lines = [
        "=== Semantic Judge 请求（由宿主模型裁决，无需额外 API Key）===",
        f"chapter: {request.get('chapter')}",
        f"request_id: {request.get('request_id')}",
        f"before_sha256: {request.get('before_sha256')}",
        f"after_sha256: {request.get('after_sha256')}",
        "",
        "请把下面 prompt 交给宿主模型，并将回答 JSON 保存为响应文件后回填：",
        f"  request_id={request.get('request_id')}",
        f"  before_sha256={request.get('before_sha256')}",
        f"  after_sha256={request.get('after_sha256')}",
        "",
        "---- prompt ----",
        str(request.get("prompt") or ""),
    ]
    return "\n".join(lines)
