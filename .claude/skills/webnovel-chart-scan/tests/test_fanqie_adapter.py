"""Tests for the fanqie adapter (Strategy.VENDOR, Playwright-backed).

NOTE on real upstream shape (2026-08-12):
    The vendored ``scrape_fanqie_ranks.run_scraper`` returns a dict whose
    book entries use these keys (verified against the upstream's daily
    ``data/latest_ranks.json``):

        { "title": str, "author": str, "reads": str,
          "intro": str, "cover": str, "url": str }

    There is no ``bookName``/``bookId``/``category``/``rank`` field at
    book level (the category lives one level up at ``{"name", "books": [...]}"``,
    and rank is just list index). The Task-8 spec's sample used the
    non-existent ``bookName``/``bookId``/``rank`` keys; we follow the
    real upstream shape instead (see Task-7 review lesson).
"""
from __future__ import annotations

import pytest

from scripts.adapters.fanqie import FanqieAdapter, parse_fanqie_rank_list


# Real-shape sample: matches the upstream's books[*] entries exactly.
SAMPLE_FANQIE_RANK = [
    {
        "title": "领主：我在苦痛世界，养成少女",
        "author": "嘎嘎乱写",
        "reads": "44万",
        "intro": "穿越中世纪，成为一名叫“菲尔德”的贵族。",
        "cover": "https://p3-reading-sign.fqnovelpic.com/novel-pic/xxx",
        "url": "https://fanqienovel.com/page/7320218217488600126",
    },
]


def test_parse_fanqie_rank_list():
    books = parse_fanqie_rank_list(SAMPLE_FANQIE_RANK, top=10)
    assert len(books) == 1
    assert books[0].title == "领主：我在苦痛世界，养成少女"
    assert books[0].author == "嘎嘎乱写"
    assert books[0].intro.startswith("穿越中世纪")
    assert books[0].cover_url and books[0].cover_url.startswith("https://")
    assert books[0].detail_url and "fanqienovel.com/page/" in books[0].detail_url
    assert books[0].rank_position == 1


def test_fanqie_adapter_metadata():
    a = FanqieAdapter()
    assert a.platform == "fanqie"
    assert a.strategy.value == "vendor"


def test_fanqie_adapter_fetch_missing_playwright(monkeypatch):
    """If Playwright is not importable, fetch() must raise a clear RuntimeError,
    not a bare ModuleNotFoundError (per the spec)."""
    a = FanqieAdapter()

    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "vendor.fanqie_rank_tracker.scrape_fanqie_ranks":
            raise ImportError("simulated: playwright not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    with pytest.raises(RuntimeError, match="Playwright"):
        # category="all" is the only value accepted by fanqie VENDOR; the
        # import-failure path we want to exercise is downstream of that.
        a.fetch(category="all", period="daily", top=10)


def test_parse_fanqie_rank_list_truncates_to_top():
    raw = SAMPLE_FANQIE_RANK * 5  # 5 copies
    books = parse_fanqie_rank_list(raw, top=3)
    assert len(books) == 3
    assert [b.rank_position for b in books] == [1, 2, 3]


def test_parse_fanqie_rank_list_handles_missing_fields():
    """Parser must tolerate missing keys (real data sometimes omits intro)."""
    books = parse_fanqie_rank_list([{"title": "孤儿"}], top=10)
    assert len(books) == 1
    assert books[0].title == "孤儿"
    assert books[0].author == ""
    assert books[0].rank_position == 1


def test_fanqie_adapter_raises_for_specific_category():
    """传具体分类时应显式报错，不静默吞掉（与 zongheng 一致）。"""
    a = FanqieAdapter()
    with pytest.raises(NotImplementedError, match="does not support category"):
        a.fetch("玄幻", "weekly", 10)
