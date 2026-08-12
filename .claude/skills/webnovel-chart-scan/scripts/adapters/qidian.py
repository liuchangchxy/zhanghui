"""起点中文网 (qidian) adapter — WEBFETCH strategy via httpx + BeautifulSoup.

Status: LIVE (verified 2026-08-13, after mobile-subdomain bypass).

    The desktop site ``www.qidian.com`` returns HTTP 202 + a probe.js
    challenge for every URL — including the public rank/category pages.
    The vendored upstream ``vendor/novel-downloader/qidian_subset/searcher.py``
    implements an RC4 cookie construction (``_calc_cookies``) intended to
    bypass the challenge, but verification on 2026-08-13 showed that the
    cookies do NOT actually bypass modern probe.js. The vendored searcher
    silently swallows the resulting 202 as a generic Exception, returning
    an empty string — i.e. the vendored reference is also broken against
    modern qidian.com.

    The runtime bypass that DOES work is using the **mobile subdomain**
    (``m.qidian.com``) with an iPhone Safari User-Agent. Mobile pages are
    server-rendered (the body contains the rank/category HTML, not just a
    Vue mount point) and don't trigger probe.js. We use::

        User-Agent:  Mozilla/5.0 (iPhone; ...) Safari/...
        URL pattern: https://m.qidian.com/rank       (all-categories rank)
                     https://m.qidian.com/category/<id>  (per-category list)

    ``qidian_cookies.py`` is kept as a faithful port of the vendored
    RC4 helper for traceability / future-proofing (in case qidian ever
    reopens the cookie-bypass path), but it is NOT the runtime code path
    used here. See the module docstring in ``qidian_cookies.py`` for
    the RC4 verification record.

Period -> tab mapping:
    The ``/rank`` page renders 9 tabs (月票榜/畅销榜/阅读榜/书友榜/推荐榜/
    更新榜/签约榜/新书榜/新人榜) with 5 books each. We map our period
    enum to one tab:

        monthly -> 月票榜 (monthly tickets)
        weekly  -> 推荐榜 (recommendations)
        daily   -> 更新榜 (updates)

Category support:
    ``/category/<id>`` works for every value in ``QIDIAN_CATEGORY_IDS``.
    The category page renders 20 books per request with author/category/
    word-count/intro on a single card.
"""
from __future__ import annotations

import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup, Tag

from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook

# Mobile User-Agent that does NOT trigger probe.js. Verified 2026-08-13.
_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)
_REFERER = "https://m.qidian.com/"
_BASE = "https://m.qidian.com"

# 起点分类 ID (same mapping the v0.1.x adapter used for the desktop URL).
# These IDs are the same numbers qidian publishes in its category nav.
QIDIAN_CATEGORY_IDS = {
    "玄幻": 21,
    "奇幻": 1,
    "武侠": 2,
    "仙侠": 22,
    "都市": 4,
    "职场": 15,
    "军事": 6,
    "历史": 5,
    "游戏": 7,
    "体育": 8,
    "科幻": 9,
    "灵异": 10,
    "二次元": 12,
    "轻小说": 13,
}

# Period -> _rankTitle_<hash> tab label on /rank.
PERIOD_TO_RANK_TAB = {
    "monthly": "月票榜",
    "weekly": "推荐榜",
    "daily": "更新榜",
}

# Word-count parser: handles "639.05万字" -> 6_390_500, "12字" -> 12, "12" -> 12.
_WORD_COUNT_RE = re.compile(r"^([\d.]+)\s*([万千]?)\s*字?$")


def _parse_word_count(text: str) -> Optional[int]:
    """Parse a Chinese-style word-count label into an int.

    Accepts: "639.05万字" -> 6390500, "12字" -> 12, "1.2万" -> 12000,
    "12" -> 12. Returns None for unparseable input.
    """
    if not text:
        return None
    m = _WORD_COUNT_RE.match(text.strip())
    if not m:
        return None
    num, unit = m.groups()
    try:
        value = float(num)
    except ValueError:
        return None
    if unit == "万":
        return int(value * 10_000)
    if unit == "千":
        return int(value * 1_000)
    return int(value)


