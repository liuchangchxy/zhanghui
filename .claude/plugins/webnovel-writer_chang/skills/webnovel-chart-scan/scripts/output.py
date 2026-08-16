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
    # M1 fix: microsecond precision + Z separator. `%f` returns 6 digits
    # (e.g. "123456"); we use a literal `_` so the microsecond block is
    # visually distinct from the seconds block and avoids same-second
    # collisions when two scans run in quick succession.
    return dt.strftime("%Y%m%dT%H%M%S_%fZ")


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


def write_chart_scan_marked_references(references: list[dict], output_dir: str | Path) -> Path:
    """Write chart-scan/marked-references.json with the schema from P1+P2 spec.

    References is a list of {platform, title, author?, category?}.
    Output path is output_dir / "marked-references.json".

    Returns the resolved path.

    M3 fix: validate output_dir is under cwd before writing anywhere.
    M4 fix: renamed from `write_marked_references` to avoid collision with
    the shared data_modules.marked_references.write_marked_references.
    """
    import sys

    # M3 fix: refuse to write outside cwd. The marked-references.json
    # product is a project-relative artifact; an absolute or escaping
    # output_dir here usually means a caller bug or path injection.
    output_dir_resolved = Path(output_dir).expanduser().resolve()
    cwd = Path.cwd().resolve()
    try:
        output_dir_resolved.relative_to(cwd)
    except ValueError:
        raise ValueError(
            f"output_dir must be within current working directory: "
            f"{output_dir_resolved} not under {cwd}"
        )

    # Import the validation helper from data_modules (relative path resolution).
    # output.py lives at skills/webnovel-chart-scan/scripts/output.py,
    # so 4 parents up reaches the webnovel-writer_chang/ plugin root, which
    # contains the shared scripts/ tree (with data_modules/).
    _plugin_root = Path(__file__).resolve().parent.parent.parent.parent
    sys.path.insert(0, str(_plugin_root / "scripts"))

    from data_modules.marked_references import validate_marked_references  # noqa: E402

    output_path = output_dir_resolved / "marked-references.json"
    payload = {
        "schema_version": 1,
        "marked_at": datetime.now(timezone.utc).isoformat(),
        "from_scan": str((output_dir_resolved / "books.json")),
        "references": references,
    }
    validate_marked_references(payload)  # raises ValueError on schema mismatch
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
