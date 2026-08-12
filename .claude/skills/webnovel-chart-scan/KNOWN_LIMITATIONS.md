# Known Limitations (v0.1.2)

Last updated: 2026-08-13

Each platform adapter is explicitly marked with `status`:
- **LIVE**: works against real upstream today
- **LIVE_WITH_SETUP**: works after user installs Playwright/chromium
- **BLOCKED_EXTERNAL**: external blocker (anti-bot / dead endpoint) — needs upstream-side fix
- **BLOCKED_IMPLEMENTATION**: needs code work — clearly documented next steps

## Platform status (verified 2026-08-13)

| Platform | Status | Why | Enable path |
|----------|--------|-----|-------------|
| **ciweimao** (刺猬猫) | LIVE | httpx + BS4 against real HTML works | n/a |
| **fanqie** (番茄) | LIVE_WITH_SETUP | Needs Playwright + chromium install | `pip install playwright && playwright install chromium` |
| **qimao** (七猫) | LIVE | Vendored regex rewrite fixed | n/a |
| **qidian** (起点) | BLOCKED_EXTERNAL | probe.js + RC4 cookie required | See fix plan below |
| **zongheng** (纵横) | BLOCKED_EXTERNAL | Public API endpoint returns HTTP 404 | See fix plan below |

## Fix plans for BLOCKED_EXTERNAL platforms

### 起点 (qidian) — RC4 cookie bypass

**Blocker**: qidian.com returns HTTP 202 + a probe.js challenge for
non-cookied requests. The vendored upstream
`vendor/novel-downloader/qidian_subset/searcher.py:_calc_cookies` has
the bypass logic (RC4-encrypted cookie construction).

**Fix steps (v0.2):**

1. Read `vendor/novel-downloader/qidian_subset/searcher.py` end-to-end
2. Port the `_calc_cookies` function into a thin module at
   `scripts/adapters/qidian_cookies.py` (or similar) — keep it as a
   private helper to the qidian adapter
3. Update `QidianAdapter.fetch()` to call the cookie computation BEFORE
   the request, attach the cookies to `httpx.get()`, and then
   `raise_for_status()`
4. Add cookie refresh on 202/probe.js response (retry once with fresh
   cookies)
5. Add unit tests for cookie computation (no network)
6. Add `@pytest.mark.slow` live HTTP test

**Estimated effort**: ~100 LOC, ~2 hours.

**Cannot fix in this repo**: qidian's anti-bot may add new challenges.
The vendored upstream tracks these; we'll need to sync periodically.

### 纵横 (zongheng) — Nuxt SSR scraping fallback

**Blocker**: The public API endpoint
`https://www.zongheng.com/api/rank/details?rankType={N}&pageSize=...`
returns HTTP 404. The site itself returns 200 with Nuxt SSR payload.

**Fix steps (v0.2):**

1. Research the actual rank page URL (likely
   `https://www.zongheng.com/rank?nav=new-book&rankType=N`)
2. Implement a `WEBFETCH` adapter (similar pattern to ciweimao):
   - httpx.get the rank page
   - Parse with BeautifulSoup
   - Extract book rows (need to inspect real HTML to determine
     selectors)
3. Switch adapter strategy from `DIRECT_API` to `WEBFETCH`
4. Update field-name mapping to match what's actually in the HTML
5. Add `@pytest.mark.slow` live HTTP test

**Estimated effort**: ~100 LOC, ~2 hours.

**Cannot fix in this repo**: the rank page HTML structure may change.

## What "BLOCKED_EXTERNAL" / "BLOCKED_IMPLEMENTATION" means

These adapters raise `NotImplementedError` immediately in `fetch()`.
The orchestrator records an `AdapterError` with a human-readable
explanation. User sees clear messages in `chart-scan/books.json`
errors[] and `chart-scan/report.md` 失败记录 section.

## What "LIVE_WITH_SETUP" means

These adapters have a working runtime code path, but require a
one-time user setup step before they can fetch data. The orchestrator
calls `fetch()` (no short-circuit) and any `RuntimeError` raised by
the adapter (e.g. "Playwright not installed — run `pip install
playwright`") surfaces as an `AdapterError` with actionable guidance.

## After v0.2 (all 5 LIVE)

When the remaining adapters become LIVE / LIVE_WITH_SETUP-with-deps:

- Run `pytest -m slow` to verify all 5 against real endpoints
- Remove this document (or convert to a "v0.2 changelog")

## How to add a new adapter

If you add a 6th platform:

1. Subclass `BaseAdapter`.
2. Set `platform`, `strategy`, and `status` class attributes.
3. If `status` is anything other than `AdapterStatus.LIVE`, write a
   tailored `fetch()` body that raises `NotImplementedError` (for
   BLOCKED_*) or `RuntimeError` (for LIVE_WITH_SETUP if deps are
   missing) with a one-line summary of the blocker + a pointer to this
   document. (The body is dead code at runtime for BLOCKED_*; for
   LIVE_WITH_SETUP it's the runtime path.)
4. Add the adapter to `ALL_PLATFORMS` in `scripts/scan.py` and to the
   `_ensure_registry()` dict.
5. Add at least the `test_*_adapter_metadata` test (verify
   `platform` + `strategy` + `status`).
6. If LIVE or LIVE_WITH_SETUP, add parser unit tests + an
   `@pytest.mark.slow` HTTP smoke test (modeled on
   `tests/test_ciweimao_live.py` or `tests/test_qimao_live.py`).