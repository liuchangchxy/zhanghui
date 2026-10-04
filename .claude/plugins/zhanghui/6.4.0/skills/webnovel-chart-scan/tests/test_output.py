import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.schema import ScanResult, ScanMeta, BookItem
from scripts.output import write_scan_result, slug_timestamp, write_chart_scan_marked_references


def test_slug_timestamp_format():
    # M1 fix: microsecond precision + literal `_` separator + Z suffix.
    ts = slug_timestamp(datetime(2026, 8, 12, 14, 30, 45, 123456, tzinfo=timezone.utc))
    assert ts == "20260812T143045_123456Z"


def test_slug_timestamp_rejects_naive_datetime():
    """Defensive runtime check (M5 plan said runtime-only; Pydantic validator
    in schema.py makes it impossible to construct a ScanMeta with naive ts,
    but slug_timestamp is also exported for direct use)."""
    with pytest.raises(ValueError, match="timezone-aware"):
        slug_timestamp(datetime(2026, 8, 12, 14, 30, 45))


# --- Adversarial M5: Pydantic UTC validator on ScanMeta.scanned_at ---

def test_scan_meta_rejects_naive_scanned_at():
    """M5: Naive datetime in scanned_at must raise ValidationError."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="timezone-aware"):
        ScanMeta(
            platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
            top=10, scanned_at=datetime(2026, 8, 12, 14, 30, 45),
            duration_seconds=10.0, total_books=0, total_errors=0,
        )


def test_scan_meta_accepts_aware_scanned_at():
    """M5: tz-aware datetime is accepted unchanged."""
    meta = ScanMeta(
        platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
        top=10, scanned_at=datetime(2026, 8, 12, 14, 30, 45, tzinfo=timezone.utc),
        duration_seconds=10.0, total_books=0, total_errors=0,
    )
    assert meta.scanned_at.tzinfo is not None


# --- Adversarial M3: write_chart_scan_marked_references validates output_dir ---

def test_write_chart_scan_marked_references_rejects_escape_from_cwd(tmp_path, monkeypatch):
    """M3: output_dir outside cwd must raise ValueError (no path traversal)."""
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / "evil"
    outside.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match="must be within current working directory"):
        write_chart_scan_marked_references(
            [{"platform": "qidian", "title": "凡人修仙传"}],
            outside,
        )


def test_write_chart_scan_marked_references_accepts_cwd_subdir(tmp_path, monkeypatch):
    """M3: output_dir under cwd is accepted."""
    monkeypatch.chdir(tmp_path)
    refs = [{"platform": "qidian", "title": "凡人修仙传", "author": "忘语"}]
    written = write_chart_scan_marked_references(refs, tmp_path / "chart-scan")
    assert written.is_file()
    assert written.name == "marked-references.json"


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
