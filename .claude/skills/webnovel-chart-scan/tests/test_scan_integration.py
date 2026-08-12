from datetime import datetime, timezone
from pathlib import Path

from scripts.schema import RawBook
from scripts.adapters.base import BaseAdapter, Strategy, AdapterStatus
from scripts.scan import build_parser, run_scan, ADAPTER_REGISTRY


class FakeAdapter(BaseAdapter):
    platform = "qidian"
    strategy = Strategy.DIRECT_API
    status = AdapterStatus.LIVE  # explicit: this fake is live

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


class FakeBlockedExternalAdapter(BaseAdapter):
    platform = "blocked_external"
    strategy = Strategy.DIRECT_API
    status = AdapterStatus.BLOCKED_EXTERNAL


class FakeBlockedImplAdapter(BaseAdapter):
    platform = "blocked_impl"
    strategy = Strategy.VENDOR
    status = AdapterStatus.BLOCKED_IMPLEMENTATION


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
        status = AdapterStatus.LIVE  # LIVE so fetch() is actually called

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


def test_run_scan_records_adapter_error_for_blocked_external(tmp_path: Path, monkeypatch):
    """BLOCKED_EXTERNAL adapters must produce an AdapterError per
    (platform, category, period) — NOT empty books and no error (silent
    failure is exactly what this refactor fixes)."""
    from scripts.scan import ADAPTER_REGISTRY
    monkeypatch.setitem(ADAPTER_REGISTRY, "blocked_ext", FakeBlockedExternalAdapter)

    parser = build_parser()
    args = parser.parse_args([
        "--platform", "blocked_ext",
        "--category", "玄幻",
        "--period", "weekly",
        "--top", "3",
        "--output-dir", str(tmp_path),
    ])

    rc = run_scan(args)
    # All (platform, category, period) combos are blocked -> exit 1
    assert rc == 1

    import json
    payload = json.loads((tmp_path / "books.json").read_text())
    assert payload["meta"]["total_books"] == 0
    assert payload["meta"]["total_errors"] == 1
    err = payload["errors"][0]
    assert err["platform"] == "blocked_ext"
    assert err["category"] == "玄幻"
    assert err["period"] == "weekly"
    # Message must include the BLOCKED_EXTERNAL hint and v0.2 marker.
    assert "外部阻塞" in err["message"]
    assert "v0.2" in err["message"]


def test_run_scan_records_adapter_error_for_blocked_implementation(tmp_path: Path, monkeypatch):
    """BLOCKED_IMPLEMENTATION adapters must produce an AdapterError per
    (platform, category, period)."""
    from scripts.scan import ADAPTER_REGISTRY
    monkeypatch.setitem(ADAPTER_REGISTRY, "blocked_impl", FakeBlockedImplAdapter)

    parser = build_parser()
    args = parser.parse_args([
        "--platform", "blocked_impl",
        "--category", "all",
        "--period", "daily,weekly,monthly",
        "--top", "3",
        "--output-dir", str(tmp_path),
    ])

    rc = run_scan(args)
    assert rc == 1

    import json
    payload = json.loads((tmp_path / "books.json").read_text())
    assert payload["meta"]["total_books"] == 0
    # 1 category * 3 periods = 3 errors
    assert payload["meta"]["total_errors"] == 3
    for err in payload["errors"]:
        assert err["platform"] == "blocked_impl"
        # Message must include the BLOCKED_IMPLEMENTATION hint and
        # KNOWN_LIMITATIONS.md pointer.
        assert "实现未完成" in err["message"]
        assert "KNOWN_LIMITATIONS.md" in err["message"]


def test_run_scan_blocked_adapter_does_not_call_fetch(tmp_path: Path, monkeypatch):
    """BLOCKED_* adapters must NOT have fetch() invoked at all — the
    orchestrator short-circuits before the network attempt."""
    from scripts.scan import ADAPTER_REGISTRY

    class FetchSpyAdapter(FakeBlockedExternalAdapter):
        fetch_called = False

        def fetch(self, category, period, top):  # noqa: ARG002
            FetchSpyAdapter.fetch_called = True
            return []

    monkeypatch.setitem(ADAPTER_REGISTRY, "spy", FetchSpyAdapter)

    parser = build_parser()
    args = parser.parse_args([
        "--platform", "spy",
        "--category", "玄幻",
        "--period", "weekly",
        "--top", "3",
        "--output-dir", str(tmp_path),
    ])

    rc = run_scan(args)
    assert rc == 1  # all blocked
    assert FetchSpyAdapter.fetch_called is False, "fetch() must NOT be invoked when status != LIVE"


def test_run_scan_live_adapter_does_call_fetch(tmp_path: Path, monkeypatch):
    """LIVE adapters (including FakeAdapter) must have fetch() invoked."""
    from scripts.scan import ADAPTER_REGISTRY
    monkeypatch.setitem(ADAPTER_REGISTRY, "fake", FakeAdapter)

    parser = build_parser()
    args = parser.parse_args([
        "--platform", "fake",
        "--category", "玄幻",
        "--period", "weekly",
        "--top", "3",
        "--output-dir", str(tmp_path),
    ])

    rc = run_scan(args)
    assert rc == 0
    import json
    payload = json.loads((tmp_path / "books.json").read_text())
    assert payload["meta"]["total_books"] == 3