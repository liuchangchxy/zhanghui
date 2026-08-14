import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.schema import ScanResult, ScanMeta, BookItem
from scripts.output import write_scan_result, slug_timestamp


def test_slug_timestamp_format():
    ts = slug_timestamp(datetime(2026, 8, 12, 14, 30, 45, tzinfo=timezone.utc))
    assert ts == "20260812T143045Z"


def test_write_scan_result_creates_files(tmp_path: Path):
    meta = ScanMeta(
        platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
        top=10, scanned_at=datetime.now(timezone.utc),
        duration_seconds=10.0, total_books=1, total_errors=0,
    )
    book = BookItem(
        id="qidian-1", platform="qidian", title="t", author="a",
        category="玄幻", category_normalized="玄幻",
        period="weekly", fetched_at=datetime.now(timezone.utc),
    )
    result = ScanResult(meta=meta, books=[book])

    written = write_scan_result(result, output_dir=tmp_path)

    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "books.json").exists()
    assert len(written) >= 2

    payload = json.loads((tmp_path / "books.json").read_text())
    assert "meta" in payload
    assert "books" in payload
    assert len(payload["books"]) == 1


def test_write_scan_result_creates_log_file(tmp_path: Path):
    meta = ScanMeta(
        platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
        top=10, scanned_at=datetime.now(timezone.utc),
        duration_seconds=10.0, total_books=0, total_errors=0,
    )
    result = ScanResult(meta=meta, books=[])

    write_scan_result(result, output_dir=tmp_path)

    log_files = list(tmp_path.glob("scan_*.log"))
    assert len(log_files) == 1
