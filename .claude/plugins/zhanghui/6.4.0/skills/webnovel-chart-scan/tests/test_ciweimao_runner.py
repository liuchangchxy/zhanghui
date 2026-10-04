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
from unittest.mock import patch

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


# ─────────────────────────────────────────────────────────────────────
# Adversarial review v0.2.1 fixes (C4+I6+M1+M2)
# ─────────────────────────────────────────────────────────────────────


def test_parse_word_count_supports_qian():
    """M1: 千 (thousand) suffix must parse as 1,000× multiplier."""
    from scripts.adapters.ciweimao_runner import parse_word_count
    assert parse_word_count("5.6千") == 5_600
    assert parse_word_count("10千") == 10_000
    assert parse_word_count("0千") == 0


def test_parse_rank_markdown_warns_on_empty(caplog):
    """M2: empty/whitespace markdown must log a warning and return []."""
    import logging
    caplog.set_level(logging.WARNING, logger="scripts.adapters.ciweimao_runner")
    books = parse_rank_markdown("", top=10)
    assert books == []
    books = parse_rank_markdown("   \n  \n", top=10)
    assert books == []
    assert any("empty markdown" in rec.message for rec in caplog.records), (
        f"expected a warning about empty markdown, got: "
        f"{[r.message for r in caplog.records]}"
    )


def test_parse_rank_markdown_flags_author_missing_when_no_meta():
    """C4: rank-1 with no upstream author OR category must set
    ``raw_payload["author_missing"] = True``.
    """
    md = (
        "# 刺猬猫 · 测试\n"
        "\n"
        "---\n"
        "\n"
        "### #1 未知作者书\n"
        "*234万*\n"  # metric only — no author, no genre
        "[作品页](https://www.ciweimao.com/book/100000001)\n"
        "\n"
        "---\n"
    )
    books = parse_rank_markdown(md, top=10)
    assert len(books) == 1
    assert books[0].author == ""
    assert books[0].raw_payload.get("author_missing") is True


def test_parse_rank_markdown_c4_routes_genre_in_rank1():
    """C4: if rank-1 meta label is a known genre (upstream format change),
    treat it as category and flag ``author_missing``.
    """
    md = (
        "# 刺猬猫 · 测试\n"
        "\n"
        "---\n"
        "\n"
        "### #1 仙侠小说名\n"
        "*仙侠 · 234万*\n"  # upstream may have shifted to genre+metric for #1
        "[作品页](https://www.ciweimao.com/book/100000002)\n"
        "\n"
        "---\n"
    )
    books = parse_rank_markdown(md, top=10)
    assert len(books) == 1
    # The label "仙侠" is a known genre → routed to category, NOT author
    assert books[0].author == ""
    assert books[0].category == "仙侠"
    assert books[0].raw_payload.get("author_missing") is True


def test_parse_rank_markdown_i6_title_heuristic_fills_rank1():
    """I6: rank-1 with no upstream genre AND no upstream author must
    try a title-keyword heuristic.
    """
    md = (
        "# 刺猬猫 · 测试\n"
        "\n"
        "---\n"
        "\n"
        "### #1 仙侠巅峰之路\n"  # title contains 仙侠
        "*234万*\n"
        "[作品页](https://www.ciweimao.com/book/100000003)\n"
        "\n"
        "---\n"
    )
    books = parse_rank_markdown(md, top=10)
    assert len(books) == 1
    assert books[0].category == "仙侠"
    # Heuristic was used → author is unknown → flag set
    assert books[0].raw_payload.get("author_missing") is True


def test_parse_rank_markdown_i6_title_heuristic_no_match_leaves_blank():
    """I6: rank-1 with no upstream genre AND no keyword in title must
    leave ``category=""`` AND set ``author_missing``.
    """
    md = (
        "# 刺猬猫 · 测试\n"
        "\n"
        "---\n"
        "\n"
        "### #1 一本没有关键词的书\n"
        "*234万*\n"
        "[作品页](https://www.ciweimao.com/book/100000004)\n"
        "\n"
        "---\n"
    )
    books = parse_rank_markdown(md, top=10)
    assert len(books) == 1
    assert books[0].category == ""
    assert books[0].raw_payload.get("author_missing") is True


def test_parse_rank_markdown_rank2_does_not_set_author_missing():
    """Rank >= 2 entries upstream-known author is unknown — we should NOT
    flag ``author_missing`` for them (that's a known upstream gap, not a
    regression we introduced; the docstring in ciweimao_runner covers it)."""
    md = FIXTURE_PATH.read_text(encoding="utf-8")
    books = parse_rank_markdown(md, top=10)
    second = books[1]  # rank 2 (genre+metric, no author)
    assert second.rank_position == 2
    assert second.author == ""
    # author_missing is reserved for the C4 rank-1 case
    assert "author_missing" not in second.raw_payload


def test_run_scraper_uses_mtime_not_lexical(tmp_path):
    """I3: when multiple files match the prefix, the most-recently-modified
    must win (not the lexically-latest).
    """
    import os
    import time

    from scripts.adapters.ciweimao_runner import run_scraper

    output_dir = tmp_path / "ciweimao"
    output_dir.mkdir()

    # Two files with the same prefix; older one has a lexically-higher name
    # to prove we're not picking the lexical max.
    older = output_dir / "刺猬猫点击榜_20260810.md"
    older.write_text("# older", encoding="utf-8")
    os.utime(older, (time.time() - 3600, time.time() - 3600))

    newer = output_dir / "刺猬猫点击榜_20260815.md"
    newer.write_text("# newer", encoding="utf-8")

    # Mock subprocess.run to avoid actually shelling out to node
    class _FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""
    with patch("subprocess.run", return_value=_FakeResult()):
        result = run_scraper("点击榜", output_dir)

    assert result == newer, (
        f"expected most-recently-modified ({newer}), got {result}"
    )


def test_run_scraper_fallback_glob_handles_bak_suffix(tmp_path):
    """I3: when the canonical .md glob misses, try a fallback glob that
    picks up .bak / .OLD etc.
    """
    import os
    import time

    from scripts.adapters.ciweimao_runner import run_scraper

    output_dir = tmp_path / "ciweimao"
    output_dir.mkdir()

    # Only a .bak file exists (no plain .md)
    bak = output_dir / "刺猬猫点击榜_20260815.md.bak"
    bak.write_text("# backup", encoding="utf-8")
    os.utime(bak, (time.time(), time.time()))

    class _FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""
    with patch("subprocess.run", return_value=_FakeResult()):
        result = run_scraper("点击榜", output_dir)

    assert result == bak