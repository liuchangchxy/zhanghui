"""Tests for the qimao adapter metadata + the shared Nuxt SSR parser.

Status: LIVE (verified 2026-08-13, after balanced-brace parser rewrite).

    The vendored parser's regex (``_NUXT_RE``) was rewritten as a
    balanced-brace scanner and lifted out into ``scripts/nuxt_parser.py``
    in v0.1.4 (shared with zongheng). The parser unit tests now live in
    ``tests/test_nuxt_parser.py``; this file exercises only the qimao
    adapter's integration with the parser.
"""
from __future__ import annotations

from scripts.adapters.qimao import QimaoAdapter
from scripts.adapters.base import AdapterStatus


def test_qimao_adapter_metadata():
    a = QimaoAdapter()
    assert a.platform == "qimao"
    assert a.strategy.value == "vendor"
    assert a.status == AdapterStatus.LIVE


def test_qimao_adapter_returns_raw_books_with_required_fields(monkeypatch):
    """Adapter.fetch returns RawBook list (without hitting the network)."""
    from scripts.schema import RawBook

    fake_items = [
        {
            "book_id": "qimao_195958",
            "rank": "1",
            "title": "盖世神医",
            "author": "狐颜乱语",
            "category_label": "都市/都市高武/收藏榜",
            "reader_count": "140.2",
            "description": "intro",
            "status": "连载",
            "cover_url": "https://cdn.qimao.com/x.jpg",
            "book_url": "https://www.qimao.com/shuku/195958/",
            "source": "qimao",
        }
    ]

    def fake_fetch(channel, rank_type, top):  # noqa: ARG001
        return list(fake_items)

    monkeypatch.setattr(
        "scripts.adapters.qimao._fetch_qimao_rank", fake_fetch
    )

    a = QimaoAdapter()
    books = a.fetch("all", "weekly", 5)
    assert len(books) == 2  # both channels (boy + girl) return same list
    assert isinstance(books[0], RawBook)
    b = books[0]
    assert b.platform_book_id == "qimao_195958"
    assert b.title == "盖世神医"
    assert b.author == "狐颜乱语"
    assert b.detail_url == "https://www.qimao.com/shuku/195958/"
    assert b.rank_position == 1
    assert b.status == "serial"