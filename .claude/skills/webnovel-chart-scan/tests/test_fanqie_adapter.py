"""Tests for the fanqie adapter metadata (Strategy.VENDOR).

Status: BLOCKED_IMPLEMENTATION (verified 2026-08-13).

    The vendored subset needs Playwright + Chromium installed::

        pip install playwright && playwright install chromium

    Even with Playwright installed, the vendored subset's ``run_scraper``
    is site-wide (one dump covering all 男频/女频/阅读榜/新书榜) — it
    does not match our per-(category, period, top) signature. A thin
    adapter over ``run_scraper`` is the v0.2 work item. Until then,
    ``fetch()`` raises a tailored ``RuntimeError`` after the Playwright
    import succeeds (or fails), so the orchestrator records an
    actionable ``AdapterError`` rather than silently returning 0 books.

    v0.1.4: relabeled from LIVE_WITH_SETUP to BLOCKED_IMPLEMENTATION
    because the RuntimeError fires with OR without Playwright — it is
    a code-side gap, not a one-time setup issue. The orchestrator
    short-circuits BLOCKED_IMPLEMENTATION adapters, but fetch() is
    still callable directly (the RuntimeError surfaces for any caller,
    not just the orchestrator).

    The orchestrator short-circuits on BLOCKED_IMPLEMENTATION, so the
    RuntimeError never reaches the orchestrator path in production — but
    it's the documented failure mode for direct callers.
"""
from scripts.adapters.fanqie import FanqieAdapter
from scripts.adapters.base import AdapterStatus


def test_fanqie_adapter_metadata():
    a = FanqieAdapter()
    assert a.platform == "fanqie"
    assert a.strategy.value == "vendor"
    assert a.status == AdapterStatus.BLOCKED_IMPLEMENTATION


def test_fanqie_adapter_raises_runtimeerror_with_install_command():
    """fetch() must raise RuntimeError with actionable guidance — not
    a generic NotImplementedError. Direct callers see this; the
    orchestrator short-circuits before invoking fetch()."""
    a = FanqieAdapter()
    try:
        a.fetch("all", "weekly", 10)
    except RuntimeError as e:
        msg = str(e)
        # Either the install hint OR the integration hint (depending on
        # whether Playwright is installed in the test environment).
        install_hint = "pip install playwright" in msg and "playwright install chromium" in msg
        integration_hint = "does not match per-(category, period, top)" in msg
        assert install_hint or integration_hint, (
            f"RuntimeError message lacks actionable hint: {msg!r}"
        )
        return
    raise AssertionError(
        "FanqieAdapter.fetch should raise RuntimeError "
        "(status=BLOCKED_IMPLEMENTATION -> direct callers see error)"
    )


def test_fanqie_adapter_runtimeerror_mentions_known_limitations():
    """Both error paths must point at KNOWN_LIMITATIONS.md so users
    can find the v0.2 work item."""
    a = FanqieAdapter()
    try:
        a.fetch(category="all", period="daily", top=10)
    except RuntimeError as e:
        assert "KNOWN_LIMITATIONS.md" in str(e), (
            f"RuntimeError must reference KNOWN_LIMITATIONS.md: {e!r}"
        )
        return
    raise AssertionError(
        "FanqieAdapter.fetch should raise RuntimeError"
    )