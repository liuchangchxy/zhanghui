"""Tests for the ciweimao adapter (LIVE_WITH_SETUP via Node subprocess).

After v0.2, ciweimao is LIVE_WITH_SETUP — fetch() shells out to a
vendored Node.js scraper (worldwonderer/oh-story-claudecode, MIT) which
uses Chrome DevTools Protocol to bypass the anti-bot captcha. These tests
mock the subprocess so they run offline.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scripts.adapters.ciweimao import CiweimaoAdapter
from scripts.adapters.base import AdapterStatus


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ciweimao_rank_click.md"


def test_ciweimao_adapter_metadata():
    """Strategy.WEBFETCH + LIVE_WITH_SETUP after v0.2."""
    a = CiweimaoAdapter()
    assert a.platform == "ciweimao"
    assert a.strategy.value == "webfetch"
    assert a.status == AdapterStatus.LIVE_WITH_SETUP


def test_ciweimao_fetch_returns_real_books_via_subprocess(monkeypatch):
    """fetch() shells out to node, parses the Markdown output, returns books.

    We mock run_scraper to return a pre-created fixture file path,
    bypassing the actual subprocess call (Node + Chrome CDP).
    """
    a = CiweimaoAdapter()

    # Pre-create the "output" file the JS would have written
    fake_output_dir = Path("/tmp/webnovel-chart-scan-test-ciweimao")
    fake_output_dir.mkdir(parents=True, exist_ok=True)
    fake_md_file = fake_output_dir / "刺猬猫点击榜_20260815.md"
    fake_md_file.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    from scripts.adapters import ciweimao_runner
    monkeypatch.setattr(
        ciweimao_runner, "run_scraper", lambda rank_type, output_dir: fake_md_file
    )

    books = a.fetch("all", "weekly", top=10)
    assert len(books) == 3, f"expected 3 books from fixture, got {len(books)}"
    assert books[0].title == "我在诡异世界当神棍"
    assert books[0].platform_book_id == "100123456"


def test_ciweimao_fetch_filters_by_category(monkeypatch):
    """fetch(category='灵异') should filter out non-matching categories."""
    a = CiweimaoAdapter()

    fake_output_dir = Path("/tmp/webnovel-chart-scan-test-ciweimao")
    fake_output_dir.mkdir(parents=True, exist_ok=True)
    fake_md_file = fake_output_dir / "刺猬猫点击榜_20260815.md"
    fake_md_file.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    from scripts.adapters import ciweimao_runner
    monkeypatch.setattr(
        ciweimao_runner, "run_scraper", lambda rank_type, output_dir: fake_md_file
    )

    books = a.fetch("灵异", "weekly", top=10)
    # Fixture has 1 灵异 book + 1 仙侠 + 1 轻小说; only 灵异 should remain
    assert len(books) == 1
    assert books[0].category == "灵异"


def test_ciweimao_period_maps_to_correct_rank_type():
    """Verify PERIOD_TO_RANK_TYPE maps our periods to upstream --type values."""
    from scripts.adapters.ciweimao_runner import PERIOD_TO_RANK_TYPE
    assert PERIOD_TO_RANK_TYPE["daily"] == "click"
    assert PERIOD_TO_RANK_TYPE["weekly"] == "click"
    assert PERIOD_TO_RANK_TYPE["monthly"] == "monthly"