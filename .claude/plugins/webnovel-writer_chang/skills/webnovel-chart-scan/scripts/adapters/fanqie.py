"""番茄（fanqie）adapter — Strategy.DIRECT_DUMP (GitHub raw JSON).

Status: LIVE_WITH_SETUP (verified 2026-08-16).

    Instead of running vendored ``run_scraper`` (which requires Playwright
    + Chromium and produces a site-wide JSON dump taking 30+ minutes),
    we fetch the upstream's **already-produced** daily dump directly from
    GitHub raw:

        https://raw.githubusercontent.com/Despacito0o/FanqieRankTracker/master/
            data/fanqie_all_ranks_YYYYMMDD.json

    Upstream's GitHub Actions cron (08:00 Beijing time daily) drives
    ``run_scraper`` against the live site, producing ~2MB JSON files
    covering 74 (category, channel) groups × 20 books each. We piggyback
    on that work — no Chromium, no Playwright, no slow batch.

    The dump uses fanqie-native subcategory names (西方奇幻, 都市修真,
    etc.) which we map to our normalized main categories via
    ``fanqie_subcat_map.SUBCAT_TO_NORMALIZED``.

    Caching: dump is cached at ``~/.cache/webnovel-chart-scan/fanqie_dump_<date>.json``
    so repeat calls on the same day don't re-download. Cache key is the
    dump date (UTC), so first call each day incurs one ~2MB download.

    period parameter: the dump represents "today's snapshot" — there is
    no per-period breakdown (no separate daily/weekly/monthly dumps).
    The adapter accepts the ``period`` arg for API compatibility but
    ignores it (logged as a comment in the RawBook.raw_payload for
    traceability).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

from scripts.adapters.base import BaseAdapter, Strategy, AdapterStatus
from scripts.adapters.fanqie_subcat_map import map_subcategory
from scripts.schema import RawBook

logger = logging.getLogger(__name__)


# Upstream dump URL — FanqieRankTracker's GitHub Actions cron produces these
# daily at 08:00 Beijing time. We pick the latest available date that is
# <= today UTC (so if today's dump isn't published yet, we fall back to
# yesterday's).
DUMP_BASE_URL = (
    "https://raw.githubusercontent.com/Despacito0o/FanqieRankTracker/"
    "master/data/fanqie_all_ranks_{date}.json"
)
CACHE_DIR = Path.home() / ".cache" / "webnovel-chart-scan"
REQUEST_TIMEOUT = 60.0  # 2MB JSON over GitHub raw — generous timeout


def _download_dump(date_str: str) -> dict:
    """Download the dump for ``date_str`` (YYYYMMDD), with local cache.

    Cache: ``~/.cache/webnovel-chart-scan/fanqie_dump_<date_str>.json``.
    If cache hit, skip HTTP. If cache miss + HTTP 404, raise FileNotFoundError
    so the caller can step back one day.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"fanqie_dump_{date_str}.json"
    if cache_file.exists():
        logger.info("fanqie dump cache hit: %s", cache_file)
        return json.loads(cache_file.read_text(encoding="utf-8"))

    url = DUMP_BASE_URL.format(date=date_str)
    logger.info("fanqie dump downloading: %s", url)
    resp = httpx.get(url, timeout=REQUEST_TIMEOUT)
    if resp.status_code == 404:
        raise FileNotFoundError(f"fanqie dump not published yet for {date_str}: {url}")
    resp.raise_for_status()
    cache_file.write_text(resp.text, encoding="utf-8")
    return json.loads(resp.text)


def parse_dump_to_rawbooks(
    dump: dict,
    category: str,
    period: str,
    top: int,
) -> list[RawBook]:
    """Slice the dump by ``category`` and return up to ``top`` RawBook rows.

    Args:
        dump: parsed JSON from fanqie_all_ranks_*.json
        category: our normalized main category (玄幻/都市/...) or 'all'
        period: accepted for API compat but ignored (dump is snapshot)
        top: max books to return

    Returns:
        list of RawBook ordered by dump's natural order (top-of-rank first).
        rank_position is 1-based per (category, subcategory) tuple.
    """
    raw_books: list[RawBook] = []

    for cat_entry in dump.get("categories", []):
        subcat_name = cat_entry.get("name", "")
        normalized = map_subcategory(subcat_name)

        # Filter by requested category (unless 'all')
        if category != "all" and normalized != category:
            continue

        for rank_idx, book in enumerate(cat_entry.get("books", []), start=1):
            url = book.get("url", "")
            # platform_book_id is the numeric id from /page/<id>
            platform_book_id = url.rsplit("/", 1)[-1] if url else ""
            raw_books.append(RawBook(
                platform_book_id=platform_book_id,
                title=book.get("title", "").strip(),
                author=book.get("author", "").strip(),
                category=normalized,
                # word_count not available in dump — leave None (KNOWN data gap)
                word_count=None,
                detail_url=url,
                rank_position=rank_idx,
                raw_payload={
                    "subcategory": subcat_name,
                    "reads": book.get("reads", ""),  # e.g. "43万"
                    "intro": book.get("intro", "").strip(),
                    "cover": book.get("cover", ""),
                    "period": period,  # echoed back for trace; ignored upstream
                },
            ))

            if len(raw_books) >= top:
                return raw_books

    return raw_books


class FanqieAdapter(BaseAdapter):
    platform = "fanqie"
    strategy = Strategy.DIRECT_DUMP  # NEW strategy value, added in Task 5
    status = AdapterStatus.LIVE_WITH_SETUP  # needs network to GitHub raw

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        # Step back at most 3 days if today's dump isn't published yet
        base_date = datetime.now(timezone.utc)
        for days_back in range(3):
            date_str = (base_date - timedelta(days=days_back)).strftime("%Y%m%d")
            try:
                dump = _download_dump(date_str)
                return parse_dump_to_rawbooks(dump, category, period, top)
            except FileNotFoundError as e:
                logger.warning("fanqie dump for %s not available, stepping back: %s", date_str, e)
                continue
        # All 3 days failed — surface a clear error (orchestrator catches this)
        raise RuntimeError(
            "fanqie dump not available for the last 3 days. "
            "Check network or GitHub upstream status. "
            "See https://github.com/Despacito0o/FanqieRankTracker/tree/master/data"
        )
