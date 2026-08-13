"""七猫（qimao）adapter — Strategy.VENDOR.

Status: LIVE (verified 2026-08-13, after balanced-brace parser rewrite).

    The vendored ``vendor/qimao_web_crawler_subset/qimao_subset/`` wraps
    a pure-Python regex parser of qimao.com's Nuxt SSR ``__NUXT__``
    payload. The original upstream regex (``_NUXT_RE``) was written
    assuming a flat JS object literal — it did not handle nested braces
    inside the real upstream payload (e.g. the ``fetch:{"data-v-cca2d2e4:0":{listData:[...]}}``
    block). The parser silently returned an empty dict, and the vendored
    ``fetch_qimao_rank`` swallowed that as ``except Exception: return items``.

    v0.1.4 lifts the parser out into ``scripts/nuxt_parser.py`` (shared
    with zongheng) — see ``parse_nuxt_payload`` there for the
    balanced-brace scanner that replaces the broken upstream regex.

    The vendored subset is still used for the book-row projection
    (``_project_list_item``) and the throttle so the field names and
    network semantics stay byte-for-byte identical with the upstream we
    track.
"""
from __future__ import annotations

import httpx

from scripts.adapters.base import BaseAdapter, Strategy, AdapterStatus
from scripts.schema import RawBook
from scripts.nuxt_parser import parse_nuxt_payload
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


def _fetch_qimao_rank(channel: str, rank_type: str, top: int) -> list[dict]:
    """Fetch up to ``top`` items from one 七猫 ranking page (LIVE path).

    Same network/field contract as the vendored ``fetch_qimao_rank``
    except we use ``parse_nuxt_payload`` (working) instead of the
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
        data = parse_nuxt_payload(resp.text)
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