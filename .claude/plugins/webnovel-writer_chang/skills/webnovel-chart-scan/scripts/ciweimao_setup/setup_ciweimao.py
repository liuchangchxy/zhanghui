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


def check_chrome_running(port: int) -> bool:
    """Probe whether Chrome is listening on the CDP port.

    Returns True if the CDP /json/version endpoint responds 2xx AND its body
    contains a "Browser" field (verifies it's actually Chrome, not e.g.
    another HTTP server that happened to bind to that port).

    Returns False on connection refused, timeout, non-2xx, or missing
    Browser field. Never raises.
    """
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            if resp.status != 200:
                return False
            body = resp.read().decode("utf-8", errors="replace")
            return '"Browser"' in body
    except Exception:
        return False


def check_agent_browser() -> bool:
    """Return True if `agent-browser` is on PATH."""
    return shutil.which("agent-browser") is not None


def install_agent_browser() -> None:
    """Run `npm install -g agent-browser` (120s timeout).

    Raises RuntimeError with actionable message on any failure mode
    (npm missing, EACCES, network error, timeout).
    """
    cmd = ["npm", "install", "-g", "agent-browser"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "找不到 npm 可执行文件。请安装 Node.js ≥18（brew install node 或 "
            "https://nodejs.org），它会附带 npm。"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            "npm install -g agent-browser 超时（120s）。请检查网络或手动运行："
            "sudo npm install -g agent-browser"
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"npm install -g agent-browser 失败（exit {result.returncode}）。\n"
            f"stderr: {result.stderr[:300]}\n"
            "请手动运行 `sudo npm install -g agent-browser` 并重试。"
        )


def launch_chrome(port: int, user_data_dir: Path) -> subprocess.Popen:
    """Start Chrome in the background with CDP enabled.

    Returns the Popen handle. The process is detached via start_new_session
    so it survives the setup script's exit. Caller is responsible for
    eventual cleanup (the user can `pkill -f "remote-debugging-port=9222"`).

    The Chrome binary is resolved via find_chrome_binary() — caller should
    have already checked the binary exists.
    """
    binary = find_chrome_binary()
    cmd = [
        str(binary),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--headless=new",
        "about:blank",  # opens a tab so CDP /json/version responds immediately
    ]
    user_data_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
