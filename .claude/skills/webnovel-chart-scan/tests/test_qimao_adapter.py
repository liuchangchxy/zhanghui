"""Tests for the qimao adapter (Strategy.VENDOR).

NOTE on real upstream shape (2026-08-12):
    The vendored ``qimao_web_crawler_subset.qimao_subset.crawl_qimao_rank``
    returns a list of dicts keyed exactly like the upstream's
    ``QimaoCrawler.crawl_rankings()`` output::

        {
            "book_id":       "qimao_<bid>",   # always prefixed upstream
            "rank":          "<1-based row>",
            "title":         str,
            "author":        str,
            "book_url":      str,
            "description":   str,
            "status":        "完结" | "连载",
            "reader_count":  str,
            "category_label": str,            # "<ch>/<cat1>[/<cat2>]/<rank>"
            "cover_url":     str,
            "source":        "qimao",
        }

    The Task-9 spec sample used non-existent keys
    (``bookName``/``authorName``/``categoryName``/``bookId``/``rankNo``);
    we follow the real upstream shape instead (see Task-7/8 review lessons
    "use real upstream field names").
"""
from __future__ import annotations

import pytest

from scripts.adapters.qimao import QimaoAdapter, parse_qimao_rank


# Real-shape sample: matches the upstream's per-book dict exactly.
SAMPLE_QIMAO_RANK = [
    {
        "book_id": "qimao_12345",
        "rank": "1",
        "title": "示例书名",
        "author": "示例作者",
        "book_url": "https://www.qimao.com/shuku/12345/",
        "description": "示例简介",
        "status": "连载",
        "reader_count": "12.3",
        "category_label": "男生/玄幻奇幻/大热榜",
        "cover_url": "https://cdn.qimao.com/bookimg/zww/upload/readerCover/68/x_360x480.jpg",
        "source": "qimao",
    },
]


def test_parse_qimao_rank_basic_fields():
    books = parse_qimao_rank(SAMPLE_QIMAO_RANK, top=10)
    assert len(books) == 1
    assert books[0].title == "示例书名"
    assert books[0].author == "示例作者"
    assert books[0].platform_book_id == "qimao_12345"
    assert books[0].category == "男生/玄幻奇幻/大热榜"
    assert books[0].rank_position == 1
    assert books[0].cover_url and books[0].cover_url.startswith("https://")
    assert books[0].detail_url and "qimao.com/shuku/12345" in books[0].detail_url


def test_qimao_adapter_metadata():
    a = QimaoAdapter()
    assert a.platform == "qimao"
    assert a.strategy.value == "vendor"


def test_parse_qimao_rank_truncates_to_top():
    raw = SAMPLE_QIMAO_RANK * 5  # 5 copies with rank="1" each
    books = parse_qimao_rank(raw, top=3)
    assert len(books) == 3
    # Upstream `rank` may collide across copies; parser tolerates either
    # repeated-rank or 1-based-list-index semantics (both are valid downstream
    # since we expose raw_payload).
    assert all(b.rank_position in (1, i + 1) for i, b in enumerate(books))


def test_parse_qimao_rank_handles_missing_fields():
    """Parser must tolerate missing keys (real data sometimes omits cover)."""
    books = parse_qimao_rank([{"title": "孤儿"}], top=10)
    assert len(books) == 1
    assert books[0].title == "孤儿"
    assert books[0].author == ""
    assert books[0].rank_position == 1
    assert books[0].platform_book_id == ""


def test_parse_qimao_rank_falls_back_rank_to_index():
    """If upstream omits ``rank`` field, parser falls back to 1-based index."""
    raw = [{"title": "A"}, {"title": "B"}]
    books = parse_qimao_rank(raw, top=10)
    assert [b.rank_position for b in books] == [1, 2]


def test_qimao_adapter_raises_for_specific_category():
    """七猫上游只支持 channelType x rankType 组合，不支持精确分类。

    传具体分类（如 ``玄幻``）时应显式报错，不静默吞掉（与 zongheng/fanqie 一致）。
    """
    a = QimaoAdapter()
    with pytest.raises(NotImplementedError, match="does not support category"):
        a.fetch("玄幻", "daily", 10)
