"""Vendored subset of staysharp1104/WebCrawler (2026-08-12).

Only the qimao ranking crawler is kept. The full upstream repo also ships:
  - crawlers/{fanqie,feilu,qidian}.py        (other platforms we don't use)
  - crawlers/base.py                         (selenium/chromedriver boilerplate)
  - config.py                                (DB-aware task scheduler constants)
  - database.py, db_ops.py, services/, sql/  (PostgreSQL task queue)
  - main.py, webapp.py, templates/, webapp/  (FastAPI web UI)
  - font_decoder.py, font_map.json           (qidian-specific font decoder)
  - book_analyzer_ddl.sql, sql/              (DB schema)
  - monitor_qidian.py, _check_status.py, _reset_books.py
  - requirements-old.txt

We intentionally omit the selenium/chromedriver driver (used only for
``crawl_book_info`` in SSR fallback paths we don't call) and all DB/web
plumbing. The adapter only needs ``fetch_qimao_rank`` to walk the
``/paihang`` SSR pages and project ``fetch[*].listData[*]`` into the
upstream-shaped item dicts.
"""
