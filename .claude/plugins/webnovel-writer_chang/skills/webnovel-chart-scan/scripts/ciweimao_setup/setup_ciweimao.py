"""ciweimao CDP setup automation.

Provides:
- check_agent_browser / install_agent_browser
- check_chrome_running / launch_chrome / verify_cdp_ready
- find_chrome_binary
- setup_ciweimao (orchestrator)

Can be invoked as a CLI: ``python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao [--port 9222]``
or programmatically via setup_ciweimao.setup_ciweimao(port).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Optional


# Default CDP port. Can be overridden via WEBNOVEL_CIWEIMAO_CDP_PORT env var.
DEFAULT_CDP_PORT = 9222

# Where Chrome's user-data-dir lives. Survives across setup() invocations so
# the user's profile (cookies, etc.) is preserved.
def _chrome_user_data_dir() -> Path:
    """Resolve Chrome user-data-dir, mirroring install_python_deps.resolve_cache_dir."""
    cache = Path(os.environ.get("WEBNOVEL_CACHE_DIR") or (Path.home() / ".cache" / "webnovel-writer-chang"))
    cache.mkdir(parents=True, exist_ok=True)
    return cache / "ciweimao-chrome"


def find_chrome_binary() -> Path:
    """Locate a Chrome binary using a 5-level priority chain.

    Returns the path to the binary. Raises RuntimeError if none found.
    """
    # 1. macOS system Chrome
    if sys.platform == "darwin":
        mac_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if mac_chrome.exists():
            return mac_chrome
    # 2. Linux google-chrome
    # 3. Linux chrome (alt name)
    for name in ("google-chrome", "chrome"):
        found = shutil.which(name)
        if found:
            return Path(found)
    # 4. playwright-installed Chromium (mac)
    if sys.platform == "darwin":
        playwright_dir = Path.home() / "Library" / "Caches" / "ms-playwright"
        for chromium_dir in sorted(playwright_dir.glob("chromium-*"), reverse=True):
            candidate = (
                chromium_dir / "chrome-mac" / "Chromium.app"
                / "Contents" / "MacOS" / "Chromium"
            )
            if candidate.exists():
                return candidate
    # 5. Not found
    raise RuntimeError(
        "找不到 Chrome 二进制。请安装 Google Chrome（macOS：brew install --cask google-chrome；"
        "Linux：apt install google-chrome-stable）或运行 `playwright install chromium` 后重试。"
    )
