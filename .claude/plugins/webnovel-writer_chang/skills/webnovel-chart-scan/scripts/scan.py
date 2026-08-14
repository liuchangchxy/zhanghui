"""webnovel-chart-scan 主控。

CLI 入口：解析参数 -> 路由到 adapter -> 归一化 -> 渲染报告 -> 写文件。
"""
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.adapters.base import BaseAdapter, AdapterStatus
from scripts.schema import ScanResult, ScanMeta, AdapterError
from scripts.normalize import raw_to_bookitem
from scripts.output import write_scan_result

# NOTE: Adapter modules (and their heavy deps like bs4 / playwright) are NOT
# imported at module load. They are pulled in lazily by ``_ensure_registry()``
# inside ``run_scan()`` so purely-CLI tests can ``import scripts.scan`` without
# triggering those optional dependencies.

ALL_PLATFORMS = ["qidian", "fanqie", "zongheng", "qimao", "ciweimao"]
ALL_CATEGORIES = ["玄幻", "都市", "仙侠", "历史", "科幻", "游戏", "同人", "军事", "灵异", "二次元", "轻小说", "体育", "现实"]
ALL_PERIODS = ["daily", "weekly", "monthly"]

ADAPTER_REGISTRY: dict[str, BaseAdapter] = {}


def _ensure_registry() -> None:
    """Populate ``ADAPTER_REGISTRY`` on first use (lazy adapter import).

    Importing the adapter modules eagerly would force every consumer of
    ``scripts.scan`` (e.g. CLI tests, ``argparse``-only invocations) to pay the
    import cost of optional dependencies such as ``bs4`` and the vendored
    Playwright subset. Lazy population keeps the module import light.
    """
    global ADAPTER_REGISTRY
    if ADAPTER_REGISTRY:
        return
    # Local imports keep bs4/playwright out of the module-load path.
    from scripts.adapters.zongheng import ZonghengAdapter
    from scripts.adapters.ciweimao import CiweimaoAdapter
    from scripts.adapters.qidian import QidianAdapter
    from scripts.adapters.fanqie import FanqieAdapter
    from scripts.adapters.qimao import QimaoAdapter

    ADAPTER_REGISTRY.update({
        "qidian": QidianAdapter(),
        "fanqie": FanqieAdapter(),
        "zongheng": ZonghengAdapter(),
        "qimao": QimaoAdapter(),
        "ciweimao": CiweimaoAdapter(),
    })


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chart-scan",
        description="扫网文平台分类榜单（起点/番茄/纵横/七猫/刺猬猫）",
    )
    parser.add_argument("--platform", default="all", help="逗号分隔，例 qidian,fanqie 或 all")
    parser.add_argument("--category", default="all", help="分类名（'all' 表示全部，传 'all' 字面量给各 adapter）或具体分类")
    parser.add_argument("--top", type=int, default=50, help="每榜前 N 本，≤100")
    parser.add_argument("--period", default="weekly", help="daily,weekly,monthly（多值用逗号）")
    parser.add_argument("--output-dir", type=Path, default=Path("./chart-scan"))
    parser.add_argument("--verbose", action="store_true")
    return parser


def _parse_list(value: str, all_values: list[str], label: str) -> list[str]:
    if value == "all":
        return list(all_values)
    items = [v.strip() for v in value.split(",") if v.strip()]
    invalid = [i for i in items if i not in all_values]
    if invalid:
        raise ValueError(f"{label} 包含无效值 {invalid}; 有效: {all_values}")
    return items


def _parse_categories(value: str) -> list[str]:
    """--category handling: 'all' is a literal string passed to adapters,
    not a list of all known categories. Adapters that support category filtering
    (ciweimao) handle 'all' themselves; adapters that don't (fanqie/zongheng/qimao)
    accept 'all' as the only valid value."""
    if value == "all":
        return ["all"]  # single literal, not expansion
    items = [v.strip() for v in value.split(",") if v.strip()]
    return items


def _parse_platforms(value: str) -> list[str]:
    """Platforms are validated against the live ADAPTER_REGISTRY (not the static
    ALL_PLATFORMS list) so test code can ``monkeypatch.setitem(ADAPTER_REGISTRY, ...)``
    to inject extra platforms without touching this module.
    """
    if value == "all":
        return list(ADAPTER_REGISTRY.keys())
    items = [v.strip() for v in value.split(",") if v.strip()]
    invalid = [i for i in items if i not in ADAPTER_REGISTRY]
    if invalid:
        raise ValueError(
            f"platform 包含无效值 {invalid}; 有效: {list(ADAPTER_REGISTRY.keys())}"
        )
    return items


