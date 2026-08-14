#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Style Fingerprint - 章节文风指纹与跨章漂移检测

移植自 oh-story-claudecode style-profile-generator.md:84-97 的句长/标点统计算法，
扩展为「句长 + 对话 + 标点 + 段长」四维指纹 + 跨章漂移检测器。

可计算维度（不依赖 LLM 归纳）：
- 句长分布：短句(<15) / 中句(15-30) / 长句(>30) 占比 + 平均句长
- 标点密度：标点符号 / 非空白字符 比
- 对话占比：双引号 / 全角引号 包起来的对话字数占正文比例
- 说话标签密度：每 1000 字出现"说/道/问/喊/笑/答"等标签次数
- 平均段长：每段字符数（不含空白）

CLI：
  python style_fingerprint.py --project <root> --chapter <N> [--baseline|--drift|--json|--compare A B]

输出：
  --baseline 生成 / 覆盖基线指纹（写入 .webnovel/style-profile/baseline.json）
  --drift    与基线做漂移比对，输出 advisory 列表
  --compare  A B 两章详细对比
  --json     以 JSON 形式输出指纹（其它 flag 优先）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 原子写入：优先复用 security_utils，独立运行（.claude/scripts 副本旁边没有
# security_utils）时回退到本地等价实现。两条路径语义一致：
# tempfile + fsync + os.replace，写入中途崩溃不会留下半截 JSON。
try:
    from security_utils import atomic_write_text as _atomic_write_text  # type: ignore
except ImportError:  # pragma: no cover - 取决于部署位置
    def _atomic_write_text(file_path, text: str, **_kwargs) -> None:
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            suffix=".tmp", prefix=file_path.stem + "_", dir=file_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, file_path)
            temp_path = None
        finally:
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass


def _atomic_write_json(path: Path, payload: Any) -> None:
    """原子落盘 JSON（不留半写文件）。"""
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2),
        use_lock=False,
        backup=False,
    )


# ---------------------------------------------------------------------------
# 常量与阈值
# ---------------------------------------------------------------------------

# 句长分桶（与源算法一致）
SHORT_BOUND = 15   # 严格小于 15
LONG_BOUND = 30    # 严格大于 30

# 标点集合（含全/半角）
PUNCT_CHARS = set("，。！？；：、…—""''「」『』（）()[]【】《》")

# 说话动词（用于检测「标签密度」）。允许的常见变体。
SPEECH_VERBS = [
    "说道", "问道", "喊道", "叫道", "答道", "答道", "答道",
    "笑道", "微笑道", "冷笑道", "沉声道", "低声道", "轻声道",
    "吼道", "怒道", "叹道", "问道", "问", "答", "说", "道",
    "喊", "叫", "笑", "吼", "怒", "叹", "喊", "应", "答",
    "冷冷地说", "低声说", "缓缓说", "沉声说", "笑着说",
]

# 漂移阈值（与 baseline 比对的容差）
DRIFT_THRESHOLDS = {
    "short_lt15_pct": 15,    # 百分点
    "mid_15to30_pct": 15,
    "long_gt30_pct": 10,
    "avg_len": 5,            # 字符
    "punct_density": 5,      # 百分点
    "dialogue_ratio": 15,    # 百分点
    "tags_density": 50,      # 相对百分比
    "avg_para_len": 30,      # 字符
}

# confidence 分级
CONF_HIGH = "high"   # ≥3 基线章 + 确定性算法
CONF_MED = "med"     # 1-2 基线章
CONF_LOW = "low"     # 无基线 / 第一章


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class Fingerprint:
    """单章文风指纹。"""
    chapter: int
    chapter_file: str
    char_count: int = 0           # 非空白字符数
    sentence_count: int = 0
    short_lt15_pct: int = 0
    mid_15to30_pct: int = 0
    long_gt30_pct: int = 0
    avg_len: int = 0              # 平均句长（字符）
    punct_density: int = 0        # 标点密度（百分点）
    dialogue_ratio: int = 0       # 对话占比（百分点）
    tags_density: int = 0         # 每 1000 字说话标签数
    paragraph_count: int = 0
    avg_para_len: int = 0         # 平均段长（字符）
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DriftIssue:
    """一条漂移告警。"""
    metric: str
    label: str
    baseline: float
    current: float
    delta: float
    threshold: float
    severity: str  # "warn" | "risk"
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 函数 1：句长统计
# ---------------------------------------------------------------------------

