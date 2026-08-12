from datetime import datetime, timezone
from scripts.schema import RawBook, BookItem, PLATFORMS, PERIODS

INTRO_MAX_LEN = 500

# 起点分类映射：子分类 -> 主分类
_QIDIAN_SUBCATEGORY_MAP = {
    "东方玄幻": "玄幻", "异世大陆": "玄幻", "高武": "玄幻",
    "都市生活": "都市", "职场": "都市", "现实题材": "现实",
    "古典仙侠": "仙侠", "修真文明": "仙侠", "现代修真": "仙侠",
}

# 番茄分类映射
_FANQIE_SUBCATEGORY_MAP = {
    "男频-玄幻": "玄幻", "女频-古言": "古言",
    "男频-都市": "都市", "女频-现言": "现言",
}


def build_book_id(platform: PLATFORMS, platform_book_id: str) -> str:
    return f"{platform}-{platform_book_id}"


def normalize_category(platform: PLATFORMS, category: str) -> str:
    """把平台原始分类归一化到统一分类。"""
    if platform == "qidian":
        return _QIDIAN_SUBCATEGORY_MAP.get(category, category)
    if platform == "fanqie":
        return _FANQIE_SUBCATEGORY_MAP.get(category, category)
    # zongheng/qimao/ciweimao 暂不强制映射，原样返回
    return category


def raw_to_bookitem(raw: RawBook, platform: PLATFORMS, period: PERIODS) -> BookItem:
    intro = raw.intro[:INTRO_MAX_LEN] if raw.intro else ""
    return BookItem(
        id=build_book_id(platform, raw.platform_book_id),
        platform=platform,
        title=raw.title,
        author=raw.author,
        category=raw.category,
        category_normalized=normalize_category(platform, raw.category),
        tags=list(raw.tags),
        intro=intro,
        word_count=raw.word_count,
        status=raw.status,
        cover_url=raw.cover_url,
        detail_url=raw.detail_url,
        rank_position=raw.rank_position,
        period=period,
        fetched_at=datetime.now(timezone.utc),
    )