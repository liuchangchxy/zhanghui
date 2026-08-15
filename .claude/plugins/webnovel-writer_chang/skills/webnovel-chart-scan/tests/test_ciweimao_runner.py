"""Tests for the ciweimao Node subprocess wrapper.

The worldwonderer/oh-story-claudecode project ships a Node.js scraper
(``ciweimao-rank-scraper.js``) that uses Chrome DevTools Protocol to
bypass ciweimao.com's anti-bot captcha. It writes per-rank Markdown
files. We shell out to it via subprocess, then parse the Markdown
output into RawBook objects.

These tests cover the Markdown parser only — the subprocess invocation
is exercised separately in test_ciweimao_adapter.py (with mocked
subprocess) and in test_ciweimao_runner_integration.py (slow integration
test that actually invokes the vendored JS via Node.js).

Fixture format matches the REAL JS output (verified against vendored
ciweimao-rank-scraper.js, commit 6af05297, 2026-08-16):

    # 刺猬猫 · 点击榜
    - 来源：...
    - 抓取时间：...
    - 条目数：3
    - 作品页链接：3 / 3
    ---

    ### #1 我在诡异世界当神棍
    *梧桐阅读 · 234万*                    # NO.1: author + metric (genre is empty upstream)
    [作品页](https://www.ciweimao.com/book/100123456)

    ---

    ### #2 模拟修仙：从一生二开始
    *仙侠 · 156万*                         # #2-10: genre + metric (author is empty upstream)
    [作品页](https://www.ciweimao.com/book/100234567)

    ---

    ### #3 诡秘复苏：我能看见诡异
    *悬疑灵异 · 89万*
    [作品页](https://www.ciweimao.com/book/100345678)

    ---
"""
from __future__ import annotations

from pathlib import Path

from scripts.adapters.ciweimao_runner import parse_rank_markdown


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ciweimao_rank_click.md"


def test_parse_rank_markdown_extracts_all_books():
    md = FIXTURE_PATH.read_text(encoding="utf-8")
    books = parse_rank_markdown(md, top=10)
    assert len(books) == 3, f"expected 3 books, got {len(books)}"


def test_parse_rank_markdown_extracts_no1_fields():
    """NO.1 entries have author + metric, NO genre (per JS output)."""
    md = FIXTURE_PATH.read_text(encoding="utf-8")
    books = parse_rank_markdown(md, top=10)
    first = books[0]  # rank 1 (NO.1)
    assert first.rank_position == 1
    assert first.title == "我在诡异世界当神棍"
    assert first.author == "梧桐阅读"
    # NO.1 has no genre in the upstream JS output (genre="" in the entry)
    assert first.category == ""
    assert first.raw_payload["native_category"] == ""
    assert first.detail_url == "https://www.ciweimao.com/book/100123456"
    assert first.platform_book_id == "100123456"
    # Metric "234万" is parsed via parse_word_count, surfaced as word_count
    # for backwards compatibility with the existing RawBook schema.
    assert first.word_count == 2340000  # 234万 → 2340000
    assert first.raw_payload["metric"] == "234万"


def test_parse_rank_markdown_extracts_rank2_fields():
    """#2-10 entries have genre + metric, NO author (per JS output)."""
    md = FIXTURE_PATH.read_text(encoding="utf-8")
    books = parse_rank_markdown(md, top=10)
    second = books[1]  # rank 2
    assert second.rank_position == 2
    assert second.title == "模拟修仙：从一生二开始"
    # #2-10 has no author in upstream JS output (author="" in the entry)
    assert second.author == ""
    # "仙侠" is already in our normalized category set — passes through unchanged
    assert second.category == "仙侠"
    assert second.raw_payload["native_category"] == "仙侠"
    assert second.detail_url == "https://www.ciweimao.com/book/100234567"
    assert second.platform_book_id == "100234567"
    assert second.word_count == 1560000  # 156万 → 1560000


def test_parse_rank_markdown_normalizes_native_category():
    """ciweimao native '悬疑灵异' should map to our normalized '灵异'."""
    md = FIXTURE_PATH.read_text(encoding="utf-8")
    books = parse_rank_markdown(md, top=10)
    third = books[2]  # rank 3 with 悬疑灵异
    assert third.category == "灵异"
    assert third.raw_payload["native_category"] == "悬疑灵异"
    assert third.word_count == 890000  # 89万 → 890000


def test_parse_rank_markdown_respects_top_limit():
    md = FIXTURE_PATH.read_text(encoding="utf-8")
    books = parse_rank_markdown(md, top=2)
    assert len(books) == 2


def test_parse_rank_markdown_handles_empty_input():
    books = parse_rank_markdown("", top=10)
    assert books == []


def test_parse_rank_markdown_handles_missing_metric():
    """A meta line with no metric (only author or genre) should still parse."""
    md = (
        "# 刺猬猫 · 测试\n"
        "\n"
        "---\n"
        "\n"
        "### #1 单字段书名\n"
        "*梧桐阅读*\n"  # author only, no metric
        "\n"
        "---\n"
    )
    books = parse_rank_markdown(md, top=10)
    assert len(books) == 1
    assert books[0].author == "梧桐阅读"
    assert books[0].word_count is None
    assert books[0].raw_payload["metric"] == ""


def test_parse_rank_markdown_handles_no_link_line():
    """A book block without [作品页](...) should leave detail_url empty."""
    md = (
        "# 刺猬猫 · 测试\n"
        "\n"
        "---\n"
        "\n"
        "### #1 无链接书名\n"
        "*梧桐阅读 · 234万*\n"
        "\n"
        "---\n"
    )
    books = parse_rank_markdown(md, top=10)
    assert len(books) == 1
    assert books[0].detail_url == ""
    assert books[0].platform_book_id == ""