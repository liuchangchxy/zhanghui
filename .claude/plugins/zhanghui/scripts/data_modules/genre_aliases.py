#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genre alias normalization and profile key mapping.
"""

from __future__ import annotations

from genre_taxonomy import normalize_genre_label_for_profile


# Fallback profile keys are a legacy markdown-section namespace, not canonical
# genre values. User-input aliases live in references/taxonomy/genre-index.csv.
GENRE_PROFILE_KEY_ALIASES: dict[str, str] = {
    # Canonical 15-value enum (genre_taxonomy.GENRE_CANONICAL) -> profile namespace.
    # These were missing, so a canonical genre like 悬疑 fell through to a raw
    # profile key and never matched genre-profiles.md. Sub-genre aliases below keep
    # working because the resolver normalizes the label before this lookup.
    "悬疑": "mystery",
    "都市": "urban-power",
    "仙侠": "xianxia",
    "奇幻": "xianxia",
    "历史": "history-travel",
    "游戏": "game-lit",
    "现言": "romance",
    "幻言": "romance",
    "修仙": "xianxia",
    "修仙/玄幻": "xianxia",
    "玄幻": "xianxia",
    "爽文/系统流": "shuangwen",
    "高武": "xianxia",
    "西幻": "xianxia",
    "都市异能": "urban-power",
    "都市脑洞": "urban-power",
    "都市日常": "urban-power",
    "狗血言情": "romance",
    "古言": "romance",
    "青春甜宠": "romance",
    "替身文": "substitute",
    "规则怪谈": "rules-mystery",
    "悬疑脑洞": "mystery",
    "悬疑灵异": "mystery",
    "知乎短篇": "zhihu-short",
    "电竞": "esports",
    "直播文": "livestream",
    "克苏鲁": "cosmic-horror",
}


def normalize_genre_token(token: str) -> str:
    value = str(token or "").strip()
    if not value:
        return ""
    return normalize_genre_label_for_profile(value)


def to_profile_key(genre: str) -> str:
    value = str(genre or "").strip()
    if not value:
        return ""
    normalized = normalize_genre_token(value)
    return GENRE_PROFILE_KEY_ALIASES.get(normalized, normalized.lower())

