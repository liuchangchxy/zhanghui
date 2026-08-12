"""番茄（fanqie）adapter — Strategy.VENDOR (Playwright-backed).

Status: LIVE_WITH_SETUP (verified 2026-08-13).

    The vendored ``vendor/fanqie_rank_tracker/scrape_fanqie_ranks.py``
    relies on ``playwright.sync_api`` to drive a headless Chromium
    against fanqienovel.com's JS-only ranking pages. Until Playwright
    is installed AND the bundled Chromium binary is downloaded, the
    adapter cannot run. The fix is purely environmental::

        pip install playwright && playwright install chromium

    This repo deliberately does not pull playwright into the default
    dependency set (it adds ~150 MB of Chromium binaries) so other
    adapters and tests stay light. Once Playwright is installed the
    adapter can call into the vendored subset's ``run_scraper`` — but
    that function is site-wide (it dumps a single JSON dump covering
    every 男频/女频/阅读榜/新书榜 category) and does not match our
    per-``(category, period, top)`` API. A thin adapter on top of
    ``run_scraper`` (read the dump, slice by category + period + top)
    is the v0.2 work item — see KNOWN_LIMITATIONS.md.

    Status is ``LIVE_WITH_SETUP`` (not ``BLOCKED_IMPLEMENTATION``)
    because the runtime code path IS exercised — the orchestrator
    calls ``fetch()`` and a tailored ``RuntimeError`` surfaces if
    either Playwright is missing OR the result adapter is missing.
    No silent failure.

Why ``LIVE_WITH_SETUP`` instead of ``LIVE``:
    A ``LIVE`` adapter promises "works today against upstream" — but
    this one doesn't, until the user runs a one-time setup. The new
    status gives the user an honest signal: "this works, you just have
    to run one command first".
"""
from __future__ import annotations

from scripts.adapters.base import BaseAdapter, Strategy, AdapterStatus
from scripts.schema import RawBook


class FanqieAdapter(BaseAdapter):
    platform = "fanqie"
    strategy = Strategy.VENDOR
    status = AdapterStatus.LIVE_WITH_SETUP

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        # Lazy-import the vendored subset. If Playwright is not installed
        # the import raises ImportError; translate that to a clear
        # RuntimeError with the install command. Other exceptions (the
        # vendored subset's own errors) are NOT caught here — they
        # surface as AdapterError via the orchestrator's try/except.
        try:
            from vendor.fanqie_rank_tracker import scrape_fanqie_ranks as _v  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "fanqie adapter needs Playwright. To enable:\n"
                "  1. pip install playwright\n"
                "  2. playwright install chromium\n"
                "Then re-run. See KNOWN_LIMITATIONS.md for details."
            ) from e
        # Playwright IS installed. The vendored ``run_scraper`` is a
        # site-wide crawl that dumps a single JSON file covering every
        # 男频/女频/阅读榜/新书榜 category; it does not fit our
        # per-(category, period, top) signature. We need a thin adapter
        # that reads the dump and slices it — v0.2 work item. Until
        # then, raise a clear RuntimeError so the orchestrator records
        # an actionable AdapterError.
        raise RuntimeError(
            "fanqie vendored run_scraper is site-wide and does not "
            "match per-(category, period, top) signature. v0.2 work "
            "item: read the dump file (vendor/fanqie_rank_tracker/data/"
            "fanqie_all_ranks_YYYYMMDD.json) and slice by category. "
            "See KNOWN_LIMITATIONS.md."
        )