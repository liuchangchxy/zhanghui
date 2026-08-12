"""Tests for the qidian adapter metadata (Strategy.HYBRID).

Status: BLOCKED_EXTERNAL (verified 2026-08-13).

    https://www.qidian.com/all returns HTTP 202 with a probe.js anti-bot
    challenge that requires RC4-signed cookies (see vendored subset at
    vendor/novel-downloader/qidian_subset/). Until the bypass is ported
    in v0.2 the adapter raises NotImplementedError immediately without
    touching the network — so network/parser tests are no longer
    applicable. Only the metadata test remains.
"""
from scripts.adapters.qidian import QidianAdapter
from scripts.adapters.base import AdapterStatus


def test_qidian_adapter_metadata():
    a = QidianAdapter()
    assert a.platform == "qidian"
    assert a.strategy.value == "hybrid"
    assert a.status == AdapterStatus.BLOCKED_EXTERNAL


def test_qidian_adapter_fetch_raises_immediately_without_network():
    """fetch() must raise before any HTTP request — no silent fallback."""
    a = QidianAdapter()
    try:
        a.fetch("仙侠", "monthly", 10)
    except NotImplementedError as e:
        msg = str(e)
        # Message should mention the actual blocker and the fix path.
        assert "probe.js" in msg or "RC4" in msg
        assert "KNOWN_LIMITATIONS.md" in msg
        return
    raise AssertionError("QidianAdapter.fetch should raise NotImplementedError (status=BLOCKED_EXTERNAL)")