def run_scan(args: argparse.Namespace) -> int:
    started = time.monotonic()
    scanned_at = datetime.now(timezone.utc)

    _ensure_registry()
    platforms = _parse_platforms(args.platform)
    categories = _parse_categories(args.category)
    periods = _parse_list(args.period, ALL_PERIODS, "period")

    books = []
    errors: list[AdapterError] = []

    for platform in platforms:
        adapter = ADAPTER_REGISTRY.get(platform)
        if adapter is None:
            errors.append(AdapterError(
                platform=platform, category="*", period="*",
                stage="normalize", message=f"unknown platform: {platform}",
                occurred_at=datetime.now(timezone.utc),
            ))
            continue
        # Allow tests to inject the class itself (e.g. via
        # ``monkeypatch.setitem(ADAPTER_REGISTRY, "fake", FakeAdapter)``).
        # Production registry entries are always instances.
        if isinstance(adapter, type) and issubclass(adapter, BaseAdapter):
            adapter = adapter()

        for category in categories:
            for period in periods:
                try:
                    if adapter.status in (
                        AdapterStatus.BLOCKED_EXTERNAL,
                        AdapterStatus.BLOCKED_IMPLEMENTATION,
                    ):
                        # Blocked adapter — don't even try fetch().
                        # Record a human-readable explanation so the
                        # report surfaces WHY this attempt produced
                        # zero books (no silent failure).
                        reason = {
                            AdapterStatus.BLOCKED_EXTERNAL: (
                                f"{adapter.platform} 平台外部阻塞 "
                                f"（endpoint dead 或 anti-bot 拦截），"
                                f"需要 v0.2 解决"
                            ),
                            AdapterStatus.BLOCKED_IMPLEMENTATION: (
                                f"{adapter.platform} 平台实现未完成 "
                                f"（详见 KNOWN_LIMITATIONS.md），"
                                f"需要 v0.2 解决"
                            ),
                        }[adapter.status]
                        errors.append(AdapterError(
                            platform=platform, category=category, period=period,
                            stage=adapter.strategy.value,
                            message=reason,
                            occurred_at=datetime.now(timezone.utc),
                        ))
                        if args.verbose:
                            print(f"[{platform}/{category}/{period}] SKIPPED ({adapter.status.value}): {reason}", file=sys.stderr)
                        continue
                    if args.verbose:
                        print(f"[{platform}/{category}/{period}] fetching top {args.top}...", file=sys.stderr)
                    # LIVE and LIVE_WITH_SETUP both call fetch() — the
                    # latter will raise RuntimeError at runtime if its
                    # optional setup (e.g. playwright install) was
                    # skipped, which the orchestrator's exception handler
                    # turns into an AdapterError with a clear message.
                    raw_books = adapter.fetch(category, period, top=args.top)
                    for raw in raw_books:
                        books.append(raw_to_bookitem(raw, platform=adapter.platform, period=period))
                except Exception as e:
                    if args.verbose:
                        print(f"[{platform}/{category}/{period}] FAILED: {e}", file=sys.stderr)
                    errors.append(AdapterError(
                        platform=platform, category=category, period=period,
                        stage=adapter.strategy.value,
                        message=str(e),
                        occurred_at=datetime.now(timezone.utc),
                    ))

    duration = time.monotonic() - started

    result = ScanResult(
        meta=ScanMeta(
            platforms=platforms,
            categories=categories,
            periods=periods,
            top=args.top,
            scanned_at=scanned_at,
            duration_seconds=duration,
            total_books=len(books),
            total_errors=len(errors),
        ),
        books=books,
        errors=errors,
    )

    written = write_scan_result(result, output_dir=args.output_dir)

    if args.verbose:
        print(f"\n✓ 写入 {len(written)} 个文件到 {args.output_dir}", file=sys.stderr)
        print(f"  总本数：{len(books)} | 失败次数：{len(errors)}", file=sys.stderr)

    if len(books) == 0 and len(errors) > 0:
        return 1
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run_scan(args)
    except ValueError as e:
        print(f"参数错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())