#!/usr/bin/env python3
"""
Chapter file path helpers.

This project has seen multiple chapter filename conventions:
1) Legacy flat layout: 正文/第0007章.md
2) Volume layout:    正文/第1卷/第007章-章节标题.md

To keep scripts robust, always resolve chapter files via these helpers instead of hardcoding a format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_CHAPTER_NUM_RE = re.compile(r"第(?P<num>\d+)章")
_SPLIT_OUTLINE_FILENAME_RE = re.compile(r"^第0*(?P<num>\d+)章[-—_ ]+(?P<title>.+?)\.md$")


# ---------------------------------------------------------------------------
# 章纲标题契约（单一真源 / single shared heading contract）
# ---------------------------------------------------------------------------
# 官方模板 `templates/output/大纲-卷详细大纲.md` 生成的章标题写作 `## 第{N}章：`，
# 而 planner 手写章纲时可能用 `### 第1章：` / `## 第一章` 等变体。历史上
# `chapter_outline_loader._extract_outline_section` 只匹配 `###`，导致「照官方模板
# 规划 → runtime prepare 读不到章纲」。
#
# 该正则即为模板、加载器与章节路径识别共用的唯一标题契约，兼容：
#   - 1..6 级标题（# ~ ######）
#   - 阿拉伯数字与常用中文数字（一/二/两/三/十/二十一 …）
#   - 全角冒号、半角冒号、无冒号（`## 第1章 标题` 也接受）
#   - 标题前后任意合理空格
CHINESE_NUMERAL_DIGITS: dict[str, int] = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

OUTLINE_CHAPTER_HEADING_RE = re.compile(
    r"^(?P<hashes>#{1,6})[ \t]*第[ \t]*(?P<num>\d+|[零〇一二两三四五六七八九十]+)[ \t]*章"
    r"(?P<rest>[ \t]*(?:[：:、.．][ \t]*)?(?P<title>.*?))[ \t]*$",
    re.MULTILINE,
)


def parse_chapter_number(value: object) -> Optional[int]:
    """把章号写法（阿拉伯数字或中文数字）解析成 int。无法解析返回 None。"""
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in CHINESE_NUMERAL_DIGITS:
        return CHINESE_NUMERAL_DIGITS[text]
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = CHINESE_NUMERAL_DIGITS.get(left, 1 if not left else 0)
        ones = CHINESE_NUMERAL_DIGITS.get(right, 0) if right else 0
        return (tens * 10 + ones) or None
    parsed = 0
    for char in text:
        digit = CHINESE_NUMERAL_DIGITS.get(char)
        if digit is None:
            return None
        parsed = parsed * 10 + digit
    return parsed or None


@dataclass(frozen=True)
class OutlineChapterHeading:
    """章纲里的一个章标题。"""

    num: int
    title: str
    level: int
    start: int
    end: int


_FENCE_RE = re.compile(r"^[ \t]*(?P<fence>```+|~~~+)")


def _blank(line: str) -> str:
    return "".join("\n" if ch == "\n" else "\r" if ch == "\r" else " " for ch in line)


def mask_fenced_code_blocks(text: str) -> str:
    """把围栏代码块（``` / ~~~）内容替换成等长空格，保留全部偏移与行结构。

    官方章纲模板把「章模板」与「章节示例」都放在 fenced block 里；如果 planner
    把整份模板连同示例一起复制进 `大纲/第N卷-详细大纲.md`，示例里的
    `## 第4章：迦南学院的考验` 会被误当成第 4 章的真实章纲。屏蔽 fenced block
    后，只有真实章纲参与标题解析。
    """
    lines = str(text or "").splitlines(keepends=True)
    masked: list[str] = []
    fence_token: Optional[str] = None
    for line in lines:
        stripped_line = line.rstrip("\r\n")
        match = _FENCE_RE.match(stripped_line)
        if fence_token is None:
            if match is not None:
                fence_token = match.group("fence")[0]
                masked.append(_blank(line))
                continue
            masked.append(line)
            continue
        # inside a fenced block
        masked.append(_blank(line))
        if match is not None and match.group("fence")[0] == fence_token and len(match.group("fence")) >= 3:
            fence_token = None
    return "".join(masked)


def iter_outline_chapter_headings(text: str) -> list[OutlineChapterHeading]:
    """按出现顺序返回文本中所有章标题（含层级、标题、行首/行尾偏移）。

    围栏代码块内的标题（模板示例）不参与解析。
    """
    masked = mask_fenced_code_blocks(text)
    headings: list[OutlineChapterHeading] = []
    for match in OUTLINE_CHAPTER_HEADING_RE.finditer(masked):
        num = parse_chapter_number(match.group("num"))
        if num is None:
            continue
        headings.append(
            OutlineChapterHeading(
                num=num,
                title=(match.group("title") or "").strip(),
                level=len(match.group("hashes")),
                start=match.start(),
                end=match.end(),
            )
        )
    return headings


def find_outline_chapter_section(text: str, chapter_num: int) -> Optional[str]:
    """截取某章在章纲文件中的完整小节（含章标题行）。

    小节结束于「下一个同级或更高级标题」。因为章正文内部只用加粗字段标签、
    不用 markdown 标题，所以正常章纲不会被截断；若某章正文里出现更深的
    `####` 小标题，也会被正确包含在本章小节内。
    """
    content = str(text or "")
    headings = iter_outline_chapter_headings(content)
    # offsets come from the fenced-masked copy, which is length-preserving
    for index, heading in enumerate(headings):
        if heading.num != chapter_num:
            continue
        end = len(content)
        for following in headings[index + 1:]:
            if following.level <= heading.level:
                end = following.start
                break
        return content[heading.start:end].strip()
    return None


def volume_num_for_chapter(chapter_num: int, *, chapters_per_volume: int = 50) -> int:
    if chapter_num <= 0:
        raise ValueError("chapter_num must be >= 1")
    return (chapter_num - 1) // chapters_per_volume + 1


def extract_chapter_num_from_filename(filename: str) -> Optional[int]:
    m = _CHAPTER_NUM_RE.search(filename)
    if not m:
        return None
    try:
        return int(m.group("num"))
    except ValueError:
        return None


def _safe_title_for_filename(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        return ""

    try:
        from security_utils import sanitize_filename
    except ImportError:  # pragma: no cover
        from scripts.security_utils import sanitize_filename

    safe_title = sanitize_filename(cleaned, max_length=60)
    return "" if safe_title == "unnamed_entity" else safe_title


def _extract_title_from_outline_text(outline_text: str, chapter_num: int) -> str:
    for heading in iter_outline_chapter_headings(outline_text):
        if heading.num != chapter_num:
            continue
        title = _safe_title_for_filename(heading.title)
        if title:
            return title
    return ""


def _extract_title_from_split_outline_filename(outline_dir: Path, chapter_num: int) -> str:
    patterns = [
        f"第{chapter_num}章*.md",
        f"第{chapter_num:02d}章*.md",
        f"第{chapter_num:03d}章*.md",
        f"第{chapter_num:04d}章*.md",
    ]
    for pattern in patterns:
        for path in sorted(outline_dir.glob(pattern)):
            match = _SPLIT_OUTLINE_FILENAME_RE.match(path.name)
            if not match:
                continue
            if int(match.group("num")) != chapter_num:
                continue
            title = _safe_title_for_filename(match.group("title"))
            if title:
                return title
    return ""


def extract_chapter_title(project_root: Path, chapter_num: int) -> str:
    """从详细大纲提取章节标题，用于生成更直观的章节文件名。"""
    try:
        from chapter_outline_loader import load_chapter_outline
    except ImportError:  # pragma: no cover
        from scripts.chapter_outline_loader import load_chapter_outline

    outline_text = load_chapter_outline(project_root, chapter_num, max_chars=None)
    if not outline_text.startswith("⚠️"):
        title = _extract_title_from_outline_text(outline_text, chapter_num)
        if title:
            return title

    outline_dir = project_root / "大纲"
    if outline_dir.exists():
        return _extract_title_from_split_outline_filename(outline_dir, chapter_num)
    return ""


def _build_chapter_filename(project_root: Path, chapter_num: int, *, use_volume_layout: bool) -> str:
    padded = f"{chapter_num:03d}" if use_volume_layout else f"{chapter_num:04d}"
    title = extract_chapter_title(project_root, chapter_num)
    if title:
        return f"第{padded}章-{title}.md"
    return f"第{padded}章.md"


def working_chapter_draft_path(project_root: Path, chapter_num: int) -> Path:
    """Working draft path before durable commit acceptance."""
    return project_root / ".webnovel" / "tmp" / f"chapter_{chapter_num:04d}_working.md"


def find_chapter_file(project_root: Path, chapter_num: int, *, include_working: bool = False) -> Optional[Path]:
    """
    Find an existing chapter file for chapter_num under project_root/正文.
    Returns the first match (stable sorted order) or None if not found.
    """
    chapters_dir = project_root / "正文"
    if not chapters_dir.exists():
        return None

    legacy = chapters_dir / f"第{chapter_num:04d}章.md"
    if legacy.exists():
        return legacy

    vol_dir = chapters_dir / f"第{volume_num_for_chapter(chapter_num)}卷"
    if vol_dir.exists():
        candidates = sorted(vol_dir.glob(f"第{chapter_num:03d}章*.md")) + sorted(vol_dir.glob(f"第{chapter_num:04d}章*.md"))
        for c in candidates:
            if c.is_file():
                return c

    # Fallback: search anywhere under 正文/ (supports custom layouts)
    candidates = sorted(chapters_dir.rglob(f"第{chapter_num:03d}章*.md")) + sorted(chapters_dir.rglob(f"第{chapter_num:04d}章*.md"))
    for c in candidates:
        if c.is_file():
            return c

    if include_working:
        working_draft = working_chapter_draft_path(project_root, chapter_num)
        if working_draft.is_file():
            return working_draft
        runtime_draft = project_root / ".webnovel" / "runtime" / f"chapter_{chapter_num:03d}" / "draft.md"
        if runtime_draft.is_file():
            return runtime_draft

    return None


def default_chapter_draft_path(project_root: Path, chapter_num: int, *, use_volume_layout: bool = False) -> Path:
    """
    Preferred draft path when creating a new chapter file.

    Args:
        project_root: 项目根目录
        chapter_num: 章节号
        use_volume_layout: True 使用卷布局 (正文/第N卷/第NNN章-章节标题.md)，False 使用平坦布局 (正文/第NNNN章-章节标题.md)

    Default is flat layout. If the detailed outline already has a chapter title,
    append it to the filename for better discoverability.
    """
    if use_volume_layout:
        vol_dir = project_root / "正文" / f"第{volume_num_for_chapter(chapter_num)}卷"
        return vol_dir / _build_chapter_filename(project_root, chapter_num, use_volume_layout=True)
    else:
        return project_root / "正文" / _build_chapter_filename(project_root, chapter_num, use_volume_layout=False)

