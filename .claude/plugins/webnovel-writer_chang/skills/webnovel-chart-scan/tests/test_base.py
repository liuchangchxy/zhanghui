import pytest
from scripts.adapters.base import BaseAdapter, Strategy, AdapterStatus
from scripts.schema import RawBook


class FakeAdapter(BaseAdapter):
    platform = "fake"
    strategy = Strategy.DIRECT_API
    status = AdapterStatus.LIVE

    def fetch(self, category, period, top):
        return [
            RawBook(platform_book_id=str(i), title=f"book-{i}", author="a", category=category)
            for i in range(top)
        ]


def test_strategy_enum_values():
    assert Strategy.VENDOR.value == "vendor"
    assert Strategy.DIRECT_API.value == "direct_api"
    assert Strategy.WEBFETCH.value == "webfetch"


def test_adapter_status_enum_values():
    assert AdapterStatus.LIVE.value == "live"
    assert AdapterStatus.LIVE_WITH_SETUP.value == "live_with_setup"
    assert AdapterStatus.BLOCKED_EXTERNAL.value == "blocked_external"
    assert AdapterStatus.BLOCKED_IMPLEMENTATION.value == "blocked_implementation"


def test_base_adapter_default_status_is_live():
    """Default status on BaseAdapter is LIVE; subclasses override."""

    class PlainAdapter(BaseAdapter):
        def fetch(self, category, period, top):
            return []

    a = PlainAdapter()
    assert a.status == AdapterStatus.LIVE


def test_base_adapter_default_fetch_raises_for_blocked_subclass():
    """A subclass that doesn't override fetch() can still be instantiated;
    calling fetch() then raises NotImplementedError with the status in
    the message (orchestrator short-circuits before reaching this in
    production, but the placeholder is the safety net)."""

    class BlockedAdapter(BaseAdapter):
        platform = "blocked_test"
        strategy = Strategy.VENDOR
        status = AdapterStatus.BLOCKED_EXTERNAL

    a = BlockedAdapter()
    with pytest.raises(NotImplementedError, match="blocked_external"):
        a.fetch("玄幻", "weekly", 5)


def test_live_with_setup_status_is_distinct_from_live():
    """LIVE_WITH_SETUP must be a distinct enum value (not aliased to
    LIVE) so the orchestrator and reports can tell them apart."""

    class SetupAdapter(BaseAdapter):
        platform = "setup_test"
        strategy = Strategy.WEBFETCH
        status = AdapterStatus.LIVE_WITH_SETUP

    a = SetupAdapter()
    assert a.status is not AdapterStatus.LIVE
    assert a.status is AdapterStatus.LIVE_WITH_SETUP
    assert a.status.value == "live_with_setup"


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
