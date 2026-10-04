# Vendored subset of worldwonderer/oh-story-claudecode

## Source

- Repo: https://github.com/worldwonderer/oh-story-claudecode
- File: `skills/story-long-scan/scripts/ciweimao-rank-scraper.js`
- License: MIT (see upstream LICENSE)
- Vendored: 2026-08-16
- Upstream SHAs:
  - `ciweimao-rank-scraper.js`: `6af052974fd86fbdbbafce3e363d643221c6ce27`
  - `cdp-utils.js`: same commit (`6af052974fd86fbdbbafce3e363d643221c6ce27`)

## What we vendor

Two files (both from `skills/story-long-scan/scripts/`):

- `ciweimao-rank-scraper.js` — the Node.js scraper that uses Chrome DevTools
  Protocol to bypass ciweimao.com's man-machine verify captcha and scrape
  rank pages into Markdown files.
- `cdp-utils.js` — the scraper's only Node dependency. Provides `ab()`,
  `sleep()`, `evalJSONBase64()`, `scrollLoad()`, `getArg()`, `localDateStamp()`,
  `runCli()` and the Windows `agent-browser` shim resolution. Required
  because `require("./cdp-utils")` on line 20 of the scraper otherwise fails
  with `MODULE_NOT_FOUND` at the very first `node` invocation, masking any
  real Chrome/CDP error. cdp-utils.js itself only requires Node built-ins
  (`child_process`, `fs`, `path`) — no further chained dependencies.

We do NOT vendor:
- Other scrapers in the upstream repo (qidian/fanqie/qimao/jjwxc) — we have
  our own implementations for those

## Why vendor

ciweimao.com's anti-bot (307 redirect to `/signup/man_machine_verify`) blocks
all headless HTTP requests as of 2026-08-13. The only known working bypass
(verified 2026-08-16) is real-browser automation via CDP. The worldwonderer
scraper is MIT-licensed, well-maintained (last push 2026-08-14), and has
17+ mirrors — high confidence in stability.

## How we use it

`scripts/adapters/ciweimao.py::CiweimaoAdapter.fetch()` calls
`scripts/adapters/ciweimao_runner.py::run_scraper(rank_type, output_dir)`
which shells out to `node <JS_SCRAPER_PATH> --type X --outdir Y --port Z`.
The scraper writes `刺猬猫{X}_YYYYMMDD.md` to output_dir; we then parse
that file via `parse_rank_markdown()` into RawBook objects.

> Note: actual CLI flags are `--type` / `--outdir` / `--port` (verified by
> reading the upstream source), not `--rank-type` / `--output-dir` as the
> original parser-stub assumed. Task 9 must adapt the runner accordingly.

## Refresh policy

Re-vendor when upstream ships a fix we need (run `gh api` for SHA, manual
review, copy). Auto-update is NOT enabled — we want explicit review of
upstream changes.

## License

Upstream is MIT. The full upstream MIT LICENSE text is included in this
directory as `LICENSE` (sibling of this README, also fetched from
`https://raw.githubusercontent.com/worldwonderer/oh-story-claudecode/main/LICENSE`
on 2026-08-16). Both vendored JS files retain their original MIT license
terms per upstream. See also
https://github.com/worldwonderer/oh-story-claudecode/blob/main/LICENSE