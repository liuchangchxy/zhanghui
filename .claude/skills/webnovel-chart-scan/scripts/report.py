from collections import Counter
from scripts.schema import ScanResult


def _tag_cloud(tags_flat: list[str]) -> str:
    """生成简单标签云（按出现次数排序的 Markdown 列表）。"""
    if not tags_flat:
        return "_（无标签数据）_"
    counter = Counter(tags_flat)
    lines = [f"- {tag} ({count})" for tag, count in counter.most_common(20)]
    return "\n".join(lines)


def _word_count_buckets(books) -> dict[str, int]:
    buckets = {"<100万": 0, "100-300万": 0, ">300万": 0, "未知": 0}
    for b in books:
        if b.word_count is None:
            buckets["未知"] += 1
        elif b.word_count < 1_000_000:
            buckets["<100万"] += 1
        elif b.word_count < 3_000_000:
            buckets["100-300万"] += 1
        else:
            buckets[">300万"] += 1
    return buckets


def render_report_markdown(result: ScanResult) -> str:
    meta = result.meta
    books = result.books

    lines: list[str] = []
    lines.append(f"# 扫描报告：{', '.join(meta.platforms)} - {', '.join(meta.categories)} - {', '.join(meta.periods)}（TOP {meta.top}）")
    lines.append("")
    lines.append(f"扫描时间：{meta.scanned_at.isoformat()}")
    lines.append(f"耗时：{meta.duration_seconds:.1f}s")
    lines.append("")
    lines.append("## 概览")
    lines.append(f"- 总本数：**{meta.total_books}**")
    lines.append(f"- 失败次数：{meta.total_errors}")
    serial_count = sum(1 for b in books if b.status == "serial")
    completed_count = sum(1 for b in books if b.status == "completed")
    lines.append(f"- 连载中：{serial_count} | 已完结：{completed_count}")
    lines.append("")
    lines.append("### 字数分布")
    for k, v in _word_count_buckets(books).items():
        lines.append(f"- {k}: {v} 本")
    lines.append("")
    lines.append("### 标签云（TOP 20）")
    all_tags = [t for b in books for t in b.tags]
    lines.append(_tag_cloud(all_tags))
    lines.append("")

    if result.errors:
        lines.append("## 失败记录")
        for e in result.errors:
            lines.append(f"- [{e.platform}/{e.period}/{e.category}] {e.stage}: {e.message}")
        lines.append("")

    lines.append("## 完整榜单")
    lines.append("")
    lines.append("| # | 书名 | 作者 | 平台 | 分类 | 字数 | 状态 | 标签 |")
    lines.append("|---|------|------|------|------|------|------|------|")
    for b in sorted(books, key=lambda x: (x.platform, x.rank_position or 9999)):
        wc = f"{b.word_count // 10000}万" if b.word_count else "-"
        status = {"serial": "连载", "completed": "完结"}.get(b.status or "", "-")
        tags = ", ".join(b.tags[:3]) if b.tags else "-"
        lines.append(f"| {b.rank_position or '-'} | {b.title} | {b.author} | {b.platform} | {b.category} | {wc} | {status} | {tags} |")

    return "\n".join(lines) + "\n"
