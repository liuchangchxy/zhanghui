# Known Limitations (v0.2.1)

Last updated: 2026-08-16

Each platform adapter is explicitly marked with `status`:
- **LIVE**: works against real upstream today
- **LIVE_WITH_SETUP**: works after user installs Playwright/chromium
- **BLOCKED_EXTERNAL**: external blocker (anti-bot / dead endpoint) — needs upstream-side fix
- **BLOCKED_IMPLEMENTATION**: needs code work — clearly documented next steps

## Platform status (verified 2026-08-16)

| Platform | Status | Why | Enable path |
|----------|--------|-----|-------------|
| **ciweimao** (刺猬猫) | 🟡 LIVE_WITH_SETUP | Vendored worldwonderer/oh-story-claudecode (MIT) Node scraper uses CDP to bypass captcha. Needs Node.js ≥18 + Chrome accessible via agent-browser | Setup: `brew install node` + install agent-browser. See `vendor/worldwonderer_subset/README.md` |
| **fanqie** (番茄) | 🟡 LIVE_WITH_SETUP | Fetches pre-built daily dump from FanqieRankTracker's GitHub raw (74 categories × 20 books, ~2MB). No Playwright needed. 1-day data lag. | Setup: ensure outbound HTTPS to raw.githubusercontent.com works. Cache at `~/.cache/webnovel-chart-scan/` |
| **qimao** (七猫) | LIVE | Vendored regex rewrite fixed (v0.1.2); shared Nuxt SSR parser in `scripts/nuxt_parser.py` | n/a |
| **qidian** (起点) | LIVE | Mobile-subdomain bypass — `https://m.qidian.com/rank` and `/category/catid<id>` return server-rendered HTML with the iPhone Safari User-Agent (no probe.js) | n/a |
| **zongheng** (纵横) | LIVE | Nuxt SSR scraping — `/rank?nav=new-book&rankType=4` returns 200 with `window.__NUXT__` payload containing all 6 rank lists; uses shared parser | n/a |

3/5 platforms are LIVE. 2/5 are LIVE_WITH_SETUP.

## Test counts (verified 2026-08-16)

- Fast tests (default, `pytest tests/`): 108 — all pass; no skips
- Slow tests (`pytest -m slow`): 13 — 11 pass (qidian ×3, qimao ×2, zongheng ×3, ciweimao_runner_integration ×3), 2 skipped (ciweimao captcha-regression HTTP smoke tests; @pytest.mark.skip)
- Total: 121

Skipped at runtime by `addopts = "-m 'not slow'"` in `pyproject.toml`. Run
slow tests explicitly with `pytest -m slow` once you have network access
and want to verify the LIVE adapters.

## v0.2.1 patch (2026-08-16)

Hotfixes from the v0.2.0 final code review (adversarial pass). Two
critical bugs that prevented the ciweimao adapter from actually working
end-to-end, despite the `LIVE_WITH_SETUP` label:

