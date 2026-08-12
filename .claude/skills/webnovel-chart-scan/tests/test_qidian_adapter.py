"""Tests for the qidian adapter (Strategy.VENDOR).

NOTE on real endpoint (2026-08-12):
    https://www.qidian.com/all returns HTTP 202 with a probe.js anti-bot
    challenge. The vendored upstream (saudadez21/novel-downloader) solves
    this with RC4 cookie computation (see ``qidian_subset/searcher.py``).
    These tests therefore use a synthesized fixture matching the spec'd
    payload shape; an end-to-end network test is out of scope until the
    probe.js bypass is implemented.
"""
import httpx

from scripts.adapters.qidian import QidianAdapter, parse_qidian_list_json

# 起点公开榜 JSON 片段示例（真实抓取后再调整）
SAMPLE_QIDIAN_LIST = {
    "code": 0,
    "data": {
        "books": [
            {
                "bookId": "12345",
                "bookName": "凡人修仙传",
                "authorName": "忘语",
                "categoryName": "仙侠",
                "coverUrl": "https://example.com/c.jpg",
            }
        ]
    },
}


def test_parse_qidian_list_json_extracts_fields():
    books = parse_qidian_list_json(SAMPLE_QIDIAN_LIST, top=10)
    assert len(books) == 1
    assert books[0].title == "凡人修仙传"
    assert books[0].author == "忘语"
    assert books[0].category == "仙侠"


def test_qidian_adapter_metadata():
    a = QidianAdapter()
    assert a.platform == "qidian"
    assert a.strategy.value == "vendor"


def test_qidian_adapter_fetch_calls_qidian_endpoint(monkeypatch):
    """Verify URL construction & headers for the spec'd endpoint."""
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        captured["params"] = kwargs.get("params", {})

        class Resp:
            status_code = 200

            def json(self_inner):
                return SAMPLE_QIDIAN_LIST

            def raise_for_status(self_inner):
                pass

        return Resp()

    monkeypatch.setattr(httpx, "get", fake_get)
    a = QidianAdapter()
    a.fetch("仙侠", "monthly", 10)

    assert "qidian.com" in captured["url"]
    assert captured["headers"].get("User-Agent", "").startswith("Mozilla")
    assert captured["headers"].get("Referer", "").startswith("https://www.qidian.com")
    # chanId for 仙侠 is 22 per QIDIAN_CATEGORY_IDS
    assert captured["params"].get("chanId") == 22
    assert captured["params"].get("pageSize") == 10


def test_qidian_adapter_fetch_all_uses_chan_id_minus_one(monkeypatch):
    """category='all' should map to chanId=-1 (全部分类)."""
    captured = {}

    def fake_get(url, **kwargs):
        captured["params"] = kwargs.get("params", {})

        class Resp:
            status_code = 200

            def json(self_inner):
                return {"code": 0, "data": {"books": []}}

            def raise_for_status(self_inner):
                pass

        return Resp()

    monkeypatch.setattr(httpx, "get", fake_get)
    a = QidianAdapter()
    a.fetch("all", "daily", 20)

    assert captured["params"].get("chanId") == -1
    assert captured["params"].get("pageSize") == 20