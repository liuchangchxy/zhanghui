"""起点中文网 adapter — HYBRID strategy via httpx.

Status: BLOCKED_EXTERNAL (verified 2026-08-13).

    ``https://www.qidian.com/all`` returns HTTP 202 (probe.js challenge)
    that requires RC4-signed cookies — exactly the mechanism implemented
    in the vendored upstream ``vendor/novel-downloader/qidian_subset/``.
    Bypassing this requires porting the upstream's ``_calc_cookies`` from
    ``qidian_subset/searcher.py`` (~100 LOC) and signing each request
    with the resulting cookies. That's v0.2 work; until then the adapter
    raises ``NotImplementedError`` immediately in ``fetch()`` without
    touching the network.

Why an explicit status declaration (not a silent fallback):
    v0.1.x callers were getting empty-book results with no error —
    indistinguishable from a successful scan of a barren category. This
    adapter now declares its BLOCKED_EXTERNAL status so the orchestrator
    records an ``AdapterError`` with a human-readable explanation
    instead of attempting the blocked endpoint.
"""
from __future__ import annotations

from scripts.adapters.base import BaseAdapter, Strategy, AdapterStatus
from scripts.schema import RawBook

QIDIAN_LIST_API = "https://www.qidian.com/all"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# 起点分类 ID（来自 qidian.com 公开分类导航）
QIDIAN_CATEGORY_IDS = {
    "玄幻": 21,
    "奇幻": 1,
    "武侠": 2,
    "仙侠": 22,
    "都市": 4,
    "职场": 15,
    "军事": 6,
    "历史": 5,
    "游戏": 7,
    "体育": 8,
    "科幻": 9,
    "灵异": 10,
    "二次元": 12,
}


class QidianAdapter(BaseAdapter):
    platform = "qidian"
    strategy = Strategy.HYBRID
    status = AdapterStatus.BLOCKED_EXTERNAL

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        # First-principles: don't silently probe a blocked endpoint.
        # No network I/O — record the BLOCKED_EXTERNAL reason instead.
        raise NotImplementedError(
            "qidian endpoint returns probe.js (HTTP 202). "
            "RC4 cookie bypass required — see KNOWN_LIMITATIONS.md. "
            "Vendor subset kept at vendor/novel-downloader/qidian_subset/ "
            "for v0.2 port of _calc_cookies."
        )