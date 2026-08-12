# Known Limitations (v0.1.x)

Last updated: 2026-08-13

Each platform adapter is explicitly marked with a `status` field on the
adapter class. There are three possible values:

- **LIVE** — works against real upstream today
- **BLOCKED_EXTERNAL** — external blocker (anti-bot / dead endpoint /
  license) — needs upstream-side or infra-side work, cannot be fixed in
  this repo alone
- **BLOCKED_IMPLEMENTATION** — needs code work in this repo —
  documented next steps below

## Platform status (verified 2026-08-13)

| Platform | Status | Why | Fix path |
|----------|--------|-----|----------|
| **ciweimao** (刺猬猫) | LIVE | httpx + BS4 against real HTML works | n/a |
| **fanqie** (番茄) | BLOCKED_IMPLEMENTATION | Needs Playwright + chromium install | `pip install playwright && playwright install chromium` |
| **qidian** (起点) | BLOCKED_EXTERNAL | probe.js + RC4 cookie required | Port RC4 cookie computation from `vendor/novel-downloader/qidian_subset/searcher.py:_calc_cookies` (v0.2) |
| **qimao** (七猫) | BLOCKED_IMPLEMENTATION | Vendored regex `_NUXT_RE` fails on real payload (nested braces); also had a silent `except Exception: return items` swallow | Replace with balanced-brace scanner (similar to existing `_split_top_level_csv` helper) (v0.2) |
| **zongheng** (纵横) | BLOCKED_EXTERNAL | Public API endpoint returns HTTP 404 | Find new endpoint or implement Nuxt SSR scraping fallback (v0.2) |

## What "BLOCKED" means

Blocked adapters:

- Raise `NotImplementedError` immediately in `fetch()` — **no network
  attempt, no silent failure**. (Real adapters raise a tailored message
  pointing at this document; the `BaseAdapter` default is a generic
  fallback.)
- The orchestrator (`scripts.scan:run_scan`) checks
  `adapter.status != AdapterStatus.LIVE` *before* calling `fetch()` and
  records an `AdapterError` per `(platform, category, period)` with a
  human-readable explanation. The blocked adapter's `fetch()` body is
  dead code at runtime.
- User sees clear messages in `chart-scan/books.json` `errors[]` array
  and `chart-scan/report.md` `失败记录` section.
- No more silent 0-book results that look successful.

The orchestrator's exception-handling loop still catches any other
unexpected error (e.g. a transient network failure on a LIVE adapter)
and records it the same way.

## What "LIVE" means

LIVE adapters:

- Actually hit the network on `fetch()`.
- Test suite includes both unit tests (parser) and `@pytest.mark.slow`
  live HTTP smoke test.
- Run slow tests with: `pytest -m slow`
- Default `pytest` invocation skips slow tests via `addopts = "-m 'not
  slow'"` in `pyproject.toml`.

## v0.2 priorities

1. **fanqie**: Enable Playwright + chromium install path (just docs +
   setup script). Once installed, no code changes needed — vendored
   subset is already wired up.
2. **qidian**: Port RC4 cookie bypass from vendored subset
   (~100 LOC, from `qidian_subset/searcher.py:_calc_cookies`).
3. **qimao**: Rewrite `_NUXT_RE` as balanced-brace scanner (~50 LOC,
   similar to the existing `_split_top_level_csv` helper). **Must also
   remove the silent `except Exception: return items` branch** — that
   was the real reason the adapter looked successful while returning
   nothing.
4. **zongheng**: Research alternative endpoint OR switch to WebFetch +
   BS4 against `/rank?nav=new-book&rankType=4` (~100 LOC).

After v0.2: all 5 platforms should be LIVE.

## How to add a new adapter

If you add a 6th platform:

1. Subclass `BaseAdapter`.
2. Set `platform`, `strategy`, and `status` class attributes.
3. If `status` is anything other than `AdapterStatus.LIVE`, write a
   tailored `fetch()` body that raises `NotImplementedError` with a
   one-line summary of the blocker + a pointer to this document. (The
   body is dead code at runtime, but it surfaces in error messages.)
4. Add the adapter to `ALL_PLATFORMS` in `scripts/scan.py` and to the
   `_ensure_registry()` dict.
5. Add at least the `test_*_adapter_metadata` test (verify
   `platform` + `strategy` + `status`).
6. If LIVE, add parser unit tests + an `@pytest.mark.slow` HTTP smoke
   test (modeled on `tests/test_ciweimao_live.py`).