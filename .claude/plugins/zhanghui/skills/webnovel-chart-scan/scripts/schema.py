from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

PLATFORMS = Literal["qidian", "fanqie", "zongheng", "qimao", "ciweimao"]
PERIODS = Literal["daily", "weekly", "monthly"]
STATUSES = Literal["serial", "completed"]
ERROR_STAGES = Literal["vendor", "hybrid", "direct_api", "webfetch", "normalize"]


class RawBook(BaseModel):
    """平台原始数据，由各 adapter 的 fetch() 返回。"""
    platform_book_id: str
    title: str
    author: str
    category: str
    tags: list[str] = Field(default_factory=list)
    intro: str = ""
    word_count: Optional[int] = None
    status: Optional[STATUSES] = None
    cover_url: Optional[str] = None
    detail_url: Optional[str] = None
    rank_position: Optional[int] = None
    raw_payload: dict = Field(default_factory=dict)


class BookItem(BaseModel):
    """归一化后的书籍元数据。"""
    id: str
    platform: PLATFORMS
    title: str
    author: str
    category: str
    category_normalized: str
    tags: list[str] = Field(default_factory=list)
    intro: str = ""
    word_count: Optional[int] = None
    status: Optional[STATUSES] = None
    cover_url: Optional[str] = None
    detail_url: Optional[str] = None
    rank_position: Optional[int] = None
    period: PERIODS
    fetched_at: datetime


class AdapterError(BaseModel):
    platform: str
    category: str
    period: str
    stage: ERROR_STAGES
    message: str
    occurred_at: datetime


class ScanMeta(BaseModel):
    platforms: list[str]
    categories: list[str]
    periods: list[str]
    top: int
    scanned_at: datetime
    duration_seconds: float
    total_books: int
    total_errors: int

    @field_validator("scanned_at")
    @classmethod
    def _scanned_at_must_be_utc(cls, v: datetime) -> datetime:
        # M5 fix: tzinfo is None == naive datetime. Naive datetimes
        # silently drop the UTC tag and downstream slug_timestamp()
        # raises — better to fail fast at parse time with a clear
        # message. Use datetime.now(timezone.utc) or attach tzinfo=UTC.
        if v.tzinfo is None:
            raise ValueError(
                "scanned_at must be timezone-aware (use datetime.now(timezone.utc))"
            )
        return v


class ScanResult(BaseModel):
    meta: ScanMeta
    books: list[BookItem]
    errors: list[AdapterError] = Field(default_factory=list)