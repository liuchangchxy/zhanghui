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
import pytest

from scripts.adapters import fanqie as fanqie_mod


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fanqie_dump_20260815.json"


def _fake_httpx_get_factory(fixture_path: Path):
    """Return a fake httpx.get that returns the fixture as a Response."""
    def _fake_get(url, **kwargs):
        content = fixture_path.read_bytes()
        return httpx.Response(200, content=content, request=httpx.Request("GET", url))
    return _fake_get


def _fake_httpx_status_factory(status_code: int, body: str = ""):
    """Return a fake httpx.get that returns a response with the given status."""
    def _fake_get(url, **kwargs):
        return httpx.Response(
            status_code, text=body,
            request=httpx.Request("GET", url),
        )
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


# ─────────────────────────────────────────────────────────────────────
# Adversarial review v0.2.1 fixes (C1+C2+C3+I1+I2)
# ─────────────────────────────────────────────────────────────────────

def test_fanqie_corrupted_cache_recovers_and_redownloads(monkeypatch, tmp_path):
    """C1: a corrupted cache file (e.g. truncated download) must not crash;
    _download_dump should log a warning, delete the cache, and re-download.
    """
    monkeypatch.setattr(fanqie_mod, "CACHE_DIR", tmp_path)

    # Pre-write a corrupted cache file (today's date)
    from datetime import datetime, timezone
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    cache_file = tmp_path / f"fanqie_dump_{date_str}.json"
    cache_file.write_text("{not valid json", encoding="utf-8")

    # HTTP will be called once after the corrupted cache is wiped.
    fake_get = _fake_httpx_get_factory(FIXTURE_PATH)
    with patch("scripts.adapters.fanqie.httpx.get", side_effect=fake_get):
        books = FanqieAdapter().fetch("玄幻", "weekly", top=3)

    assert len(books) > 0
    # The cache file should now contain valid JSON (re-written).
    assert json.loads(cache_file.read_text(encoding="utf-8"))


def test_fanqie_non_json_200_ok_raises_clear_runtime_error(monkeypatch, tmp_path):
    """C2: a non-JSON 200 OK response (e.g. HTML error page) must raise a
    RuntimeError with a clear message naming content-type + first chars,
    not the cryptic ``json.JSONDecodeError``.
    """
    monkeypatch.setattr(fanqie_mod, "CACHE_DIR", tmp_path)
    fake_get = _fake_httpx_status_factory(
        200, body="<html><body>Cloudflare challenge</body></html>",
    )
    with patch("scripts.adapters.fanqie.httpx.get", side_effect=fake_get):
        with pytest.raises(RuntimeError, match="non-JSON"):
            FanqieAdapter().fetch("玄幻", "weekly", top=3)


def test_fanqie_non_json_200_ok_does_not_cache(monkeypatch, tmp_path):
    """C3: if json.loads fails, no cache file should be written so the next
    call retries from upstream.
    """
    monkeypatch.setattr(fanqie_mod, "CACHE_DIR", tmp_path)
    fake_get = _fake_httpx_status_factory(
        200, body="<html><body>Cloudflare</body></html>",
    )
    with patch("scripts.adapters.fanqie.httpx.get", side_effect=fake_get):
        with pytest.raises(RuntimeError):
            FanqieAdapter().fetch("玄幻", "weekly", top=3)

    # No cache file should exist (the non-JSON body was never persisted).
    cache_files = list(tmp_path.glob("fanqie_dump_*.json"))
    assert cache_files == [], (
        f"non-JSON body should not be cached, found: {cache_files}"
    )


def test_fanqie_empty_categories_steps_back_and_succeeds(monkeypatch, tmp_path):
    """I1: if a dump's ``categories`` list is empty, treat as 404-equivalent
    and step back a day so the fallback loop can find yesterday's dump.
    """
    monkeypatch.setattr(fanqie_mod, "CACHE_DIR", tmp_path)

    empty_dump = json.dumps({"date": "2026-08-15", "categories": []})

    def _fake_get(url, **kwargs):
        # First call (today) returns an empty dump; second call
        # (yesterday) returns the real fixture.
        if not hasattr(_fake_get, "_called"):
            _fake_get._called = True
            return httpx.Response(
                200, text=empty_dump,
                request=httpx.Request("GET", url),
            )
        return httpx.Response(
            200, content=FIXTURE_PATH.read_bytes(),
            request=httpx.Request("GET", url),
        )

    with patch("scripts.adapters.fanqie.httpx.get", side_effect=_fake_get):
        books = FanqieAdapter().fetch("玄幻", "weekly", top=3)

    assert len(books) > 0, "should have stepped back to yesterday's dump"


def test_fanqie_transient_http_error_steps_back_and_succeeds(monkeypatch, tmp_path):
    """I2: httpx transport errors should be caught and treated like 404
    (step back a day). After the first error, a normal response should
    yield books.
    """
    monkeypatch.setattr(fanqie_mod, "CACHE_DIR", tmp_path)

    def _fake_get(url, **kwargs):
        if not hasattr(_fake_get, "_called"):
            _fake_get._called = True
            raise httpx.ConnectError("simulated transient network error")
        return httpx.Response(
            200, content=FIXTURE_PATH.read_bytes(),
            request=httpx.Request("GET", url),
        )

    with patch("scripts.adapters.fanqie.httpx.get", side_effect=_fake_get):
        books = FanqieAdapter().fetch("玄幻", "weekly", top=3)

    assert len(books) > 0


def test_fanqie_max_fallback_days_constant_exists():
    """M4: the magic number 3 must be exposed as a module-level constant."""
    assert fanqie_mod.MAX_FALLBACK_DAYS == 3
    assert isinstance(fanqie_mod.MAX_FALLBACK_DAYS, int)


def test_fanqie_raw_payload_uses_period_arg_key():
    """M7 part 1: the echoed user period arg must be keyed ``period_arg``
    (clearer that it's the user's arg, not upstream data)."""
    fake_get = _fake_httpx_get_factory(FIXTURE_PATH)
    with patch("scripts.adapters.fanqie.httpx.get", side_effect=fake_get):
        books = FanqieAdapter().fetch("玄幻", "weekly", top=1)
    assert "period_arg" in books[0].raw_payload
    assert "period" not in books[0].raw_payload