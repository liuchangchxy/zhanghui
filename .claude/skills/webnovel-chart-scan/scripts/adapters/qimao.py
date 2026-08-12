"""七猫（qimao）adapter — Strategy.VENDOR.

Status: BLOCKED_IMPLEMENTATION (verified 2026-08-13).

    The vendored ``vendor/qimao_web_crawler_subset/qimao_subset/`` wraps
    a pure-Python regex parser of qimao.com's Nuxt SSR ``__NUXT__``
    payload. The regex (``_NUXT_RE`` in the vendored subset) was written
    assuming a flat JS object literal — it does not handle nested
    braces inside the real upstream payload. The parser falls through
    to a ``except Exception: return items`` branch that silently returns
    whatever it managed to parse (typically zero books) without raising.
    That makes the adapter look successful while returning no data.

    Fix path (v0.2): rewrite the regex as a balanced-brace scanner (~50
    LOC) — similar to the existing ``_split_top_level_csv`` helper in
    the vendored subset.

Why an explicit status declaration (not a silent fallback):
    v0.1.x callers were getting empty-book results with no error —
    indistinguishable from a successful scan of a barren category. This
    adapter now declares its BLOCKED_IMPLEMENTATION status so the
    orchestrator records an ``AdapterError`` with a human-readable
    explanation instead of triggering the silent-swallow code path.
"""
from __future__ import annotations

from scripts.adapters.base import BaseAdapter, Strategy, AdapterStatus
from scripts.schema import RawBook

# Map our period -> upstream rank_type. 上游 RANK_TYPES =
# hot/new/over/collect/update. Choose the closest semantic match.
PERIOD_TO_RANK_TYPE = {
    "daily": "hot",
    "weekly": "collect",
    "monthly": "over",
}
DEFAULT_RANK_TYPE = "hot"


class QimaoAdapter(BaseAdapter):
    platform = "qimao"
    strategy = Strategy.VENDOR
    status = AdapterStatus.BLOCKED_IMPLEMENTATION

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        # First-principles: don't run the broken vendored parser.
        # No network I/O, no silent swallow — record the
        # BLOCKED_IMPLEMENTATION reason instead.
        raise NotImplementedError(
            "qimao vendored parser regex fails on real __NUXT__ payload "
            "(nested braces). Needs balanced-brace scanner rewrite for "
            "v0.2 — see KNOWN_LIMITATIONS.md."
        )