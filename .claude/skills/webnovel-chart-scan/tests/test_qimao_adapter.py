"""Tests for the qimao adapter metadata (Strategy.VENDOR).

Status: BLOCKED_IMPLEMENTATION (verified 2026-08-13).

    The vendored parser's regex (``_NUXT_RE``) does not handle nested
    braces in the real upstream payload and falls through to a silent
    ``except Exception: return items`` branch. v0.2 will rewrite it as
    a balanced-brace scanner. Until then the adapter raises
    NotImplementedError immediately — so parser tests are no longer
    applicable. Only the metadata test remains.
"""
from scripts.adapters.qimao import QimaoAdapter
from scripts.adapters.base import AdapterStatus


def test_qimao_adapter_metadata():
    a = QimaoAdapter()
    assert a.platform == "qimao"
    assert a.strategy.value == "vendor"
    assert a.status == AdapterStatus.BLOCKED_IMPLEMENTATION


def test_qimao_adapter_fetch_raises_immediately_without_network():
    """fetch() must raise before any HTTP request — no silent fallback,
    no silent ``return items`` from the broken vendored parser."""
    a = QimaoAdapter()
    try:
        a.fetch("all", "daily", 10)
    except NotImplementedError as e:
        msg = str(e)
        assert "regex" in msg or "__NUXT__" in msg or "balanced-brace" in msg
        assert "KNOWN_LIMITATIONS.md" in msg
        return
    raise AssertionError("QimaoAdapter.fetch should raise NotImplementedError (status=BLOCKED_IMPLEMENTATION)")