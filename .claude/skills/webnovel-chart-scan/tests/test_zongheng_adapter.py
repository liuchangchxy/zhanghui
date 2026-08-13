"""Tests for the zongheng adapter metadata + parser integration.

Status: LIVE (verified 2026-08-13, after Nuxt SSR scraping rewrite).

    The public zongheng.com API endpoint returns HTTP 404. The site
    itself returns 200 with a Nuxt SSR payload containing all rank lists
    under state.rank.popularityRank. This adapter extracts the period-
    appropriate list and projects each row into a RawBook.

    Tests use a real captured HTML fixture saved at
    tests/fixtures/zongheng_rank_newbook.html (captured 2026-08-13 from
    https://www.zongheng.com/rank?nav=new-book&rankType=4).

    v0.1.4: parser low-level unit tests moved to ``test_nuxt_parser.py``;
    this file exercises the integration of the parser with the adapter.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.adapters.zongheng import (
    ZonghengAdapter,
    parse_rank_payload,
    _serial_status_to_literal,
    _extract_int,
    _normalize_rank_no,
)
from scripts.adapters.base import AdapterStatus


# --- metadata ---------------------------------------------------------------

def test_zongheng_adapter_metadata():
    a = ZonghengAdapter()
    assert a.platform == "zongheng"
    assert a.strategy.value == "webfetch"
    assert a.status == AdapterStatus.LIVE


# --- helper unit tests ------------------------------------------------------

def test_serial_status_to_literal():
    assert _serial_status_to_literal(1) == "completed"
    assert _serial_status_to_literal("1") == "completed"
    assert _serial_status_to_literal("完结") == "completed"
    assert _serial_status_to_literal(0) == "serial"
    assert _serial_status_to_literal("0") == "serial"
    assert _serial_status_to_literal("连载中") == "serial"
    assert _serial_status_to_literal(None) is None
    assert _serial_status_to_literal("unknown") is None


def test_extract_int():
    assert _extract_int("12") == 12
    assert _extract_int(12) == 12
    assert _extract_int(None) is None
    assert _extract_int("abc") is None


def test_normalize_rank_no():
    assert _normalize_rank_no(3, 1) == 3
    assert _normalize_rank_no("3", 1) == 3
    assert _normalize_rank_no(0, 5) == 5  # falsy -> fallback
    assert _normalize_rank_no(None, 7) == 7


# --- integration tests against real captured HTML ----------------------------

@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


def test_parse_rank_payload_monthly_picks_month_ticket(fixtures_dir):
    """Period=monthly -> monthTicketRankList (verified 2026-08-13: top entry
    is 无敌天命)."""
    html = (fixtures_dir / "zongheng_rank_newbook.html").read_text()
    books = parse_rank_payload(html, top=5, period="monthly")
    assert len(books) >= 1
    for b in books:
        assert b.platform_book_id
        assert b.title
        assert b.detail_url and b.detail_url.startswith("https://www.zongheng.com/book/")
        assert b.rank_position is not None
    assert books[0].title == "无敌天命"


def test_parse_rank_payload_weekly_picks_recommend(fixtures_dir):
    """Period=weekly -> recommendRankList."""
    html = (fixtures_dir / "zongheng_rank_newbook.html").read_text()
    books = parse_rank_payload(html, top=5, period="weekly")
    assert len(books) >= 1
    for b in books:
        assert b.platform_book_id
        assert b.title
    assert books[0].raw_payload["rank_list_key"] == "recommendRankList"


def test_parse_rank_payload_daily_picks_new_book(fixtures_dir):
    """Period=daily -> newBookRankList (verified 2026-08-13: top entry
    is 一百岁老头子)."""
    html = (fixtures_dir / "zongheng_rank_newbook.html").read_text()
    books = parse_rank_payload(html, top=5, period="daily")
    assert len(books) >= 1
    assert books[0].raw_payload["rank_list_key"] == "newBookRankList"
    assert books[0].title == "一百岁老头子，谁让你装嫩修仙了"


def test_parse_rank_payload_extracts_word_count(fixtures_dir):
    """word_count is parsed from totalWords field."""
    html = (fixtures_dir / "zongheng_rank_newbook.html").read_text()
    books = parse_rank_payload(html, top=5, period="monthly")
    # The first book 无敌天命 has totalWords=5229312 in the fixture.
    assert books[0].word_count == 5_229_312


def test_parse_rank_payload_extracts_cover_url(fixtures_dir):
    """cover_url is parsed from imageUrl field."""
    html = (fixtures_dir / "zongheng_rank_newbook.html").read_text()
    books = parse_rank_payload(html, top=5, period="monthly")
    assert books[0].cover_url and books[0].cover_url.startswith(
        "https://static.zongheng.com/upload/"
    )


def test_parse_rank_payload_respects_top_limit(fixtures_dir):
    """The top parameter caps the result count."""
    html = (fixtures_dir / "zongheng_rank_newbook.html").read_text()
    books = parse_rank_payload(html, top=2, period="monthly")
    assert len(books) == 2