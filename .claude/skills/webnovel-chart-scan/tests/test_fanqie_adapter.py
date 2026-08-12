"""Tests for the fanqie adapter metadata (Strategy.VENDOR).

Status: LIVE_WITH_SETUP (verified 2026-08-13).

    The vendored subset needs Playwright + Chromium installed::

        pip install playwright && playwright install chromium

    Once installed, the vendored subset's ``run_scraper`` is callable,
    but its API is site-wide (one dump covering all 男频/女频/阅读榜/
    新书榜) — it does not match our per-(category, period, top)
    signature. A thin adapter is the v0.2 work item. Until then,
    ``fetch()`` raises a tailored ``RuntimeError`` after the Playwright
    import succeeds, so the orchestrator records an actionable
    ``AdapterError`` rather than silently returning 0 books.

    The orchestrator calls ``fetch()`` (because status is
    ``LIVE_WITH_SETUP``, not ``BLOCKED_*``), so any RuntimeError
    surfaces in ``books.json`` errors[] and ``report.md`` 失败记录.
"""
from scripts.adapters.fanqie import FanqieAdapter
from scripts.adapters.base import AdapterStatus


def test_fanqie_adapter_metadata():
    a = FanqieAdapter()
    assert a.platform == "fanqie"
    assert a.strategy.value == "vendor"
    assert a.status == AdapterStatus.LIVE_WITH_SETUP


def test_fanqie_adapter_raises_runtimeerror_with_install_command():
    """fetch() must raise RuntimeError with the install command — not
    a generic NotImplementedError. The orchestrator catches the
    RuntimeError and records an AdapterError so users see actionable
    guidance in the report."""
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
        "(status=LIVE_WITH_SETUP -> orchestrator calls fetch())"
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