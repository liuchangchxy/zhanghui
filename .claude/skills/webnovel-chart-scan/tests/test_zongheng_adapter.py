import json
from pathlib import Path
import httpx
import pytest

from scripts.adapters.zongheng import ZonghengAdapter, parse_rank_response


def test_parse_rank_response_extracts_basic_fields():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "zongheng_rank_details.json").read_text()
    )
    books = parse_rank_response(fixture, top=5)
    assert len(books) == 5
    assert all(b.platform_book_id for b in books)
    assert all(b.title for b in books)
    assert all(b.author for b in books)
    assert all(b.rank_position is not None for b in books)


def test_zongheng_adapter_metadata():
    a = ZonghengAdapter()
    assert a.platform == "zongheng"
    assert a.strategy.value == "direct_api"


def test_zongheng_adapter_fetch_uses_httpx(monkeypatch):
    """mock httpx.get，验证 URL 和 headers 正确。"""
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        captured["params"] = kwargs.get("params", {})

        class Resp:
            def __init__(self):
                self.status_code = 200

            def json(self):
                return {"data": {"bookList": []}}

            def raise_for_status(self):
                pass

        return Resp()

    monkeypatch.setattr(httpx, "get", fake_get)
    a = ZonghengAdapter()
    a.fetch("all", "weekly", 10)  # zongheng 不支持 category 过滤

    assert "zongheng.com" in captured["url"]
    assert captured["headers"].get("User-Agent", "").startswith("Mozilla")
    assert captured["params"].get("pageSize") == 10


def test_zongheng_adapter_raises_for_specific_category():
    """传具体分类时应显式报错，不静默吞掉。"""
    a = ZonghengAdapter()
    with pytest.raises(NotImplementedError, match="does not support category"):
        a.fetch("玄幻", "weekly", 10)