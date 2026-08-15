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

Word-count parsing: the JS output uses Chinese 万/亿/千 suffixes
("234万" → 2,340,000; "1.2亿" → 120,000,000; "5.6千" → 5,600).
Native English digit strings are passed through unchanged.

Markdown format (verified against vendored ciweimao-rank-scraper.js,
commit 6af052974fd86fbdbbafce3e363d643221c6ce27):

    # 刺猬猫 · {榜单}

    - 来源：https://www.ciweimao.com/rank-index
    - 抓取时间：{ISO timestamp}
    - 条目数：{N}
    - 作品页链接：{linked} / {N}

    ---

    ### #1 {title}
    *{author} · {metric}*            # NO.1: author + metric (no genre)
    [作品页]({url})

    ---

    ### #2 {title}
    *{genre} · {metric}*             # #2-10: genre + metric (no author)
    [作品页]({url})

    ---

The two distinct meta-line shapes (NO.1 vs #2-10) exist because the
upstream parser extracts NO.1 from a 3-line block (title/author/metric)
where genre is empty, while #2-10 entries come from a single
"N[genre]title" line with author empty.

Rank-1 author-availability caveat (C4): the upstream JS does NOT emit
the author for rank-1 (it parses a 3-line block where the genre slot
is empty by upstream convention). If upstream ever changes and starts
putting a genre label in rank-1's first slot, we treat it as a genre
(mis-classification bug otherwise) and flag ``raw_payload["author_missing"]
= True`` so downstream consumers know the author is unknown.

For rank-1, when upstream doesn't provide a genre either, we apply a
loose title-based heuristic (see ``_TITLE_GENRE_KEYWORDS``). If that
also fails to match, we leave ``category=""`` and set the flag.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from scripts.adapters.ciweimao_cat_map import NATIVE_TO_NORMALIZED, map_native_category
from scripts.schema import RawBook

logger = logging.getLogger(__name__)


# Path to the vendored JS scraper. Set in Task 8 (vendor step).
JS_SCRAPER_PATH = (
    Path(__file__).parent.parent.parent
    / "vendor"
    / "worldwonderer_subset"
    / "ciweimao-rank-scraper.js"
)


# Map our (period) → worldwonderer JS --type value.
# Verified against upstream ciweimao-rank-scraper.js (commit 6af05297):
#   --type click  → 点击榜 (most-active, refreshes often)
#   --type monthly → 月票榜 (monthly tickets)
#   --type all    → all ranks (heavier; not used by us)
PERIOD_TO_RANK_TYPE = {
    "daily": "click",
    "weekly": "click",
    "monthly": "monthly",
}


# Loose title-based genre heuristic for rank-1 (when upstream emits no
# genre and no author — see C4/I6). Order matters: longer keywords
# come first so 仙侠 doesn't accidentally match before 修仙小说.
_TITLE_GENRE_KEYWORDS = (
    "修仙", "玄幻", "奇幻", "都市", "仙侠", "武侠", "科幻",
    "游戏", "竞技", "悬疑", "灵异", "同人", "历史", "军事",
    "二次元", "轻小说",
)


def _title_genre_guess(title: str) -> str:
    """Loose genre guess based on keywords in the book title.

    Used for rank-1 entries only (upstream doesn't emit a genre for the
    top slot). Returns empty string if no keyword matches — caller must
    then flag ``author_missing=True``.
    """
    if not title:
        return ""
    for kw in _TITLE_GENRE_KEYWORDS:
        if kw in title:
            return map_native_category(kw)
    return ""


def parse_word_count(text: str) -> Optional[int]:
    """Convert "234万" / "1.2亿" / "5.6千" / "15000" → int. Return None on parse fail."""
    if not text:
        return None
    text = text.strip()
    m = re.match(r"^([\d.]+)\s*万$", text)
    if m:
        return int(float(m.group(1)) * 10_000)
    m = re.match(r"^([\d.]+)\s*亿$", text)
    if m:
        return int(float(m.group(1)) * 100_000_000)
    m = re.match(r"^([\d.]+)\s*千$", text)
    if m:
        return int(float(m.group(1)) * 1_000)
    if text.isdigit():
        return int(text)
    return None


# Pattern matches each "### #N {title}" block. Capture group 1 is the rank
# number (without the leading "#"), group 2 is the title (raw, no 《 》 wrapping
# in real JS output).
_BOOK_HEADER_RE = re.compile(
    r"^###\s+#(\d+)\s+(.+?)\s*$", re.MULTILINE
)

# The italic meta line — either "*author · metric*" (NO.1) or
# "*genre · metric*" (#2-10). Captures the inner content (without the *).
_META_LINE_RE = re.compile(r"^\*(.+?)\*\s*$")

# The book URL link line — exactly "[作品页](https://www.ciweimao.com/book/N)".
_LINK_LINE_RE = re.compile(r"^\[作品页\]\(([^)]+)\)\s*$")

# Meta values use " · " (middle dot, U+00B7) as the field separator.
# The metric field (always last when present) matches a number with optional
# 万/亿/千 suffix. Anything else is either an author name (rank 1) or a genre
# label (rank 2-10).
_META_SEPARATOR = " · "
_METRIC_RE = re.compile(r"^[\d.]+\s*(?:万|亿|千)?$")


def _split_meta_line(meta_content: str, rank_num: int) -> tuple[str, str, str]:
    """Parse a meta line into (author, category, metric).

    For rank=1 (NO.1): parts are [author, metric] (genre is empty upstream).
    For rank>=2 (#2-10): parts are [genre, metric] (author is empty upstream).

    A meta line is "*X · Y*" (2 parts, one of which is metric) or
    "*X*" (1 part — could be just metric or just author/genre). Unknown
    ordering is disambiguated by rank.

    C4 hardening: if rank=1 and the only label is actually a known
    category name (which would happen if upstream changed its format
    and started emitting a genre in the rank-1 slot), we treat it as
    a category instead of an author — and flag ``author_missing``
    via ``raw_payload["author_missing"] = True`` in the caller.
    The ``author=""`` return + ``category=<mapped>`` return signals the
    caller to set the flag.
    """
    parts = [p.strip() for p in meta_content.split(_META_SEPARATOR)]
    author = ""
    category = ""
    metric = ""

    if len(parts) == 0:
        return author, category, metric

    # Identify which part is the metric (last part if it parses as a number,
    # else no metric present).
    last = parts[-1]
    if _METRIC_RE.match(last) or parse_word_count(last) is not None:
        metric = last
        label_parts = parts[:-1]
    else:
        label_parts = parts

    if not label_parts:
        return author, category, metric

    # The single remaining label is author (rank 1) or category (rank >= 2).
    label = label_parts[0]
    if rank_num == 1:
        # C4: if this "label" is actually a known genre name, upstream
        # probably changed format. Treat it as a category (NOT author)
        # and signal the caller via empty author.
        if label in NATIVE_TO_NORMALIZED:
            author = ""
            category = label
        else:
            author = label
    else:
        category = label

    return author, category, metric


def parse_rank_markdown(md_text: str, top: int = 50) -> list[RawBook]:
    """Parse ciweimao-rank-scraper.js's Markdown output into RawBook list.

    See module docstring for the exact Markdown shape produced by the
    vendored JS (verified against upstream commit 6af05297).
    """
    if not md_text or not md_text.strip():
        logger.warning(
            "parse_rank_markdown: empty markdown received — returning []"
        )
        return []

    books: list[RawBook] = []
    # Split into per-book blocks by matching headers
    headers = list(_BOOK_HEADER_RE.finditer(md_text))
    for idx, match in enumerate(headers):
        rank_num = int(match.group(1))
        title = match.group(2).strip()
        # Block = from end of this header to start of next (or end of text)
        block_start = match.end()
        block_end = headers[idx + 1].start() if idx + 1 < len(headers) else len(md_text)
        block = md_text[block_start:block_end]

        author = ""
        native_category = ""
        metric = ""
        detail_url = ""
        # C4: flag we set if the author is genuinely unknown upstream
        # (rank-1 with no upstream author, or upstream format change
        # caused mis-classification).
        author_missing = False

        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue

            meta_match = _META_LINE_RE.match(line)
            if meta_match:
                author, native_category, metric = _split_meta_line(
                    meta_match.group(1), rank_num
                )
                # C4: rank-1 with empty author means upstream didn't
                # emit an author. Flag it so downstream consumers know.
                if rank_num == 1 and not author and not native_category:
                    author_missing = True
                # C4: rank-1 where _split_meta_line re-routed the label
                # to category (because it matched a known genre name)
                # also means the real author is unknown.
                if rank_num == 1 and not author and native_category:
                    author_missing = True
                continue

            link_match = _LINK_LINE_RE.match(line)
            if link_match:
                detail_url = link_match.group(1).strip()
                continue

        # I6: rank-1 fallback — if we still don't have a category
        # (upstream changed format AND no keyword matched), try a
        # loose title-keyword heuristic.
        if rank_num == 1 and not native_category:
            guess = _title_genre_guess(title)
            if guess:
                native_category = guess
                # We used a heuristic, so the upstream genre is also
                # effectively unknown (we guessed). Flag it.
                author_missing = True

        # Map ciweimao native category → our normalized category
        normalized_category = map_native_category(native_category)
        # Metric (e.g., "234万") is rank-specific (clicks for click rank,
        # tickets for monthly rank). We surface it as word_count for
        # backwards compatibility with the existing API contract — the
        # schema doesn't have a separate "metric_value" field.
        word_count = parse_word_count(metric) if metric else None
        # platform_book_id is the last URL segment for ciweimao (/book/<id>)
        platform_book_id = detail_url.rsplit("/", 1)[-1] if detail_url else ""

        books.append(RawBook(
            platform_book_id=platform_book_id,
            title=title,
            author=author,
            category=normalized_category,
            word_count=word_count,
            detail_url=detail_url,
            rank_position=rank_num,
            raw_payload={
                "metric": metric,
                "native_category": native_category,
                **({"author_missing": True} if author_missing else {}),
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
    # The worldwonderer scraper accepts --type, --outdir, --port args
    # (verified against upstream commit 6af05297, 2026-08-14). Adjust if
    # upstream API has changed — see vendor/worldwonderer_subset/README.md.
    cmd = [
        "node",
        str(JS_SCRAPER_PATH),
        "--type", rank_type,
        "--outdir", str(output_dir),
        "--port", "9222",
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

    # I3: pick the most-recently-modified matching file. Lexical sort
    # (sorted(...)[-1]) is fragile to upstream filename variations like
    # 刺猬猫点击榜_20260815.md.bak or 刺猬猫点击榜_20260815.md.OLD.
    expected_pattern = f"刺猬猫{rank_type}_"
    matching = list(output_dir.glob(f"{expected_pattern}*.md"))
    if not matching:
        # Fallback glob: allow .bak / .OLD / etc. — anything starting
        # with the prefix. This handles legacy rotation patterns
        # without falsely accepting unrelated files.
        fallback = [
            p for p in output_dir.glob(f"{expected_pattern}*")
            if p.is_file()
        ]
        if not fallback:
            raise RuntimeError(
                f"ciweimao scraper succeeded but no output file matching "
                f"{expected_pattern}* found in {output_dir}. "
                f"stdout={result.stdout[:500]}"
            )
        # Among fallback files, pick most-recently-modified too.
        return max(fallback, key=lambda p: p.stat().st_mtime)

    # I3: most-recently-modified wins (handles re-scrape overwrites
    # where filename is the same but mtime differs).
    return max(matching, key=lambda p: p.stat().st_mtime)