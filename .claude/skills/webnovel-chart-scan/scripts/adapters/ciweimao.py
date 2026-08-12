"""刺猬猫 (ciweimao) adapter — WEBFETCH strategy via httpx + BeautifulSoup.

NOTE on URL/HTML structure (2026-08-12):
    The spec'd URL pattern ``/category/<encoded-name>`` returned HTTP 404 at
    task implementation time. Real category URLs on ciweimao.com use
    ``/book_list/{category_slug}/`` (e.g. ``/book_list/yijiehuanxiang/`` for
    玄幻奇幻). Each category page renders a ``<table class="book-list-table">``
    with one ``<tr>`` per book; the first ``<tr>`` is the header.

    Real fields per row:
        <td><p class="type">[玄幻奇幻]</p></td>
        <td><p class="name"><a href="https://www.ciweimao.com/book/{id}"
            title="{title}">{title}</a></p></td>
        <td><p class="chapter">...</p></td>
        <td><p class="author"><a href=".../reader/{id}">{author}</a></p></td>
        <td><p class="num">{word_count}</p></td>
        <td><p class="date">{yyyy-mm-dd}</p></td>

    ``period`` is mapped to the ciweimao sort key embedded in the URL:
        /book_list/{category}-{tag}-{sort}-{update}-{word}-{other}/quanbu/{page}
    For "default" sort, we just hit ``/book_list/{category_slug}/``.
"""
from __future__ import annotations

import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook

CIWEIMAO_BASE = "https://www.ciweimao.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Map our normalized categories -> ciweimao category slug.
# "all" means use the "全部" view which lists every category mixed.
CATEGORY_SLUG_MAP = {
    "all": "",
    "玄幻": "yijiehuanxiang",      # 玄幻奇幻
    "都市": "qingchunrichang",     # 都市青春
    "灵异": "shenmiweizhi",        # 灵异未知
    "历史": "zhanzhenglishi",      # 历史军事
    "军事": "zhanzhenglishi",
    "科幻": "weilaihuanxiang",     # 科幻无限
    "无限": "weilaihuanxiang",
    "游戏": "youxishijie",         # 游戏竞技
    "竞技": "youxishijie",
    "仙侠": "rexuejingji",         # 仙侠武侠
    "武侠": "rexuejingji",
    "同人": "tongrenfenlei",       # 免费同人
    "女频": "nvpinfenlei",         # 女频
}

# period -> ciweimao sort key for the 3rd URL segment.
# "0" means the site default sort.
PERIOD_SORT_MAP = {
    "daily": "day_no_vip_click",
    "weekly": "week_no_vip_click",
    "monthly": "month_no_vip_click",
}


def _extract_book_id(href: str) -> str:
    """从 ``/book/{id}`` 或 ``https://www.ciweimao.com/book/{id}`` 抽数字 id。"""
    if not href:
        return ""
    m = re.search(r"/book/(\d+)", href)
    return m.group(1) if m else ""


def parse_category_html(html: str, top: int) -> list[RawBook]:
    """解析刺猬猫分类页 HTML（``<table class="book-list-table">``）。

    每本书对应一个 ``<tr>``（首条 ``<tr>`` 是表头，跳过）。
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.book-list-table")
    if not table:
        return []

    rows = table.select("tr")
    books: list[RawBook] = []

    for idx, row in enumerate(rows):
        # 跳过表头（首个 tr 含 th 而非 td）
        if row.select_one("th") or not row.select_one("td"):
            continue

        name_p = row.select_one("p.name")
        if not name_p:
            continue
        link = name_p.select_one("a[href*='/book/']")
        if not link or not link.get("href"):
            continue
        href = link["href"]

        book_id = _extract_book_id(href)
        if not book_id:
            continue

        type_p = row.select_one("p.type")
        author_p = row.select_one("p.author")
        num_p = row.select_one("p.num")
        date_p = row.select_one("p.date")
        chapter_p = row.select_one("p.chapter")

        # category 形如 "[玄幻奇幻]" -> 去括号
        category_text = ""
        if type_p:
            category_text = type_p.get_text(strip=True).strip("[]")

        # word_count 转 int（失败保留 None）
        word_count: Optional[int] = None
        if num_p:
            num_text = num_p.get_text(strip=True).replace(",", "")
            if num_text.isdigit():
                word_count = int(num_text)

        # detail_url 标准化为绝对 URL
        if href.startswith("http"):
            detail_url = href
        else:
            detail_url = CIWEIMAO_BASE + href

        books.append(
            RawBook(
                platform_book_id=book_id,
                title=link.get_text(strip=True) or link.get("title", ""),
                author=author_p.get_text(strip=True) if author_p else "",
                category=category_text,
                word_count=word_count,
                detail_url=detail_url,
                rank_position=idx,  # 1-based 排名：enumerate 索引天然 1-based，因为 header 行 (idx=0) 被 continue 跳过
                raw_payload={
                    "latest_chapter": chapter_p.get_text(strip=True) if chapter_p else "",
                    "updated_date": date_p.get_text(strip=True) if date_p else "",
                    "html_snippet": str(row)[:500],
                },
            )
        )

        if len(books) >= top:
            break

    return books


class CiweimaoAdapter(BaseAdapter):
    platform = "ciweimao"
    strategy = Strategy.WEBFETCH

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        slug = CATEGORY_SLUG_MAP.get(category, CATEGORY_SLUG_MAP["玄幻"])
        sort_key = PERIOD_SORT_MAP.get(period, "0")

        if slug:
            if sort_key == "0":
                # default sort — use the canonical category URL
                url = f"{CIWEIMAO_BASE}/book_list/{slug}/"
            else:
                url = f"{CIWEIMAO_BASE}/book_list/0-0-{sort_key}-0-0-0/{slug}/1"
        else:
            # "all" -> 全部 category
            if sort_key == "0":
                url = f"{CIWEIMAO_BASE}/book_list/0-0-0-0-0-0/quanbu/1"
            else:
                url = f"{CIWEIMAO_BASE}/book_list/0-0-{sort_key}-0-0-0/quanbu/1"

        headers = {
            "User-Agent": USER_AGENT,
            "Referer": CIWEIMAO_BASE,
        }

        resp = httpx.get(url, headers=headers, timeout=30.0)
        resp.raise_for_status()
        return parse_category_html(resp.text, top=top)