def _split_subtitle(subtitle: str) -> tuple[str, str, Optional[int]]:
    """Split the rank-page subtitle "作者 · 分类 · 字数" into 3 fields.

    Returns (author, category, word_count). When the subtitle has fewer
    pieces (e.g. only author + word count on the category page), the
    missing slots are empty / None.

    Heuristic for word_count: the LAST segment whose ``_parse_word_count``
    succeeds is treated as the word count (categories never end with a
    bare integer). Author is the FIRST segment. Anything in between is
    category.
    """
    if not subtitle:
        return "", "", None
    parts = [p.strip() for p in re.split(r"[·•・]", subtitle) if p.strip()]
    if not parts:
        return "", "", None
    author = parts[0]
    word_count: Optional[int] = None
    category_idx = -1  # last segment where we found a word count
    for i in range(len(parts) - 1, 0, -1):
        wc = _parse_word_count(parts[i])
        if wc is not None:
            word_count = wc
            category_idx = i
            break
    if category_idx > 1:
        category = " · ".join(parts[1:category_idx])
    elif len(parts) >= 2:
        category = parts[1]
    else:
        category = ""
    return author, category, word_count


def _abs_url(href: str) -> str:
    """Coerce a possibly-protocol-relative ``//host/path`` URL to https://."""
    if not href:
        return ""
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return _BASE + href
    return _BASE + "/" + href


def parse_rank_html(html: str, top: int, period: str) -> list[RawBook]:
    """Parse the rank-page HTML and return up to ``top`` books for the period's tab.

    Walks the DOM in order so that each ``_rankTitle_*`` element is paired
    with the book anchors that follow it (until the next title or end of
    document).
    """
    soup = BeautifulSoup(html, "lxml")
    target_tab = PERIOD_TO_RANK_TAB.get(period, "月票榜")

    current_tab: Optional[str] = None
    current_books: list[Tag] = []
    tab_to_books: dict[str, list[Tag]] = {}

    for el in soup.descendants:
        if not isinstance(el, Tag):
            continue
        classes = el.get("class", [])
        if not isinstance(classes, list):
            continue
        if any(c.startswith("_rankTitle") for c in classes):
            if current_tab is not None:
                tab_to_books[current_tab] = current_books
            current_tab = el.get_text(strip=True)
            current_books = []
            continue
        if el.name == "a" and any(c.startswith("_bookWrapper") for c in classes):
            current_books.append(el)
    # Final tab close.
    if current_tab is not None:
        tab_to_books[current_tab] = current_books

    anchors = tab_to_books.get(target_tab, [])
    out: list[RawBook] = []
    for idx, a in enumerate(anchors):
        if len(out) >= top:
            break
        book_id = a.get("data-bid", "")
        if not book_id:
            continue
        href = _abs_url(a.get("href", ""))
        title_el = a.select_one('[class*="_title_"]')
        subtitle_el = a.select_one('[class*="_subTitle_"]')
        ranking_el = a.select_one('[class*="_ranking_"]')
        cover_el = a.select_one("img")
        title = title_el.get_text(strip=True) if title_el else ""
        subtitle = subtitle_el.get_text(strip=True) if subtitle_el else ""
        author, category, word_count = _split_subtitle(subtitle)
        cover_url = ""
        if cover_el is not None:
            cover_url = _abs_url(
                cover_el.get("data-src") or cover_el.get("src") or ""
            )
        rank_no: Optional[int] = None
        if ranking_el:
            try:
                rank_no = int(ranking_el.get_text(strip=True))
            except ValueError:
                rank_no = idx + 1
        else:
            rank_no = idx + 1
        out.append(
            RawBook(
                platform_book_id=book_id,
                title=title,
                author=author,
                category=category,
                word_count=word_count,
                cover_url=cover_url or None,
                detail_url=href,
                rank_position=rank_no,
                raw_payload={
                    "source": "m.qidian.com",
                    "rank_tab": target_tab,
                    "rank_label": ranking_el.get_text(strip=True)
                    if ranking_el else "",
                },
            )
        )
    return out


