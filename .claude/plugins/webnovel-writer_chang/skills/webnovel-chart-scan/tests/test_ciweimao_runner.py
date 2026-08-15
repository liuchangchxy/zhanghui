"""Tests for the ciweimao Node subprocess wrapper.

The worldwonderer/oh-story-claudecode project ships a Node.js scraper
(``ciweimao-rank-scraper.js``) that uses Chrome DevTools Protocol to
bypass ciweimao.com's anti-bot captcha. It writes per-rank Markdown
files. We shell out to it via subprocess, then parse the Markdown
output into RawBook objects.

These tests cover the Markdown parser only — the subprocess invocation
is exercised separately in test_ciweimao_adapter.py (with mocked
subprocess) and in test_ciweimao_runner_live.py (slow integration test).
"""
from __future__ import annotations

from pathlib import Path

from scripts.adapters.ciweimao_runner import parse_rank_markdown


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ciweimao_rank_click.md"


def test_parse_rank_markdown_extracts_all_books():
    md = FIXTURE_PATH.read_text(encoding="utf-8")
    books = parse_rank_markdown(md, top=10)
    assert len(books) == 3, f"expected 3 books, got {len(books)}"


def test_parse_rank_markdown_extracts_basic_fields():
    md = FIXTURE_PATH.read_text(encoding="utf-8")
    books = parse_rank_markdown(md, top=10)
    first = books[0]
    assert first.title == "我在诡异世界当神棍"
    assert first.author == "梧桐阅读"
    assert first.category == "灵异"  # ciweimao native "悬疑灵异" → we map to 灵异? or pass through?
    assert first.detail_url == "https://www.ciweimao.com/book/100123456"
    assert first.platform_book_id == "100123456"
    assert first.word_count == 2340000  # 234万 → 2340000


def test_parse_rank_markdown_respects_top_limit():
    md = FIXTURE_PATH.read_text(encoding="utf-8")
    books = parse_rank_markdown(md, top=2)
    assert len(books) == 2


def test_parse_rank_markdown_handles_empty_input():
    books = parse_rank_markdown("", top=10)
    assert books == []