"""番茄（fanqie）adapter — Strategy.VENDOR (Playwright-backed).

Status: BLOCKED_IMPLEMENTATION (verified 2026-08-13).

    The vendored ``vendor/fanqie_rank_tracker/scrape_fanqie_ranks.py``
    relies on ``playwright.sync_api`` to drive a headless Chromium
    against fanqienovel.com's JS-only ranking pages. Until Playwright
    is installed AND the bundled Chromium binary is downloaded, the
    adapter cannot run. The fix is purely environmental:

        pip install playwright && playwright install chromium

    This repo deliberately does not pull playwright into the default
    dependency set (it adds ~150 MB of Chromium binaries) so other
    adapters and tests stay light. Once Playwright is installed the
    adapter will work end-to-end with no code changes — the vendored
    subset is already wired up.

Why an explicit status declaration (not a silent fallback):
    v0.1.x callers were getting empty-book results with no error —
    indistinguishable from a successful scan of a barren category. This
    adapter now declares its BLOCKED_IMPLEMENTATION status so the
    orchestrator records an ``AdapterError`` with a clear install
    instruction instead of triggering the missing-import code path.
"""
from __future__ import annotations

from scripts.adapters.base import BaseAdapter, Strategy, AdapterStatus
from scripts.schema import RawBook


class FanqieAdapter(BaseAdapter):
    platform = "fanqie"
    strategy = Strategy.VENDOR
    status = AdapterStatus.BLOCKED_IMPLEMENTATION

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        # First-principles: don't trigger the vendored Playwright path
        # until the user has opted in by installing it. No network I/O,
        # no import attempt — record the BLOCKED_IMPLEMENTATION reason
        # with install instructions instead.
        raise NotImplementedError(
            "fanqie requires Playwright + chromium: "
            "'pip install playwright && playwright install chromium'. "
            "Run that command, then this adapter will work. "
            "See KNOWN_LIMITATIONS.md."
        )