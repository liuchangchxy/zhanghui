"""Live HTTP smoke test for the qimao adapter.

Skipped by default via ``addopts = "-m 'not slow'"`` in pyproject.toml.
Run explicitly with::

    pytest -m slow
    # or
    pytest tests/test_qimao_live.py -v

If qimao.com returns a transient network error or changes its payload
shape, this test will fail — that's the point. We want a real signal
that the LIVE adapter still works against upstream.
"""
from __future__ import annotations

import pytest

from scripts.adapters.qimao import QimaoAdapter
from scripts.adapters.base import AdapterStatus


def test_qimao_adapter_is_live():
    """Sanity check: qimao must be a LIVE adapter (after the v0.1.2
    balanced-brace parser rewrite)."""
    a = QimaoAdapter()
    assert a.status == AdapterStatus.LIVE
    assert a.platform == "qimao"
    assert a.strategy.value == "vendor"


@pytest.mark.slow
def test_qimao_live_fetch_real_data():
    """Real HTTP smoke test against qimao.com.

    Fetches the 收藏榜 (weekly -> collect rank type) and verifies the
    adapter returns real books with non-empty platform_book_id.
    """
    a = QimaoAdapter()
    books = a.fetch("all", "weekly", 5)
    assert len(books) >= 1, "expected at least one book from qimao weekly"
    assert all(b.platform_book_id for b in books), "all books should have platform_book_id"
    assert all(b.title for b in books), "all books should have title"
    assert all(b.detail_url for b in books), "all books should have detail_url"


@pytest.mark.slow
def test_qimao_live_fetch_daily_rank():
    """Real HTTP smoke test against the daily (大热榜) rank."""
    a = QimaoAdapter()
    books = a.fetch("all", "daily", 5)
    assert len(books) >= 1, "expected at least one book from qimao daily"
    for b in books:
        assert b.platform_book_id
        assert b.title
        assert b.rank_position is not None