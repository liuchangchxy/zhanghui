from datetime import datetime, timezone
from pathlib import Path

from scripts.schema import RawBook
from scripts.adapters.base import BaseAdapter, Strategy
from scripts.scan import build_parser, run_scan, ADAPTER_REGISTRY


class FakeAdapter(BaseAdapter):
    platform = "qidian"
    strategy = Strategy.DIRECT_API

    def fetch(self, category, period, top):
        return [
            RawBook(
                platform_book_id=str(i),
                title=f"book-{i}",
                author=f"author-{i}",
                category=category,
                rank_position=i + 1,
            )
            for i in range(top)
        ]


def test_build_parser_defaults():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.platform == "all"
    assert args.category == "all"
    assert args.top == 50
    assert args.period == "weekly"
    assert args.output_dir == Path("./chart-scan")


def test_run_scan_collects_books_and_writes_files(tmp_path: Path, monkeypatch):
    from scripts.scan import ADAPTER_REGISTRY
    monkeypatch.setitem(ADAPTER_REGISTRY, "fake", FakeAdapter)

    parser = build_parser()
    args = parser.parse_args(["--platform", "fake", "--category", "玄幻", "--top", "3", "--output-dir", str(tmp_path)])

    rc = run_scan(args)
    assert rc == 0

    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "books.json").exists()

    import json
    payload = json.loads((tmp_path / "books.json").read_text())
    assert payload["meta"]["total_books"] == 3
    assert all(b["title"].startswith("book-") for b in payload["books"])
    assert all(b["platform"] == "qidian" for b in payload["books"])


def test_run_scan_returns_zero_on_partial_failure(tmp_path: Path, monkeypatch):
    """一个 adapter 失败不应让整体退出码非零。"""
    class BrokenAdapter(BaseAdapter):
        platform = "broken"
        strategy = Strategy.DIRECT_API

        def fetch(self, category, period, top):
            raise RuntimeError("simulated upstream failure")

    from scripts.scan import ADAPTER_REGISTRY
    monkeypatch.setitem(ADAPTER_REGISTRY, "broken", BrokenAdapter)
    monkeypatch.setitem(ADAPTER_REGISTRY, "fake", FakeAdapter)

    parser = build_parser()
    args = parser.parse_args(["--platform", "broken,fake", "--category", "玄幻", "--top", "2", "--output-dir", str(tmp_path)])

    rc = run_scan(args)
    assert rc == 0  # 部分失败不算失败

    import json
    payload = json.loads((tmp_path / "books.json").read_text())
    assert payload["meta"]["total_errors"] >= 1
    assert payload["meta"]["total_books"] == 2