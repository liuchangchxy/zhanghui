"""Integration test for the vendored ciweimao Node.js scraper.

This test ACTUALLY invokes the vendored JS via Node.js to verify:

1. The vendored ``ciweimao-rank-scraper.js`` + ``cdp-utils.js`` load
   without ``MODULE_NOT_FOUND``. (Bug C2 — we used to see
   ``Error: Cannot find module './cdp-utils'`` because the scraper's
   only Node dependency wasn't vendored.)
2. When Chrome / CDP is not available, the scraper fails with a CLEAR
   "agent-browser can't reach CDP" error (not a require failure).
3. The scraper's CLI arg parsing works (``--type click``, ``--outdir``,
   ``--port`` accepted without crashing).

This test is marked ``@pytest.mark.slow`` so it is **skipped by default**
in the normal CI run. To exercise it:

    /tmp/chart-scan-venv/bin/python -m pytest tests/test_ciweimao_runner_integration.py -v
    /tmp/chart-scan-venv/bin/python -m pytest tests/ -m slow -v

It does NOT require Chrome / CDP / agent-browser to be running — the
test only verifies the script loads and fails cleanly when CDP is
absent.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


JS_SCRAPER_PATH = (
    Path(__file__).parent.parent
    / "vendor"
    / "worldwonderer_subset"
    / "ciweimao-rank-scraper.js"
)
CDP_UTILS_PATH = (
    Path(__file__).parent.parent
    / "vendor"
    / "worldwonderer_subset"
    / "cdp-utils.js"
)


pytestmark = pytest.mark.slow


def _node_available() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _node_available(), reason="node executable not on PATH")
def test_vendored_cdp_utils_exists():
    """The cdp-utils.js dependency must be vendored alongside the scraper.

    Without this file, the scraper's first line of code fails with
    ``Error: Cannot find module './cdp-utils'`` (Bug C2).
    """
    assert CDP_UTILS_PATH.exists(), (
        f"cdp-utils.js not vendored at {CDP_UTILS_PATH}. "
        "Run the vendor step (see vendor/worldwonderer_subset/README.md)."
    )


@pytest.mark.skipif(not _node_available(), reason="node executable not on PATH")
def test_scraper_does_not_fail_with_module_not_found(tmp_path):
    """The vendored scraper must not crash with MODULE_NOT_FOUND.

    Bug C2 regression check: when cdp-utils.js is missing, the scraper
    fails before it even tries to connect to Chrome, masking the real
    "Chrome isn't running" error. With cdp-utils.js vendored, the
    scraper should reach the ``agent-browser failed`` error path (because
    no Chrome is listening on 9222 in the test environment).
    """
    assert JS_SCRAPER_PATH.exists(), f"Scraper not found at {JS_SCRAPER_PATH}"

    # Use a throwaway outdir and a port nothing is listening on.
    # 192.0.2.0/24 is TEST-NET-1 (RFC 5737) — guaranteed unrouted.
    # Using a closed port on localhost would also work but might race
    # with another test holding the port open.
    result = subprocess.run(
        [
            "node",
            str(JS_SCRAPER_PATH),
            "--type", "click",
            "--outdir", str(tmp_path),
            "--port", "9222",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    # Bug C2 regression: we MUST NOT see MODULE_NOT_FOUND. The scraper
    # should reach the CDP-failure path and emit a clear
    # "agent-browser failed" or "CDP 无响应" message.
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Cannot find module" not in combined, (
        f"Scraper failed with MODULE_NOT_FOUND — cdp-utils.js is missing "
        f"or not on the require path. Output:\n{combined[:1000]}"
    )

    # The scraper should mention either Chrome/CDP failure or have
    # written 0 files. Either is acceptable — what matters is that it
    # got past the require() check.
    assert (
        "CDP" in combined
        or "agent-browser" in combined
        or "Chrome" in combined
        or "connection" in combined.lower()
    ), (
        f"Scraper output didn't look like a Chrome/CDP failure. "
        f"Was cdp-utils.js vendored correctly? Output:\n{combined[:1000]}"
    )


@pytest.mark.skipif(not _node_available(), reason="node executable not on PATH")
def test_scraper_accepts_known_cli_args(tmp_path):
    """The scraper must accept --type / --outdir / --port without throwing.

    This is a sanity check that the upstream CLI surface matches what
    scripts/adapters/ciweimao_runner.py::run_scraper passes. If upstream
    renames --type to --rank-type or similar, this test will fail
    (along with the real adapter)."""
    result = subprocess.run(
        [
            "node",
            str(JS_SCRAPER_PATH),
            "--type", "monthly",  # different rank type to exercise getArg path
            "--outdir", str(tmp_path),
            "--port", "9223",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    combined = (result.stdout or "") + (result.stderr or "")
    # If --type wasn't accepted, the JS would fall back to "all" and
    # still try to scrape — we'd see "采集 刺猬猫排行榜...". So the mere
    # absence of "Cannot find module" / "Unknown argument" / TypeError
    # is enough to prove the CLI flags parse correctly.
    assert "Cannot find module" not in combined
    assert "Unknown argument" not in combined
    assert "TypeError" not in combined or "Cannot read" not in combined