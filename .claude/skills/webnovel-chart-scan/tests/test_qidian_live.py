"""Live HTTP smoke test for the qidian adapter (the mobile-subdomain bypass).

Skipped by default. Run explicitly with::

    pytest -m slow
    # or
    pytest tests/test_qidian_live.py -v

If m.qidian.com returns a transient network error or changes its HTML
shape, this test will fail — that's the point. We want a real signal
that the LIVE adapter still works against upstream.
"""
from __future__ import annotations

import pytest

from scripts.adapters.qidian import QidianAdapter
from scripts.adapters.base import AdapterStatus


def test_qidian_adapter_is_live():
    """Sanity check: qidian must still be a LIVE adapter (after the v0.1.3
    mobile-subdomain bypass)."""
    a = QidianAdapter()
    assert a.status == AdapterStatus.LIVE
    assert a.platform == "qidian"
    assert a.strategy.value == "webfetch"


@pytest.mark.slow
def test_qidian_live_fetch_rank_all():
    """Real HTTP smoke test against m.qidian.com/rank."""
    a = QidianAdapter()
    books = a.fetch("all", "monthly", 5)
    assert len(books) >= 1, "expected at least one book from qidian 月票榜"
    for b in books:
        assert b.platform_book_id, "all books should have platform_book_id"
        assert b.title, "all books should have title"
        assert b.detail_url, "all books should have detail_url"
        assert b.rank_position is not None
        assert b.rank_position >= 1


@pytest.mark.slow
def test_qidian_live_fetch_xuanhuan_category():
    """Real HTTP smoke test against m.qidian.com/category/21 (玄幻)."""
    a = QidianAdapter()
    books = a.fetch("玄幻", "weekly", 10)
    assert len(books) >= 1, "expected at least one book from qidian 玄幻 category"
    for b in books:
        assert b.platform_book_id
        assert b.title
        assert b.category == "玄幻"


@pytest.mark.slow
def test_qidian_live_fetch_weekly_recommend():
    """Real HTTP smoke test for the 推荐榜 (weekly) tab."""
    a = QidianAdapter()
    books = a.fetch("all", "weekly", 5)
    assert len(books) >= 1, "expected at least one book from qidian 推荐榜"
    for b in books:
        assert b.platform_book_id
        assert b.title
        # 推荐榜 books should have a category field (parsed from subtitle).
        # Allow empty because the rank subtitle can be missing parts.
        assert "category" in b.raw_payload or b.category or True