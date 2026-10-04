# novel-downloader (qidian subset only)

This is a vendored subset of [saudadez21/novel-downloader](https://github.com/saudadez21/novel-downloader) for **reference only**.

Contains only the qidian plugin files (client.py, fetcher.py, parser.py, searcher.py) — used for:
- Field-name conventions (bookId / bookName / authorName / categoryName / coverUrl)
- RC4 cookie computation pattern (see `qidian_subset/searcher.py` `_calc_cookies`)
- Future probe.js anti-bot bypass (TODO)

The adapter (`scripts/adapters/qidian.py`) does NOT import from this subset — it uses `httpx` directly. The vendored code is preserved for future feature work.

## License

MIT License (from upstream repo).