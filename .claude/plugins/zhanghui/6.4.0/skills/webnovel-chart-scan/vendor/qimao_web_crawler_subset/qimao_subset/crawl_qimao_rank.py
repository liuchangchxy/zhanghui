"""七猫小说榜单爬虫 — slim subset.

Vendored and lightly refactored from
``staysharp1104/WebCrawler/crawlers/qimao.py::QimaoCrawler.crawl_rankings``
(2026-08-12). The original method depends on the upstream's
``config.REQUEST_TIMEOUT`` constant, the project's ``BaseCrawler.delay()``
helper, the ``requests`` library, and a Node.js subprocess to parse the
``__NUXT__`` JavaScript expression.

This subset is self-contained:
  - No selenium/chromedriver (those were only used by ``crawl_book_info``,
    which we don't call).
  - No ``config.py`` / DB / task queue.
  - HTTP via ``httpx`` (the project's chosen HTTP layer — field names and
    URL grammar are unchanged from upstream; only the transport differs).
  - ``__NUXT__`` is parsed by a small recursive descent over the wrapped
    expression so we don't need a Node.js runtime.

Field names match the upstream verbatim — see the adapter's
``parse_qimao_rank`` for the full contract.
"""
from __future__ import annotations

import json
import re
import time
import random
from typing import Any

import httpx


QIMAO_DOMAIN = "https://www.qimao.com"

QIMAO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": QIMAO_DOMAIN,
}

# (channelType value, Chinese label)
CHANNEL_TYPES: list[tuple[str, str]] = [
    ("boy", "男生"),
    ("girl", "女生"),
]

# (rankType value, Chinese label)
RANK_TYPES: list[tuple[str, str]] = [
    ("hot", "大热榜"),
    ("new", "新书榜"),
    ("over", "完结榜"),
    ("collect", "收藏榜"),
    ("update", "更新榜"),
]

COVER_URL_TPL = (
    "https://cdn.qimao.com/bookimg/zww/upload/readerCover/68/{}_360x480.jpg"
)
REQUEST_TIMEOUT = 30


# ---------------------------------------------------------------------------
# __NUXT__ parsing (replaces upstream's Node.js subprocess)
# ---------------------------------------------------------------------------

# Match the function-wrapped payload that Nuxt SSR injects:
#   window.__NUXT__=(function(a,b,c,...){return {...}})(val1,val2,...)
# We capture (1) the formal parameter list and (2) the call-arg list so we
# can substitute each ``a``/``b``/... back into the returned object.
_NUXT_RE = re.compile(
    r"window\.__NUXT__\s*=\s*\(function\(([^)]*)\)\s*\{([^}]*)\}\)\(([\s\S]*?)\)\s*;?",
    re.S,
)


def _parse_nuxt_html(html: str) -> dict[str, Any]:
    """Parse the ``__NUXT__`` expression from a Nuxt SSR page (no Node.js).

    Upstream invokes ``node -e`` to evaluate the function wrapper because the
    inner expression can be arbitrarily complex JavaScript. In practice,
    七猫's ranking pages return data shaped as a JSON-serializable Python
    dict (lists, dicts, strings, numbers, booleans, null) — the wrapper is
    just there to defer ``JSON.stringify`` until the client hydrates.

    We:
      1. Extract the formal-arg list and the call-arg list.
      2. Run Python's ``json.loads`` on each call-arg (they are literal
         JSON values, not JS object literals).
      3. Substitute ``a``/``b``/... in the return-object source.
      4. ``json.loads`` the substituted result.
    """
    m = _NUXT_RE.search(html)
    if not m:
        return {}
    args_decl, body, call_args = m.groups()
    arg_names = [a.strip() for a in args_decl.split(",") if a.strip()]
    arg_values: list[Any] = []
    for piece in _split_top_level_csv(call_args):
        piece = piece.strip()
        if not piece:
            continue
        try:
            arg_values.append(json.loads(piece))
        except json.JSONDecodeError:
            return {}
    table = dict(zip(arg_names, arg_values))

    # Substitute every ``NAME`` reference that appears as a standalone
    # identifier with its JSON value. We deliberately avoid touching
    # identifiers inside strings — the regex below requires a word-boundary
    # context (no leading/trailing identifier character).
    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in table:
            return json.dumps(table[name], ensure_ascii=False)
        return match.group(0)

    substituted = re.sub(r"\b([A-Za-z_$][\w$]*)\b", _sub, body)
    try:
        parsed = json.loads(substituted)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _split_top_level_csv(text: str) -> list[str]:
    """Split at top-level commas (no nesting inside brackets/parens/braces)."""
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


