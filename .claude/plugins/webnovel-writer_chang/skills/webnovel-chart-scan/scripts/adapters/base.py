from abc import ABC
from enum import Enum

from scripts.schema import RawBook, BookItem
from scripts import normalize as _normalize_module


class Strategy(str, Enum):
    VENDOR = "vendor"           # imports from vendored submodule
    HYBRID = "hybrid"           # uses httpx + reference to vendored code
    DIRECT_API = "direct_api"
    WEBFETCH = "webfetch"


class AdapterStatus(str, Enum):
    """Honest declaration of whether an adapter actually fetches data today.

    - LIVE: fetches real data from upstream right now
    - LIVE_WITH_SETUP: fetches real data after a one-time user setup
      step (e.g. ``pip install playwright``); orchestrator still calls
      ``fetch()`` and the user-facing RuntimeError surfaces if the setup
      was skipped
    - BLOCKED_EXTERNAL: endpoint dead / anti-bot — needs upstream-side or
      infra-side work, cannot be fixed in this repo alone
    - BLOCKED_IMPLEMENTATION: needs code work in this repo (parser
      rewrite, etc.) — see KNOWN_LIMITATIONS.md
    """
    LIVE = "live"
    LIVE_WITH_SETUP = "live_with_setup"
    BLOCKED_EXTERNAL = "blocked_external"
    BLOCKED_IMPLEMENTATION = "blocked_implementation"


class BaseAdapter(ABC):
    """所有平台 adapter 必须继承。"""
    platform: str = ""
    strategy: Strategy = Strategy.WEBFETCH
    status: AdapterStatus = AdapterStatus.LIVE  # subclasses must override

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        """按平台策略抓取榜单，返回平台原始数据。

        LIVE subclasses MUST override this with a real implementation.

        BLOCKED_* subclasses can rely on this default placeholder — the
        orchestrator (``scripts.scan:run_scan``) short-circuits on
        ``adapter.status != LIVE`` and records an ``AdapterError``
        instead of invoking ``fetch()``. If the default body is ever
        reached (a bug), it raises ``NotImplementedError`` loudly.

        Blocked subclasses in this repo DO override fetch() with a
        tailored message (so callers see the platform-specific fix
        path), but the override is dead code at runtime.
        """
        raise NotImplementedError(
            f"{self.platform} adapter is marked status={self.status.value!r} "
            f"and must not be invoked at runtime. See KNOWN_LIMITATIONS.md."
        )

    def normalize(self, raw: RawBook, period: str) -> BookItem:
        """默认调用 normalize.raw_to_bookitem；adapter 可重写。

        通过模块属性访问 raw_to_bookitem，以支持 monkeypatch 测试。
        """
        return _normalize_module.raw_to_bookitem(raw, platform=self.platform, period=period)