# Known Limitations (v0.1.4)

Last updated: 2026-08-13

Each platform adapter is explicitly marked with `status`:
- **LIVE**: works against real upstream today
- **LIVE_WITH_SETUP**: works after user installs Playwright/chromium
- **BLOCKED_EXTERNAL**: external blocker (anti-bot / dead endpoint) — needs upstream-side fix
- **BLOCKED_IMPLEMENTATION**: needs code work — clearly documented next steps

## Platform status (verified 2026-08-13)

| Platform | Status | Why | Enable path |
|----------|--------|-----|-------------|
| **ciweimao** (刺猬猫) | 🔴 BLOCKED_EXTERNAL | Captcha 307 (man-machine verify) added 2026-08-13 — `/book_list/*` now redirects to `/signup/man_machine_verify` even minutes after a first success | v0.2: Playwright + hCaptcha solver, or alternative endpoint |
| **fanqie** (番茄) | 🔴 BLOCKED_IMPLEMENTATION | Even with Playwright installed, vendored `run_scraper` is a site-wide JSON dump that doesn't match our per-(category, period, top) signature — needs a thin adapter over `run_scraper` | v0.2: read dump file (vendor/fanqie_rank_tracker/data/fanqie_all_ranks_YYYYMMDD.json) and slice by category |
| **qimao** (七猫) | LIVE | Vendored regex rewrite fixed (v0.1.2); shared Nuxt SSR parser in `scripts/nuxt_parser.py` | n/a |
| **qidian** (起点) | LIVE | Mobile-subdomain bypass — `https://m.qidian.com/rank` and `/category/catid<id>` return server-rendered HTML with the iPhone Safari User-Agent (no probe.js) | n/a |
| **zongheng** (纵横) | LIVE | Nuxt SSR scraping — `/rank?nav=new-book&rankType=4` returns 200 with `window.__NUXT__` payload containing all 6 rank lists; uses shared parser | n/a |

3/5 platforms are LIVE. 2/5 are blocked (1 external, 1 implementation).

## Test counts (verified 2026-08-13)

- Fast tests (default, `pytest tests/`): 89 — all pass; no skips
- Slow tests (`pytest -m slow`): 10 — 8 pass (qidian ×3, qimao ×2, zongheng ×3), 2 skipped (ciweimao captcha-regression HTTP smoke tests; @pytest.mark.skip)
- Total: 99

Skipped at runtime by `addopts = "-m 'not slow'"` in `pyproject.toml`. Run
slow tests explicitly with `pytest -m slow` once you have network access
and want to verify the LIVE adapters.

## v0.1.4 changelog (2026-08-13)

### Critical fixes (adversarial review v0.1.3 -> v0.1.4)

- **C1: ciweimao relabeled LIVE -> BLOCKED_EXTERNAL.** Live re-verification
  on 2026-08-13 (4 minutes after a first success) showed ciweimao.com
  now gates `/book_list/*` with a 307 redirect to
  `/signup/man_machine_verify`. The adapter is preserved (parser intact)
  but the orchestrator short-circuits and records an actionable
  AdapterError instead of running `fetch()` into a captcha wall. Live
  tests marked `@pytest.mark.skip` so CI doesn't fail.
- **C2: `scripts/adapters/qidian_cookies.py` + `tests/test_qidian_cookies.py`
  deleted.** The vendored
  `vendor/novel-downloader/qidian_subset/searcher.py` contains the
  RC4 cookie helper as the single source of truth — the local port
  was dead code (does not bypass modern probe.js, verified 2026-08-13).
  `qidian.py` docstring updated to point readers at the vendored path
  for traceability.
- **C3: fanqie relabeled LIVE_WITH_SETUP -> BLOCKED_IMPLEMENTATION.**
  The vendored `run_scraper` is site-wide and `fetch()` raises
  `RuntimeError` even with Playwright installed — that is a code-side
  gap, not a one-time setup issue. v0.2 work item: thin adapter over
  `run_scraper`.

### Important fixes

- **I1: `scripts/nuxt_parser.py` extracted.** Shared between qimao +
  zongheng (was duplicated verbatim in both adapters). Public API:
  `scan_balanced`, `split_top_level_csv`, `parse_nuxt_payload`. Tests
  moved to `tests/test_nuxt_parser.py`.
- **I2: qidian --top truncation documented.** See "Known data gaps"
  below.
- **I3: qimao word_count gap documented.** See below.
- **I4: zongheng intro empty gap documented.** See below.
- **I5: honest test counts.** See "Test counts" above. No more
  unverified "X + Y = Z" claims.

## Known Data Gaps

