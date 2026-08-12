import pytest
from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook


class FakeAdapter(BaseAdapter):
    platform = "fake"
    strategy = Strategy.DIRECT_API

    def fetch(self, category, period, top):
        return [
            RawBook(platform_book_id=str(i), title=f"book-{i}", author="a", category=category)
            for i in range(top)
        ]


def test_strategy_enum_values():
    assert Strategy.VENDOR.value == "vendor"
    assert Strategy.DIRECT_API.value == "direct_api"
    assert Strategy.WEBFETCH.value == "webfetch"


def test_adapter_subclass_must_implement_fetch():
    class IncompleteAdapter(BaseAdapter):
        platform = "x"
        strategy = Strategy.WEBFETCH

    with pytest.raises(TypeError):
        IncompleteAdapter()  # 不能实例化抽象类


def test_adapter_fetch_returns_list_of_rawbook():
    a = FakeAdapter()
    result = a.fetch("玄幻", "weekly", 3)
    assert len(result) == 3
    assert all(isinstance(r, RawBook) for r in result)
    assert all(r.category == "玄幻" for r in result)


def test_adapter_normalize_defaults_to_module_function(monkeypatch):
    """默认 normalize 应该调用 scripts.normalize.raw_to_bookitem"""
    from scripts import normalize
    called = []

    def spy(raw, platform, period):
        called.append((platform, period))
        return None  # 返回值用不到；测试只验证 spy 被调用

    monkeypatch.setattr(normalize, "raw_to_bookitem", spy)

    a = FakeAdapter()
    raw = RawBook(platform_book_id="1", title="t", author="a", category="玄幻")
    a.normalize(raw, period="weekly")

    assert called == [("fake", "weekly")]
