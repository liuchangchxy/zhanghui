"""End-to-end test for the ciweimao adapter.

Requires a real Chrome listening on the CDP port (default 9222) AND
agent-browser on $PATH. Skipped automatically if either is missing —
so this test is opt-in via ``pytest -m slow``.

To run:
    <VENV_PYTHON> -m pytest tests/test_ciweimao_e2e.py -v -m slow

Verifies:
1. Adapter returns at least 1 book when fully set up.
2. Returned books have title + detail_url populated.
3. setup_ciweimao() is idempotent (re-running doesn't break anything).
"""
from __future__ import annotations

import shutil
import subprocess
import urllib.request

import pytest

from scripts.adapters.ciweimao import CiweimaoAdapter
from scripts.ciweimao_setup.setup_ciweimao import (
    DEFAULT_CDP_PORT,
    check_agent_browser,
    check_chrome_running,
    setup_ciweimao,
)


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not shutil.which("node"),
        reason="node not on PATH",
    ),
    pytest.mark.skipif(
        not check_agent_browser(),
        reason="agent-browser not installed",
    ),
    pytest.mark.skipif(
        not check_chrome_running(DEFAULT_CDP_PORT),
        reason=f"Chrome not listening on {DEFAULT_CDP_PORT}",
    ),
]


def _adapter_returns_books():
    adapter = CiweimaoAdapter()
    books = adapter.fetch("all", "daily", top=10)
    assert len(books) >= 1, f"expected ≥1 book, got {len(books)}"
    for book in books:
        assert book.title, f"book missing title: {book}"
        assert book.detail_url, f"book missing detail_url: {book}"
    return books


def test_adapter_returns_books_when_fully_set_up():
    """Smoke: with Chrome+agent-browser up, adapter returns real data."""
    _adapter_returns_books()


def test_setup_ciweimao_is_idempotent():
    """Calling setup_ciweimao() again is a no-op (env already ready)."""
    # First call should be a no-op since pytestmark already verified env is up
    setup_ciweimao(port=DEFAULT_CDP_PORT)
    # Second call too
    setup_ciweimao(port=DEFAULT_CDP_PORT)
    # And adapter still works
    _adapter_returns_books()