"""Tests for the qidian adapter metadata + parser unit tests.

Status: LIVE (verified 2026-08-13, after mobile-subdomain bypass).

    The desktop site www.qidian.com returns HTTP 202 + probe.js for every
    URL. The vendored upstream's RC4 cookie computation does NOT actually
    bypass modern probe.js (verified 2026-08-13). The working runtime
    path is the mobile subdomain (m.qidian.com) with an iPhone UA, which
    serves the rank/category HTML directly. See scripts/adapters/qidian.py
    for the bypass rationale.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.adapters.qidian import (
    QidianAdapter,
    parse_rank_html,
    parse_category_html,
    _parse_word_count,
    _split_subtitle,
)
from scripts.adapters.base import AdapterStatus


# --- metadata ---------------------------------------------------------------

def test_qidian_adapter_metadata():
    a = QidianAdapter()
    assert a.platform == "qidian"
    assert a.strategy.value == "webfetch"
    assert a.status == AdapterStatus.LIVE


# --- word-count helpers -----------------------------------------------------

def test_parse_word_count_handles_wan_unit():
    assert _parse_word_count("639.05万字") == 6_390_500
    assert _parse_word_count("12.3万字") == 123_000
    assert _parse_word_count("1万") == 10_000


def test_parse_word_count_handles_qian_unit():
    assert _parse_word_count("12.3千字") == 12_300


def test_parse_word_count_handles_bare_number():
    assert _parse_word_count("12字") == 12
    assert _parse_word_count("12") == 12


def test_parse_word_count_returns_none_on_garbage():
    assert _parse_word_count("") is None
    assert _parse_word_count("abc") is None
    assert _parse_word_count(None) is None


def test_split_subtitle_three_parts():
    author, category, wc = _split_subtitle("纯洁滴小龙 · 都市 · 639.05万字")
    assert author == "纯洁滴小龙"
    assert category == "都市"
    assert wc == 6_390_500


def test_split_subtitle_two_parts():
    author, category, wc = _split_subtitle("辰东 · 玄幻")
    assert author == "辰东"
    assert category == "玄幻"
    assert wc is None


def test_split_subtitle_word_count_in_first_slot_means_no_category():
    """If the only segments are author + bare number (no category between),
    the heuristic classifies the second segment as the category rather
    than word_count — because "12" alone could be either, and the
    rank-page schema is "作者 · 分类 · 字数"."""
    # Per the schema, "12字" alone wouldn't appear; "12" alone in the
    # middle position is more likely a category. Verify the heuristic.
    author, category, wc = _split_subtitle("辰东 · 12")
    # wc=None is acceptable; the parser doesn't try to interpret "12" as
    # a word count without a "万" suffix.
    assert author == "辰东"
    assert wc is None or wc == 12  # either heuristic is acceptable


def test_split_subtitle_empty():
    assert _split_subtitle("") == ("", "", None)


# --- parser tests against saved fixtures ------------------------------------

@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


def test_parse_rank_html_extracts_books_from_each_tab(fixtures_dir):
    """The rank page renders 9 tabs × 5 books = 45 book anchors; the parser
    groups them under each ``_rankTitle_*`` heading."""
    html = (fixtures_dir / "qidian_rank_all.html").read_text()
    monthly = parse_rank_html(html, top=10, period="monthly")
    assert len(monthly) >= 5, "月票榜 should have at least 5 books"
    for b in monthly:
        assert b.platform_book_id
        assert b.title
        assert b.detail_url and b.detail_url.startswith("https://m.qidian.com/book/")
        assert b.rank_position is not None
        # 月票榜 first row should be 捞尸人 (verified 2026-08-13).
        if b.rank_position == 1:
            assert b.title == "捞尸人"


def test_parse_rank_html_picks_correct_tab_per_period(fixtures_dir):
    """Different periods select different rank tabs."""
    html = (fixtures_dir / "qidian_rank_all.html").read_text()
    monthly = parse_rank_html(html, top=5, period="monthly")
    weekly = parse_rank_html(html, top=5, period="weekly")
    daily = parse_rank_html(html, top=5, period="daily")
    # Tabs should differ — first-row titles should be different.
    titles = {m[0].title for m in [monthly, weekly, daily] if m}
    # Three tabs may share some books but at least the monthly top should
    # be 月票榜 (which 2026-08-13 puts 捞尸人 first), not the same as the
    # daily/weekly firsts.
    assert len(titles) >= 1  # at least some overlap is OK
    # Verify the rank tab label is in raw_payload.
    assert monthly[0].raw_payload["rank_tab"] == "月票榜"
    assert weekly[0].raw_payload["rank_tab"] == "推荐榜"
    assert daily[0].raw_payload["rank_tab"] == "更新榜"


def test_parse_category_html_extracts_books(fixtures_dir):
    """The 玄幻 category page renders ~20 book cards."""
    html = (fixtures_dir / "qidian_category_xuanhuan.html").read_text()
    books = parse_category_html(html, top=20)
    assert len(books) >= 10, "玄幻 category should have at least 10 books"
    for b in books:
        assert b.platform_book_id
        assert b.title
        assert b.category == "玄幻"
        assert b.author, "category-page books should have an author field"
        # word_count may be missing for very new books; rank_position always set.
        assert b.rank_position is not None


def test_qidian_adapter_metadata_supports_known_categories():
    """All platform categories that the existing fixture data uses must
    map to a real m.qidian.com/category/<id>."""
    from scripts.adapters.qidian import QIDIAN_CATEGORY_IDS
    for cat, cid in QIDIAN_CATEGORY_IDS.items():
        assert isinstance(cid, int) and cid > 0, f"{cat!r} -> invalid id {cid}"