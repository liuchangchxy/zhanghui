"""七猫（qimao）adapter — Strategy.VENDOR.

Wraps the vendored ``staysharp1104/WebCrawler`` ranking crawler under
``vendor/qimao_web_crawler_subset/qimao_subset/``. The slim subset is a
faithful refactor of the upstream ``QimaoCrawler.crawl_rankings`` method
(self-contained: no selenium, no DB, no Node.js — uses pure-Python regex
parsing of the Nuxt SSR ``__NUXT__`` wrapper).

Why VENDOR (not HYBRID):
    We genuinely ``import`` the upstream function ``fetch_qimao_rank`` and
    call it. We do not reimplement the SSR parsing or the
    channelType x rankType URL grammar in httpx.

Upstream's URL grammar (verified 2026-08-12):
    https://www.qimao.com/paihang?channelType={boy|girl}&rankType={hot|new|over|collect|update}

Upstream's output keys (verbatim from
``crawlers/qimao.py::QimaoCrawler.crawl_rankings``)::

    {
        "book_id":       "qimao_<bid>",     # always prefixed upstream
        "rank":          "<1-based row>",
        "title":         str,
        "author":        str,
        "book_url":      str,
        "description":   str,               # this is the book intro
        "status":        "完结" | "连载",
        "reader_count":  str,
        "category_label": str,             # "<ch>/<cat1>[/<cat2>]/<rank>"
        "cover_url":     str,
        "source":        "qimao",
    }

The Task-9 spec sample used the non-existent keys
``bookName``/``authorName``/``categoryName``/``bookId``/``rankNo``; we
follow the real upstream shape (see Task-7/8 review lesson "use real
upstream field names").

Strict policy (mirrors zongheng/fanqie):
    七猫 only exposes ``channelType`` x ``rankType`` at the URL level — there
    is NO way to request "玄幻" or "都市" alone without hacking the
    parameters. We refuse ``category != "all"`` loudly (NotImplementedError)
    instead of silently swallowing the value.

``period`` mapping (best-effort onto upstream's ``rank_type`` enum):
    daily   -> "hot"
    weekly  -> "collect"
    monthly -> "over"
    other   -> "hot"

    Upstream has no separate daily/weekly/monthly endpoint — these are
    loose semantic mappings, not strict contract.
"""
from __future__ import annotations

from typing import Optional

from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook


# Map our period -> upstream rank_type. 上游 RANK_TYPES =
# hot/new/over/collect/update. Choose the closest semantic match.
PERIOD_TO_RANK_TYPE = {
    "daily": "hot",
    "weekly": "collect",
    "monthly": "over",
}
DEFAULT_RANK_TYPE = "hot"


def parse_qimao_rank(raw_list: list[dict], top: int) -> list[RawBook]:
    """Map the upstream's per-book dicts to ``RawBook`` rows.

    Accepts the real upstream shape (keys: ``book_id``/``rank``/``title``/
    ``author``/``book_url``/``description``/``status``/``reader_count``/
    ``category_label``/``cover_url``/``source``).

    Notes for downstream consumers:
      - ``rank_position`` comes from upstream ``rank`` (1-based string).
        Falls back to 1-based list index if the upstream omits it (some
        fixtures and edge cases do).
      - ``platform_book_id`` uses the upstream's already-prefixed
        ``qimao_<bid>`` value verbatim. Stripping the prefix is left to
        consumers that want the bare numeric id.
      - ``status`` ("完结" / "连载") is mapped onto our ``STATUSES`` enum
        (``"completed"`` / ``"serial"``) when possible; left ``None`` if
        the upstream value is something unexpected.
    """
    books: list[RawBook] = []
    for i, item in enumerate(raw_list[:top]):
        if not isinstance(item, dict):
            continue

        # rank_position: prefer upstream ``rank``, else 1-based index.
        raw_rank = item.get("rank")
        if raw_rank is None or raw_rank == "":
            rank_position: Optional[int] = i + 1
        else:
            try:
                rank_position = int(raw_rank)
            except (TypeError, ValueError):
                rank_position = i + 1

        # status mapping (中文 -> enum).
        raw_status = item.get("status")
        status: Optional[str]
        if raw_status in ("完结", "completed"):
            status = "completed"
        elif raw_status in ("连载", "serial"):
            status = "serial"
        else:
            status = None

        books.append(
            RawBook(
                platform_book_id=str(item.get("book_id", "")),
                title=item.get("title", ""),
                author=item.get("author", ""),
                category=item.get("category_label", ""),
                intro=item.get("description", ""),
                cover_url=item.get("cover_url"),
                detail_url=item.get("book_url"),
                status=status,
                rank_position=rank_position,
                raw_payload=item,
            )
        )
    return books


class QimaoAdapter(BaseAdapter):
    platform = "qimao"
    strategy = Strategy.VENDOR

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        # Mirror zongheng/fanqie's strict policy: don't silently swallow
        # unsupported category values — fail loud so the caller knows to
        # fall back to category="all" until v0.2 refactors the upstream to
        # accept per-category params.
        if category != "all":
            raise NotImplementedError(
                f"qimao VENDOR does not support category='{category}'. "
                f"Upstream only exposes channelType x rankType at the URL "
                f"level; use category='all' and post-filter, or wait for v0.2."
            )

        # Lazy import: the vendored subset needs ``httpx`` (and we
        # don't want a missing install to break the rest of the skill).
        try:
            from vendor.qimao_web_crawler_subset.qimao_subset import fetch_qimao_rank
        except ImportError as e:  # pragma: no cover - exercised by test
            raise RuntimeError(
                "qimao adapter requires the httpx library. "
                "Install: pip install httpx"
            ) from e

        rank_type = PERIOD_TO_RANK_TYPE.get(period, DEFAULT_RANK_TYPE)

        # Upstream exposes two channels (男生/女生) and there is no way to
        # fetch both in one call without refactoring the vendored
        # subset's URL grammar. We call both and concatenate so the
        # caller sees the upstream-equivalent of "all categories".
        books: list[RawBook] = []
        for ch in ("boy", "girl"):
            raw = fetch_qimao_rank(channel=ch, rank_type=rank_type, top=top)
            books.extend(parse_qimao_rank(raw, top=top))
        return books
