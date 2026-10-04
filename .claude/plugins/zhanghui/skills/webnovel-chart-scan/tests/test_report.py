from datetime import datetime, timezone
from scripts.schema import ScanResult, ScanMeta, BookItem
from scripts.report import render_report_markdown


def _make_book(title, author, category, platform="qidian", word_count=None,
               status=None, rank=None, tags=None):
    return BookItem(
        id=f"{platform}-1", platform=platform, title=title, author=author,
        category=category, category_normalized=category,
        tags=tags or [], word_count=word_count, status=status,
        rank_position=rank, period="weekly",
        fetched_at=datetime.now(timezone.utc),
    )


def test_render_report_includes_overview():
    meta = ScanMeta(
        platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
        top=10, scanned_at=datetime.now(timezone.utc),
        duration_seconds=10.0, total_books=2, total_errors=0,
    )
    books = [
        _make_book("凡人修仙传", "忘语", "仙侠", word_count=3500000, status="completed", rank=1),
        _make_book("xxx", "yyy", "玄幻", word_count=500000, status="serial", rank=2),
    ]
    result = ScanResult(meta=meta, books=books)
    md = render_report_markdown(result)
    assert "# 扫描报告" in md
    assert "凡人修仙传" in md
    assert "总本数" in md


def test_render_report_includes_error_section():
    meta = ScanMeta(
        platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
        top=10, scanned_at=datetime.now(timezone.utc),
        duration_seconds=10.0, total_books=0, total_errors=1,
    )
    from scripts.schema import AdapterError
    err = AdapterError(
        platform="qidian", category="玄幻", period="weekly",
        stage="vendor", message="connection refused",
        occurred_at=datetime.now(timezone.utc),
    )
    result = ScanResult(meta=meta, books=[], errors=[err])
    md = render_report_markdown(result)
    assert "失败" in md or "错误" in md


def test_render_report_includes_table():
    meta = ScanMeta(
        platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
        top=10, scanned_at=datetime.now(timezone.utc),
        duration_seconds=10.0, total_books=1, total_errors=0,
    )
    result = ScanResult(meta=meta, books=[_make_book("t", "a", "玄幻", rank=1)])
    md = render_report_markdown(result)
    assert "| # |" in md or "| 书名 |" in md