def parse_category_html(html: str, top: int) -> list[RawBook]:
    """Parse the category-page HTML and return up to ``top`` books.

    Each book card has: ``_bookTitle_*`` (title), ``_bookSubTitle_*`` (intro),
    ``_bookTip_*`` (author), and ``._tags_* p`` siblings (category, status,
    word count). The site limits each page to ~20 books.
    """
    soup = BeautifulSoup(html, "lxml")
    anchors = [
        a for a in soup.select("a")
        if any(
            isinstance(c, str) and c.startswith("_bookWrapper")
            for c in (a.get("class") or [])
        )
    ]
    out: list[RawBook] = []
    for idx, a in enumerate(anchors):
        if len(out) >= top:
            break
        book_id = a.get("data-bid", "")
        if not book_id:
            continue
        href = _abs_url(a.get("href", ""))
        title_el = a.select_one('[class*="_bookTitle_"]')
        subtitle_el = a.select_one('[class*="_bookSubTitle_"]')
        author_el = a.select_one('[class*="_bookTip_"]')
        tags_container = a.select_one('[class*="_tags_"]')
        cover_el = a.select_one("img")
        title = title_el.get_text(strip=True) if title_el else ""
        intro = subtitle_el.get_text(strip=True) if subtitle_el else ""
        author = author_el.get_text(strip=True) if author_el else ""
        # tags: [category, status, word_count]
        tags: list[str] = []
        word_count: Optional[int] = None
        status_label = ""
        if tags_container is not None:
            for p in tags_container.select("p"):
                t = p.get_text(strip=True)
                if not t:
                    continue
                tags.append(t)
            if len(tags) >= 1:
                category = tags[0]
            else:
                category = ""
            if len(tags) >= 2:
                status_label = tags[1]
                if status_label in ("完结", "已完结"):
                    status = "completed"
                else:
                    status = "serial"
            else:
                status = None
            if len(tags) >= 3:
                word_count = _parse_word_count(tags[2])
        else:
            category = ""
            status = None
        cover_url = ""
        if cover_el is not None:
            cover_url = _abs_url(
                cover_el.get("data-src") or cover_el.get("src") or ""
            )
        out.append(
            RawBook(
                platform_book_id=book_id,
                title=title,
                author=author,
                category=category,
                intro=intro,
                word_count=word_count,
                status=status,  # type: ignore[arg-type]
                cover_url=cover_url or None,
                detail_url=href,
                rank_position=idx + 1,
                raw_payload={
                    "source": "m.qidian.com",
                    "status_label": status_label,
                    "tags": tags,
                },
            )
        )
    return out


def fetch_qidian_category(category: str, period: str, top: int) -> list[RawBook]:
    """Fetch the qidian mobile category page for ``category``."""
    cat_id = QIDIAN_CATEGORY_IDS.get(category)
    if not cat_id:
        # "all" or unknown — fall back to the all-categories rank page.
        return fetch_qidian_rank(period=period, top=top)

    # m.qidian.com 301-redirects ``/category/<id>`` to ``/category/catid<id>``.
    # httpx follow_redirects=True handles this transparently, but we
    # construct the canonical URL directly so the request is observable.
    url = f"{_BASE}/category/catid{cat_id}"
    headers = {
        "User-Agent": _MOBILE_UA,
        "Referer": _REFERER,
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    resp = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    return parse_category_html(resp.text, top=top)


def fetch_qidian_rank(period: str, top: int) -> list[RawBook]:
    """Fetch the qidian mobile ``/rank`` page for ``period``."""
    url = f"{_BASE}/rank"
    headers = {
        "User-Agent": _MOBILE_UA,
        "Referer": _REFERER,
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    resp = httpx.get(url, headers=headers, timeout=30.0)
    resp.raise_for_status()
    return parse_rank_html(resp.text, top=top, period=period)


class QidianAdapter(BaseAdapter):
    platform = "qidian"
    strategy = Strategy.WEBFETCH

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        """Fetch qidian rank/category list via mobile subdomain.

        ``category="all"`` -> the all-categories ``/rank`` page (period
        picks the tab). ``category="玄幻"`` (etc.) -> the per-category
        ``/category/<id>`` page. ``period`` is ignored for category pages
        (the category page is not split by period).
        """
        if category == "all" or category not in QIDIAN_CATEGORY_IDS:
            return fetch_qidian_rank(period=period, top=top)
        return fetch_qidian_category(category=category, period=period, top=top)