- **C1: parser regex didn't match the real JS output format.**
  `scripts/adapters/ciweimao_runner.py::_BOOK_HEADER_RE` expected
  `^##\s+(\d+)\.\s+《([^》]+)》\s*$` (h2 heading with `《》` wrappers and
  a period after the rank number) — but the vendored
  `ciweimao-rank-scraper.js` actually emits `### #N {title}` (h3, hash
  prefix, no 《》). The hand-crafted fixture
  `tests/fixtures/ciweimao_rank_click.md` was synthesized against the
  regex, not against the JS, so the parser was tested in a closed loop
  that never matched reality. Fixed by:
  - Rewriting `_BOOK_HEADER_RE` to match `### #N {title}`
  - Replacing the per-field `"- key: value"` parser with three small
    regexes: `_BOOK_HEADER_RE` for the heading, `_META_LINE_RE` for
    `*author · metric*` (NO.1) / `*genre · metric*` (#2-10), and
    `_LINK_LINE_RE` for `[作品页]({url})`
  - Disambiguating author vs genre by rank (`rank==1` → author is the
    first meta part, genre is empty upstream; `rank>=2` → genre is the
    first meta part, author is empty upstream). Verified against the
    vendored JS source lines 73-86 (NO.1 / #2-10 extraction) and lines
    190-222 (Markdown formatting).
  - Regenerating `tests/fixtures/ciweimao_rank_click.md` to be a
    line-by-line match of what the vendored JS emits.
- **C2: missing vendored dependency `cdp-utils.js`.**
  `ciweimao-rank-scraper.js` line 20 requires `./cdp-utils` (helpers:
  `ab`, `sleep`, `evalJSONBase64`, `scrollLoad`, `getArg`,
  `localDateStamp`, `runCli`). v0.2.0 vendored only the scraper and
  documented cdp-utils as "caller's responsibility" — but our caller
  IS the vendored scraper itself, so the very first `node` invocation
  died with `Error: Cannot find module './cdp-utils'`, masking the
  real "Chrome isn't running" error. Fixed by vendoring cdp-utils.js
  (8564 bytes, upstream commit `6af052974fd86fbdbbafce3e363d643221c6ce27`,
  same as the scraper) and noting in
  `vendor/worldwonderer_subset/README.md` that it's required, not
  optional. cdp-utils.js requires only Node built-ins (`child_process`,
  `fs`, `path`) — no further chained dependencies to vendor.

After these fixes, `node ciweimao-rank-scraper.js --type click --port 9222`
fails with a clean "agent-browser failed: CDP discovery failed for
127.0.0.1:9222" instead of MODULE_NOT_FOUND, and the parser correctly
extracts books from the JS output.

### New file
- `tests/test_ciweimao_runner_integration.py` — 3 `@pytest.mark.slow`
  tests that actually invoke the vendored JS via Node.js:
  `test_vendored_cdp_utils_exists` (regression guard for C2),
  `test_scraper_does_not_fail_with_module_not_found` (asserts no
  `Cannot find module` in output), `test_scraper_accepts_known_cli_args`
  (asserts `--type` / `--outdir` / `--port` parse without TypeError).

### Test count change
- v0.2.0: 104 fast + 10 slow = 114 total
- v0.2.1: 108 fast + 13 slow = 121 total
- +4 fast tests (split NO.1 vs rank-2 fixtures, native category
  normalization, missing metric, missing link line)
- +3 slow tests (integration test for vendored JS invocation)

## v0.2.0 changelog (2026-08-16)

### Platform upgrades
- **fanqie: BLOCKED_IMPLEMENTATION → LIVE_WITH_SETUP.** Replaced Playwright-based `run_scraper` wrapper with direct fetch of upstream's pre-built daily dump from `raw.githubusercontent.com/Despacito0o/FanqieRankTracker/master/data/fanqie_all_ranks_YYYYMMDD.json`. No Chromium, no batch blocking. New subcategory→normalized mapping (`scripts/adapters/fanqie_subcat_map.py`) covers all 34 fanqie subcategories.
- **ciweimao: BLOCKED_EXTERNAL → LIVE_WITH_SETUP.** Vendored `worldwonderer/oh-story-claudecode` `ciweimao-rank-scraper.js` (MIT, 5600★) — uses Chrome DevTools Protocol to bypass the 307 captcha. Python shells out to Node.js + the JS, parses Markdown output via `scripts/adapters/ciweimao_runner.py`. New category mapping (`scripts/adapters/ciweimao_cat_map.py`) handles native→normalized conversion.
- **Strategy enum:** Added `Strategy.DIRECT_DUMP` for adapters that fetch pre-built upstream data (vs scraping).

### New files
- `scripts/adapters/fanqie_subcat_map.py` — fanqie native subcategory → normalized category mapping (34 entries)
- `scripts/adapters/ciweimao_cat_map.py` — ciweimao native category → normalized category mapping (~24 entries)
- `scripts/adapters/ciweimao_runner.py` — Markdown parser + Node subprocess wrapper
- `vendor/worldwonderer_subset/ciweimao-rank-scraper.js` — vendored upstream (MIT)
- `vendor/worldwonderer_subset/cdp-utils.js` — vendored upstream (MIT), required dependency of the scraper
- `vendor/worldwonderer_subset/README.md` — attribution + how-to-use
- `tests/fixtures/ciweimao_rank_click.md` — sample Markdown output for parser tests
- `tests/fixtures/fanqie_dump_20260815.json` — sample dump for parser tests (already added 2026-08-16)
- `tests/test_fanqie_subcat_map.py` — subcategory mapping tests (6 tests)
- `tests/test_ciweimao_runner.py` — Markdown parser tests (4 tests)

### Test count change
- v0.1.4: 89 fast + 10 slow = 99 total
- v0.2.0: 104 fast + 10 slow = 114 total
- +15 fast tests (6 fanqie_subcat_map + 4 ciweimao_runner + 1 fanqie_status + 4 ciweimao_adapter rewrite)

5/5 platforms now LIVE or LIVE_WITH_SETUP.

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