"""fanqie subcategory → normalized category mapping.

The FanqieRankTracker dump groups books by fanqie-native subcategory names
(see ``tests/fixtures/fanqie_dump_20260815.json`` for the actual 34 unique
subcategory names). Our orchestrator's normalized category list is:

    ALL_CATEGORIES = ["玄幻", "都市", "仙侠", "历史", "科幻", "游戏", "同人",
                      "军事", "灵异", "二次元", "轻小说", "体育", "现实"]

This module bridges the two. Each fanqie subcategory maps to ONE of those,
or to a female-specific bucket (古言 / 现言 / 悬疑) when applicable.

Source: inspected 2026-08-15 dump + cross-checked against fanqie.com sidebar
nav as of 2026-08-13. Add new mappings here when new subcategories appear.
"""
from __future__ import annotations


# Mapping derived from inspecting the 2026-08-15 fanqie dump + fanqie.com
# sidebar navigation. Keys are fanqie-native subcategory names; values are
# our normalized main categories from scripts/scan.ALL_CATEGORIES or the
# female-specific buckets (古言 / 现言 / 悬疑).
SUBCAT_TO_NORMALIZED: dict[str, str] = {
    # ── 男频 (male channel) ──
    "西方奇幻": "玄幻",
    "传统玄幻": "玄幻",
    "玄幻脑洞": "玄幻",
    "东方仙侠": "仙侠",
    "都市日常": "都市",
    "都市修真": "都市",
    "都市高武": "都市",
    "都市种田": "都市",
    "都市脑洞": "都市",
    "战神赘婿": "都市",
    "历史古代": "历史",
    "历史脑洞": "历史",
    "抗战谍战": "军事",
    "悬疑灵异": "灵异",
    "悬疑脑洞": "悬疑",
    "科幻末世": "科幻",
    "游戏体育": "游戏",
    "动漫衍生": "二次元",
    "男频衍生": "同人",
    # ── 女频 (female channel) ──
    "古风世情": "古言",
    "玄幻言情": "古言",
    "种田": "古言",
    "年代": "现言",
    "现言脑洞": "现言",
    "宫斗宅斗": "古言",
    "古言脑洞": "古言",
    "快穿": "现言",
    "青春甜宠": "现言",
    "星光璀璨": "现言",
    "女频悬疑": "悬疑",
    "职场婚恋": "现言",
    "豪门总裁": "现言",
    "民国言情": "古言",
    "女频衍生": "同人",
}


def map_subcategory(subcat_name: str) -> str:
    """Map a fanqie-native subcategory name to our normalized category.

    Unknown subcategories pass through unchanged — the orchestrator's
    ``normalize.py:_normalize_category`` will fall back to passthrough
    for unrecognized names. This keeps us forward-compatible if fanqie
    adds new subcategories.
    """
    return SUBCAT_TO_NORMALIZED.get(subcat_name, subcat_name)
