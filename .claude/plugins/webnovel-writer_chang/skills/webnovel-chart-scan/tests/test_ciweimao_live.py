"""Live HTTP smoke test for the ciweimao adapter.

Status: SKIPPED (verified 2026-08-13 — captcha 307 regression).

    Live re-verification on 2026-08-13 (4 minutes after a first success)
    showed ciweimao.com now gates ``/book_list/*`` with a 307 redirect to
    ``/signup/man_machine_verify`` (a man-machine CAPTCHA page). The
    adapter status was relabeled ``BLOCKED_EXTERNAL`` in v0.1.4 to reflect
    this. The tests below would fail against current upstream; the skip
    marker records why, and the orchestrator short-circuits the adapter.

    Bypassing the captcha is the v0.2 work item — likely needs
    Playwright + hCaptcha solver, similar to fanqie.

    The non-network metadata test is left live (it asserts
    ``status == BLOCKED_EXTERNAL``), so a future regression that
    silently flips the label back to ``LIVE`` would fail CI.
"""
from __future__ import annotations

import pytest

from scripts.adapters.ciweimao import CiweimaoAdapter
from scripts.adapters.base import AdapterStatus


def test_ciweimao_adapter_is_blocked_external():
    """Sanity check: ciweimao must be labeled BLOCKED_EXTERNAL after the
    2026-08-13 captcha regression. If this test fails, someone flipped
    the label back to LIVE without re-verifying against upstream."""
    a = CiweimaoAdapter()
    assert a.status == AdapterStatus.BLOCKED_EXTERNAL
    assert a.platform == "ciweimao"
    assert a.strategy.value == "webfetch"


@pytest.mark.skip(
    reason="captcha 307 regression observed 2026-08-13 — "
    "ciweimao.com gates /book_list/* with man_machine_verify; "
    "v0.2 fix needs Playwright + hCaptcha solver."
)
@pytest.mark.slow
def test_ciweimao_live_fetch_real_data():
    """Real HTTP smoke test against ciweimao.com (disabled).

    Re-enable when the captcha is bypassed. Fetches the 玄幻 (default
    sort) weekly-ish view and verifies the adapter returns real books
    with non-empty platform_book_id.
    """
    a = CiweimaoAdapter()
    books = a.fetch("玄幻", "weekly", 5)
    assert len(books) >= 1, "expected at least one book from ciweimao 玄幻 weekly"
    assert all(b.platform_book_id for b in books), "all books should have platform_book_id"
    assert all(b.title for b in books), "all books should have title"


@pytest.mark.skip(
    reason="captcha 307 regression observed 2026-08-13 — "
    "ciweimao.com gates /book_list/* with man_machine_verify; "
    "v0.2 fix needs Playwright + hCaptcha solver."
)
@pytest.mark.slow
def test_ciweimao_live_fetch_all_category():
    """Real HTTP smoke test against the 'all' (quanbu) category (disabled)."""
    a = CiweimaoAdapter()
    books = a.fetch("all", "weekly", 5)
    for b in books:
        assert b.platform_book_id
        assert b.title
        assert b.rank_position is not None