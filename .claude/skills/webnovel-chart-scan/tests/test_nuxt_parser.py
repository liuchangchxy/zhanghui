"""Unit tests for the shared Nuxt SSR ``__NUXT__`` parser.

Extracted from ``test_qimao_adapter.py`` in v0.1.4 so the parser logic
(used by both qimao + zongheng adapters) has one home for tests.

The parser replaced a broken upstream regex (``_NUXT_RE``) that did
not handle nested braces inside the real upstream payload (e.g. the
``fetch:{"data-v-cca2d2e4:0":{listData:[...]}}`` block).
"""
from __future__ import annotations

from scripts.nuxt_parser import (
    parse_nuxt_payload,
    scan_balanced,
    split_top_level_csv,
)


# --- scan_balanced ------------------------------------------------------------

def test_scan_balanced_finds_matching_brace():
    """Plain case: single nested brace pair."""
    text = '{a:1,b:{c:2}}'
    close_idx, content = scan_balanced(text, 0, "{", "}")
    assert close_idx == 12
    assert content == "a:1,b:{c:2}"


def test_scan_balanced_handles_strings_with_braces():
    """Brace inside a quoted string is NOT treated as a depth change."""
    text = '{a:"}",b:1}'
    # The first '{' at index 0 — its matching '}' is the last char.
    close_idx, content = scan_balanced(text, 0, "{", "}")
    assert close_idx == 10
    assert content == 'a:"}",b:1'


def test_scan_balanced_returns_minus_one_when_unbalanced():
    """Unbalanced input returns (-1, "") so callers can fail loudly."""
    text = '{a:1,b:2'
    assert scan_balanced(text, 0, "{", "}") == (-1, "")


def test_scan_balanced_returns_minus_one_when_start_is_wrong_char():
    """If s[start] is not the open char, the function does not try."""
    text = 'a{b:1}'
    assert scan_balanced(text, 0, "{", "}") == (-1, "")


def test_scan_balanced_handles_parens():
    """scan_balanced is generic over open/close — works for parens too."""
    text = "(a, (b, c), d)"
    close_idx, content = scan_balanced(text, 0, "(", ")")
    assert close_idx == len(text) - 1
    assert content == "a, (b, c), d"


# --- split_top_level_csv ------------------------------------------------------

def test_split_top_level_csv_handles_nested_braces():
    """Commas inside nested brackets/braces/parens are not separators."""
    text = 'a:1,b:{c:2,d:[3,4]},e:"x,y"'
    parts = split_top_level_csv(text, 0)
    assert len(parts) == 3
    assert parts[0] == "a:1"
    assert parts[1] == "b:{c:2,d:[3,4]}"
    assert parts[2] == 'e:"x,y"'


def test_split_top_level_csv_respects_start_offset():
    """The start parameter lets the caller skip leading characters."""
    text = '   a:1,b:2,c:3'
    parts = split_top_level_csv(text, 3)
    assert parts == ["a:1", "b:2", "c:3"]


def test_split_top_level_csv_handles_empty_input():
    assert split_top_level_csv("", 0) == []


def test_split_top_level_csv_handles_escape_sequences():
    """Escape sequences inside strings are tracked correctly."""
    text = 'a:"foo\\",bar",b:2'
    parts = split_top_level_csv(text, 0)
    # The escaped quote does not terminate the string.
    assert parts[0] == 'a:"foo\\",bar"'
    assert parts[1] == "b:2"


# --- parse_nuxt_payload -------------------------------------------------------

def test_parse_nuxt_payload_returns_empty_for_missing_marker():
    assert parse_nuxt_payload("<html>no marker here</html>") == {}


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
    parsed = parse_nuxt_payload(html)
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
    parsed = parse_nuxt_payload(html)
    assert parsed == {"layout": "x", "name": "alice"}


def test_parse_nuxt_payload_does_not_substitute_inside_strings():
    """Identifiers inside quoted strings (``"data-v-cca2d2e4:0"``) must
    NOT be substituted — only outside-string identifiers."""
    html = (
        'window.__NUXT__=(function(a){return {'
        'fetch:{"data-v-hash:0":{listData:[{title:a}]}}'
        '}})("Book");'
    )
    parsed = parse_nuxt_payload(html)
    fetch_keys = list(parsed["fetch"].keys())
    assert "data-v-hash:0" in fetch_keys
    assert parsed["fetch"]["data-v-hash:0"]["listData"][0]["title"] == "Book"


def test_parse_nuxt_payload_strips_return_keyword():
    html = (
        'window.__NUXT__=(function(a){return {key:a}})("value");'
    )
    parsed = parse_nuxt_payload(html)
    assert parsed == {"key": "value"}


def test_parse_nuxt_payload_returns_empty_for_malformed():
    """Bad input -> empty dict (caller checks truthiness)."""
    assert parse_nuxt_payload("window.__NUXT__=(function(a){return {key:}") == {}
    assert parse_nuxt_payload("window.__NUXT__=(function(") == {}
    assert parse_nuxt_payload("window.__NUXT__=not a function call") == {}