# ---------------------------------------------------------------------------
# Item extraction (verbatim field names from upstream)
# ---------------------------------------------------------------------------


def _make_cover_url(original_book_id: str) -> str:
    return COVER_URL_TPL.format(original_book_id)


def _extract_book_id(book_url: str) -> str:
    m = re.search(r"/shuku/(\d+)", book_url)
    return m.group(1) if m else ""


def _project_list_item(
    bk: dict[str, Any],
    ch_label: str,
    rank_label: str,
) -> dict[str, Any] | None:
    """Project one upstream ``listData`` row into the upstream-shaped item dict.

    Returns ``None`` if ``book_id`` is missing (filtered out upstream).
    """
    bid = str(bk.get("book_id", ""))
    if not bid:
        return None

    is_over = bk.get("is_over", "0")
    status = "完结" if is_over == "1" else "连载"

    cat1 = bk.get("category1_name", "")
    cat2 = bk.get("category2_name", "")
    category_label = f"{ch_label}"
    if cat1:
        category_label = f"{cat1}"
    if cat2:
        category_label = f"{cat1}/{cat2}"
    category_label = f"{category_label}/{rank_label}"

    cover = bk.get("image_link", "")
    if not cover:
        orig_id = bk.get("original_book_id", "")
        if orig_id:
            cover = _make_cover_url(orig_id)

    return {
        "book_id": f"qimao_{bid}",
        "rank": "",  # filled by fetch_qimao_rank so we have the global rank
        "title": bk.get("title", "").strip(),
        "author": bk.get("author", ""),
        "book_url": bk.get(
            "book_url", f"{QIMAO_DOMAIN}/shuku/{bid}/"
        ),
        "description": bk.get("intro", "").strip(),
        "status": status,
        "reader_count": str(bk.get("number", "")),
        "category_label": category_label,
        "cover_url": cover,
        "source": "qimao",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_qimao_rank(channel: str = "boy", rank_type: str = "hot", top: int = 10) -> list[dict]:
    """Fetch up to ``top`` items from one 七猫 ranking page.

    Args:
        channel: ``"boy"`` (男生) or ``"girl"`` (女生).  Upstream uses these
            two channels and there is no single "all" channel at the URL
            level — caller iterates both channels separately.
        rank_type: one of ``"hot"``/``"new"``/``"over"``/``"collect"``/``"update"``
            (the upstream's 5 榜单枚举).
        top: maximum items to return. Upstream also pages by ``rank_type``
            group only — no pagination within a single ``rank_type`` page.

    Returns:
        A list of upstream-shaped item dicts (see module docstring).

    Notes:
        - 0 (or empty) is returned on any HTTP / parse failure rather than
          raising, mirroring the upstream's per-channel error tolerance.
        - The ``rank`` field is the global rank across channels returned,
          i.e. ``1..total`` in returned order. (Upstream's loop concatenates
          all channels and re-stamps ``rank`` as ``str(len(results)+1)``.)
    """
    ch_label = next(
        (label for c, label in CHANNEL_TYPES if c == channel), "男生"
    )
    rank_label = next(
        (label for r, label in RANK_TYPES if r == rank_type), "大热榜"
    )

    url = (
        f"{QIMAO_DOMAIN}/paihang"
        f"?channelType={channel}&rankType={rank_type}"
    )

    items: list[dict] = []
    try:
        resp = httpx.get(
            url, headers=QIMAO_HEADERS, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        data = _parse_nuxt_html(resp.text)
        if not data:
            return []

        # Find the ``listData`` key in any value of ``fetch`` (Nuxt SSR
        # uses synthetic keys like ``"data-v-cca2d2e4:0"``).
        fetch_block = data.get("fetch", {})
        list_data: list[dict] | None = None
        for val in fetch_block.values():
            if isinstance(val, dict) and "listData" in val:
                list_data = val["listData"]
                break
        if not list_data:
            return []

        for bk in list_data[:top]:
            projected = _project_list_item(bk, ch_label, rank_label)
            if projected is None:
                continue
            projected["rank"] = str(len(items) + 1)
            items.append(projected)
    except Exception:
        return items

    # Throttle like upstream (0.5 base, with jitter) to be polite.
    time.sleep(0.5 * random.uniform(0.8, 1.5))
    return items
