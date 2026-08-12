"""纵横中文网 adapter — DIRECT_API strategy via httpx.

Status: BLOCKED_EXTERNAL (verified 2026-08-13).

    The publicly documented endpoint
    ``https://www.zongheng.com/api/rank/details`` returns HTTP 404. The
    page that *does* return 200 (``/rank?nav=new-book&rankType=4``)
    embeds the book list as a Nuxt SSR payload, not as a documented
    JSON API. Scraping the SSR payload would work but is a separate
    implementation effort — v0.2.

Why an explicit status declaration (not a silent fallback):
    v0.1.x callers were getting empty-book results with no error —
    indistinguishable from a successful scan of a barren category. This
    adapter now declares its BLOCKED_EXTERNAL status so the orchestrator
    records an ``AdapterError`` with a human-readable explanation
    instead of attempting the blocked endpoint.
"""
from scripts.adapters.base import BaseAdapter, Strategy, AdapterStatus
from scripts.schema import RawBook

ZONGHENG_API = "https://www.zongheng.com/api/rank/details"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# rankType (per /rank?nav=... links observed on the site):
#   1=月票 3=日更 4=新书 5=点击 6=推荐 7=捧场 8=完本 9=新书订阅 10=日更新 12=作者人气
RANK_TYPE_MAP = {"monthly": 1, "daily": 3, "weekly": 5}


class ZonghengAdapter(BaseAdapter):
    platform = "zongheng"
    strategy = Strategy.DIRECT_API
    status = AdapterStatus.BLOCKED_EXTERNAL

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        # First-principles: don't silently probe a 404 endpoint.
        # No network I/O — record the BLOCKED_EXTERNAL reason instead.
        raise NotImplementedError(
            "zongheng public API endpoint returns HTTP 404. "
            "Nuxt SSR scraping fallback required for v0.2 — "
            "see KNOWN_LIMITATIONS.md."
        )