#!/usr/bin/env python3
"""Context slice 定义与读盘。

每个 slice 是一组 (path_pattern, required) 白名单条目。
read_slice(project_root, slice_name, chapter=N) 按白名单匹配文件并读入。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SliceEntry:
    """单条白名单。pattern 是相对于 project_root 的 glob。"""
    pattern: str
    required: bool = False  # required=True 但文件不存在时 raise（默认 False = 静默跳过）


@dataclass
class ContextSlice:
    """一组白名单 + 元信息。"""
    name: str
    description: str
    entries: list[SliceEntry] = field(default_factory=list)


# === 内置 slice 定义 ===
WRITER_SLICE = ContextSlice(
    name="writer",
    description="写一章正文需要的最小上下文：章纲 + 角色卡 + 前 2 章摘要 + 当前章相关设定",
    entries=[
        SliceEntry("大纲/第1卷-详细大纲.md"),
        SliceEntry("大纲/总纲.md", required=False),
        SliceEntry("设定集/角色库/*.md"),
        SliceEntry("设定集/物品库/*.md", required=False),
        SliceEntry("设定集/其他设定/*.md", required=False),
        # 前 2 章摘要（chapter 参数驱动；read_slice 时按 chapter 展开）
        SliceEntry(".webnovel/summaries/ch{NNNN-2}.md", required=False),
        SliceEntry(".webnovel/summaries/ch{NNNN-1}.md", required=False),
    ],
)


REVIEWER_SLICE = ContextSlice(
    name="reviewer",
    description="reviewer 看：当前章正文 + 前后 ±2 章正文 + 爽点规划 + 相关角色设定",
    entries=[
        SliceEntry("正文/第{NNNN-2}章*.md", required=False),
        SliceEntry("正文/第{NNNN-1}章*.md", required=False),
        SliceEntry("正文/第{NNNN}章*.md"),
        SliceEntry("正文/第{NNNN+1}章*.md", required=False),
        SliceEntry("正文/第{NNNN+2}章*.md", required=False),
        SliceEntry("大纲/爽点规划.md", required=False),
        SliceEntry("大纲/第1卷-时间线.md", required=False),
        SliceEntry("设定集/角色库/*.md", required=False),
        SliceEntry("设定集/物品库/*.md", required=False),
    ],
)


POLISHER_SLICE = ContextSlice(
    name="polisher",
    description="polisher 看：当前章正文 + 文风指纹 + anti-slop 白名单",
    entries=[
        SliceEntry("正文/第{NNNN}章*.md"),
        SliceEntry("设定集/其他设定/文风.md", required=False),
        SliceEntry(".claude/references/deslop/whitelist.md", required=False),
    ],
)


SLICES: dict[str, ContextSlice] = {
    "writer": WRITER_SLICE,
    "reviewer": REVIEWER_SLICE,
    "polisher": POLISHER_SLICE,
}


def list_slices() -> list[str]:
    return sorted(SLICES.keys())


def _expand_pattern(pattern: str, chapter: int) -> str:
    """把 {NNNN}, {NNNN-1}, {NNNN+2} 等占位符展开为 4 位章节号。"""
    def repl(m: re.Match) -> str:
        offset = int(m.group(1)) if m.group(1) else 0
        actual = chapter + offset
        return f"{actual:04d}"
    return re.sub(r"\{NNNN([+-]\d+)?\}", repl, pattern)


def read_slice(
    project_root: Path,
    slice_name: str,
    chapter: int,
) -> dict[str, str]:
    """按 slice 白名单读文件，返回 {relative_path: content}。

    缺失文件：required=False 静默跳过；required=True 抛 FileNotFoundError。
    """
    if slice_name not in SLICES:
        raise ValueError(
            f"未知 slice: {slice_name!r}，可用: {list_slices()}"
        )
    slice_def = SLICES[slice_name]

    result: dict[str, str] = {}
    for entry in slice_def.entries:
        pat = _expand_pattern(entry.pattern, chapter)
        matched = sorted(project_root.glob(pat))
        for p in matched:
            if not p.is_file():
                continue
            rel = p.relative_to(project_root).as_posix()
            try:
                result[rel] = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # 二进制文件跳过
                continue

    # required 检查
    missing_required = [
        _expand_pattern(e.pattern, chapter)
        for e in slice_def.entries if e.required
        if not list(project_root.glob(_expand_pattern(e.pattern, chapter)))
    ]
    if missing_required:
        raise FileNotFoundError(
            f"slice {slice_name!r} 的 required 文件不存在: {missing_required}"
        )

    return result


def estimate_tokens(text: str) -> int:
    """粗估 token 数：中文 1 字 ≈ 1.5 token，英文 1 word ≈ 1.3 token。"""
    # 分离中英文
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    english_words = len(re.findall(r"[a-zA-Z]+", text))
    # other 包含英文 char + 标点 + 空格（非中文部分）
    other = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + english_words * 1.3 + other * 0.5)
