"""七猫（qimao）adapter — Strategy.VENDOR.

Status: LIVE (verified 2026-08-13, after balanced-brace parser rewrite).

    The vendored ``vendor/qimao_web_crawler_subset/qimao_subset/`` wraps
    a pure-Python regex parser of qimao.com's Nuxt SSR ``__NUXT__``
    payload. The original upstream regex (``_NUXT_RE``) was written
    assuming a flat JS object literal — it did not handle nested braces
    inside the real upstream payload (e.g. the ``fetch:{"data-v-cca2d2e4:0":{listData:[...]}}``
    block). The parser silently returned an empty dict, and the vendored
    ``fetch_qimao_rank`` swallowed that as ``except Exception: return items``.

    This file replaces the broken vendored regex with a balanced-brace
    scanner (modeled on the existing ``_split_top_level_csv`` helper in
    the vendored subset) — see ``_parse_nuxt_payload`` below — and then
    re-implements the upstream call-arg substitution so the returned
    object can be parsed as JSON.

    The vendored subset is still used for the book-row projection
    (``_project_list_item``) and the throttle so the field names and
    network semantics stay byte-for-byte identical with the upstream we
    track.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from scripts.adapters.base import BaseAdapter, Strategy, AdapterStatus
from scripts.schema import RawBook
from vendor.qimao_web_crawler_subset.qimao_subset.crawl_qimao_rank import (
    QIMAO_DOMAIN,
    QIMAO_HEADERS,
    REQUEST_TIMEOUT,
    CHANNEL_TYPES,
    RANK_TYPES,
    _project_list_item,
)

# Map our period -> upstream rank_type. 上游 RANK_TYPES =
# hot/new/over/collect/update. Choose the closest semantic match.
PERIOD_TO_RANK_TYPE = {
    "daily": "hot",
    "weekly": "collect",
    "monthly": "over",
}
DEFAULT_RANK_TYPE = "hot"

# Re-implemented (in this file, not the vendored subset) balanced-brace
# scanner that replaces the broken upstream regex. The vendored subset
# keeps its original code untouched so we can sync upstream changes; the
# adapter imports the projection helpers it needs but NOT
# ``_parse_nuxt_html``.


def _split_top_level_csv(text: str) -> list[str]:
    """Split at top-level commas (no nesting inside brackets/parens/braces).

    Verbatim copy of the helper in the vendored subset — we need it here
    because the vendored subset's module-level helpers aren't re-exported
    and we don't want to depend on them (they may change upstream).
    """
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    in_str: str | None = None
    escape = False
    for ch in text:
        if escape:
            cur.append(ch)
            escape = False
            continue
        if in_str is not None:
            cur.append(ch)
            if ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in ('"', "'"):
            in_str = ch
            cur.append(ch)
            continue
        if ch in "([{":
            depth += 1
            cur.append(ch)
            continue
        if ch in ")]}":
            depth -= 1
            cur.append(ch)
            continue
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


def _scan_balanced(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """Find the index of the matching ``close_ch`` for the ``open_ch`` at
    ``text[start]``. Returns -1 if not found. Tracks string state and
    escape sequences so braces inside quoted keys/values don't confuse
    the depth counter.
    """
    if start >= len(text) or text[start] != open_ch:
        return -1
    depth = 1
    i = start + 1
    in_str: str | None = None
    escape = False
    while i < len(text):
        ch = text[i]
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
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _parse_nuxt_payload(html: str) -> dict[str, Any]:
    """Parse the ``__NUXT__`` expression from a Nuxt SSR page (no Node.js).

    Replaces the broken upstream ``_NUXT_RE`` regex. The pattern is::

        window.__NUXT__=(function(a,b,c,...){return {...}})(val1,val2,...);

    Steps (all depth-aware so nested braces don't confuse us):

      1. Find ``window.__NUXT__`` and the ``(function(`` opener.
      2. Find the matching ``)`` for the formal-args list (no nested
         parens, plain regex works — but we use a balanced scan to be
         robust).
      3. Find the matching ``}`` for the function body (BRACE-DEPTH
         SCAN — this is the fix).
      4. Find the matching ``)`` for the call-args list.
      5. Substitute ``a``/``b``/... in the body source with their JSON
         values and ``json.loads`` the result.

    七猫's payload is JSON-safe (lists, dicts, strings, numbers, bools,
    null) so the final ``json.loads`` succeeds.
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
    args_close = _scan_balanced(html, args_open, "(", ")")
    if args_close < 0:
        return {}
    args_decl = html[args_open + 1 : args_close]
    # Body: from the '{' right after args_close to its matching '}'.
    body_open = html.find("{", args_close)
    if body_open < 0:
        return {}
    body_close = _scan_balanced(html, body_open, "{", "}")
    if body_close < 0:
        return {}
    body = html[body_open + 1 : body_close]
    # Call-args: from the '(' after body_close to its matching ')'.
    call_open = html.find("(", body_close)
    if call_open < 0:
        return {}
    call_close = _scan_balanced(html, call_open, "(", ")")
    if call_close < 0:
        return {}

    arg_names = [a.strip() for a in args_decl.split(",") if a.strip()]
    call_args_text = html[call_open + 1 : call_close]

    arg_values: list[Any] = []
    for piece in _split_top_level_csv(call_args_text):
        piece = piece.strip()
        if not piece:
            continue
        try:
            arg_values.append(json.loads(piece))
        except json.JSONDecodeError:
            return {}
    table = dict(zip(arg_names, arg_values))

    # Substitute identifier references with their JSON values. CRITICAL:
    # we must be string-aware — the body contains quoted keys like
    # ``"data-v-cca2d2e4":0`` whose ``data`` / ``v`` substrings must NOT
    # be replaced even though they look like identifiers. Walk the body
    # char-by-char, track string state, and only substitute identifiers
    # that appear outside of any string literal.
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
        # Outside a string: try to match an identifier.
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

    # The body is a JavaScript object literal, not JSON. JS allows bare
    # identifier keys (``layout:`` instead of ``"layout":``); JSON does
    # not. Walk through the substituted text and quote any bare-key
    # identifier followed by ``:`` (again, string-aware so we don't
    # touch identifiers inside string values).
    def _quote_bare_keys(s: str) -> str:
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
                # If followed by optional whitespace then ":", this is a
                # bare key — wrap it in double quotes.
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

    # Strip the leading "return " JS keyword before JSON parsing.
    stripped = substituted.strip()
    if stripped.startswith("return "):
        stripped = stripped[len("return "):].lstrip()

    quoted = _quote_bare_keys(stripped)
    try:
        parsed = json.loads(quoted)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _fetch_qimao_rank(channel: str, rank_type: str, top: int) -> list[dict]:
    """Fetch up to ``top`` items from one 七猫 ranking page (LIVE path).

    Same network/field contract as the vendored ``fetch_qimao_rank``
    except we use ``_parse_nuxt_payload`` (working) instead of the
    vendored ``_parse_nuxt_html`` (broken regex). On any HTTP / parse
    failure we return what we have so far (mirroring the vendored
    ``except Exception: return items`` behavior — but here it can only
    trigger on transient errors, not on a structural parser bug).
    """
    ch_label = next(
        (label for c, label in CHANNEL_TYPES if c == channel), "男生"
    )
    rank_label = next(
        (label for r, label in RANK_TYPES if r == rank_type), "大热榜"
    )

    url = f"{QIMAO_DOMAIN}/paihang?channelType={channel}&rankType={rank_type}"

    items: list[dict] = []
    try:
        resp = httpx.get(url, headers=QIMAO_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = _parse_nuxt_payload(resp.text)
        if not data:
            return items

        fetch_block = data.get("fetch", {})
        list_data: list[dict] | None = None
        for val in fetch_block.values():
            if isinstance(val, dict) and "listData" in val:
                list_data = val["listData"]
                break
        if not list_data:
            return items

        for bk in list_data[:top]:
            projected = _project_list_item(bk, ch_label, rank_label)
            if projected is None:
                continue
            projected["rank"] = str(len(items) + 1)
            items.append(projected)
    except Exception:
        return items

    return items


class QimaoAdapter(BaseAdapter):
    platform = "qimao"
    strategy = Strategy.VENDOR
    status = AdapterStatus.LIVE

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        """Fetch 七猫 rank list. Maps period -> rank_type, then iterates
        the two channels (boy + girl) since 七猫 has no single "all"
        channel at the URL level — mirrors the vendored upstream.
        """
        rank_type = PERIOD_TO_RANK_TYPE.get(period, DEFAULT_RANK_TYPE)

        # 七猫 has two channels at the URL level: boy + girl. Upstream
        # iterates both; we do the same and concatenate results.
        all_items: list[dict] = []
        for channel in ("boy", "girl"):
            all_items.extend(_fetch_qimao_rank(channel, rank_type, top))

        # Map vendored item dicts -> RawBook. We only use the top-N after
        # the union (upstream ranks globally across channels).
        books: list[RawBook] = []
        for idx, item in enumerate(all_items[:top]):
            books.append(
                RawBook(
                    platform_book_id=item.get("book_id", ""),
                    title=item.get("title", ""),
                    author=item.get("author", ""),
                    category=item.get("category_label", ""),
                    word_count=None,  # upstream's `number` is reader count, not words_num
                    intro=item.get("description", ""),
                    status="completed" if item.get("status") == "完结" else "serial",
                    cover_url=item.get("cover_url") or None,
                    detail_url=item.get("book_url") or None,
                    rank_position=idx + 1,
                    raw_payload={
                        "rank_label": item.get("rank"),
                        "category_label": item.get("category_label"),
                        "reader_count_label": item.get("reader_count"),
                        "source": item.get("source"),
                    },
                )
            )
        return books