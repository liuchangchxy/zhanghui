"""Shared Nuxt SSR ``__NUXT__`` payload parser.

Status: shared library used by both ``scripts.adapters.qimao`` and
``scripts.adapters.zongheng`` (verified 2026-08-13).

Why extracted:
    The two adapters originally inlined near-identical copies of
    ``_scan_balanced`` + ``_split_top_level_csv`` + ``_parse_nuxt_payload``
    (about 200 LOC duplicated). Extracting them here keeps the parser
    logic in one place — future upstream-shape changes are fixed once,
    not twice.

Algorithm overview:
    Nuxt SSR pages embed the initial Vuex state as a single JS expression::

        window.__NUXT__=(function(a,b,c,...){return {...}})(val1,val2,...);

    Steps (all depth-aware so nested braces don't confuse us):

      1. Find ``window.__NUXT__`` and the ``(function(`` opener.
      2. Find the matching ``)`` for the formal-args list.
      3. Find the matching ``}`` for the function body.
      4. Find the matching ``)`` for the call-args list.
      5. Substitute ``a``/``b``/... in the body source with their JSON
         values (string-aware so quoted keys are not touched) and
         ``json.loads`` the result.

    七猫 + 纵横's payloads are JSON-safe (lists, dicts, strings, numbers,
    bools, null) so the final ``json.loads`` succeeds after one more pass
    to quote bare identifier keys (``layout:`` -> ``"layout":``).
"""
from __future__ import annotations

import json
from typing import Any


def scan_balanced(
    s: str, start: int, open_char: str, close_char: str
) -> tuple[int, str]:
    """Find the matching ``close_char`` for the ``open_char`` at ``s[start]``.

    Uses depth counting with full string/escape awareness so braces
    inside quoted keys/values don't confuse the depth counter.

    Returns ``(close_idx, content_between)`` where ``content_between`` is
    ``s[start + 1 : close_idx]``. Returns ``(-1, "")`` if not found or if
    ``s[start]`` is not ``open_char``.
    """
    if start >= len(s) or s[start] != open_char:
        return (-1, "")
    depth = 1
    i = start + 1
    in_str: str | None = None
    escape = False
    while i < len(s):
        ch = s[i]
        if escape:
            escape = False
            i += 1
            continue
        if in_str is not None:
            if ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = ch
            i += 1
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return (i, s[start + 1 : i])
        i += 1
    return (-1, "")


def split_top_level_csv(s: str, start: int) -> list[str]:
    """Split ``s[start:]`` at top-level commas.

    Respects string literals (with escape sequences) and nested
    brackets/parens/braces so commas inside ``[1, 2, 3]`` or
    ``{a:1, b:[1,2]}`` are not treated as separators.
    """
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    in_str: str | None = None
    escape = False
    i = start
    while i < len(s):
        ch = s[i]
        if escape:
            cur.append(ch)
            escape = False
            i += 1
            continue
        if in_str is not None:
            cur.append(ch)
            if ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = ch
            cur.append(ch)
            i += 1
            continue
        if ch in "([{":
            depth += 1
            cur.append(ch)
            i += 1
            continue
        if ch in ")]}":
            depth -= 1
            cur.append(ch)
            i += 1
            continue
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    if cur:
        out.append("".join(cur))
    return out


def _quote_bare_keys(s: str) -> str:
    """Quote bare JS identifier keys (``layout:`` -> ``"layout":``).

    Walks the substituted text and quotes any identifier followed by
    optional whitespace then ``:`` so the result is JSON-parseable.
    String-aware — identifiers inside string literals are not touched.
    """
    out: list[str] = []
    i = 0
    in_str: str | None = None
    escape = False
    while i < len(s):
        ch = s[i]
        if escape:
            out.append(ch)
            escape = False
            i += 1
            continue
        if in_str is not None:
            out.append(ch)
            if ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = ch
            out.append(ch)
            i += 1
            continue
        if ch.isalpha() or ch == "_" or ch == "$":
            j = i
            while j < len(s) and (s[j].isalnum() or s[j] in "_$"):
                j += 1
            name = s[i:j]
            k = j
            while k < len(s) and s[k] in " \t":
                k += 1
            if k < len(s) and s[k] == ":":
                out.append(f'"{name}"')
                i = j
                continue
            out.append(name)
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_nuxt_payload(html: str) -> dict[str, Any]:
    """Extract the data object from ``window.__NUXT__ = ...``.

    Returns the parsed Python dict, or ``{}`` if the marker is missing,
    the payload is structurally broken, or the final JSON parse fails.
    """
    marker = "window.__NUXT__"
    m = html.find(marker)
    if m < 0:
        return {}

    # Locate "(function(" after the marker.
    fn_start = html.find("(function(", m)
    if fn_start < 0:
        return {}
    args_open = fn_start + len("(function")

    # Formal-args close: balanced scan starting at the '(' that follows.
    args_close, args_decl = scan_balanced(html, args_open, "(", ")")
    if args_close < 0:
        return {}

    # Body: from the '{' right after args_close to its matching '}'.
    body_open = html.find("{", args_close)
    if body_open < 0:
        return {}
    body_close, body = scan_balanced(html, body_open, "{", "}")
    if body_close < 0:
        return {}

    # Call-args: from the '(' after body_close to its matching ')'.
    call_open = html.find("(", body_close)
    if call_open < 0:
        return {}
    call_close, _ = scan_balanced(html, call_open, "(", ")")
    if call_close < 0:
        return {}

    arg_names = [a.strip() for a in args_decl.split(",") if a.strip()]

    arg_values: list[Any] = []
    call_args_text = html[call_open + 1 : call_close]
    for piece in split_top_level_csv(call_args_text, 0):
        piece = piece.strip()
        if not piece:
            continue
        try:
            arg_values.append(json.loads(piece))
        except json.JSONDecodeError:
            return {}
    table = dict(zip(arg_names, arg_values))

    # Substitute identifier references with their JSON values. CRITICAL:
    # string-aware — the body contains quoted keys like
    # ``"data-v-cca2d2e4":0`` whose ``data`` / ``v`` substrings must NOT
    # be replaced even though they look like identifiers.
    out_parts: list[str] = []
    i = 0
    in_str: str | None = None
    escape = False
    while i < len(body):
        ch = body[i]
        if escape:
            out_parts.append(ch)
            escape = False
            i += 1
            continue
        if in_str is not None:
            out_parts.append(ch)
            if ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = ch
            out_parts.append(ch)
            i += 1
            continue
        if ch.isalpha() or ch == "_" or ch == "$":
            j = i
            while j < len(body) and (body[j].isalnum() or body[j] in "_$"):
                j += 1
            name = body[i:j]
            if name in table:
                out_parts.append(json.dumps(table[name], ensure_ascii=False))
            else:
                out_parts.append(name)
            i = j
            continue
        out_parts.append(ch)
        i += 1
    substituted = "".join(out_parts)

    stripped = substituted.strip()
    if stripped.startswith("return "):
        stripped = stripped[len("return "):].lstrip()

    quoted = _quote_bare_keys(stripped)
    try:
        parsed = json.loads(quoted)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}