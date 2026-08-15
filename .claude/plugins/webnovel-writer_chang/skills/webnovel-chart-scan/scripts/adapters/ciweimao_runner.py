"""ciweimao Node subprocess wrapper + Markdown output parser.

The worldwonderer/oh-story-claudecode project's
``ciweimao-rank-scraper.js`` (MIT, 5600★) uses Chrome DevTools Protocol
to bypass ciweimao.com's anti-bot captcha. It outputs per-rank Markdown
files (e.g. ``刺猬猫点击榜_20260815.md``). This module:

1. Vendors the JS into ``vendor/worldwonderer_subset/`` (Task 8)
2. Provides ``run_scraper(rank_type, output_dir)`` that shells out to node + the JS
3. Provides ``parse_rank_markdown(text, top)`` that parses the output
   into ``list[RawBook]``

Why shell-out instead of porting the JS to Python:
- The JS uses ``agent-browser`` (a CDP wrapper) which has no Python
  equivalent without re-implementing the protocol layer
- Porting would be 200+ lines of fragile browser automation code
- The JS file is 9KB and updated frequently upstream — vendor-pinning
  + shelling out is the lower-maintenance path

Word-count parsing: the JS output uses Chinese 万/亿 suffixes
("234万" → 2,340,000; "1.2亿" → 120,000,000). Native English digit
strings are passed through unchanged.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from scripts.adapters.ciweimao_cat_map import map_native_category
from scripts.schema import RawBook


# Path to the vendored JS scraper. Set in Task 8 (vendor step).
JS_SCRAPER_PATH = (
    Path(__file__).parent.parent.parent
    / "vendor"
    / "worldwonderer_subset"
    / "ciweimao-rank-scraper.js"
)


# Map our (category, period) → ciweimao rank_type understood by the JS.
# ciweimao has 9 rank types: 点击榜 / 收藏榜 / 推荐榜 / 订阅榜 / 月票榜 /
# 吐槽榜 / 新书榜 / 刀片榜 / 更新榜. We map "weekly" → 点击榜 (default
# click rank = most-active on the platform), "daily" → 更新榜 (today's
# updates), "monthly" → 月票榜 (monthly tickets).
PERIOD_TO_RANK_TYPE = {
    "daily": "更新榜",
    "weekly": "点击榜",
    "monthly": "月票榜",
}


def parse_word_count(text: str) -> Optional[int]:
    """Convert "234万" / "1.2亿" / "15000" → int. Return None on parse fail."""
    if not text:
        return None
    text = text.strip()
    m = re.match(r"^([\d.]+)\s*万$", text)
    if m:
        return int(float(m.group(1)) * 10_000)
    m = re.match(r"^([\d.]+)\s*亿$", text)
    if m:
        return int(float(m.group(1)) * 100_000_000)
    if text.isdigit():
        return int(text)
    return None


# Pattern matches each "## N. 《书名》" block. Capture group 1 is the rank
# number, group 2 is the title (without 《 》).
_BOOK_HEADER_RE = re.compile(
    r"^##\s+(\d+)\.\s+《([^》]+)》\s*$", re.MULTILINE
)

# Each field line is "- 字段名: 值". Map field name → parser.
_FIELD_PARSERS = {
    "作者": ("author", lambda s: s.strip()),
    "分类": ("category", lambda s: s.strip()),
    "字数": ("word_count", parse_word_count),
    "简介": ("intro", lambda s: s.strip()),
    "链接": ("detail_url", lambda s: s.strip()),
    "最新章节": ("latest_chapter", lambda s: s.strip()),
}


def parse_rank_markdown(md_text: str, top: int = 50) -> list[RawBook]:
    """Parse ciweimao-rank-scraper.js's Markdown output into RawBook list.

    Markdown format (per worldwonderer/oh-story-claudecode upstream):

        # 刺猬猫{榜单} {YYYY-MM-DD}

        ## 1. 《书名》
        - 作者: XXX
        - 分类: XXX
        - 字数: 234万
        - 简介: ...
        - 链接: https://www.ciweimao.com/book/12345
        - 最新章节: ...

        ## 2. 《书名二》
        ...
    """
    if not md_text.strip():
        return []

    books: list[RawBook] = []
    # Split into per-book blocks by matching headers
    headers = list(_BOOK_HEADER_RE.finditer(md_text))
    for idx, match in enumerate(headers):
        rank_num = int(match.group(1))
        title = match.group(2)
        # Block = from end of this header to start of next (or end of text)
        block_start = match.end()
        block_end = headers[idx + 1].start() if idx + 1 < len(headers) else len(md_text)
        block = md_text[block_start:block_end]

        fields: dict[str, str] = {}
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("- "):
                continue
            # "- 作者: XXX" or "- 链接: https://..."
            kv = line[2:].split(":", 1)
            if len(kv) != 2:
                continue
            key, val = kv[0].strip(), kv[1].strip()
            if key in _FIELD_PARSERS:
                target_field, parser = _FIELD_PARSERS[key]
                fields[target_field] = parser(val)

        detail_url = fields.get("detail_url", "")
        # platform_book_id is the last URL segment for ciweimao (/book/<id>)
        platform_book_id = detail_url.rsplit("/", 1)[-1] if detail_url else ""

        # Map ciweimao native category → our normalized category
        raw_category = fields.get("category", "")
        normalized_category = map_native_category(raw_category)

        books.append(RawBook(
            platform_book_id=platform_book_id,
            title=title,
            author=fields.get("author", ""),
            category=normalized_category,
            word_count=fields.get("word_count"),
            detail_url=detail_url,
            rank_position=rank_num,
            raw_payload={
                "intro": fields.get("intro", ""),
                "latest_chapter": fields.get("latest_chapter", ""),
                "native_category": raw_category,
            },
        ))

        if len(books) >= top:
            break

    return books


def run_scraper(rank_type: str, output_dir: Path) -> Path:
    """Shell out to the vendored JS scraper. Return path to generated .md file.

    Raises RuntimeError if the JS exits non-zero, the output file is
    missing, or node / the JS file is unavailable.

    Args:
        rank_type: one of ciweimao's 9 榜单 (e.g. "点击榜", "新书榜")
        output_dir: where to write the Markdown output

    Returns:
        Path to the generated Markdown file (e.g.
        ``output_dir/刺猬猫{rank_type}_YYYYMMDD.md``)
    """
    if not JS_SCRAPER_PATH.exists():
        raise RuntimeError(
            f"Vendored JS scraper not found at {JS_SCRAPER_PATH}. "
            "Did you run Task 8 (vendor the JS)?"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    # The worldwonderer scraper accepts --rank-type and --output-dir args
    # (verified against upstream source 2026-08-16). Adjust if upstream API
    # has changed — see vendor/worldwonderer_subset/README.md.
    cmd = [
        "node",
        str(JS_SCRAPER_PATH),
        "--rank-type", rank_type,
        "--output-dir", str(output_dir),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
            check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "node executable not found on PATH. Install Node.js ≥18 to "
            "enable ciweimao adapter."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"ciweimao scraper timed out after 180s. Site may be slow "
            "or the CDP connection failed."
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"ciweimao scraper failed (exit {result.returncode}): "
            f"stderr={result.stderr[:500]}"
        )

    # The scraper writes a file named 刺猬猫{rank_type}_{YYYYMMDD}.md
    expected_pattern = f"刺猬猫{rank_type}_"
    matching = sorted(output_dir.glob(f"{expected_pattern}*.md"))
    if not matching:
        raise RuntimeError(
            f"ciweimao scraper succeeded but no output file matching "
            f"{expected_pattern}*.md found in {output_dir}. "
            f"stdout={result.stdout[:500]}"
        )
    return matching[-1]  # most recent if multiple
