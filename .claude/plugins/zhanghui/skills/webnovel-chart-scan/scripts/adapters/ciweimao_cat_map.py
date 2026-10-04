"""ciweimao native category → normalized category mapping.

The worldwonderer/oh-story-claudecode scraper emits ciweimao-native
category labels in the Markdown output (悬疑灵异, 仙侠, 轻小说, etc.).
Our orchestrator's normalized category list is:

    ALL_CATEGORIES = ["玄幻", "都市", "仙侠", "历史", "科幻", "游戏", "同人",
                      "军事", "灵异", "二次元", "轻小说", "体育", "现实"]

This module bridges the two. Each ciweimao native label maps to ONE
of our normalized main categories. Unknown labels pass through
unchanged.

Source: inspected the 2026-08-16 ciweimao fixture (ciweimao_rank_click.md)
plus the existing CATEGORY_SLUG_MAP in scripts/adapters/ciweimao.py.
"""
from __future__ import annotations


# Mapping derived from ciweimao fixture + cross-checked against ciweimao.com
# sidebar nav. Keys are ciweimao-native category labels from the scraper
# output; values are our normalized main categories.
NATIVE_TO_NORMALIZED: dict[str, str] = {
    "悬疑灵异": "灵异",
    "悬疑": "灵异",
    "灵异": "灵异",
    "仙侠": "仙侠",
    "武侠": "仙侠",
    "玄幻": "玄幻",
    "奇幻": "玄幻",
    "都市": "都市",
    "言情": "现言",
    "古言": "古言",
    "现言": "现言",
    "校园": "同人",
    "同人": "同人",
    "二次元": "二次元",
    "动漫": "二次元",
    "轻小说": "轻小说",
    "科幻": "科幻",
    "游戏": "游戏",
    "竞技": "游戏",
    "军事": "军事",
    "历史": "历史",
    "体育": "体育",
    "现实": "现实",
    "女频": "古言",  # fallback for unlabeled female-channel entries
}


def map_native_category(native_label: str) -> str:
    """Map a ciweimao-native category label to our normalized category.

    Unknown labels pass through unchanged. The orchestrator's
    normalize.py handles unknown passthrough gracefully.
    """
    return NATIVE_TO_NORMALIZED.get(native_label, native_label)
