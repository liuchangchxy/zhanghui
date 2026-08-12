"""占位实现 — Task 11 会用真正的 Markdown 报告渲染替换本文件。"""

from scripts.schema import ScanResult


def render_report_markdown(result: ScanResult) -> str:
    """渲染扫描报告 Markdown（占位版本，仅输出摘要行）。"""
    return (
        "# 网文榜单扫描报告\n\n"
        f"- 扫描时间: {result.meta.scanned_at.isoformat()}\n"
        f"- 平台: {', '.join(result.meta.platforms)}\n"
        f"- 分类: {', '.join(result.meta.categories)}\n"
        f"- 周期: {', '.join(result.meta.periods)}\n"
        f"- 书籍总数: {result.meta.total_books}\n"
        f"- 错误总数: {result.meta.total_errors}\n"
    )
