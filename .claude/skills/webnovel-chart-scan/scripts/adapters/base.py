from abc import ABC, abstractmethod
from enum import Enum

from scripts.schema import RawBook, BookItem
from scripts import normalize as _normalize_module


class Strategy(str, Enum):
    VENDOR = "vendor"           # imports from vendored submodule
    HYBRID = "hybrid"           # uses httpx + reference to vendored code
    DIRECT_API = "direct_api"
    WEBFETCH = "webfetch"


class BaseAdapter(ABC):
    """所有平台 adapter 必须继承。"""
    platform: str = ""
    strategy: Strategy = Strategy.WEBFETCH

    @abstractmethod
    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        """按平台策略抓取榜单，返回平台原始数据。"""

    def normalize(self, raw: RawBook, period: str) -> BookItem:
        """默认调用 normalize.raw_to_bookitem；adapter 可重写。

        通过模块属性访问 raw_to_bookitem，以支持 monkeypatch 测试。
        """
        return _normalize_module.raw_to_bookitem(raw, platform=self.platform, period=period)
