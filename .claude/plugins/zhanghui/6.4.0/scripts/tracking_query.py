#!/usr/bin/env python3
"""tracking_query.py — 伏笔追踪查询（active / overdue）。

端口来源：oh-story-claudecode 的 `tracking_commit.py:549-559`
            `active_foreshadow_lines(rows)` 算法。

设计约束：
- 不引入第二权威 — 读 `state.json` 的 `plot_threads.foreshadowing`
  （这是 webnovel-writer 当前的真实写源）。
- 复用 `status_reporter.py` 已有的 `is_resolved_foreshadowing_status`、
  `normalize_foreshadowing_tier`、`resolve_chapter_field`，不重复实现。
- CLI 入口：`python tracking_query.py --project <root> --chapter <N> [--json|--md]`

CLI 例子：
    # 下一章热上下文（active 列表，markdown）
    python tracking_query.py --project . --chapter 4 --md

    # 报超期未回收（advisory）
    python tracking_query.py --project . --chapter 50 --overdue --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 复用现有 helpers，避免重复实现 urgency 计算（任务硬约束：不写第二份）
try:  # pragma: no cover - 兼容从 .claude/scripts/ 直接运行
    from status_reporter import _is_resolved_foreshadowing_status
except ImportError:
    try:
        from scripts.status_reporter import _is_resolved_foreshadowing_status
    except ImportError:
        # 最后兜底：直接读 state_validator
        try:
            from data_modules.state_validator import is_resolved_foreshadowing_status

            def _is_resolved_foreshadowing_status(raw_status):
                return is_resolved_foreshadowing_status(raw_status)
        except ImportError:  # pragma: no cover
            def _is_resolved_foreshadowing_status(raw_status):
                """保底实现：与 state_validator 保持一致的语义。"""
                if raw_status is None:
                    return False
                text = str(raw_status).strip().lower()
                return text in {"resolved", "paid", "回收", "已回收", "已完成"}

try:
    from status_reporter import _normalize_foreshadowing_tier
except ImportError:
    try:
        from scripts.status_reporter import _normalize_foreshadowing_tier
    except ImportError:
        # 兜底实现，权重与 status_reporter 一致（核心 3.0 / 支线 2.0 / 装饰 1.0）
        _TIER_WEIGHT_CORE = 3.0
        _TIER_WEIGHT_SUB = 2.0
        _TIER_WEIGHT_DECOR = 1.0

        def _normalize_foreshadowing_tier(raw_tier):
            text = str(raw_tier or "").strip()
            if text in {"核心", "core"}:
                return "核心", _TIER_WEIGHT_CORE
            if text in {"装饰", "decor"}:
                return "装饰", _TIER_WEIGHT_DECOR
            return "支线", _TIER_WEIGHT_SUB

# oh-story active_foreshadow_lines 排序键：importance（数值越大越重要） →
# planned_resolution_chapter（越小越紧） → id（确定序）。
TIER_IMPORTANCE: Dict[str, int] = {
    "核心": 3,
    "支线": 2,
    "装饰": 1,
}

DEFAULT_OVERDUE_THRESHOLD = 20  # 任务规格阈值：埋了 20 章没填 → advisory
DEFAULT_ACTIVE_TOP_K = 8         # 任务规格阈值：取前 8 条作为下一章热上下文

# H-R4-1: 防止恶意 / 异常的 state.json 让 json.load 把内存吃光（C-R4-1 DoS）。
# 真实 webnovel-writer 项目的 state.json 通常 < 1MB；5MB 已是 100x 上限。
MAX_STATE_BYTES = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def _resolve_state_path(project_root: Path) -> Path:
    """定位 state.json；约定 `.webnovel/state.json`。"""
    return project_root / ".webnovel" / "state.json"


def load_foreshadow_index(state_path: Path | str) -> Dict[str, Dict[str, Any]]:
    """从 state.json 读所有伏笔 → 以 id 索引的 dict。

    兼容字段：
    - `id` 或 `foreshadow_id`（R4 用 foreshadow_id；state.json 老格式无 id）
    - `status`：状态机字符串（中文 "已埋"/"已回收" 或英文 "active"/"resolved"）
    - `tier`：层级（"核心"/"支线"/"装饰"）
    - `planted_chapter` / `added_chapter` / `source_chapter` / `start_chapter` / `chapter`
    - `target_chapter` / `due_chapter` / `deadline_chapter` / `resolve_by_chapter` / `target`

    H-R4-1（C-R4-1）：超过 MAX_STATE_BYTES 字节直接返回空 + stderr 警告，
    避免攻击者构造超大 JSON 让 json.load 长时间占用内存。
    """
    state_path = Path(state_path)
    if not state_path.is_file():
        return {}

    # H-R4-1：先检查文件大小，避免 json.load 解析超大文件
    try:
        size = state_path.stat().st_size
    except OSError:
        return {}
    if size > MAX_STATE_BYTES:
        print(
            f"WARNING: state.json 体积 {size} 字节超过上限 {MAX_STATE_BYTES}，跳过加载（疑似异常/恶意输入）: {state_path}",
            file=sys.stderr,
        )
        return {}

    try:
        with open(state_path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}

    plot_threads = state.get("plot_threads") if isinstance(state, dict) else None
    if not isinstance(plot_threads, dict):
        return {}
    foreshadowing = plot_threads.get("foreshadowing")
    if not isinstance(foreshadowing, list):
        return {}

    index: Dict[str, Dict[str, Any]] = {}
    for idx, raw in enumerate(foreshadowing):
        if not isinstance(raw, dict):
            continue
        # 没有显式 id 时，使用 index + content 的 md5 前 8 位作稳定后缀（M-R4-3）。
        # 避免重复章节产生不同 fallback key（"fs:0:三年之约" 与 "fs:0:三年之约 " 因空格
        # 漂移就会让同一伏笔在不同次 load 里变成两个 row）；hashlib 永远给同一字符串
        # 同一摘要，可跨 load / 跨进程对齐。
        fid = raw.get("id") or raw.get("foreshadow_id")
        if not fid:
            content = str(raw.get("content") or "").strip()
            digest = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
            fid = f"fs:{idx}:{digest}"
        # 复制并补齐标准化字段（不修改原对象）
        row = dict(raw)
        row["id"] = str(fid)
        tier, weight = _normalize_foreshadowing_tier(raw.get("tier"))
        row["tier"] = tier
        row["weight"] = float(weight)
        row["status"] = str(raw.get("status") or "active")
        row["is_resolved"] = _is_resolved_foreshadowing_status(row["status"])
        row["planted_chapter"] = _resolve_int(
            raw,
            ["planted_chapter", "added_chapter", "source_chapter", "start_chapter", "chapter"],
        )
        row["target_chapter"] = _resolve_int(
            raw,
            ["target_chapter", "due_chapter", "deadline_chapter", "resolve_by_chapter", "target"],
        )
        index[row["id"]] = row
    return index


def _resolve_int(item: Dict[str, Any], keys: List[str]) -> Optional[int]:
    """按候选键顺序读出第一个正整数；失败返回 None。

    H-R4-2 修复：与上游 `state_validator.to_positive_int` 行为对齐：
    - 兼容纯数字（int / float / "5"）
    - 兼容字符串里的数字（"5章" / "第5章" / "五章" 等——后者会被忽略，因为只匹配阿拉伯数字）
    - 兼容全角数字 "５"（先 normalize 再 regex 抓数字）
    - 拒绝 None / bool（bool 是 int 子类，要显式排除）
    """
    for k in keys:
        if k not in item:
            continue
        v = item[k]
        if v is None or isinstance(v, bool):
            continue
        # 先尝试直接 int()（支持 int / float / 纯数字字符串 / 字节串）
        try:
            iv = int(v)
            if iv > 0:
                return iv
            continue
        except (TypeError, ValueError):
            pass
        # 再走字符串兜底：抓首个连续数字串（"5章"、"第5章"、"５" 经 normalize 后）
        if isinstance(v, str):
            normalized = v.translate(_FULL_WIDTH_DIGIT_TRANSLATION)
            m = re.search(r"\d+", normalized)
            if m:
                try:
                    iv = int(m.group(0))
                    if iv > 0:
                        return iv
                except ValueError:
                    continue
    return None


# H-R4-2：全角→半角数字翻译表（"５" → "5"）。
_FULL_WIDTH_DIGIT_TRANSLATION = str.maketrans("０１２３４５６７８９", "0123456789")


# ---------------------------------------------------------------------------
# 查询函数（核心算法）
# ---------------------------------------------------------------------------

def _is_active(row: Dict[str, Any]) -> bool:
    """判断 row 是否处于“已埋未回收”状态。

    兼容：oh-story 用 "已埋"；state.json 实测用 "active"；R4 db 用 "setup"。
    """
    if row.get("is_resolved"):
        return False
    status = str(row.get("status") or "").strip().lower()
    # 包含“resolved/paid/回收”的都视为非 active
    if status in {"resolved", "paid", "回收", "已回收", "已完成", "done"}:
        return False
    return True


def compute_active_foreshadow(
    state_path: Path | str,
    current_chapter: int,
    top_k: int = DEFAULT_ACTIVE_TOP_K,
) -> List[Dict[str, Any]]:
    """下一章热上下文 — 端口 oh-story `active_foreshadow_lines` 算法。

    排序键：
        1. importance（核心 3 > 支线 2 > 装饰 1）
        2. planned_resolution_chapter（越小越紧；缺省 → +∞）
        3. id（确定序）

    返回：长度 ≤ top_k 的 list；每条包含原始 row + `elapsed` 派生字段。
    """
    rows = load_foreshadow_index(state_path)
    candidates = [r for r in rows.values() if _is_active(r)]
    candidates.sort(
        key=lambda r: (
            -TIER_IMPORTANCE.get(r.get("tier", "支线"), 0),
            r.get("target_chapter") if r.get("target_chapter") is not None else 10**12,
            r.get("id", ""),
        )
    )

    out: List[Dict[str, Any]] = []
    for r in candidates[: max(0, int(top_k))]:
        planted = r.get("planted_chapter")
        elapsed = (current_chapter - planted) if isinstance(planted, int) else None
        item = {
            "id": r.get("id"),
            "content": r.get("content") or "[未命名伏笔]",
            "tier": r.get("tier", "支线"),
            "weight": r.get("weight", 2.0),
            "status": r.get("status"),
            "planted_chapter": planted,
            "target_chapter": r.get("target_chapter"),
            "elapsed": elapsed,
            "remaining": (
                r.get("target_chapter") - current_chapter
                if isinstance(r.get("target_chapter"), int)
                else None
            ),
        }
        out.append(item)
    return out


def compute_overdue_foreshadow(
    state_path: Path | str,
    current_chapter: int,
    threshold: int = DEFAULT_OVERDUE_THRESHOLD,
) -> List[Dict[str, Any]]:
    """超期未回收伏笔：埋了 >= threshold 章仍未关闭。

    判定：
        - 未关闭（!is_resolved）
        - planted_chapter 是正整数
        - current_chapter - planted_chapter >= threshold
        - （额外）target_chapter 存在且 current_chapter > target_chapter → "已超期"

    返回：list；每条带 `elapsed`、`overdue_kind` 派生字段。
    """
    rows = load_foreshadow_index(state_path)
    overdue: List[Dict[str, Any]] = []
    for r in rows.values():
        if r.get("is_resolved"):
            continue
        planted = r.get("planted_chapter")
        if not isinstance(planted, int):
            continue
        elapsed = current_chapter - planted
        if elapsed < max(0, int(threshold)):
            continue
        target = r.get("target_chapter")
        if isinstance(target, int) and current_chapter > target:
            kind = "已超期"
        else:
            kind = "埋太久未填"
        overdue.append({
            "id": r.get("id"),
            "content": r.get("content") or "[未命名伏笔]",
            "tier": r.get("tier", "支线"),
            "status": r.get("status"),
            "planted_chapter": planted,
            "target_chapter": target,
            "elapsed": elapsed,
            "overdue_kind": kind,
        })
    # 严重程度优先：超期 > 埋太久；同内按时按 elapsed 倒序
    overdue.sort(
        key=lambda r: (0 if r["overdue_kind"] == "已超期" else 1, -r["elapsed"], r["id"]),
    )
    return overdue


# ---------------------------------------------------------------------------
# 输出格式化
# ---------------------------------------------------------------------------

def format_active_foreshadow_md(rows: List[Dict[str, Any]]) -> str:
    """把 active 列表渲染为 markdown（人类可读 + 给 LLM 当 context 都行）。"""
    if not rows:
        return "## 活跃伏笔\n\n（无）\n"
    lines = ["## 活跃伏笔（下一章热上下文）", ""]
    lines.append(f"共 {len(rows)} 条：")
    lines.append("")
    lines.append("| # | 层级 | 埋章 | 目标章 | 已过 | 剩余 | 内容 |")
    lines.append("|---|------|------|--------|------|------|------|")
    for i, r in enumerate(rows, 1):
        tier = r.get("tier", "支线")
        planted = r.get("planted_chapter")
        target = r.get("target_chapter")
        elapsed = r.get("elapsed")
        remaining = r.get("remaining")
        planted_s = str(planted) if planted is not None else "?"
        target_s = str(target) if target is not None else "?"
        elapsed_s = f"{elapsed}章" if elapsed is not None else "?"
        remaining_s = f"{remaining}章" if remaining is not None else "?"
        # M-R4-1: 同时转义 | 与换行符，确保 markdown 表格不破（之前只替换了 |，
        # 多行 content 会撑开行数，让表格解析错乱）。
        content = str(r.get("content") or "[未命名伏笔]")
        content = re.sub(r"\|", r"\\|", content)
        content = re.sub(r"\s*\n\s*", " ", content)
        lines.append(
            f"| {i} | {tier} | {planted_s} | {target_s} | {elapsed_s} | {remaining_s} | {content} |"
        )
    lines.append("")
    return "\n".join(lines)


def format_overdue_foreshadow_md(rows: List[Dict[str, Any]]) -> str:
    """超期列表的渲染。"""
    if not rows:
        return "## 超期伏笔\n\n（无）\n"
    lines = ["## 超期伏笔（advisory）", ""]
    lines.append(f"共 {len(rows)} 条埋了 ≥ 阈值章仍未回收：")
    lines.append("")
    for r in rows:
        planted = r.get("planted_chapter")
        target = r.get("target_chapter")
        elapsed = r.get("elapsed")
        planted_s = f"第{planted}章" if planted is not None else "?"
        target_s = f"→ 目标第{target}章" if target is not None else ""
        kind = r.get("overdue_kind", "埋太久未填")
        tier = r.get("tier", "支线")
        content = str(r.get("content") or "[未命名伏笔]")
        lines.append(
            f"- **[{tier}/{kind}]** {content}（{planted_s} 埋，{target_s}，已过 {elapsed} 章）"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_md(text: str) -> None:
    print(text)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="伏笔追踪查询（active / overdue）。",
    )
    parser.add_argument("--project", required=True, help="项目根目录（含 .webnovel/state.json）")
    parser.add_argument("--chapter", required=True, type=int, help="当前章号")
    parser.add_argument("--top-k", default=str(DEFAULT_ACTIVE_TOP_K), help="active 列表上限（默认 8）")
    parser.add_argument("--threshold", default=str(DEFAULT_OVERDUE_THRESHOLD), help="overdue 阈值章数（默认 20）")
    parser.add_argument("--overdue", action="store_true", help="只输出超期伏笔（默认输出 active）")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--md", action="store_true", help="Markdown 输出（默认）")
    args = parser.parse_args(argv)

    # M-R4-4: 拒绝负数和 > 1_000_000 的章号，防止溢出 / 误输入污染排序
    if args.chapter <= 0 or args.chapter > 1_000_000:
        print(
            f"❌ --chapter={args.chapter} 非法，必须在 [1, 1_000_000] 之间",
            file=sys.stderr,
        )
        return 2

    project_root = Path(args.project).resolve()
    state_path = _resolve_state_path(project_root)
    if not state_path.is_file():
        print(f"❌ state.json 不存在：{state_path}", file=sys.stderr)
        return 2

    try:
        top_k = int(args.top_k)
    except ValueError:
        top_k = DEFAULT_ACTIVE_TOP_K
    try:
        threshold = int(args.threshold)
    except ValueError:
        threshold = DEFAULT_OVERDUE_THRESHOLD

    use_json = bool(args.json) and not bool(args.md)

    if args.overdue:
        rows = compute_overdue_foreshadow(state_path, args.chapter, threshold=threshold)
        if use_json:
            _print_json({
                "kind": "overdue",
                "current_chapter": args.chapter,
                "threshold": threshold,
                "count": len(rows),
                "rows": rows,
            })
        else:
            _print_md(format_overdue_foreshadow_md(rows))
        return 0

    rows = compute_active_foreshadow(state_path, args.chapter, top_k=top_k)
    if use_json:
        _print_json({
            "kind": "active",
            "current_chapter": args.chapter,
            "top_k": top_k,
            "count": len(rows),
            "rows": rows,
        })
    else:
        _print_md(format_active_foreshadow_md(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())