"""TARGETED adversarial verification of the v0.2 chart-scan CRITICAL fixes.

This file independently re-creates the adversarial test scenarios for
C1, C2, C3, C4 (separate from the existing test_fanqie_adapter.py /
test_ciweimao_runner.py tests). If the underlying fix is broken, these
tests will FAIL — they are written skeptically, not confirmatorily.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from scripts.adapters.fanqie import FanqieAdapter
from scripts.adapters import fanqie as fanqie_mod
from scripts.adapters.ciweimao_runner import parse_rank_markdown

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fanqie_dump_20260815.json"


def _fake_httpx_get_factory(fixture_path: Path):
    def _fake_get(url, **kwargs):
        content = fixture_path.read_bytes()
        return httpx.Response(200, content=content, request=httpx.Request("GET", url))
    return _fake_get


def _fake_httpx_html_factory(body: str):
    def _fake_get(url, **kwargs):
        return httpx.Response(
            200, text=body,
            request=httpx.Request("GET", url),
        )
    return _fake_get


# ─────────────────────────────────────────────────────────────────────
# C1: fanqie cache corruption recovery
# ─────────────────────────────────────────────────────────────────────

def test_C1_corrupted_cache_recovers(monkeypatch, tmp_path):
    """C1: a corrupted cache file must not crash; _download_dump should
    log, delete the cache, and re-download.

    Adversarial conditions:
    - Broken JSON pre-written to cache directory.
    - httpx mocked to return valid JSON.
    - Verify books returned, broken cache DELETED, new valid cache
      written, NO exception propagates.
    """
    monkeypatch.setattr(fanqie_mod, "CACHE_DIR", tmp_path)

    # Pre-write a corrupted cache file
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    cache_file = tmp_path / f"fanqie_dump_{date_str}.json"
    cache_file.write_text("{not valid json<@@>", encoding="utf-8")
    assert cache_file.exists(), "precondition — broken cache must exist"

    fake_get = _fake_httpx_get_factory(FIXTURE_PATH)
    with patch("scripts.adapters.fanqie.httpx.get", side_effect=fake_get):
        # Must NOT raise
        books = FanqieAdapter().fetch("玄幻", "weekly", top=5)

    # Books returned
    assert len(books) > 0, f"expected >0 books, got {len(books)}"

    # New cache file should be valid JSON
    assert cache_file.exists(), "expected new valid cache file"
    parsed = json.loads(cache_file.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    assert "categories" in parsed


# ─────────────────────────────────────────────────────────────────────
# C2: fanqie non-JSON 200 OK clear error
# ─────────────────────────────────────────────────────────────────────

def test_C2_non_json_200_raises_runtime_error(monkeypatch, tmp_path):
    """C2: a non-JSON 200 OK response must raise RuntimeError with a clear
    message naming content-type + first chars (NOT JSONDecodeError).
    """
    monkeypatch.setattr(fanqie_mod, "CACHE_DIR", tmp_path)
    fake_get = _fake_httpx_html_factory(
        "<html><body>Rate limit exceeded</body></html>"
    )
    with patch("scripts.adapters.fanqie.httpx.get", side_effect=fake_get):
        with pytest.raises(RuntimeError) as excinfo:
            FanqieAdapter().fetch("玄幻", "weekly", top=5)

    msg = str(excinfo.value)
    assert "non-JSON" in msg or "Content-Type" in msg, (
        f"error message should mention non-JSON/Content-Type, got: {msg!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# C3: fanqie parse-before-cache — no cache write on failure
# ─────────────────────────────────────────────────────────────────────

def test_C3_no_cache_on_parse_failure(monkeypatch, tmp_path):
    """C3: when upstream returns non-JSON, no cache file should be
    written so the next call retries from upstream.
    """
    monkeypatch.setattr(fanqie_mod, "CACHE_DIR", tmp_path)
    # Sanity: cache dir starts empty
    assert list(tmp_path.glob("fanqie_dump_*.json")) == []

    fake_get = _fake_httpx_html_factory("<html>bad upstream</html>")
    with patch("scripts.adapters.fanqie.httpx.get", side_effect=fake_get):
        with pytest.raises(RuntimeError):
            FanqieAdapter().fetch("玄幻", "weekly", top=5)

    # After the call, NO cache files should exist
    cache_files = list(tmp_path.glob("fanqie_dump_*.json"))
    assert cache_files == [], (
        f"expected no cache files on failure, found: {cache_files}"
    )


# ─────────────────────────────────────────────────────────────────────
# C4: ciweimao parser robustness vs upstream format change
# ─────────────────────────────────────────────────────────────────────

def test_C4_rank1_genre_label_routed_correctly():
    """C4: when rank-1 meta line is `*<genre> · <author> · <metric>*`
    (3 fields including genre, as upstream might emit in the future),
    the genre should be classified as category, NOT mis-assigned as
    author, AND ``raw_payload["author_missing"]`` should be True.

    NOTE: title deliberately lacks genre keywords so we are testing the
    C4 genre-routing path, NOT the I6 title-heuristic fallback path.
    """
    md = (
        "# 刺猬猫 · 测试\n"
        "\n"
        "---\n"
        "\n"
        "### #1 一本普通书名\n"  # NO genre keywords in title
        "*玄幻 · 嘎嘎乱写 · 43万*\n"  # 3 fields: genre, author, metric
        "[作品页](https://www.ciweimao.com/book/100000010)\n"
        "\n"
        "---\n"
    )
    books = parse_rank_markdown(md, top=10)
    assert len(books) == 1, f"expected 1 book, got {len(books)}"
    first = books[0]

    # The genre "玄幻" should be in category (not author)
    assert first.author != "玄幻", (
        f"author must NOT be '玄幻', got: {first.author!r}"
    )
    assert first.category == "玄幻", (
        f"category should be '玄幻', got: {first.category!r}"
    )
    # author_missing flag must be set (author is genuinely unknown)
    assert first.raw_payload.get("author_missing") is True, (
        f"author_missing flag should be set, raw_payload: {first.raw_payload}"
    )
    # Sanity: title-keyword heuristic did NOT fire (would have re-flagged
    # but for the C4 reason). Title contains no genre keywords, so if
    # C4 wasn't active, category would be "" instead of "玄幻".
    assert first.raw_payload.get("native_category") == "玄幻"


def test_C4_existing_test_file_passes():
    """Sanity check: the existing C4 test in test_ciweimao_runner.py
    passes. This catches the case where the in-file test was added but
    the parser logic was reverted.
    """
    # We re-implement the assertion rather than importing the test fn
    # (avoids running into any test-collection issues).
    md = (
        "# 刺猬猫 · 测试\n"
        "\n"
        "---\n"
        "\n"
        "### #1 仙侠小说名\n"
        "*仙侠 · 234万*\n"
        "[作品页](https://www.ciweimao.com/book/100000002)\n"
        "\n"
        "---\n"
    )
    books = parse_rank_markdown(md, top=10)
    assert len(books) == 1
    assert books[0].author == ""
    assert books[0].category == "仙侠"
    assert books[0].raw_payload.get("author_missing") is True