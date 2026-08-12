import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.schema import ScanResult


def slug_timestamp(dt: datetime) -> str:
    """UTC ISO 时间戳转文件友好字符串。"""
    if dt.tzinfo is None:
        raise ValueError(
            "slug_timestamp requires a timezone-aware datetime. "
            "Use datetime.now(timezone.utc) or attach tzinfo."
        )
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def write_scan_result(result: ScanResult, output_dir: Path) -> list[Path]:
    """把 ScanResult 写到 output_dir，返回写入的文件列表。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    # books.json
    json_path = output_dir / "books.json"
    json_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    written.append(json_path)

    # report.md（由 report.py 生成）
    report_path = output_dir / "report.md"
    from scripts.report import render_report_markdown  # 延迟 import
    report_path.write_text(render_report_markdown(result), encoding="utf-8")
    written.append(report_path)

    # scan_<ts>.log
    log_path = output_dir / f"scan_{slug_timestamp(result.meta.scanned_at)}.log"
    log_path.write_text(
        f"webnovel-chart-scan run at {result.meta.scanned_at.isoformat()}\n"
        f"platforms: {', '.join(result.meta.platforms)}\n"
        f"categories: {', '.join(result.meta.categories)}\n"
        f"periods: {', '.join(result.meta.periods)}\n"
        f"top: {result.meta.top}\n"
        f"total_books: {result.meta.total_books}\n"
        f"total_errors: {result.meta.total_errors}\n",
        encoding="utf-8",
    )
    written.append(log_path)

    return written
