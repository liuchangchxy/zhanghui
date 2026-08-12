"""纵横中文网 (zongheng) adapter — WEBFETCH strategy via httpx + BeautifulSoup.

Status: LIVE (verified 2026-08-13).

    The publicly documented API endpoint
    ``https://www.zongheng.com/api/rank/details`` returns HTTP 404 (the
    v0.1.x adapter was marked BLOCKED_EXTERNAL because of this). The site
    itself returns 200 with a Nuxt SSR payload embedded as
    ``window.__NUXT__`` — every rank page contains ALL rank lists
    (``monthTicketRankList`` / ``newBookRankList`` / ``popularRankList`` /
    ``clickRankList`` / ``recommendRankList`` / etc.) under
    ``state.rank.popularityRank``.

    We use the same balanced-brace + identifier-substitution Nuxt parser
    that ``scripts.adapters.qimao`` uses (reused as a private helper, NOT
    imported across adapters — we copy the two helpers verbatim so
    upstream changes don't break this adapter by surprise) and pick the
    right list for the requested period.

Period -> rank list key:
    daily   -> ``newBookRankList``    (新书榜)
    weekly  -> ``recommendRankList``   (推荐榜)
    monthly -> ``monthTicketRankList`` (月票榜)

Field mapping (from real observed Nuxt SSR payloads, see
tests/fixtures/zongheng_rank_newbook.html):
    ``bookId``     -> platform_book_id
    ``bookName``   -> title
    ``authorName`` -> author
    ``authorId``   -> raw_payload (used for detail_url slug)
    ``imageUrl``   -> cover_url
    ``description``-> intro (empty in payload — fetched separately if needed)
    ``totalWords`` -> word_count
    ``serialStatus``-> status (0=serial, 1=completed; see _serial_status_to_literal)
    ``rankNo``     -> rank_position
    ``numberDesc`` -> raw_payload (rank label like "X万月票")
    ``cateFineName``-> category
"""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook

_BASE = "https://www.zongheng.com"
_RANK_URL = f"{_BASE}/rank?nav=new-book&rankType=4"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": _BASE,
}

# Period -> key inside state.rank.popularityRank.
PERIOD_TO_RANK_LIST = {
    "daily": "newBookRankList",       # 新书榜
    "weekly": "recommendRankList",    # 推荐榜
    "monthly": "monthTicketRankList", # 月票榜
}

# Default to the most-popular list (月票榜) when period is unknown.
_DEFAULT_RANK_LIST = "monthTicketRankList"


# ---------------------------------------------------------------------------
# Nuxt SSR __NUXT__ payload parser
# ---------------------------------------------------------------------------
#
# Reuses the same approach as scripts.adapters.qimao. Copied here (rather
# than imported) to keep the adapter self-contained and avoid coupling on
# the qimao adapter's internal helpers.

