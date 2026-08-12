from datetime import datetime, timezone
from scripts.schema import RawBook
from scripts.normalize import raw_to_bookitem, normalize_category, build_book_id

def test_build_book_id_format():
    assert build_book_id("qidian", "12345") == "qidian-12345"
    assert build_book_id("fanqie", "abc") == "fanqie-abc"

def test_normalize_category_qidian_xuanhuan():
    assert normalize_category("qidian", "玄幻") == "玄幻"
    assert normalize_category("qidian", "东方玄幻") == "玄幻"

def test_normalize_category_unknown_platform_passthrough():
    assert normalize_category("ciweimao", "奇幻") == "奇幻"  # 不强行映射

def test_raw_to_bookitem_basic():
    raw = RawBook(
        platform_book_id="12345",
        title="凡人修仙传",
        author="忘语",
        category="仙侠",
        tags=["修真", "凡人"],
        intro="一个普通凡人...",
        word_count=3500000,
        status="completed",
        cover_url="https://example.com/c.jpg",
        detail_url="https://book.qidian.com/info/12345",
        rank_position=1,
    )
    book = raw_to_bookitem(raw, platform="qidian", period="weekly")
    assert book.id == "qidian-12345"
    assert book.platform == "qidian"
    assert book.category == "仙侠"
    assert book.category_normalized == "仙侠"
    assert book.tags == ["修真", "凡人"]
    assert book.word_count == 3500000
    assert book.status == "completed"
    assert book.rank_position == 1
    assert book.period == "weekly"
    assert isinstance(book.fetched_at, datetime)

def test_raw_to_bookitem_truncates_long_intro():
    raw = RawBook(
        platform_book_id="x", title="t", author="a", category="c",
        intro="x" * 1000,
    )
    book = raw_to_bookitem(raw, platform="fanqie", period="daily")
    assert len(book.intro) == 500

def test_raw_to_bookitem_handles_missing_optional():
    raw = RawBook(platform_book_id="1", title="t", author="a", category="玄幻")
    book = raw_to_bookitem(raw, platform="qidian", period="monthly")
    assert book.word_count is None
    assert book.tags == []
    assert book.intro == ""


def test_raw_to_bookitem_propagates_urls():
    raw = RawBook(
        platform_book_id="1", title="t", author="a", category="玄幻",
        cover_url="https://example.com/c.jpg",
        detail_url="https://example.com/book/1",
    )
    book = raw_to_bookitem(raw, platform="qidian", period="weekly")
    assert book.cover_url == "https://example.com/c.jpg"
    assert book.detail_url == "https://example.com/book/1"


def test_raw_to_bookitem_tags_independent():
    raw = RawBook(
        platform_book_id="1", title="t", author="a", category="玄幻",
        tags=["A", "B"],
    )
    book = raw_to_bookitem(raw, platform="qidian", period="weekly")
    book.tags.append("C")
    assert raw.tags == ["A", "B"]  # input not mutated


def test_normalize_category_passthrough_unknown():
    """qidian 不在 map 里的分类原样返回"""
    assert normalize_category("qidian", "言情") == "言情"
    assert normalize_category("qidian", "轻小说") == "轻小说"


def test_normalize_category_fanqie():
    """fanqie 分类映射"""
    assert normalize_category("fanqie", "男频-玄幻") == "玄幻"
    assert normalize_category("fanqie", "女频-古言") == "古言"
    assert normalize_category("fanqie", "未映射分类") == "未映射分类"


def test_build_book_id_with_literal_type():
    """验证 PLATFORMS Literal 类型在 build_book_id 里工作"""
    from scripts.schema import PLATFORMS
    # 这是个类型检查点：调用时 platform 必须是合法的 Literal
    assert build_book_id("zongheng", "999") == "zongheng-999"