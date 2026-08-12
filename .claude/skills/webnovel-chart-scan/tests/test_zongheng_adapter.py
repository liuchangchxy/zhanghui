"""Tests for the zongheng adapter metadata (Strategy.DIRECT_API).

Status: BLOCKED_EXTERNAL (verified 2026-08-13).

    The publicly documented endpoint
    https://www.zongheng.com/api/rank/details returns HTTP 404. Until
    the Nuxt SSR scraping fallback lands in v0.2 the adapter raises
    NotImplementedError immediately — so network/parser tests are no
    longer applicable. Only the metadata test remains.
"""
from scripts.adapters.zongheng import ZonghengAdapter
from scripts.adapters.base import AdapterStatus


def test_zongheng_adapter_metadata():
    a = ZonghengAdapter()
    assert a.platform == "zongheng"
    assert a.strategy.value == "direct_api"
    assert a.status == AdapterStatus.BLOCKED_EXTERNAL


def test_zongheng_adapter_fetch_raises_immediately_without_network():
    """fetch() must raise before any HTTP request — no silent fallback."""
    a = ZonghengAdapter()
    try:
        a.fetch("all", "weekly", 10)
    except NotImplementedError as e:
        msg = str(e)
        assert "404" in msg
        assert "KNOWN_LIMITATIONS.md" in msg
        return
    raise AssertionError("ZonghengAdapter.fetch should raise NotImplementedError (status=BLOCKED_EXTERNAL)")