def _scan_balanced(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """Find the matching ``close_ch`` for the ``open_ch`` at ``text[start]``.

    Returns -1 if not found. Tracks string state and escape sequences so
    braces inside quoted keys/values don't confuse the depth counter.
    """
    if start >= len(text) or text[start] != open_ch:
        return -1
    depth = 1
    i = start + 1
    in_str: Optional[str] = None
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


def _split_top_level_csv(text: str) -> list[str]:
    """Split at top-level commas (no nesting inside brackets/parens/braces)."""
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    in_str: Optional[str] = None
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


def _parse_nuxt_payload(html: str) -> dict[str, Any]:
    """Parse the ``__NUXT__`` expression from a Nuxt SSR page (no Node.js).

    The payload is::

        window.__NUXT__=(function(a,b,c,...){return {...}})(val1,val2,...);

    The function body uses single-letter identifier references to values
    passed as call args. We substitute identifier references with their
    JSON values and ``json.loads`` the result. See scripts/adapters/qimao
    for a more commented version of the same algorithm.
    """
    marker = "window.__NUXT__"
    m = html.find(marker)
    if m < 0:
        return {}
    fn_start = html.find("(function(", m)
    if fn_start < 0:
        return {}
    args_open = fn_start + len("(function")
    args_close = _scan_balanced(html, args_open, "(", ")")
    if args_close < 0:
        return {}
    args_decl = html[args_open + 1: args_close]
    body_open = html.find("{", args_close)
    if body_open < 0:
        return {}
    body_close = _scan_balanced(html, body_open, "{", "}")
    if body_close < 0:
        return {}
    body = html[body_open + 1: body_close]
    call_open = html.find("(", body_close)
    if call_open < 0:
        return {}
    call_close = _scan_balanced(html, call_open, "(", ")")
    if call_close < 0:
        return {}

    arg_names = [a.strip() for a in args_decl.split(",") if a.strip()]
    call_args_text = html[call_open + 1: call_close]

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

    # Identifier substitution — string-aware so quoted keys like
    # ``"data-v-cca2d2e4":0`` aren't touched.
    out_parts: list[str] = []
    i = 0
    in_str: Optional[str] = None
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

    # Quote bare JS keys (layout: -> "layout":).
    def _quote_bare_keys(s: str) -> str:
        out: list[str] = []
        i = 0
        in_str: Optional[str] = None
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

    stripped = substituted.strip()
    if stripped.startswith("return "):
        stripped = stripped[len("return "):].lstrip()

    quoted = _quote_bare_keys(stripped)
    try:
        parsed = json.loads(quoted)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _serial_status_to_literal(value: Any) -> Optional[str]:
    """Map zongheng ``serialStatus`` (0=serial, 1=completed) to our enum."""
    if value is None:
        return None
    if value in (1, "1", "完结", "已完结"):
        return "completed"
    if value in (0, "0", "连载", "连载中"):
        return "serial"
    return None


def _extract_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_rank_no(value: Any, fallback: int) -> int:
    """``rankNo`` may arrive as int or string (or be absent). Use it if
    available, otherwise fall back to the list position."""
    as_int = _extract_int(value)
    return as_int if as_int is not None and as_int > 0 else fallback


def parse_rank_payload(html: str, top: int, period: str) -> list[RawBook]:
    """Parse the Nuxt SSR payload and return up to ``top`` books for ``period``.

    Locates ``state.rank.popularityRank`` in the payload, picks the
    period-appropriate list, and projects each row into ``RawBook``.
    """
    data = _parse_nuxt_payload(html)
    rank_block = (
        data.get("state", {}).get("rank", {}).get("popularityRank", {})
    )
    if not isinstance(rank_block, dict):
        return []

    rank_list_key = PERIOD_TO_RANK_LIST.get(period, _DEFAULT_RANK_LIST)
    rows = rank_block.get(rank_list_key) or []
    if not isinstance(rows, list):
        return []

    out: list[RawBook] = []
    for idx, row in enumerate(rows[:top]):
        if not isinstance(row, dict):
            continue
        book_id = str(row.get("bookId") or "")
        if not book_id:
            continue
        detail_url = f"{_BASE}/book/{book_id}/"
        author_id = _extract_int(row.get("authorId"))
        cover_url = row.get("imageUrl") or None
        word_count = _extract_int(row.get("totalWords"))
        status = _serial_status_to_literal(row.get("serialStatus"))
        rank_pos = _normalize_rank_no(row.get("rankNo"), idx + 1)
        out.append(
            RawBook(
                platform_book_id=book_id,
                title=str(row.get("bookName") or ""),
                author=str(row.get("authorName") or ""),
                category=str(row.get("cateFineName") or ""),
                intro=str(row.get("description") or ""),
                word_count=word_count,
                status=status,  # type: ignore[arg-type]
                cover_url=cover_url,
                detail_url=detail_url,
                rank_position=rank_pos,
                raw_payload={
                    "source": "zongheng.com",
                    "rank_list_key": rank_list_key,
                    "author_id": author_id,
                    "number": row.get("number"),
                    "numberDesc": row.get("numberDesc"),
                    "cateFineId": row.get("cateFineId"),
                },
            )
        )
    return out


class ZonghengAdapter(BaseAdapter):
    platform = "zongheng"
    strategy = Strategy.WEBFETCH

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        """Fetch zongheng rank list via the public /rank Nuxt SSR page.

        ``category`` is accepted for interface compatibility with the
        orchestrator's ``(category, period, top)`` signature but is
        ignored — zongheng's Nuxt SSR page does not support per-category
        rank filtering at the URL level. (The site uses a category
        sub-nav that requires JS to switch.)
        """
        resp = httpx.get(_RANK_URL, headers=_HEADERS, timeout=30.0)
        resp.raise_for_status()
        return parse_rank_payload(resp.text, top=top, period=period)