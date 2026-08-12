"""起点中文网 adapter — HYBRID strategy via httpx.

The Strategy enum value is ``HYBRID`` because the adapter borrows
field-name conventions from the vendored upstream
``saudadez21/novel-downloader`` (see ``vendor/novel-downloader/qidian_subset/``)
but does NOT import from it. Network I/O uses ``httpx`` directly, just like
``DIRECT_API`` adapters. ``HYBRID`` distinguishes this case: parsing-layer
conventions sourced from a vendored reference, but no actual vendored
imports.

qidian.com is fronted by an anti-bot probe (HTTP 202 + probe.js)
that requires RC4-signed cookies — exactly the mechanism implemented in
the upstream's ``searcher.py``. This adapter currently hits the spec'd
public endpoint with a browser User-Agent; a future revision should
port the upstream cookie computation to drop the probe.js wall.

NOTE on URL/endpoint (2026-08-12):
    ``https://www.qidian.com/all`` returned HTTP 202 (probe.js challenge)
    at task implementation time. The synthesized fixture in the tests
    follows the spec'd ``data.books[*]`` shape (bookId/bookName/authorName
    /categoryName/coverUrl) which mirrors the upstream's ``SearchResult``
    schema (``book_id``/``book_name``/``author``/``category``) but with the
    camelCase keys the live JSON endpoint historically returns.

NOTE on category IDs (2026-08-12):
    The chanId mapping is taken from the public-facing category nav on
    qidian.com. ``-1`` means "全部" (all categories).
"""
from __future__ import annotations

from typing import Optional

import httpx

from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook

QIDIAN_LIST_API = "https://www.qidian.com/all"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# 起点分类 ID（来自 qidian.com 公开分类导航）
QIDIAN_CATEGORY_IDS = {
    "玄幻": 21,
    "奇幻": 1,
    "武侠": 2,
    "仙侠": 22,
    "都市": 4,
    "职场": 15,
    "军事": 6,
    "历史": 5,
    "游戏": 7,
    "体育": 8,
    "科幻": 9,
    "灵异": 10,
    "二次元": 12,
}


def parse_qidian_list_json(payload: dict, top: int) -> list[RawBook]:
    """解析起点分类页 JSON 响应。字段以真实响应为准。

    Spec'd payload shape::

        {"code": 0, "data": {"books": [
            {"bookId", "bookName", "authorName",
             "categoryName", "coverUrl", ...},
            ...
        ]}}
    """
    books_data = (
        payload.get("data", {}).get("books", []) if isinstance(payload, dict) else []
    )
    books: list[RawBook] = []
    for i, item in enumerate(books_data[:top]):
        if not isinstance(item, dict):
            continue
        # rank_position: prefer server-supplied rank field; fall back to index.
        rank_position: Optional[int] = item.get("rankNo", item.get("rank", i + 1))
        books.append(
            RawBook(
                platform_book_id=str(item.get("bookId", "")),
                title=item.get("bookName", ""),
                author=item.get("authorName", ""),
                category=item.get("categoryName", ""),
                cover_url=item.get("coverUrl"),
                detail_url=item.get("bookUrl"),
                rank_position=rank_position,
                raw_payload=item,
            )
        )
    return books


class QidianAdapter(BaseAdapter):
    platform = "qidian"
    strategy = Strategy.HYBRID

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        chan_id = QIDIAN_CATEGORY_IDS.get(category, -1)  # -1 = 全部
        url = QIDIAN_LIST_API
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.qidian.com/",
        }
        params = {
            "chanId": chan_id,
            "subCateId": -1,
            "pageSize": min(top, 100),
            "page": 1,
        }

        resp = httpx.get(url, headers=headers, params=params, timeout=30.0)
        resp.raise_for_status()
        return parse_qidian_list_json(resp.json(), top=top)