| Platform | Field | Why | Fix path |
|----------|-------|-----|----------|
| qidian | `--top > 5` returns ≤5 per period | m.qidian.com rank page caps at 5 books per tab, no pagination visible in the server-rendered HTML | Use desktop site (blocked by probe.js) OR aggregate 9 tabs (45 books max, may duplicate across tabs) |
| qimao | `word_count` always null | Upstream Nuxt SSR `number` field is reader_count, not word_count | v0.2: detail-page fetch or alternative API |
| zongheng | `intro` always empty | Rank payload's `description` field is empty (site fills it on detail page) | v0.2: detail-page fetch for each book |
| ciweimao | `status` often null | Table row doesn't include 完结/连载 label (only update date) | v0.2: detail-page fetch (after captcha bypass) |

## v0.1.3 changelog (carried forward for reference)

### Fix: qidian (起点) — mobile-subdomain bypass

The runtime bypass that DOES work is using the **mobile subdomain**
(`m.qidian.com`) with an iPhone Safari User-Agent. Mobile pages are
server-rendered (the body contains the rank/category HTML, not just a
Vue mount point) and don't trigger probe.js.

The vendored upstream `vendor/novel-downloader/qidian_subset/searcher.py`
contains an RC4 cookie construction (`_calc_cookies`) attempt, but
verified 2026-08-13 that it does NOT bypass modern probe.js. Runtime
bypass is `m.qidian.com` (see `scripts/adapters/qidian.py`).

v0.1.4 deleted the local `qidian_cookies.py` port as dead code. The
vendored `vendor/novel-downloader/qidian_subset/searcher.py` is now the
single source of truth for the RC4 helper if it is ever re-needed.

### Fix: zongheng (纵横) — Nuxt SSR scraping

The previously assumed JSON API `https://www.zongheng.com/api/rank/details`
returns HTTP 404. The site itself returns 200 with a Nuxt SSR payload
embedded as `window.__NUXT__`, containing all rank lists
(`monthTicketRankList`, `newBookRankList`, `popularRankList`,
`clickRankList`, `recommendRankList`, `newOrderRankList`) under
`state.rank.popularityRank`.

v0.1.4 extracts the shared balanced-brace + identifier-substitution
Nuxt parser to `scripts/nuxt_parser.py` (was duplicated in
`scripts/adapters/qimao.py` and `scripts/adapters/zongheng.py`).

### New tests (v0.1.3, since modified in v0.1.4)

- `tests/test_qidian_cookies.py` — DELETED in v0.1.4 (was dead code).
- `tests/test_qidian_adapter.py` — parser unit tests against real
  captured HTML fixtures. Still present.
- `tests/test_qidian_live.py` — 3 `@pytest.mark.slow` HTTP smoke tests
  against `m.qidian.com`. Still present.
- `tests/test_zongheng_adapter.py` — parser unit tests against the real
  captured HTML fixture. v0.1.4 trimmed to integration-only tests
  (low-level parser tests moved to `tests/test_nuxt_parser.py`).
- `tests/test_zongheng_live.py` — 3 `@pytest.mark.slow` HTTP smoke
  tests against `zongheng.com/rank`. Still present.
- `tests/test_nuxt_parser.py` (v0.1.4 NEW) — 15 unit tests for the
  shared Nuxt SSR parser (`scan_balanced`, `split_top_level_csv`,
  `parse_nuxt_payload`). Covers string-aware brace scanning, escape
  sequences, bare-key quoting, identifier substitution boundaries.
- `tests/test_ciweimao_live.py` (v0.1.4 MODIFIED) — 1 fast metadata
  test + 2 slow HTTP smoke tests. The slow tests are marked
  `@pytest.mark.skip` after the 2026-08-13 captcha 307 regression;
  the metadata test asserts `status == BLOCKED_EXTERNAL` so a future
  regression that flips the label back to LIVE would fail CI.

## What "BLOCKED_EXTERNAL" / "BLOCKED_IMPLEMENTATION" means

These adapters raise `NotImplementedError` immediately in `fetch()`.
The orchestrator records an `AdapterError` with a human-readable
explanation. User sees clear messages in `chart-scan/books.json`
errors[] and `chart-scan/report.md` 失败记录 section.

## After v0.1.4 (3/5 LIVE)

Three platforms return real data today (qidian, qimao, zongheng).
Two are blocked: ciweimao (external captcha, v0.2 needs Playwright +
hCaptcha solver) and fanqie (implementation gap, v0.2 needs a thin
adapter over the vendored site-wide crawl).

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
   `tests/test_qimao_live.py` or `tests/test_zongheng_live.py`).