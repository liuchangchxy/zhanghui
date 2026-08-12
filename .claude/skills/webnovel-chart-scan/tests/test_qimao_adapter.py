"""Tests for the qimao adapter metadata + the new ``__NUXT__`` parser.

Status: LIVE (verified 2026-08-13, after balanced-brace parser rewrite).

    The vendored parser's regex (``_NUXT_RE``) was rewritten as a
    balanced-brace scanner in ``scripts.adapters.qimao`` (see
    ``_parse_nuxt_payload``). These tests exercise the parser against
    a synthetic ``__NUXT__`` payload that mirrors the real upstream's
    shape (nested braces, identifier keys, identifier arg references).
"""
from __future__ import annotations

from scripts.adapters.qimao import (
    QimaoAdapter,
    _parse_nuxt_payload,
    _scan_balanced,
    _split_top_level_csv,
)
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


def test_split_top_level_csv_handles_nested_braces():
    # No outer wrapping — the function expects to be called with content
    # at depth 0 (e.g. comma-separated call-args), not wrapped in {...}.
    text = 'a:1,b:{c:2,d:[3,4]},e:"x,y"'
    parts = _split_top_level_csv(text)
    assert len(parts) == 3
    assert parts[0] == "a:1"
    assert parts[1] == "b:{c:2,d:[3,4]}"
    assert parts[2] == 'e:"x,y"'


def test_scan_balanced_finds_matching_brace():
    text = '{a:1,b:{c:2}}'
    assert _scan_balanced(text, 0, "{", "}") == 12


def test_scan_balanced_handles_strings_with_braces():
    text = '{a:"}",b:1}'
    # The first '{' at index 0 — its matching '}' is the last char.
    assert _scan_balanced(text, 0, "{", "}") == 10


def test_scan_balanced_returns_minus_one_when_unbalanced():
    text = '{a:1,b:2'
    assert _scan_balanced(text, 0, "{", "}") == -1


def test_parse_nuxt_payload_returns_empty_for_missing_marker():
    assert _parse_nuxt_payload("<html>no marker here</html>") == {}


def test_parse_nuxt_payload_handles_realistic_shape():
    """Mirrors the real upstream payload: nested fetch block with
    ``listData``, identifier arg references that must be substituted,
    and bare identifier keys that must be quoted for JSON parsing."""
    html = (
        'window.__NUXT__=(function(a,b,c,d){'
        'return {layout:"default-main",data:[{channelType:"boy",rankType:b}],'
        'fetch:{"data-v-cca2d2e4:0":{listData:['
        '{book_id:a,title:"Test",author:c,is_over:d}'
        ']}},serverRendered:true}'
        '})("","hot","alice",true);'
    )
    parsed = _parse_nuxt_payload(html)
    assert parsed["layout"] == "default-main"
    assert parsed["serverRendered"] is True
    assert parsed["data"][0]["channelType"] == "boy"
    assert parsed["data"][0]["rankType"] == "hot"
    fetch = parsed["fetch"]
    # Find the listData block (key includes the data-v hash)
    list_data = None
    for v in fetch.values():
        if isinstance(v, dict) and "listData" in v:
            list_data = v["listData"]
            break
    assert list_data is not None
    assert len(list_data) == 1
    book = list_data[0]
    assert book["book_id"] == ""
    assert book["title"] == "Test"
    assert book["author"] == "alice"
    assert book["is_over"] is True


def test_parse_nuxt_payload_quotes_bare_keys():
    """Bare identifier keys (``layout:``) must become quoted for JSON
    parsing — otherwise ``json.loads`` rejects the payload."""
    html = (
        'window.__NUXT__=(function(a){return {layout:"x",name:a}})("alice");'
    )
    parsed = _parse_nuxt_payload(html)
    assert parsed == {"layout": "x", "name": "alice"}


def test_parse_nuxt_payload_does_not_substitute_inside_strings():
    """Identifiers inside quoted strings (``"data-v-cca2d2e4:0"``) must
    NOT be substituted — only outside-string identifiers."""
    html = (
        'window.__NUXT__=(function(a){return {'
        'fetch:{"data-v-hash:0":{listData:[{title:a}]}}'
        '}})("Book");'
    )
    parsed = _parse_nuxt_payload(html)
    fetch_keys = list(parsed["fetch"].keys())
    assert "data-v-hash:0" in fetch_keys
    assert parsed["fetch"]["data-v-hash:0"]["listData"][0]["title"] == "Book"


def test_parse_nuxt_payload_strips_return_keyword():
    html = (
        'window.__NUXT__=(function(a){return {key:a}})("value");'
    )
    parsed = _parse_nuxt_payload(html)
    assert parsed == {"key": "value"}