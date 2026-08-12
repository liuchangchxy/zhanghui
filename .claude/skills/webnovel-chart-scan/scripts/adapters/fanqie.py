"""番茄（fanqie）adapter — Strategy.VENDOR (Playwright-backed).

This adapter wraps the vendored ``Despacito0o/FanqieRankTracker`` scrape
script under ``vendor/fanqie_rank_tracker/``. The upstream script
launches a headless Chromium (via ``playwright.sync_api``) to render
fanqienovel.com's JS-driven ranking pages, then walks every
male/female × reading/new-board category and writes a daily JSON
snapshot.

Why VENDOR (not HYBRID):
    We genuinely ``import`` the upstream function ``run_scraper`` and
    call it. We do not reimplement the JS rendering in httpx — the
    fanqie site is JS-only and would not work any other way.

Playwright is the only heavyweight dependency in the whole project
(it requires Chromium, ~150 MB). It is therefore installed lazily:
``fetch()`` only fails if you actually try to scrape. Importing this
module is free.

NOTE on the upstream's API (2026-08-12):
    - Entry function is ``run_scraper(limit=30, sleep_sec=5)``. There is
      no ``scrape_fanqie_ranks`` symbol and no per-category parameter;
      it always scrapes all 4 tabs (男频阅读榜/男频新书榜/女频阅读榜/女频新书榜)
      across every category, throttled by ``sleep_sec`` between calls.
      The full run takes minutes.
    - The output is a ``dict`` with shape::

            {"date": "YYYY-MM-DD",
             "categories": [
                 {"name": "西方奇幻", "books": [
                     {"title", "author", "reads",
                      "intro", "cover", "url"},
                     ...
                 ]},
                 ...]}

      Each category contains up to ``limit`` books.
    - Field names differ from the Task-8 spec sample (which used
      ``bookName``/``bookId``/``category``/``rank``). The real
      upstream output uses ``title``/``author``/``reads``/``intro``/
      ``cover``/``url``; the category name lives one level up on the
      parent dict. We follow the real shape (see Task-7 review lesson
      "use real field names when possible").

What this adapter does today:
    Calls ``run_scraper`` with ``limit=top`` and flattens every
    category's books into ``RawBook`` entries, stamping the category
    name from the parent. ``category`` must be ``"all"`` (the upstream
    scrapes every category in one batch; we cannot filter to a single
    one without refactoring upstream). ``period`` is accepted but
    unused — fanqie has no separate daily/weekly/monthly endpoint and
    the upstream always scrapes today's state.
"""
from __future__ import annotations

from typing import Optional

from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook


def parse_fanqie_rank_list(
    raw_list: list[dict], top: int, category: str = ""
) -> list[RawBook]:
    """Map the upstream's per-book dicts to ``RawBook`` rows.

    Accepts the real upstream shape (keys: ``title``/``author``/``reads``/
    ``intro``/``cover``/``url``). If the caller passes a flat list
    detached from any category, ``category`` defaults to "".

    Note: the upstream output also has a top-level ``category`` key per
    item in the parent ``categories[*]`` dict, not per book. We let the
    adapter stamp that at flatten time.
    """
    books: list[RawBook] = []
    for i, item in enumerate(raw_list[:top]):
        if not isinstance(item, dict):
            continue
        # rank_position falls back to list index (real upstream has no
        # rank field — the upstream just takes the first ``limit`` books
        # in DOM order, which IS the displayed rank).
        rank_position: Optional[int] = item.get("rank", i + 1)
        # platform_book_id: upstream only has a detail URL; extract the
        # last path segment as a stable-ish identifier. Falls back to ""
        # if no URL is present.
        url = item.get("url") or ""
        platform_book_id = url.rstrip("/").split("/")[-1] if url else ""
        books.append(
            RawBook(
                platform_book_id=platform_book_id,
                title=item.get("title", ""),
                author=item.get("author", ""),
                category=category,
                intro=item.get("intro", ""),
                cover_url=item.get("cover"),
                detail_url=url or None,
                rank_position=rank_position,
                raw_payload=item,
            )
        )
    return books


class FanqieAdapter(BaseAdapter):
    platform = "fanqie"
    strategy = Strategy.VENDOR

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        # Mirror zongheng's strict policy: don't silently swallow
        # unsupported category/period values — fail loud so the caller
        # knows to fall back to category="all" until v0.2 refactors the
        # upstream to accept per-category params.
        if category != "all":
            raise NotImplementedError(
                f"fanqie VENDOR does not support category='{category}'. "
                f"Upstream scrapes every category in one batch; "
                f"use category='all' and post-filter, or wait for v0.2."
            )

        # Lazy import: Playwright is heavy (Chromium download), and we
        # don't want a missing install to break the rest of the skill.
        try:
            from vendor.fanqie_rank_tracker.scrape_fanqie_ranks import (
                run_scraper,
            )
        except ImportError as e:  # pragma: no cover - exercised by test
            raise RuntimeError(
                "fanqie adapter requires Playwright. "
                "Install: pip install playwright && playwright install chromium"
            ) from e

        # NOTE: run_scraper ignores ``period`` — it scrapes ALL
        # categories and ALL four tabs in one slow batch. We just slice
        # the result down to ``top`` per category. This is faithful to
        # what the upstream gives us today; a future revision could
        # refactor the upstream to take per-category params.
        snapshot = run_scraper(limit=top, sleep_sec=5)

        books: list[RawBook] = []
        for cat in snapshot.get("categories", []):
            cat_name = cat.get("name", "") if isinstance(cat, dict) else ""
            books.extend(parse_fanqie_rank_list(cat.get("books", []), top=top, category=cat_name))
        return books
