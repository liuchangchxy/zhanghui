"""Tests for the fanqie adapter metadata (Strategy.DIRECT_DUMP).

Status: LIVE_WITH_SETUP (verified 2026-08-16).

    After v0.2, the adapter fetches a pre-produced daily dump from the
    upstream GitHub repository (no Playwright, no Chromium). The strategy
    is ``Strategy.DIRECT_DUMP`` and ``status`` is ``LIVE_WITH_SETUP``
    (still needs network access to GitHub raw). fetch() returns real
    RawBook rows under normal conditions.

    The three pre-v0.2 tests below were rewritten to match the new
    LIVE behavior. Their semantic role — verify the adapter's external
    contract — is preserved; only the assertions changed.
"""
from scripts.adapters.fanqie import FanqieAdapter
from scripts.adapters.base import AdapterStatus, Strategy
from scripts.schema import RawBook


def test_fanqie_adapter_metadata():
    """Strategy.DIRECT_DUMP + LIVE_WITH_SETUP after v0.2."""
    a = FanqieAdapter()
    assert a.platform == "fanqie"
    assert a.strategy == Strategy.DIRECT_DUMP
    assert a.status == AdapterStatus.LIVE_WITH_SETUP


def test_fanqie_adapter_metadata_vendor_value():
    """DIRECT_DUMP string value is the Strategy enum's canonical value."""
    assert Strategy.DIRECT_DUMP.value == "direct_dump"


def test_fanqie_adapter_module_imports_cleanly():
    """The adapter module must import without raising (no missing imports
    on the Strategy enum). This is the regression guard for the
    DIRECT_DUMP addition in Task 5."""
    from scripts.adapters import fanqie  # noqa: F401
    assert hasattr(fanqie, "FanqieAdapter")
    assert hasattr(fanqie, "parse_dump_to_rawbooks")
    assert hasattr(fanqie, "_download_dump")


"""Happy-path tests for fanqie adapter using fixture dump.

These tests verify that the rewritten fetch() (which pulls from
GitHub raw dump) actually returns real books from the saved fixture,
not just raises RuntimeError.
"""
# Note: `from __future__ import annotations` intentionally omitted —
# it must be at the top of the file (already there from the existing
# block above), and duplicating it here is a SyntaxError.

import json
from pathlib import Path
from unittest.mock import patch

import httpx

from scripts.adapters.fanqie import FanqieAdapter


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fanqie_dump_20260815.json"


def _fake_httpx_get_factory(fixture_path: Path):
    """Return a fake httpx.get that returns the fixture as a Response."""
    def _fake_get(url, **kwargs):
        content = fixture_path.read_bytes()
        return httpx.Response(200, content=content, request=httpx.Request("GET", url))
    return _fake_get


def test_fanqie_fetch_returns_real_books_for_xuanhuan():
    """Happy path: fetch(category=玄幻, period=weekly, top=10) must return
    >0 real books (not raise RuntimeError, not return [])."""
    a = FanqieAdapter()
    fake_get = _fake_httpx_get_factory(FIXTURE_PATH)
    with patch("scripts.adapters.fanqie.httpx.get", side_effect=fake_get):
        books = a.fetch("玄幻", "weekly", top=10)

    assert len(books) > 0, f"expected >0 books for 玄幻, got {len(books)}"
    assert all(b.platform_book_id for b in books), "all books must have platform_book_id"
    assert all(b.title for b in books), "all books must have title"
    assert all(b.detail_url.startswith("https://") for b in books)
    assert all(b.category == "玄幻" for b in books), \
        f"all books must be 玄幻, got categories: {set(b.category for b in books)}"


def test_fanqie_fetch_respects_top_limit():
    """fetch(top=5) must return at most 5 books."""
    a = FanqieAdapter()
    fake_get = _fake_httpx_get_factory(FIXTURE_PATH)
    with patch("scripts.adapters.fanqie.httpx.get", side_effect=fake_get):
        books = a.fetch("玄幻", "weekly", top=5)

    assert len(books) <= 5, f"top=5 should return ≤5 books, got {len(books)}"


def test_fanqie_fetch_all_returns_books_from_every_subcategory():
    """fetch(category='all') must return books from many subcategories
    (mixed 男频 + 女频)."""
    a = FanqieAdapter()
    fake_get = _fake_httpx_get_factory(FIXTURE_PATH)
    # top=300 covers ≥10 subcategories (each subcat has 20 books in the
    # fixture, and the fixture has 74 categories / 34 unique subcats).
    with patch("scripts.adapters.fanqie.httpx.get", side_effect=fake_get):
        books = a.fetch("all", "weekly", top=300)

    assert len(books) >= 50, f"expected ≥50 books for 'all', got {len(books)}"
    # Verify we got books from at least 10 different subcategories (dump has 34)
    subcats_seen = {b.raw_payload.get("subcategory", "") for b in books}
    assert len(subcats_seen) >= 10, f"only saw {len(subcats_seen)} subcategories: {subcats_seen}"


def test_fanqie_adapter_status_is_live_after_fix():
    """After this task lands, the adapter should be relabeled from
    BLOCKED_IMPLEMENTATION to LIVE (or LIVE_WITH_SETUP if dump download
    is gated by network). BLOCKED_IMPLEMENTATION is no longer true."""
    a = FanqieAdapter()
    assert a.status.value in ("live", "live_with_setup"), \
        f"adapter still BLOCKED_*: {a.status.value}"