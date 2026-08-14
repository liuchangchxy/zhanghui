"""Live HTTP smoke test for the zongheng adapter (Nuxt SSR scraping).

Skipped by default. Run explicitly with::

    pytest -m slow
    # or
    pytest tests/test_zongheng_live.py -v

If zongheng.com returns a transient network error or changes its
Nuxt SSR payload shape, this test will fail — that's the point. We
want a real signal that the LIVE adapter still works against upstream.
"""
from __future__ import annotations

import pytest

from scripts.adapters.zongheng import ZonghengAdapter
from scripts.adapters.base import AdapterStatus


def test_zongheng_adapter_is_live():
    """Sanity check: zongheng must still be a LIVE adapter (after the v0.1.3
    Nuxt SSR scraping rewrite)."""
    a = ZonghengAdapter()
    assert a.status == AdapterStatus.LIVE
    assert a.platform == "zongheng"
    assert a.strategy.value == "webfetch"


@pytest.mark.slow
def test_zongheng_live_fetch_monthly_ticket():
    """Real HTTP smoke test against zongheng /rank (monthly -> 月票榜)."""
    a = ZonghengAdapter()
    books = a.fetch("all", "monthly", 5)
    assert len(books) >= 1, "expected at least one book from zongheng 月票榜"
    for b in books:
        assert b.platform_book_id, "all books should have platform_book_id"
        assert b.title, "all books should have title"
        assert b.detail_url, "all books should have detail_url"
        assert b.rank_position is not None


@pytest.mark.slow
def test_zongheng_live_fetch_weekly_recommend():
    """Real HTTP smoke test against zongheng /rank (weekly -> 推荐榜)."""
    a = ZonghengAdapter()
    books = a.fetch("all", "weekly", 5)
    assert len(books) >= 1, "expected at least one book from zongheng 推荐榜"
    for b in books:
        assert b.platform_book_id
        assert b.title


@pytest.mark.slow
def test_zongheng_live_fetch_daily_new_book():
    """Real HTTP smoke test against zongheng /rank (daily -> 新书榜)."""
    a = ZonghengAdapter()
    books = a.fetch("all", "daily", 5)
    assert len(books) >= 1, "expected at least one book from zongheng 新书榜"
    for b in books:
        assert b.platform_book_id
        assert b.title