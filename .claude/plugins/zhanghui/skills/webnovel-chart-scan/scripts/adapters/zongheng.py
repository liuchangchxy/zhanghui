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

    We use the shared balanced-brace + identifier-substitution Nuxt
    parser at ``scripts/nuxt_parser.py`` (also used by
    ``scripts.adapters.qimao``) and pick the right list for the
    requested period.

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

from typing import Any, Optional

import httpx

from scripts.adapters.base import BaseAdapter, Strategy
from scripts.nuxt_parser import parse_nuxt_payload
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
# v0.1.4 refactor: the parser logic was lifted out into
# ``scripts/nuxt_parser.py`` and is shared with ``scripts.adapters.qimao``
# (was duplicated verbatim in both adapters before this change). The
# Nuxt SSR parsing algorithm itself is unchanged.


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
    data = parse_nuxt_payload(html)
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