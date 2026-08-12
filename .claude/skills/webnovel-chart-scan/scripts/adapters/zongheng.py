"""纵横中文网 adapter — DIRECT_API strategy via httpx.

NOTE on field names (2026-08-12):
    The publicly documented endpoint
    ``https://www.zongheng.com/api/rank/details`` returned HTTP 404 at task
    implementation time. Real field names were harvested from the embedded
    Nuxt SSR payload of
    ``https://www.zongheng.com/rank?nav=new-book&rankType=4`` (returned 200).

    Real fields per book item:
        bookId, bookName, authorId, authorName, imageUrl, description,
        serialStatus, totalWords, number, numberDesc, rankNo, cateName,
        cateFineId, cateFineName.

    The adapter implements the spec'd contract
    (``data.bookList[*]``) and reads ``rankNo`` for rank position (the real
    field name). ``orderNo`` from the spec template is not present in the
    real payload — kept as a fallback so future API revisions that swap the
    field name still parse cleanly.
"""
import httpx

from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook

ZONGHENG_API = "https://www.zongheng.com/api/rank/details"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# rankType (per /rank?nav=... links observed on the site):
#   1=月票 3=日更 4=新书 5=点击 6=推荐 7=捧场 8=完本 9=新书订阅 10=日更新 12=作者人气
# We map our periods onto the closest matching rankType.
#   monthly -> 1 (月票榜)
#   weekly  -> 5 (点击榜 — weekly-ish engagement proxy)
#   daily   -> 3 (日榜)
RANK_TYPE_MAP = {"monthly": 1, "daily": 3, "weekly": 5}


def parse_rank_response(payload: dict, top: int) -> list[RawBook]:
    """把 zongheng API 的 JSON 响应解析为 RawBook 列表。

    Real payload shape (verified 2026-08-12 from Nuxt SSR data):
        {"data": {"bookList": [
            {"bookId", "bookName", "authorName", "rankNo", "cateFineName",
             "description", "totalWords", "imageUrl", "serialStatus", ...},
            ...
        ]}}
    """
    book_list = payload.get("data", {}).get("bookList", []) or []
    books: list[RawBook] = []
    for i, item in enumerate(book_list[:top]):
        # Prefer rankNo (real field). Fall back to orderNo (spec template) and
        # finally to 1-based index so rank_position is never None.
        rank_position = item.get("rankNo", item.get("orderNo", i + 1))
        # serialStatus: 1=连载 2=完本 (per real payload); map to schema enum.
        serial = item.get("serialStatus")
        status = None
        if serial in ("1", 1):
            status = "serial"
        elif serial in ("2", 2):
            status = "completed"

        books.append(
            RawBook(
                platform_book_id=str(item.get("bookId", "")),
                title=item.get("bookName", ""),
                author=item.get("authorName", ""),
                category=item.get("cateFineName", ""),
                intro=item.get("description", ""),
                word_count=item.get("totalWords"),
                status=status,
                cover_url=item.get("imageUrl"),
                rank_position=rank_position,
                raw_payload=item,
            )
        )
    return books


class ZonghengAdapter(BaseAdapter):
    platform = "zongheng"
    strategy = Strategy.DIRECT_API

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        if category != "all":
            # zongheng 公开 API 不支持 category 参数（只支持 rankType 过滤）
            # v0.1 严格处理：用户传了具体分类时直接报错，不静默吞掉
            # v0.2 增强：可考虑 WebFetch 兜底抓带 category 的页面
            raise NotImplementedError(
                f"zongheng DIRECT_API does not support category='{category}'. "
                f"Use category='all' or wait for v0.2 WebFetch fallback."
            )

        rank_type = RANK_TYPE_MAP.get(period, 4)
        url = ZONGHENG_API
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.zongheng.com/",
        }
        params = {
            "rankType": rank_type,
            "pageSize": min(top, 100),
            "pageNum": 1,
        }

        resp = httpx.get(url, headers=headers, params=params, timeout=30.0)
        resp.raise_for_status()
        return parse_rank_response(resp.json(), top=top)