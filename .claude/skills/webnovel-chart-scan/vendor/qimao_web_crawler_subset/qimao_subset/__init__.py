"""Slim extract of staysharp1104/WebCrawler's qimao ranking crawler.

Public API:
    fetch_qimao_rank(channel="boy", rank_type="hot", top=10) -> list[dict]

Output dict keys (verbatim from upstream ``QimaoCrawler.crawl_rankings``):
    book_id, rank, title, author, book_url, description,
    status (中文: "完结" / "连载"), reader_count, category_label,
    cover_url, source.
"""
from .crawl_qimao_rank import fetch_qimao_rank

__all__ = ["fetch_qimao_rank"]