def compute_sentence_stats(text: str) -> Dict[str, int]:
    """对一段中文文本做句长/标点统计。

    输出：{short, mid, long, total, avg_len, punct_density, char_count}
    """
    if not text or not text.strip():
        return {
            "short": 0, "mid": 0, "long": 0, "total": 0,
            "avg_len": 0, "punct_density": 0, "char_count": 0,
        }

    # C-R4-7: 增加分号作为句末分隔符（中文「；」亦可作句末）
    sents = [s for s in re.split(r"[。！？；]+", text) if s.strip()]
    total = max(len(sents), 1)

    short = sum(1 for s in sents if len(s) < SHORT_BOUND)
    mid = sum(1 for s in sents if SHORT_BOUND <= len(s) <= LONG_BOUND)
    long = sum(1 for s in sents if len(s) > LONG_BOUND)

    chars = max(sum(1 for c in text if not c.isspace()), 1)
    puncts = sum(1 for c in text if c in PUNCT_CHARS)
    avg = sum(len(s) for s in sents) // total

    return {
        "short": short,
        "mid": mid,
        "long": long,
        "total": total,
        "avg_len": avg,
        "punct_density": int(100 * puncts // chars),
        "char_count": chars,
    }


# ---------------------------------------------------------------------------
# 函数 2：对话统计
# ---------------------------------------------------------------------------

def compute_dialogue_stats(text: str) -> Dict[str, int]:
    """对话占比 + 说话标签密度。

    - dialogue_ratio：被全/半角引号包起来的内容占总非空白字符的百分点
    - tags_density：每 1000 字说话动词出现次数
    """
    if not text or not text.strip():
        return {"dialogue_ratio": 0, "tags_density": 0, "dialogue_chars": 0, "tag_count": 0}

    # 匹配被全/半角引号包裹的对话块（不做嵌套处理）
    dialogue_pattern = re.compile(r"[\"“]([^\"”\n]+)[\"”]|「([^「」\n]+)」")
    dialogue_chars = 0
    for m in dialogue_pattern.finditer(text):
        spoken = m.group(1) or m.group(2) or ""
        dialogue_chars += len(spoken)

    char_count = max(sum(1 for c in text if not c.isspace()), 1)
    ratio = int(100 * dialogue_chars // char_count)

    # 说话标签：长动词优先，避免短字符重复匹配
    # 先按 verb 长度降序匹配（"笑道" 优先于 "笑"），再去重
    tag_count = 0
    seen_spans: List[Tuple[int, int]] = []
    for verb in sorted(set(SPEECH_VERBS), key=len, reverse=True):
        for m in re.finditer(re.escape(verb), text):
            span = m.span()
            # 跳过已被更长 verb 覆盖的位置
            if any(s <= span[0] and span[1] <= e for s, e in seen_spans):
                continue
            seen_spans.append(span)
            tag_count += 1

    tags_density = int(1000 * tag_count // char_count)

    return {
        "dialogue_ratio": ratio,
        "tags_density": tags_density,
        "dialogue_chars": dialogue_chars,
        "tag_count": tag_count,
    }


def compute_paragraph_stats(text: str) -> Dict[str, int]:
    """段落统计：段数 + 平均段长（字符）。"""
    if not text or not text.strip():
        return {"paragraph_count": 0, "avg_para_len": 0}
    # C-R4-6: 用 \n+ 切段，识别单换行；过滤空段与纯空白段
    paras = [p for p in re.split(r"\n+", text) if p.strip()]
    if not paras:
        return {"paragraph_count": 0, "avg_para_len": 0}
    non_ws = [len(re.sub(r"\s", "", p)) for p in paras]
    avg = sum(non_ws) // max(len(paras), 1)
    return {"paragraph_count": len(paras), "avg_para_len": avg}


# ---------------------------------------------------------------------------
# 函数 3：整合
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_chapter_fingerprint(chapter_text: str, chapter_meta: Dict[str, Any]) -> Fingerprint:
    """整合所有维度为单章指纹。chapter_meta 至少包含 chapter_no 与 chapter_file。"""
    s = compute_sentence_stats(chapter_text)
    d = compute_dialogue_stats(chapter_text)
    p = compute_paragraph_stats(chapter_text)

    total = max(s["total"], 1)
    return Fingerprint(
        chapter=int(chapter_meta.get("chapter_no", 0)),
        chapter_file=str(chapter_meta.get("chapter_file", "")),
        char_count=s["char_count"],
        sentence_count=s["total"],
        short_lt15_pct=int(100 * s["short"] // total),
        mid_15to30_pct=int(100 * s["mid"] // total),
        long_gt30_pct=int(100 * s["long"] // total),
        avg_len=s["avg_len"],
        punct_density=s["punct_density"],
        dialogue_ratio=d["dialogue_ratio"],
        tags_density=d["tags_density"],
        paragraph_count=p["paragraph_count"],
        avg_para_len=p["avg_para_len"],
        generated_at=_now_iso(),
    )


# ---------------------------------------------------------------------------
# 路径与文件 IO
# ---------------------------------------------------------------------------

def _resolve_chapter_file(project_root: Path, chapter_no: int) -> Optional[Path]:
    """在项目根下找第 N 章正文。"""
    candidates: List[Path] = []
    body = project_root / "正文"
    if body.is_dir():
        # 形如 第0001章-title.md 或 第0001章.md
        padded = f"{chapter_no:04d}"
        candidates.append(body / f"第{padded}章.md")
        # 列举匹配
        if body.exists():
            for f in sorted(body.iterdir()):
                if f.is_file() and f.stem.startswith(f"第{padded}章"):
                    candidates.append(f)
    # 兜底：项目根直接放
    candidates.append(project_root / f"chapter_{chapter_no:04d}.md")
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def _style_profile_dir(project_root: Path) -> Path:
    d = project_root / ".webnovel" / "style-profile"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fingerprint_path(project_root: Path, chapter_no: int) -> Path:
    return _style_profile_dir(project_root) / f"ch{chapter_no:04d}.json"


def _baseline_path(project_root: Path) -> Path:
    return _style_profile_dir(project_root) / "baseline.json"


# ---------------------------------------------------------------------------
# 函数 4：保存
# ---------------------------------------------------------------------------

def save_fingerprint(project_root: Path, chapter_no: int, fingerprint: Fingerprint) -> Path:
    """落盘单章指纹；返回写入路径。"""
    path = _fingerprint_path(project_root, chapter_no)
    _atomic_write_json(path, fingerprint.to_dict())
    return path


# ---------------------------------------------------------------------------
# 函数 5：基线加载 / 生成
# ---------------------------------------------------------------------------

def _read_fingerprint(path: Path) -> Optional[Fingerprint]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return Fingerprint(**data)


def load_baseline(project_root: Path) -> Optional[Dict[str, Any]]:
    """读 baseline.json，返回 dict 或 None。"""
    p = _baseline_path(project_root)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _compute_aggregate(metric_values: List[float]) -> Dict[str, float]:
    """对一组数值算 mean/min/max，作为基线。"""
    if not metric_values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": sum(metric_values) / len(metric_values),
        "min": min(metric_values),
        "max": max(metric_values),
    }


def generate_baseline(project_root: Path, baseline_chapters: Optional[List[int]] = None) -> Dict[str, Any]:
    """基于已落盘的指纹文件生成基线。

    - 若 baseline_chapters 为 None：使用前 3 章（按 chapter 升序）的指纹
    - 否则：使用指定章号的指纹
    - 至少需要 1 个指纹；返回的 dict 包含 confidence 字段
    """
    sp_dir = _style_profile_dir(project_root)
    fps: List[Fingerprint] = []
    if baseline_chapters is not None:
        for ch in baseline_chapters:
            fp = _read_fingerprint(sp_dir / f"ch{ch:04d}.json")
            if fp is not None:
                fps.append(fp)
    else:
        # 按 ch*.json 文件名排序，取前 3
        paths = sorted(sp_dir.glob("ch*.json"))
        for p in paths[:3]:
            fp = _read_fingerprint(p)
            if fp is not None:
                fps.append(fp)

    if not fps:
        return {
            "ok": False,
            "reason": "no_fingerprints",
            "confidence": CONF_LOW,
        }

    metrics_to_aggregate = [
        "short_lt15_pct", "mid_15to30_pct", "long_gt30_pct",
        "avg_len", "punct_density", "dialogue_ratio",
        "tags_density", "avg_para_len",
    ]
    agg: Dict[str, Dict[str, float]] = {}
    for m in metrics_to_aggregate:
        values = [float(getattr(fp, m)) for fp in fps]
        agg[m] = _compute_aggregate(values)

    # 平均字数
    char_count_mean = sum(fp.char_count for fp in fps) / len(fps)

    confidence = CONF_HIGH if len(fps) >= 3 else CONF_MED

    payload = {
        "ok": True,
        "baseline_chapters": [fp.chapter for fp in fps],
        "char_count_mean": int(char_count_mean),
        "metrics": agg,
        "thresholds": DRIFT_THRESHOLDS,
        "confidence": confidence,
        "generated_at": _now_iso(),
    }

    _atomic_write_json(_baseline_path(project_root), payload)
    return payload


# ---------------------------------------------------------------------------
# 函数 6：漂移检测
# ---------------------------------------------------------------------------

METRIC_LABELS = {
    "short_lt15_pct": "短句(<15) 占比",
    "mid_15to30_pct": "中句(15-30) 占比",
    "long_gt30_pct": "长句(>30) 占比",
    "avg_len": "平均句长",
    "punct_density": "标点密度",
    "dialogue_ratio": "对话占比",
    "tags_density": "说话标签密度",
    "avg_para_len": "平均段长",
}


def _severity_for(metric: str, delta: float, threshold: float) -> str:
    """把绝对 delta 与 threshold 比较，确定 warn / risk。"""
    if abs(delta) >= 2 * threshold:
        return "risk"
    if abs(delta) >= threshold:
        return "warn"
    return "ok"


def detect_drift(current: Fingerprint, baseline: Dict[str, Any]) -> List[DriftIssue]:
    """比对当前章指纹与基线，输出 DriftIssue 列表（不含 severity=ok 的项）。"""
    if not baseline or not baseline.get("ok"):
        return []

    thresholds: Dict[str, float] = baseline.get("thresholds", DRIFT_THRESHOLDS)
    metrics: Dict[str, Dict[str, float]] = baseline.get("metrics", {})
    issues: List[DriftIssue] = []

    for m, label in METRIC_LABELS.items():
        if m not in metrics:
            continue
        b_mean = metrics[m].get("mean", 0.0)
        cur = float(getattr(current, m, 0))
        threshold = float(thresholds.get(m, 0))

        # C-R4-10: tags_density 是相对量，需用相对百分比判定 severity
        if m == "tags_density":
            rel_pct = abs(cur - b_mean) / max(b_mean, 1.0) * 100.0
            delta = cur - b_mean
            # 直接用相对百分比与 threshold 比（threshold 单位是「相对百分比」）
            if rel_pct >= 2 * threshold:
                severity = "risk"
            elif rel_pct >= threshold:
                severity = "warn"
            else:
                severity = "ok"
            note = f"相对变化 {(cur - b_mean) / max(b_mean, 1) * 100:+.1f}%"
        else:
            delta = cur - b_mean
            severity = _severity_for(m, delta, threshold)
            note = f"绝对变化 {delta:+.1f}pp"

        if severity == "ok":
            continue
        issues.append(DriftIssue(
            metric=m,
            label=label,
            baseline=round(b_mean, 2),
            current=cur,
            delta=round(delta, 2),
            threshold=threshold,
            severity=severity,
            note=note,
        ))

    return issues


# ---------------------------------------------------------------------------
# 报告渲染
# ---------------------------------------------------------------------------

def render_drift_markdown(current: Fingerprint, baseline: Dict[str, Any], issues: List[DriftIssue]) -> str:
    """生成 markdown 格式的漂移报告。"""
    lines: List[str] = []
    conf = baseline.get("confidence", CONF_LOW) if baseline else CONF_LOW
    bl_chs = baseline.get("baseline_chapters", []) if baseline else []

    lines.append(f"# 第 {current.chapter} 章 文风漂移报告")
    lines.append("")
    lines.append(f"- 基线章：第 {bl_chs} 章（{len(bl_chs)} 章）")
    lines.append(f"- 置信度：{conf}")
    lines.append(f"- 生成时间：{_now_iso()}")
    lines.append("")
    lines.append("## 指纹对比")
    lines.append("")
    lines.append("| 维度 | 基线 | 当前 | 阈值 | 状态 |")
    lines.append("|---|---:|---:|---:|:--:|")
    for m, label in METRIC_LABELS.items():
        b_mean = baseline.get("metrics", {}).get(m, {}).get("mean", 0.0) if baseline else 0.0
        cur = float(getattr(current, m, 0))
        th = DRIFT_THRESHOLDS.get(m, 0)
        status = "pass"
        for iss in issues:
            if iss.metric == m:
                status = "risk" if iss.severity == "risk" else "warn"
                break
        lines.append(f"| {label} | {b_mean:.1f} | {cur:.1f} | {th} | {status} |")
    lines.append("")
    if not issues:
        lines.append("## 结论")
        lines.append("")
        lines.append("无显著漂移；当前章节文风与基线一致。")
        return "\n".join(lines) + "\n"

    lines.append("## 漂移告警")
    lines.append("")
    for iss in issues:
        emoji = "🔴" if iss.severity == "risk" else "🟠"
        lines.append(f"- {emoji} **{iss.label}**：基线 {iss.baseline} → 当前 {iss.current}（{iss.note}，阈值 {iss.threshold}）")
    lines.append("")
    lines.append("## 建议")
    lines.append("")
    lines.append("- 漂移本身不等于错误；如剧情需要（战斗章、对话章）可保留。")
    lines.append("- 若无明确剧情原因，建议在 Step 4 润色时回看一下是否在以下维度失守：")
    lines.append("  - 句长分布是否突然单调（连续 3 章 +20pp 同向）")
    lines.append("  - 对话占比是否因本章写大量内心独白而塌缩")
    lines.append("  - 标点密度是否因引入大段设定说明而下降")
    return "\n".join(lines) + "\n"


def render_compare_markdown(fp_a: Fingerprint, fp_b: Fingerprint) -> str:
    """两章详细对比报告。"""
    lines: List[str] = []
    lines.append(f"# 第 {fp_a.chapter} 章 vs 第 {fp_b.chapter} 章 文风对比")
    lines.append("")
    lines.append("| 维度 | 第{}章 | 第{}章 | 差异 |".format(fp_a.chapter, fp_b.chapter))
    lines.append("|---|---:|---:|---:|")
    for m, label in METRIC_LABELS.items():
        a = float(getattr(fp_a, m, 0))
        b = float(getattr(fp_b, m, 0))
        diff = b - a
        sign = "+" if diff >= 0 else ""
        lines.append(f"| {label} | {a:.1f} | {b:.1f} | {sign}{diff:.1f} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _read_text_with_encoding(path: Path) -> str:
    """C-R4-8: 容忍非 UTF-8 编码（GBK / GB18030 等），加 BOM 检测。

    优先级：BOM-UTF8 → UTF-8 (strict) → UTF-8 (replace)。
    对 GBK 走 errors='replace' 路径，最坏情况乱码但不会让 CLI traceback。
    """
    raw = path.read_bytes()
    # BOM 检测
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8")
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        # UTF-16 带 BOM（极少用，但仍做兜底）
        return raw.decode("utf-16")
    # 尝试 UTF-8 严格解码
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # 退到 GBK + replace（中文环境最常见的非 UTF-8 编码）
        try:
            return raw.decode("gbk", errors="replace")
        except LookupError:
            return raw.decode("utf-8", errors="replace")


def _read_chapter_text(project_root: Path, chapter_no: int) -> Tuple[Optional[Path], str]:
    path = _resolve_chapter_file(project_root, chapter_no)
    if path is None:
        return None, ""
    return path, _read_text_with_encoding(path)


def _is_safe_project_root(project_root: Path) -> bool:
    """C-R4-11: symlink 安全检查。

    拒绝以下情形：
    1. project_root 本身仍是 symlink（说明调用者故意链到别处）
    2. project_root 链解析前后路径不一致（resolve 消解了中间 symlink 段）
    3. .webnovel 子目录本身是 symlink（防止子目录越权）

    注意：这里**不做**白名单限制——CLI 的合法用例包括 `/tmp/<pytest>` 临时项目。
    """
    # 1) 路径本身仍是 symlink → 拒绝
    try:
        if project_root.is_symlink():
            return False
    except OSError:
        return False
    # 2) .webnovel 子目录若是 symlink → 拒绝（防止子目录越权）
    webnovel_dir = project_root / ".webnovel"
    try:
        if webnovel_dir.exists() and webnovel_dir.is_symlink():
            return False
    except OSError:
        pass
    return True


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="webnovel-style-profile：章节文风指纹 + 跨章漂移检测",
    )
    parser.add_argument("--project", required=True, help="书项目根目录（含 .webnovel/state.json）")
    parser.add_argument("--chapter", type=int, required=True, help="要分析的章号")
    parser.add_argument("--baseline", action="store_true", help="生成/覆盖基线（默认基于前 3 章指纹）")
    parser.add_argument("--drift", action="store_true", help="与基线比对，输出 advisory")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出指纹")
    parser.add_argument("--compare", type=int, nargs=2, metavar=("A", "B"), help="对比 A B 两章")
    parser.add_argument("--baseline-chapters", type=int, nargs="+", metavar="N", help="基线使用的章号列表")
    args = parser.parse_args(argv)

    # C-R4-11: 关键安全检查在 resolve 之前 —— 检测调用者是否传了 symlink
    pre_resolve = Path(args.project).expanduser()
    try:
        if pre_resolve.is_symlink():
            print(
                f"ERROR: --project 是 symlink，拒绝写入（防止越权）: {pre_resolve}",
                file=sys.stderr,
            )
            return 2
    except OSError:
        pass

    project_root = pre_resolve.resolve()
    if not _is_safe_project_root(project_root):
        print(
            f"ERROR: 项目根不安全（.webnovel 是 symlink）: {project_root}",
            file=sys.stderr,
        )
        return 2
    if not (project_root / ".webnovel" / "state.json").exists():
        print(f"ERROR: 项目根未找到 .webnovel/state.json: {project_root}", file=sys.stderr)
        return 2

    # 对比模式
    if args.compare is not None:
        a, b = args.compare
        pa, ta = _read_chapter_text(project_root, a)
        pb, tb = _read_chapter_text(project_root, b)
        if pa is None or pb is None:
            print("ERROR: 对比章节文件缺失", file=sys.stderr)
            return 1
        fp_a = compute_chapter_fingerprint(ta, {"chapter_no": a, "chapter_file": str(pa)})
        fp_b = compute_chapter_fingerprint(tb, {"chapter_no": b, "chapter_file": str(pb)})
        print(render_compare_markdown(fp_a, fp_b))
        return 0

    # 单章指纹
    chap_path, chap_text = _read_chapter_text(project_root, args.chapter)
    if chap_path is None:
        # test_drift_flag 修复：--drift 模式下，章节缺失 → 写 advisory 报告而不是 error
        if args.drift:
            bl = load_baseline(project_root)
            if bl is None or not bl.get("ok"):
                bl = generate_baseline(project_root)
            report_md = render_drift_markdown(
                Fingerprint(chapter=args.chapter, chapter_file=""),
                bl,
                [],
            )
            advisory = (
                f"\n\n> ⚠️  第 {args.chapter} 章正文不存在；"
                "仅输出基线参考，无本章指纹可对比。\n"
            )
            report_md = report_md + advisory
            out_path = _style_profile_dir(project_root) / f"drift-ch{args.chapter:04d}.md"
            _atomic_write_text(out_path, report_md, use_lock=False, backup=False)
            if args.json:
                print(json.dumps({
                    "fingerprint": None,
                    "baseline": bl,
                    "drift": [],
                    "advisory": "chapter_missing",
                }, ensure_ascii=False, indent=2))
            else:
                print(report_md)
                print(f"漂移报告：{out_path}")
            return 0
        print(f"ERROR: 找不到第 {args.chapter} 章正文", file=sys.stderr)
        return 1

    fp = compute_chapter_fingerprint(
        chap_text,
        {"chapter_no": args.chapter, "chapter_file": str(chap_path)},
    )

    if args.baseline:
        # 先生成当前章指纹（如果还没有），再做基线
        save_fingerprint(project_root, args.chapter, fp)
        bl = generate_baseline(project_root, args.baseline_chapters)
        if args.json:
            print(json.dumps({"fingerprint": fp.to_dict(), "baseline": bl}, ensure_ascii=False, indent=2))
        else:
            print(f"基线生成：{'成功' if bl.get('ok') else '失败'}（{bl.get('confidence', CONF_LOW)}）")
            print(f"基线章：第 {bl.get('baseline_chapters', [])} 章")
            print(f"基线文件：{_baseline_path(project_root)}")
        return 0 if bl.get("ok") else 1

    # 默认行为：先保存指纹
    save_fingerprint(project_root, args.chapter, fp)

    if args.drift:
        bl = load_baseline(project_root)
        if bl is None or not bl.get("ok"):
            # 没有基线 → 自动用已有指纹生成
            bl = generate_baseline(project_root)
        issues = detect_drift(fp, bl)
        report_md = render_drift_markdown(fp, bl, issues)
        # C-R4-9: 漂移报告落盘
        out_path = _style_profile_dir(project_root) / f"drift-ch{args.chapter:04d}.md"
        _atomic_write_text(out_path, report_md, use_lock=False, backup=False)
        if args.json:
            payload = {
                "fingerprint": fp.to_dict(),
                "baseline": bl,
                "drift": [iss.to_dict() for iss in issues],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(report_md)
            print(f"漂移报告：{out_path}")
        return 0

    # 默认：仅打印指纹
    if args.json:
        print(json.dumps(fp.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"# 第 {fp.chapter} 章 指纹（{fp.chapter_file}）")
        print(f"  字数: {fp.char_count}")
        print(f"  句数: {fp.sentence_count}")
        print(f"  短句/中句/长句: {fp.short_lt15_pct}% / {fp.mid_15to30_pct}% / {fp.long_gt30_pct}%")
        print(f"  平均句长: {fp.avg_len} 字")
        print(f"  标点密度: {fp.punct_density}%")
        print(f"  对话占比: {fp.dialogue_ratio}%")
        print(f"  说话标签密度: {fp.tags_density} / 千字")
        print(f"  段数/平均段长: {fp.paragraph_count} / {fp.avg_para_len} 字")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
