from datetime import datetime, timezone
from scripts.schema import BookItem, RawBook, AdapterError, ScanMeta, ScanResult

def test_bookitem_minimal_required_fields():
    b = BookItem(
        id="qidian-12345",
        platform="qidian",
        title="凡人修仙传",
        author="忘语",
        category="仙侠",
        category_normalized="仙侠",
        period="weekly",
        fetched_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    assert b.id == "qidian-12345"
    assert b.tags == []
    assert b.intro == ""
    assert b.word_count is None
    assert b.status is None

def test_bookitem_full_fields():
    b = BookItem(
        id="fanqie-67890",
        platform="fanqie",
        title="xxx",
        author="yyy",
        category="都市",
        category_normalized="都市",
        tags=["系统流", "穿越"],
        intro="简介内容",
        word_count=1500000,
        status="serial",
        cover_url="https://example.com/cover.jpg",
        detail_url="https://fanqie.com/book/67890",
        rank_position=1,
        period="monthly",
        fetched_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    assert b.word_count == 1500000
    assert b.rank_position == 1

def test_bookitem_rejects_invalid_platform():
    import pytest
    with pytest.raises(ValueError):
        BookItem(
            id="x-1", platform="unknown", title="t", author="a",
            category="c", category_normalized="c", period="weekly",
            fetched_at=datetime.now(timezone.utc),
        )

def test_rawbook_required_fields():
    r = RawBook(platform_book_id="123", title="t", author="a", category="玄幻")
    assert r.tags == []
    assert r.raw_payload == {}

def test_adapter_error_required_fields():
    e = AdapterError(
        platform="qidian", category="玄幻", period="weekly",
        stage="vendor", message="connection refused",
        occurred_at=datetime.now(timezone.utc),
    )
    assert e.stage == "vendor"

def test_scan_meta_aggregates():
    m = ScanMeta(
        platforms=["qidian", "fanqie"],
        categories=["玄幻", "都市"],
        periods=["weekly"],
        top=50,
        scanned_at=datetime.now(timezone.utc),
        duration_seconds=120.5,
        total_books=200,
        total_errors=3,
    )
    assert m.total_books == 200

def test_scan_result_holds_books_and_errors():
    r = ScanResult(
        meta=ScanMeta(
            platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
            top=10, scanned_at=datetime.now(timezone.utc),
            duration_seconds=10.0, total_books=10, total_errors=0,
        ),
        books=[],
        errors=[],
    )
    assert r.errors == []