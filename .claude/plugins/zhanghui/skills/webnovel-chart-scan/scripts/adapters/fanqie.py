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

    Data lag: up to ~24h, depending on the user's timezone vs Beijing
    publish time. Upstream's GitHub Actions cron publishes the dump at
    08:00 Beijing (UTC+8) every day, so e.g. users in UTC run with ~16h
    lag (next-day Beijing publish -> current-day UTC fetch) while users
    in Beijing itself have ~0h lag right after 08:00 local.

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

# How many days back to try when today's dump isn't available yet.
# 3 covers typical upstream cron-delay windows; bump higher if upstream
# flakes longer.
MAX_FALLBACK_DAYS = 3


def _download_dump(date_str: str) -> dict:
    """Download the dump for ``date_str`` (YYYYMMDD), with local cache.

    Cache: ``~/.cache/webnovel-chart-scan/fanqie_dump_<date_str>.json``.
    If cache hit, skip HTTP. If cache hit but the file is corrupted
    (JSONDecodeError), delete and re-download. If HTTP 404, raise
    FileNotFoundError so the caller can step back one day.

    The HTTP body is parsed BEFORE being written to cache, so if
    upstream returns non-JSON (e.g. an HTML error page) we never
    persist a bad cache file — the next call retries from upstream.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"fanqie_dump_{date_str}.json"
    if cache_file.exists():
        logger.info("fanqie dump cache hit: %s", cache_file)
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            # Corrupted cache file (truncated download, manual edit,
            # partial write on crash). Wipe and fall through to HTTP.
            logger.warning(
                "fanqie cache file %s is corrupted (%s); deleting and "
                "re-downloading from upstream",
                cache_file, e,
            )
            try:
                cache_file.unlink()
            except OSError as unlink_err:
                logger.warning(
                    "failed to delete corrupted cache file %s: %s",
                    cache_file, unlink_err,
                )

    url = DUMP_BASE_URL.format(date=date_str)
    logger.info("fanqie dump downloading: %s", url)
    resp = httpx.get(url, timeout=REQUEST_TIMEOUT)
    if resp.status_code == 404:
        raise FileNotFoundError(f"fanqie dump not published yet for {date_str}: {url}")
    resp.raise_for_status()

    # Detect non-JSON 200 OK (upstream occasionally returns an HTML
    # error page or a Cloudflare challenge with a 200 status).
    # Without this guard, json.loads() would raise a cryptic error.
    stripped = resp.text.lstrip()
    if not stripped or stripped[0] not in "{[":
        raise RuntimeError(
            f"fanqie upstream returned non-JSON (Content-Type: "
            f"{resp.headers.get('content-type')!r}, "
            f"first 200 chars: {resp.text[:200]!r})"
        )

    # Parse BEFORE writing to cache: if json.loads raises (e.g. the
    # body is JSON-look-alike but malformed), no cache file is left
    # behind and the next call retries from upstream.
    data = json.loads(resp.text)
    cache_file.write_text(resp.text, encoding="utf-8")
    return data


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
                    # echoed user arg, NOT upstream data — upstream
                    # has no per-period breakdown; ignored. See
                    # KNOWN_LIMITATIONS.md "Known Data Gaps".
                    "period_arg": period,
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
        # Step back at most MAX_FALLBACK_DAYS days if today's dump
        # isn't published yet OR a transient network/HTTP error occurs.
        base_date = datetime.now(timezone.utc)
        for days_back in range(MAX_FALLBACK_DAYS):
            date_str = (base_date - timedelta(days=days_back)).strftime("%Y%m%d")
            try:
                dump = _download_dump(date_str)
            except FileNotFoundError as e:
                # Upstream hasn't published for this date yet — try
                # an earlier day.
                logger.warning(
                    "fanqie dump for %s not available, stepping back: %s",
                    date_str, e,
                )
                continue
            except (httpx.HTTPError, httpx.RequestError) as e:
                # Transient network / protocol error — treat like a
                # 404 and step back a day. After MAX_FALLBACK_DAYS
                # of failures we surface a clear error.
                logger.warning(
                    "fanqie HTTP error for %s, stepping back: %s",
                    date_str, e,
                )
                continue

            # Validate that the dump actually has categories. An empty
            # ``categories`` list (upstream may publish a partial dump
            # after a category rename) is treated like a 404 so the
            # fallback loop can find yesterday's full dump.
            if not dump.get("categories"):
                logger.warning(
                    "fanqie dump for %s has empty categories list, "
                    "stepping back",
                    date_str,
                )
                continue

            return parse_dump_to_rawbooks(dump, category, period, top)

        # All MAX_FALLBACK_DAYS attempts failed — surface a clear error
        # (orchestrator catches this and reports to the user).
        raise RuntimeError(
            f"fanqie dump not available for the last "
            f"{MAX_FALLBACK_DAYS} days. Check network or GitHub upstream "
            f"status. See "
            f"https://github.com/Despacito0o/FanqieRankTracker/tree/master/data"
        )