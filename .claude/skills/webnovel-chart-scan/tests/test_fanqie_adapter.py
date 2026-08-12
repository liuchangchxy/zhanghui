"""Tests for the fanqie adapter metadata (Strategy.VENDOR).

Status: BLOCKED_IMPLEMENTATION (verified 2026-08-13).

    The vendored subset needs Playwright + Chromium installed:

        pip install playwright && playwright install chromium

    Until then the adapter raises NotImplementedError immediately
    without attempting to import playwright — so import/parser tests
    are no longer applicable. Only the metadata + immediate-raise test
    remain.
"""
from scripts.adapters.fanqie import FanqieAdapter
from scripts.adapters.base import AdapterStatus


def test_fanqie_adapter_metadata():
    a = FanqieAdapter()
    assert a.platform == "fanqie"
    assert a.strategy.value == "vendor"
    assert a.status == AdapterStatus.BLOCKED_IMPLEMENTATION


def test_fanqie_adapter_raises_for_specific_category():
    """Even BLOCKED_IMPLEMENTATION adapters should still raise for
    unsupported category values (defensive — pre-existing behavior
    preserved)."""
    a = FanqieAdapter()
    try:
        a.fetch("玄幻", "weekly", 10)
    except NotImplementedError as e:
        msg = str(e)
        # Must mention either the category restriction (legacy) or the
        # BLOCKED_IMPLEMENTATION reason (new). Both contain the
        # substring "KNOWN_LIMITATIONS.md" or "Playwright".
        assert ("Playwright" in msg) or ("does not support category" in msg)
        return
    raise AssertionError("FanqieAdapter.fetch should raise NotImplementedError (status=BLOCKED_IMPLEMENTATION)")


def test_fanqie_adapter_fetch_raises_immediately_without_playwright():
    """fetch(category='all', ...) must raise before any Playwright import.
    Verifies the BLOCKED_IMPLEMENTATION short-circuit prevents the
    vendored import path from running."""
    a = FanqieAdapter()
    try:
        a.fetch(category="all", period="daily", top=10)
    except NotImplementedError as e:
        msg = str(e)
        assert "Playwright" in msg
        assert "KNOWN_LIMITATIONS.md" in msg
        return
    raise AssertionError("FanqieAdapter.fetch should raise NotImplementedError before importing playwright")