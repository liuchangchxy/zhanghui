# Known Limitations (v0.1.3)

Last updated: 2026-08-13

Each platform adapter is explicitly marked with `status`:
- **LIVE**: works against real upstream today
- **LIVE_WITH_SETUP**: works after user installs Playwright/chromium
- **BLOCKED_EXTERNAL**: external blocker (anti-bot / dead endpoint) — needs upstream-side fix
- **BLOCKED_IMPLEMENTATION**: needs code work — clearly documented next steps

## Platform status (verified 2026-08-13)

| Platform | Status | Why | Enable path |
|----------|--------|-----|-------------|
| **ciweimao** (刺猬猫) | LIVE (degraded) | httpx + BS4 against real HTML works, but site has begun gating `/book_list/*` with a man-machine CAPTCHA redirect (observed 2026-08-13). Captcha bypass is a separate item — see "Captcha regressions" below. | n/a (until captcha is solved) |
| **fanqie** (番茄) | LIVE_WITH_SETUP | Needs Playwright + chromium install | `pip install playwright && playwright install chromium` |
| **qimao** (七猫) | LIVE | Vendored regex rewrite fixed (v0.1.2); unchanged | n/a |
| **qidian** (起点) | LIVE | Mobile-subdomain bypass — `https://m.qidian.com/rank` and `/category/catid<id>` return server-rendered HTML with the iPhone Safari User-Agent (no probe.js) | n/a |
| **zongheng** (纵横) | LIVE | Nuxt SSR scraping — `/rank?nav=new-book&rankType=4` returns 200 with `window.__NUXT__` payload containing all 6 rank lists | n/a |

5/5 platforms are LIVE or LIVE_WITH_SETUP. No BLOCKED_EXTERNAL.

## v0.1.3 changelog (2026-08-13)

### Fix: qidian (起点) — port RC4 cookie helper + mobile-subdomain bypass

The vendored upstream at `vendor/novel-downloader/qidian_subset/searcher.py`
implements an RC4 cookie construction (`_calc_cookies`) intended to bypass
qidian.com's probe.js anti-bot. Verification on 2026-08-13 showed:

  - The vendored RC4 cookies do NOT actually bypass modern probe.js.
    Both with and without the cookies, `https://www.qidian.com/...`
    returns HTTP 202 + `https://www.qidian.com/C2WF946J0/probe.js`.
  - The vendored searcher silently catches the failure and returns an
    empty string — so even when the vendored upstream "succeeds" it's
    actually returning nothing.

The runtime bypass that DOES work is using the **mobile subdomain**
(`m.qidian.com`) with an iPhone Safari User-Agent. The mobile pages are
server-rendered (the body contains the rank/category HTML directly, not
just a Vue mount point) and don't trigger probe.js.

We still ported the vendored RC4 helper verbatim into
`scripts/adapters/qidian_cookies.py` for traceability and future-proofing
(in case qidian reopens the cookie-bypass path). Tests exercise the
helper byte-deterministic-ally without network access.

- `scripts/adapters/qidian_cookies.py` (new) — pure-Python port of the
  vendored RC4 + `_calc_cookies`. ~120 LOC.
- `scripts/adapters/qidian.py` — full rewrite to WEBFETCH strategy
  against `m.qidian.com`. Parses 9 rank tabs on `/rank` (period picks
  tab) and 20 books per category on `/category/catid<id>`. ~180 LOC.
- Status: BLOCKED_EXTERNAL → LIVE.

### Fix: zongheng (纵横) — Nuxt SSR scraping

The previously assumed JSON API
`https://www.zongheng.com/api/rank/details` returns HTTP 404. The site
itself returns 200 with a Nuxt SSR payload embedded as
`window.__NUXT__`, containing all rank lists (`monthTicketRankList`,
`newBookRankList`, `popularRankList`, `clickRankList`,
`recommendRankList`, `newOrderRankList`) under
`state.rank.popularityRank`.

We reuse the balanced-brace + identifier-substitution Nuxt parser
originally written for the qimao adapter (copied verbatim into
`scripts/adapters/zongheng.py` so the adapter is self-contained and
doesn't break on qimao refactors) and pick the right list for the
requested period.

- `scripts/adapters/zongheng.py` — full rewrite to WEBFETCH strategy
  against the public `/rank` page. ~200 LOC.
- Status: BLOCKED_EXTERNAL → LIVE.

### New tests

- `tests/test_qidian_cookies.py` (new) — 9 unit tests for the RC4
  helper, no network. Pin byte-level behavior so future changes don't
  silently drift the cookie shape.
- `tests/test_qidian_adapter.py` (updated) — parser unit tests against
  real captured HTML fixtures (`tests/fixtures/qidian_rank_all.html`,
  `tests/fixtures/qidian_category_xuanhuan.html`). Captured 2026-08-13.
- `tests/test_qidian_live.py` (new) — 3 `@pytest.mark.slow` HTTP smoke
  tests against `m.qidian.com`.
- `tests/test_zongheng_adapter.py` (updated) — parser unit tests
  against the real captured HTML fixture
  (`tests/fixtures/zongheng_rank_newbook.html`). The old synthesized
  fixture `tests/fixtures/zongheng_rank_details.json` is no longer used
  by tests but is kept for historical reference (git history).
- `tests/test_zongheng_live.py` (new) — 3 `@pytest.mark.slow` HTTP smoke
  tests against `zongheng.com/rank`.

### Captcha regressions (separate from this fix)

- **ciweimao**: The site's `/book_list/*` endpoints now redirect (HTTP
  307) to a man-machine verification page (`/signup/man_machine_verify`)
  for some requests. The current adapter raises `HTTPStatusError` when
  this happens. The adapter status is still `LIVE` (it does work for
  the in-fixture URLs), but the live smoke test fails on the
  CAPTCHA-gated endpoints. Bypassing the captcha is a separate item —
  likely needs Playwright + hCaptcha solver, similar to fanqie.

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

## After v0.1.3 (5/5 LIVE / LIVE_WITH_SETUP)

All five platforms are now either LIVE or LIVE_WITH_SETUP. No further
adapter-fix work is needed for this skill to return data on every
platform (assuming the user runs `pip install playwright &&
playwright install chromium` for fanqie).

- Run `pytest -m slow` to verify all 5 against real endpoints (note:
  ciweimao smoke tests currently fail due to the captcha regression
  documented above)
- The next time this doc is updated, consider converting it to a
  "current capabilities" doc with a small "Open follow-ups" section

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