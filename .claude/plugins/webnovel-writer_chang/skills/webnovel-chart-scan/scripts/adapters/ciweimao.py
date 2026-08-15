"""刺猬猫 (ciweimao) adapter — vendored CDP scraper via Node.js subprocess.

Status: LIVE_WITH_SETUP (verified 2026-08-16 via Task 9 session start hook).

Required setup:
- Chrome browser listening on CDP port (default 9222)
- ``agent-browser`` on $PATH

To set up automatically:
    python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao

The setup script is idempotent and safe to re-run. If Chrome was killed,
the next scan will surface a humanized error message referencing the setup
command above.

Why Node.js subprocess instead of Python+Playwright:
- The vendored JS (worldwonderer/oh-story-claudecode, MIT) uses CDP via
  agent-browser to bypass ciweimao's man-machine captcha. Porting that to
  Python is 200+ lines of fragile browser automation. The JS is updated
  upstream frequently, so vendoring + shelling out beats maintaining a
  Python port. See docs/superpowers/specs/2026-08-16-ciweimao-setup-design.md
  for the full rationale and future-work scope.
"""
from __future__ import annotations

from pathlib import Path

from scripts.adapters.base import BaseAdapter, Strategy, AdapterStatus
from scripts.schema import RawBook


class CiweimaoAdapter(BaseAdapter):
    platform = "ciweimao"
    strategy = Strategy.WEBFETCH
    # v0.1.4: relabeled from LIVE to BLOCKED_EXTERNAL after live
    # re-verification on 2026-08-13 showed ciweimao.com now gates
    # /book_list/* with a 307 redirect to /signup/man_machine_verify
    # (a CAPTCHA page). The orchestrator short-circuited and recorded
    # an AdapterError instead of running fetch() into a captcha wall.
    # v0.2: relabeled from BLOCKED_EXTERNAL back to LIVE_WITH_SETUP after
    # vendoring worldwonderer/oh-story-claudecode (MIT) which uses CDP to
    # bypass the captcha. Requires: Node.js ≥18, Chrome browser accessible
    # via agent-browser or direct CDP, and `node` on PATH.
    status = AdapterStatus.LIVE_WITH_SETUP

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        """Fetch via vendored Node.js scraper (CDP-based, bypasses captcha).

        Flow:
        1. Map period → ciweimao rank TYPE (click / monthly)
        2. Shell out to node + vendored JS → writes .md file
        3. Parse .md → list[RawBook]
        4. Filter by category if not 'all' (the scraper returns ALL
           categories for the chosen rank type — we filter post-hoc)
        """
        from scripts.adapters.ciweimao_runner import (
            run_scraper, parse_rank_markdown, PERIOD_TO_RANK_TYPE,
        )

        rank_type = PERIOD_TO_RANK_TYPE.get(period, "click")
        # Write to a temp output dir under our cache
        output_dir = (
            Path.home() / ".cache" / "webnovel-chart-scan"
            / "ciweimao"
        )

        md_file = run_scraper(rank_type, output_dir)

        md_text = md_file.read_text(encoding="utf-8")
        books = parse_rank_markdown(md_text, top=max(top, 100))

        # If user asked for a specific category, filter (the JS scraper
        # returns ALL categories for the chosen rank type)
        if category != "all":
            books = [b for b in books if b.category == category][:top]

        return books
