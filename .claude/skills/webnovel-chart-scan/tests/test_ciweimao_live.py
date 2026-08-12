"""Live HTTP smoke test for the ciweimao adapter (the only LIVE one).

Skipped by default via the ``--addopts="-m 'not slow'"`` in pyproject.toml.
Run explicitly with::

    pytest -m slow
    # or
    pytest tests/test_ciweimao_live.py -v

If ciweimao.com returns a transient network error, this test will fail —
that's the point. We want a real signal that the LIVE adapter still
works against upstream.
"""
from __future__ import annotations

import pytest

from scripts.adapters.ciweimao import CiweimaoAdapter
from scripts.adapters.base import AdapterStatus


def test_ciweimao_adapter_is_live():
    """Sanity check: ciweimao must still be the only LIVE adapter."""
    a = CiweimaoAdapter()
    assert a.status == AdapterStatus.LIVE
    assert a.platform == "ciweimao"
    assert a.strategy.value == "webfetch"


@pytest.mark.slow
def test_ciweimao_live_fetch_real_data():
    """Real HTTP smoke test against ciweimao.com.

    Fetches the 玄幻 (default sort) weekly-ish view and verifies the
    adapter returns real books with non-empty platform_book_id.
    """
    a = CiweimaoAdapter()
    books = a.fetch("玄幻", "weekly", 5)
    assert len(books) >= 1, "expected at least one book from ciweimao 玄幻 weekly"
    assert all(b.platform_book_id for b in books), "all books should have platform_book_id"
    assert all(b.title for b in books), "all books should have title"


@pytest.mark.slow
def test_ciweimao_live_fetch_all_category():
    """Real HTTP smoke test against the 'all' (quanbu) category."""
    a = CiweimaoAdapter()
    books = a.fetch("all", "weekly", 5)
    # quanbu may or may not return books depending on site state; we
    # only assert the call completed without exception and the schema
    # is well-formed.
    for b in books:
        assert b.platform_book_id
        assert b.title
        assert b.rank_position is not None