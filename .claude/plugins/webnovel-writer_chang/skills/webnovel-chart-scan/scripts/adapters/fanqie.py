"""番茄（fanqie）adapter — Strategy.VENDOR (Playwright-backed).

Status: BLOCKED_IMPLEMENTATION (verified 2026-08-13).

    The vendored ``vendor/fanqie_rank_tracker/scrape_fanqie_ranks.py``
    relies on ``playwright.sync_api`` to drive a headless Chromium
    against fanqienovel.com's JS-only ranking pages.

    Two problems:

    1. Even with Playwright installed and Chromium downloaded, the
       vendored ``run_scraper`` is a site-wide crawl that dumps a single
       JSON covering every 男频/女频/阅读榜/新书榜 category. It does not
       match our per-``(category, period, top)`` API.

    2. ``fetch()`` therefore raises ``RuntimeError`` even when the user
       has done the env setup. That is exactly what
       ``BLOCKED_IMPLEMENTATION`` is for: a code-side gap that needs a
       thin adapter over ``run_scraper`` (read the dump, slice by
       category + period + top) — see ``KNOWN_LIMITATIONS.md`` and the
       v0.2 work item.

    The previous ``LIVE_WITH_SETUP`` label was misleading because the
    RuntimeError fires with OR without Playwright — it is not a one-time
    setup issue. v0.1.4 relabels this adapter honestly.

This repo deliberately does not pull playwright into the default
dependency set (it adds ~150 MB of Chromium binaries) so other adapters
and tests stay light.
"""
from __future__ import annotations

from scripts.adapters.base import BaseAdapter, Strategy, AdapterStatus
from scripts.schema import RawBook


class FanqieAdapter(BaseAdapter):
    platform = "fanqie"
    strategy = Strategy.VENDOR
    status = AdapterStatus.BLOCKED_IMPLEMENTATION

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        # The orchestrator short-circuits on BLOCKED_IMPLEMENTATION, so
        # this body is dead code at runtime — but we keep the install
        # hint for clarity in case future code paths invoke fetch()
        # directly (e.g. a maintenance script).
        try:
            from vendor.fanqie_rank_tracker import scrape_fanqie_ranks as _v  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "fanqie adapter needs Playwright. To enable:\n"
                "  1. pip install playwright\n"
                "  2. playwright install chromium\n"
                "Then the BLOCKED_IMPLEMENTATION work item below still\n"
                "needs the thin per-(category, period, top) adapter.\n"
                "See KNOWN_LIMITATIONS.md."
            ) from e
        # Playwright IS installed. The vendored ``run_scraper`` is a
        # site-wide crawl that dumps a single JSON file covering every
        # 男频/女频/阅读榜/新书榜 category; it does not fit our
        # per-(category, period, top) signature. We need a thin adapter
        # that reads the dump and slices it — v0.2 work item.
        raise RuntimeError(
            "fanqie vendored run_scraper is site-wide and does not "
            "match per-(category, period, top) signature. v0.2 work "
            "item: read the dump file (vendor/fanqie_rank_tracker/data/"
            "fanqie_all_ranks_YYYYMMDD.json) and slice by category. "
            "See KNOWN_LIMITATIONS.md."
        )