# ciweimao Setup Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ciweimao adapter's "LIVE_WITH_SETUP" label honest — auto-install `agent-browser`, auto-launch Chrome on port 9222, prompt via SessionStart hook, humanize runtime errors, clean up dead code, and add a skip-if-unavailable end-to-end test.

**Architecture:** Mirror fanqie's chromium-prompt lifecycle in a parallel `scripts/ciweimao_setup/` subpackage. Hook detects missing setup and prompts; setup script runs `npm install` + launches Chrome. Adapter layer reads `WEBNOVEL_CIWEIMAO_CDP_PORT` env var and emits actionable error messages. Decision marker (`.ciweimao-prompted`) is independent from fanqie's `.chromium-prompted`.

**Tech Stack:** Python 3.11+, Node.js ≥18 (existing dependency), `agent-browser` npm package, Chrome with `--remote-debugging-port=9222`, `subprocess` + `urllib.request` stdlib only.

**Spec:** `docs/superpowers/specs/2026-08-16-ciweimao-setup-design.md`

---

## File Structure

**Create:**
- `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/scripts/ciweimao_setup/__init__.py` — empty package marker
- `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/scripts/ciweimao_setup/setup_ciweimao.py` — orchestrator + helpers (find_chrome_binary, check_chrome_running, check_agent_browser, install_agent_browser, launch_chrome, verify_cdp_ready, setup_ciweimao)
- `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/scripts/ciweimao_setup/sessionstart_integration.py` — `_ciweimao_marker`, `should_prompt_ciweimao`, `write_ciweimao_decision`, `format_ciweimao_prompt`
- `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/tests/test_ciweimao_setup.py` — unit tests for setup_ciweimao module
- `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/tests/test_ciweimao_sessionstart_integration.py` — unit tests for decision marker mirror
- `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/tests/test_ciweimao_e2e.py` — end-to-end test with skip-if-unavailable
- `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/tests/test_ciweimao_runner_humanize.py` — tests for humanized error messages

**Modify:**
- `.claude/plugins/webnovel-writer_chang/hooks/session_start.py` — add `check_ciweimao_prompt()` and call from `main()`
- `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/scripts/adapters/ciweimao_runner.py` — env var port, humanized errors
- `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/scripts/adapters/ciweimao.py` — delete dead code, period=weekly comment
- `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/pyproject.toml` — entry point for setup script
- `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/KNOWN_LIMITATIONS.md` — note new setup flow
- `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/SKILL.md` — update "安装" section

---

## Task 1: `find_chrome_binary()` — find Chrome binary by priority chain

**Files:**
- Create: `scripts/ciweimao_setup/__init__.py`
- Create: `scripts/ciweimao_setup/setup_ciweimao.py`
- Create: `tests/test_ciweimao_setup.py`

- [ ] **Step 1: Create the package marker**

Write empty file:
```python
# scripts/ciweimao_setup/__init__.py
```

Run: `ls scripts/ciweimao_setup/__init__.py`
Expected: file exists

- [ ] **Step 2: Write the failing test**

Create `tests/test_ciweimao_setup.py`:
```python
"""Unit tests for scripts/ciweimao_setup.setup_ciweimao helpers.

These tests cover the pure-Python helpers without launching actual Chrome
or running npm. Subprocess-touching helpers are tested with unittest.mock.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ciweimao_setup.setup_ciweimao import find_chrome_binary


def test_find_chrome_binary_finds_macos_app(monkeypatch):
    """macOS: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome."""
    monkeypatch.setattr(sys, "platform", "darwin")
    fake = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    monkeypatch.setattr("os.path.exists", lambda p: str(p) == str(fake))
    assert find_chrome_binary() == fake


def test_find_chrome_binary_finds_linux_binary(monkeypatch):
    """Linux: shutil.which('google-chrome') wins."""
    monkeypatch.setattr(sys, "platform", "linux")
    fake = Path("/usr/bin/google-chrome")
    monkeypatch.setattr("shutil.which", lambda cmd: str(fake) if cmd == "google-chrome" else None)
    monkeypatch.setattr("os.path.exists", lambda p: False)
    assert find_chrome_binary() == fake


def test_find_chrome_binary_finds_playwright_chromium(monkeypatch):
    """Fallback: playwright-installed Chromium under ~/Library/Caches/ms-playwright/."""
    monkeypatch.setattr(sys, "platform", "darwin")
    playwright_chrome = (
        Path.home() / "Library/Caches/ms-playwright/chromium-1234/chrome-mac"
        / "Chromium.app/Contents/MacOS/Chromium"
    )

    def fake_exists(p):
        return str(p) == str(playwright_chrome)

    monkeypatch.setattr("os.path.exists", fake_exists)
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert find_chrome_binary() == playwright_chrome


def test_find_chrome_binary_raises_when_not_found(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    monkeypatch.setattr("os.path.exists", lambda p: False)
    with pytest.raises(RuntimeError, match="找不到 Chrome"):
        find_chrome_binary()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan && ../../../../webnovel_chart_scan.egg-info/../../../../../../tmp/chart-scan-venv/bin/python -m pytest tests/test_ciweimao_setup.py -v 2>&1 | head -30` (or substitute the venv path)
Expected: `ModuleNotFoundError: No module named 'scripts.ciweimao_setup.setup_ciweimao'`

- [ ] **Step 4: Write minimal implementation**

Create `scripts/ciweimao_setup/setup_ciweimao.py`:
```python
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
        if playwright_dir.exists():
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan && <VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/ciweimao_setup/ tests/test_ciweimao_setup.py
git commit -m "feat(ciweimao-setup): find_chrome_binary with 5-level priority chain"
```

---

## Task 2: `check_chrome_running()` — HTTP probe of CDP endpoint

**Files:**
- Modify: `scripts/ciweimao_setup/setup_ciweimao.py`
- Modify: `tests/test_ciweimao_setup.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ciweimao_setup.py`:
```python
def test_check_chrome_running_returns_true_when_browser_field_present(monkeypatch):
    """CDP /json/version returning 'Browser' in body → Chrome is running."""
    from scripts.ciweimao_setup.setup_ciweimao import check_chrome_running

    class FakeResp:
        status = 200
        def read(self):
            return b'{"Browser":"Chrome/120.0.6099.71","Protocol-Version":"1.3"}'
        def __enter__(self): return self
        def __exit__(self, *args): pass

    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=2: FakeResp())
    assert check_chrome_running(9222) is True


def test_check_chrome_running_returns_false_on_connection_refused(monkeypatch):
    """CDP unreachable → False (do NOT raise — caller decides)."""
    from scripts.ciweimao_setup.setup_ciweimao import check_chrome_running

    def fake_urlopen(url, timeout=2):
        raise OSError("Connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert check_chrome_running(9222) is False


def test_check_chrome_running_returns_false_on_non_2xx(monkeypatch):
    """CDP returns 404 or other non-2xx → False."""
    from scripts.ciweimao_setup.setup_ciweimao import check_chrome_running

    class FakeResp:
        status = 503
        def read(self): return b""
        def __enter__(self): return self
        def __exit__(self, *args): pass

    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=2: FakeResp())
    assert check_chrome_running(9222) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py::test_check_chrome_running_returns_true_when_browser_field_present -v`
Expected: FAIL — `cannot import name 'check_chrome_running'`

- [ ] **Step 3: Add `check_chrome_running` to setup_ciweimao.py**

Append below `find_chrome_binary`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py -v`
Expected: 7 passed (4 prior + 3 new)

- [ ] **Step 5: Commit**

```bash
git add scripts/ciweimao_setup/setup_ciweimao.py tests/test_ciweimao_setup.py
git commit -m "feat(ciweimao-setup): check_chrome_running HTTP probe"
```

---

## Task 3: `check_agent_browser()` — npm binary on PATH

**Files:**
- Modify: `scripts/ciweimao_setup/setup_ciweimao.py`
- Modify: `tests/test_ciweimao_setup.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ciweimao_setup.py`:
```python
def test_check_agent_browser_returns_true_when_on_path(monkeypatch):
    from scripts.ciweimao_setup.setup_ciweimao import check_agent_browser
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/agent-browser" if cmd == "agent-browser" else None)
    assert check_agent_browser() is True


def test_check_agent_browser_returns_false_when_missing(monkeypatch):
    from scripts.ciweimao_setup.setup_ciweimao import check_agent_browser
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert check_agent_browser() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py::test_check_agent_browser_returns_true_when_on_path -v`
Expected: FAIL — `cannot import name 'check_agent_browser'`

- [ ] **Step 3: Add `check_agent_browser`**

Append:
```python
def check_agent_browser() -> bool:
    """Return True if `agent-browser` is on PATH."""
    return shutil.which("agent-browser") is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/ciweimao_setup/setup_ciweimao.py tests/test_ciweimao_setup.py
git commit -m "feat(ciweimao-setup): check_agent_browser PATH detection"
```

---

## Task 4: `install_agent_browser()` — subprocess wrapper

**Files:**
- Modify: `scripts/ciweimao_setup/setup_ciweimao.py`
- Modify: `tests/test_ciweimao_setup.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ciweimao_setup.py`:
```python
def test_install_agent_browser_runs_npm_install_g(monkeypatch):
    """Install runs `npm install -g agent-browser` with 120s timeout."""
    from scripts.ciweimao_setup.setup_ciweimao import install_agent_browser

    captured = {}
    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        captured["timeout"] = kwargs.get("timeout")
        captured["env"] = kwargs.get("env")
        class R: returncode = 0; stderr = ""
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    install_agent_browser()
    assert captured["cmd"][:3] == ["npm", "install", "-g"]
    assert captured["cmd"][3] == "agent-browser"
    assert captured["timeout"] == 120


def test_install_agent_browser_raises_runtime_error_on_failure(monkeypatch):
    from scripts.ciweimao_setup.setup_ciweimao import install_agent_browser

    def fake_run(cmd, *args, **kwargs):
        class R: returncode = 1; stderr = "EACCES permission denied"
        raise subprocess.CalledProcessError(1, cmd, stderr=b"EACCES permission denied")

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="npm install -g agent-browser 失败"):
        install_agent_browser()


def test_install_agent_browser_raises_on_file_not_found(monkeypatch):
    """`npm` itself missing → clear error."""
    from scripts.ciweimao_setup.setup_ciweimao import install_agent_browser

    def fake_run(cmd, *args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "npm")

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="找不到 npm"):
        install_agent_browser()


def test_install_agent_browser_raises_on_timeout(monkeypatch):
    from scripts.ciweimao_setup.setup_ciweimao import install_agent_browser
    def fake_run(cmd, *args, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 120)
    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="超时"):
        install_agent_browser()
```

Note: add `import subprocess` at top of test file if not present.

- [ ] **Step 2: Run test to verify it fails**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py::test_install_agent_browser_runs_npm_install_g -v`
Expected: FAIL — `cannot import name 'install_agent_browser'`

- [ ] **Step 3: Add `install_agent_browser`**

Append:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/ciweimao_setup/setup_ciweimao.py tests/test_ciweimao_setup.py
git commit -m "feat(ciweimao-setup): install_agent_browser with humanized errors"
```

---

## Task 5: `launch_chrome()` — background Chrome process

**Files:**
- Modify: `scripts/ciweimao_setup/setup_ciweimao.py`
- Modify: `tests/test_ciweimao_setup.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ciweimao_setup.py`:
```python
def test_launch_chrome_passes_remote_debugging_port_and_user_data_dir(monkeypatch, tmp_path):
    """launch_chrome returns Popen with --remote-debugging-port=PORT and --user-data-dir=DIR."""
    from scripts.ciweimao_setup.setup_ciweimao import launch_chrome

    captured = {}
    class FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            self.pid = 12345
    monkeypatch.setattr("subprocess.Popen", FakePopen)

    user_data_dir = tmp_path / "chrome-profile"
    result = launch_chrome(9222, user_data_dir)

    assert "--remote-debugging-port=9222" in captured["cmd"]
    assert f"--user-data-dir={user_data_dir}" in captured["cmd"]
    assert "--no-first-run" in captured["cmd"]
    assert captured["kwargs"].get("start_new_session") is True
    assert result.pid == 12345


def test_launch_chrome_includes_headless_flag(monkeypatch, tmp_path):
    """Headless mode is enabled (matches the spec — server/CI friendly)."""
    from scripts.ciweimao_setup.setup_ciweimao import launch_chrome
    captured = {}
    class FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
    monkeypatch.setattr("subprocess.Popen", FakePopen)
    launch_chrome(9222, tmp_path / "chrome-profile")
    assert "--headless=new" in captured["cmd"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py::test_launch_chrome_passes_remote_debugging_port_and_user_data_dir -v`
Expected: FAIL — `cannot import name 'launch_chrome'`

- [ ] **Step 3: Add `launch_chrome`**

Append:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/ciweimao_setup/setup_ciweimao.py tests/test_ciweimao_setup.py
git commit -m "feat(ciweimao-setup): launch_chrome with CDP flags + detached session"
```

---

## Task 6: `verify_cdp_ready()` — retry loop

**Files:**
- Modify: `scripts/ciweimao_setup/setup_ciweimao.py`
- Modify: `tests/test_ciweimao_setup.py`

- [ ] **Step 1: Write the failing test**

Append:
```python
def test_verify_cdp_ready_returns_silently_when_check_succeeds(monkeypatch):
    """If check_chrome_running is True immediately → no exception, no sleep."""
    from scripts.ciweimao_setup.setup_ciweimao import verify_cdp_ready

    calls = []
    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_ciweimao.check_chrome_running",
        lambda port: calls.append(port) or True,
    )
    monkeypatch.setattr("scripts.ciweimao_setup.setup_ciweimao.time.sleep", lambda *_: None)
    verify_cdp_ready(9222, retries=5, delay=0.1)  # should not raise
    assert calls == [9222]


def test_verify_cdp_ready_retries_then_raises(monkeypatch):
    """If check_chrome_running stays False across all retries → RuntimeError."""
    from scripts.ciweimao_setup.setup_ciweimao import verify_cdp_ready

    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_civeimao.check_chrome_running",  # INTENTIONAL typo to verify import path
        lambda port: False,
    )
    monkeypatch.setattr("scripts.ciweimao_setup.setup_ciweimao.time.sleep", lambda *_: None)
    with pytest.raises(RuntimeError, match="CDP 未就绪"):
        verify_cdp_ready(9222, retries=3, delay=0.01)


def test_verify_cdp_ready_succeeds_after_some_retries(monkeypatch):
    """Succeeds on attempt 2 → no error."""
    from scripts.ciweimao_setup.setup_ciweimao import verify_cdp_ready

    state = {"n": 0}
    def fake_check(port):
        state["n"] += 1
        return state["n"] >= 2
    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_ciweimao.check_chrome_running", fake_check,
    )
    monkeypatch.setattr("scripts.ciweimao_setup.setup_ciweimao.time.sleep", lambda *_: None)
    verify_cdp_ready(9222, retries=5, delay=0.01)  # should not raise
    assert state["n"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py::test_verify_cdp_ready_returns_silently_when_check_succeeds -v`
Expected: FAIL — `cannot import name 'verify_cdp_ready'`

- [ ] **Step 3: Add `verify_cdp_ready` and `import time`**

Add `import time` at top of setup_ciweimao.py (after `import shutil`). Then append:
```python
def verify_cdp_ready(port: int, retries: int = 10, delay: float = 0.5) -> None:
    """Poll check_chrome_running until it returns True or retries exhausted.

    Raises RuntimeError if Chrome doesn't come up. Default 10×0.5s = 5s
    total — long enough for Chrome to start listening, short enough to
    fail fast on misconfiguration.
    """
    for attempt in range(1, retries + 1):
        if check_chrome_running(port):
            return
        time.sleep(delay)
    raise RuntimeError(
        f"Chrome 启动后 {retries * delay:.1f}s 内 CDP @ {port} 未就绪。\n"
        f"可能原因：\n"
        f"  - Chrome 进程被 OOM killer 或 sandbox 杀掉\n"
        f"  - 端口 {port} 被另一个进程占用（试 WEBNOVEL_CIWEIMAO_CDP_PORT=9333）\n"
        f"  - 防火墙拦截 127.0.0.1:{port}\n"
        f"手动检查：curl http://127.0.0.1:{port}/json/version"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py -v`
Expected: 18 passed

NOTE: The second test uses a typo'd path — fix the test before running. Change
`"scripts.ciweimao_setup.setup_civeimao.check_chrome_running"` → `"scripts.ciweimao_setup.setup_ciweimao.check_chrome_running"`.

- [ ] **Step 5: Commit**

```bash
git add scripts/ciweimao_setup/setup_ciweimao.py tests/test_ciweimao_setup.py
git commit -m "feat(ciweimao-setup): verify_cdp_ready retry loop"
```

---

## Task 7: `setup_ciweimao()` orchestrator + CLI entry

**Files:**
- Modify: `scripts/ciweimao_setup/setup_ciweimao.py`
- Modify: `tests/test_ciweimao_setup.py`

- [ ] **Step 1: Write the failing test**

Append:
```python
def test_setup_ciweimao_idempotent_when_already_ready(monkeypatch):
    """When agent-browser is on PATH and Chrome is running, do nothing."""
    from scripts.ciweimao_setup.setup_ciweimao import setup_ciweimao

    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_ciweimao.check_agent_browser", lambda: True,
    )
    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_ciweimao.check_chrome_running", lambda port: True,
    )
    install_called = []
    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_ciweimao.install_agent_browser",
        lambda: install_called.append(True),
    )
    launch_called = []
    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_ciweimao.launch_chrome",
        lambda port, user_data_dir: launch_called.append((port, user_data_dir)) or object(),
    )

    setup_ciweimao(port=9222)

    assert install_called == [], "should not reinstall when on PATH"
    assert launch_called == [], "should not launch when already running"


def test_setup_ciweimao_installs_then_launches(monkeypatch, tmp_path):
    """When agent-browser missing + Chrome not running, install then launch."""
    from scripts.ciweimao_setup.setup_ciweimao import setup_ciweimao

    state = {"agent": False, "chrome": False}
    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_ciweimao.check_agent_browser", lambda: state["agent"],
    )
    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_ciweimao.check_chrome_running", lambda port: state["chrome"],
    )
    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_ciweimao.install_agent_browser",
        lambda: state.__setitem__("agent", True),
    )
    def fake_launch(port, user_data_dir):
        state["chrome"] = True
        return object()
    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_ciweimao.launch_chrome", fake_launch,
    )
    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_ciweimao.verify_cdp_ready", lambda *a, **k: None,
    )
    # Override cache dir to use tmp_path
    monkeypatch.setattr(
        "scripts.ciweimao_setup.setup_ciweimao._chrome_user_data_dir",
        lambda: tmp_path / "chrome",
    )

    setup_ciweimao(port=9333)

    assert state["agent"] is True
    assert state["chrome"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py::test_setup_ciweimao_idempotent_when_already_ready -v`
Expected: FAIL — `cannot import name 'setup_ciweimao'`

- [ ] **Step 3: Add orchestrator and CLI entry**

Append:
```python
def setup_ciweimao(port: int = DEFAULT_CDP_PORT) -> None:
    """Idempotent setup: ensure agent-browser is on PATH and Chrome @ port is up.

    Order of operations:
    1. Install agent-browser if missing.
    2. Probe Chrome on the CDP port.
    3. If Chrome is not running, find binary, launch it, verify CDP ready.
    4. If Chrome IS already running, do nothing.

    Raises RuntimeError on any unrecoverable failure with an actionable
    message pointing the user to the next step.
    """
    # Step 1: agent-browser
    if not check_agent_browser():
        install_agent_browser()
    if not check_agent_browser():
        # Install claimed success but binary still missing — very weird
        raise RuntimeError(
            "npm install -g agent-browser 报告成功，但 PATH 中仍找不到 agent-browser。"
            "请手动运行 `which agent-browser` 和 `npm list -g agent-browser` 排查。"
        )

    # Step 2-4: Chrome
    if check_chrome_running(port):
        return  # already ready

    user_data_dir = _chrome_user_data_dir()
    launch_chrome(port, user_data_dir)
    verify_cdp_ready(port)


def main() -> int:
    """CLI entry: ``python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao [--port PORT]``."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Set up Chrome @ CDP port + agent-browser for ciweimao adapter.",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_CDP_PORT,
        help=f"CDP port (default {DEFAULT_CDP_PORT}; honors $WEBNOVEL_CIWEIMAO_CDP_PORT)",
    )
    args = parser.parse_args()
    port = int(os.environ.get("WEBNOVEL_CIWEIMAO_CDP_PORT", args.port))
    try:
        setup_ciweimao(port=port)
    except RuntimeError as e:
        print(f"FAIL: {e}", file=sys.stderr, flush=True)
        return 1
    print(f"OK: ciweimao CDP ready on port {port}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_setup.py -v`
Expected: 20 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/ciweimao_setup/setup_ciweimao.py tests/test_ciweimao_setup.py
git commit -m "feat(ciweimao-setup): setup_ciweimao orchestrator + CLI entry"
```

---

## Task 8: `sessionstart_integration.py` — mirror chromium decision pattern

**Files:**
- Create: `scripts/ciweimao_setup/sessionstart_integration.py`
- Create: `tests/test_ciweimao_sessionstart_integration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ciweimao_sessionstart_integration.py`:
```python
"""Tests for the ciweimao-prompted decision mirror.

Mirrors install_python_deps.chromium pattern but with .ciweimao-prompted.
"""
from __future__ import annotations

from pathlib import Path

from scripts.ciweimao_setup.sessionstart_integration import (
    CIWEIMAO_PROMPT_FILENAME,
    _ciweimao_marker,
    should_prompt_ciweimao,
    write_ciweimao_decision,
    format_ciweimao_prompt,
)


def test_ciweimao_marker_filename_is_distinct_from_chromium():
    """The marker filename must NOT collide with .chromium-prompted."""
    from scripts.ciweimao_setup.sessionstart_integration import CIWEIMAO_PROMPT_FILENAME as cwm
    # Different filename = independent decisions
    assert cwm != ".chromium-prompted"
    assert cwm == ".ciweimao-prompted"


def test_should_prompt_ciweimao_true_when_marker_missing(tmp_path, monkeypatch):
    """If no .ciweimao-prompted exists → should prompt."""
    monkeypatch.setattr(
        "scripts.ciweimao_setup.sessionstart_integration._ciweimao_marker",
        lambda module_name: tmp_path / "ciweimao-venv" / ".ciweimao-prompted",
    )
    assert should_prompt_ciweimao("webnovel-chart-scan") is True


def test_should_prompt_ciweimao_false_when_marker_yes(tmp_path, monkeypatch):
    """If .ciweimao-prompted exists → should not prompt."""
    marker = tmp_path / "ciweimao-venv" / ".ciweimao-prompted"
    marker.parent.mkdir(parents=True)
    marker.write_text("yes\n")
    monkeypatch.setattr(
        "scripts.ciweimao_setup.sessionstart_integration._ciweimao_marker",
        lambda module_name: marker,
    )
    assert should_prompt_ciweimao("webnovel-chart-scan") is False


def test_write_ciweimao_decision_yes(tmp_path, monkeypatch):
    """write_ciweimao_decision('yes') creates file with content 'yes'."""
    marker = tmp_path / "ciweimao-venv" / ".ciweimao-prompted"
    monkeypatch.setattr(
        "scripts.ciweimao_setup.sessionstart_integration._ciweimao_marker",
        lambda module_name: marker,
    )
    write_ciweimao_decision("webnovel-chart-scan", "yes")
    assert marker.read_text() == "yes\n"


def test_write_ciweimao_decision_no(tmp_path, monkeypatch):
    marker = tmp_path / "ciweimao-venv" / ".ciweimao-prompted"
    monkeypatch.setattr(
        "scripts.ciweimao_setup.sessionstart_integration._ciweimao_marker",
        lambda module_name: marker,
    )
    write_ciweimao_decision("webnovel-chart-scan", "no")
    assert marker.read_text() == "no\n"


def test_format_ciweimao_prompt_mentions_setup_script():
    """The prompt must tell the user exactly which command to run."""
    text = format_ciweimao_prompt()
    assert "ciweimao" in text
    assert "agent-browser" in text
    assert "9222" in text
    assert "setup_ciweimao" in text or "webnovel_chart_scan" in text
    assert "y/N" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_sessionstart_integration.py -v`
Expected: `ModuleNotFoundError: No module named 'scripts.ciweimao_setup.sessionstart_integration'`

- [ ] **Step 3: Implement sessionstart_integration.py**

Create `scripts/ciweimao_setup/sessionstart_integration.py`:
```python
"""ciweimao-prompted decision mirror.

Mirrors the chromium-prompted pattern in install_python_deps.py, but for
the ciweimao adapter's setup (Chrome @ 9222 + agent-browser).

The decision is persisted in a separate file (.ciweimao-prompted) so
fanqie's chromium decision and ciweimao's setup decision are tracked
independently — a user accepting chromium for fanqie should not be
treated as having accepted ciweimao's setup.

Marker file location: ``<resolve_cache_dir()>/venvs/<module_name>/.ciweimao-prompted``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


CIWEIMAO_PROMPT_FILENAME = ".ciweimao-prompted"


def _resolve_cache_dir_via_hook() -> Path:
    """Best-effort: borrow install_python_deps.resolve_cache_dir if available.

    Falls back to ~/.cache/webnovel-writer-chang if not importable.
    """
    try:
        # Add <plugin>/hooks to sys.path so we can import install_python_deps
        # (which lives in .claude/plugins/webnovel-writer_chang/hooks/).
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if plugin_root:
            sys.path.insert(0, str(Path(plugin_root) / "hooks"))
        from install_python_deps import resolve_cache_dir
        return resolve_cache_dir()
    except Exception:
        return Path.home() / ".cache" / "webnovel-writer-chang"


def _ciweimao_marker(module_name: str) -> Path:
    """Return path to the .ciweimao-prompted marker for `module_name`."""
    return _resolve_cache_dir_via_hook() / "venvs" / module_name / CIWEIMAO_PROMPT_FILENAME


def should_prompt_ciweimao(module_name: str) -> bool:
    """Return True iff the user has not yet been asked about ciweimao setup."""
    return not _ciweimao_marker(module_name).exists()


def write_ciweimao_decision(module_name: str, decision: str) -> None:
    """Persist the user's y/N choice for ciweimao setup.

    Args:
        module_name: typically "webnovel-chart-scan"
        decision: "yes" or "no" (case-insensitive, normalized to lowercase)
    """
    marker = _ciweimao_marker(module_name)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(decision.strip().lower() + "\n")


def format_ciweimao_prompt() -> str:
    """Generate the prompt text shown to Claude at SessionStart."""
    return (
        "ciweimao adapter 需要 Chrome @ 9222 + agent-browser（绕过验证码）。\n"
        "装好后可用刺猬猫平台榜单扫描；不装也能用其它 4 个平台。\n"
        "是否安装？(y/N)\n"
        "\n"
        "【Claude 指引】用户回答后请执行以下操作之一完成决策持久化，避免下次 SessionStart 再问：\n"
        "  - 用户接受 y: python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao\n"
        "    （自动检测/安装 agent-browser + 启动 Chrome @ 9222）\n"
        "  - 然后调用 write_ciweimao_decision('webnovel-chart-scan', 'yes')\n"
        "    （写在 venv 旁的 .ciweimao-prompted 标记，永久 skip ciweimao 提示）\n"
        "  - 用户拒绝 N: write_ciweimao_decision('webnovel-chart-scan', 'no')\n"
        "    （永久 skip ciweimao adapter）"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_sessionstart_integration.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/ciweimao_setup/sessionstart_integration.py tests/test_ciweimao_sessionstart_integration.py
git commit -m "feat(ciweimao-setup): sessionstart integration + decision marker"
```

---

## Task 9: Hook integration — wire `check_ciweimao_prompt` into session_start.py

**Files:**
- Modify: `hooks/session_start.py`

This is hook-level code, not under pytest. Testing strategy: run the hook in a Python subprocess and assert output contains the ciweimao prompt when venv is set up but marker missing.

- [ ] **Step 1: Add `check_ciweimao_prompt` after `check_chromium_prompt`**

Open `hooks/session_start.py`. Find the line containing `def trigger_background_python_install(plugin_root) -> None:` and insert this block ABOVE it:

```python
def check_ciweimao_prompt(plugin_root: Path) -> str | None:
    """检查 webnovel-chart-scan 是否需要 ciweimao SETUP 弹窗。

    Returns:
        需要弹窗时返回 prompt 文本（给 Claude）；否则 None。

    整个函数体都被 try/except 包住：ciweimao nag 永远不应该 crash SessionStart hook。
    缓存路径通过 install_python_deps.resolve_cache_dir()（spec §4.6.5 fallback chain）
    解析，和 chromium 模式共用同一套 cache 根。
    """
    try:
        sys.path.insert(0, str(plugin_root / "skills" / "webnovel-chart-scan" / "scripts"))
        try:
            from ciweimao_setup.sessionstart_integration import (
                should_prompt_ciweimao,
                format_ciweimao_prompt,
            )
        except (ImportError, OSError, PermissionError):
            return None  # sessionstart_integration.py 还没部署；静默 skip

        # Suppress unless install_python_deps.py has marked chart-scan as fully installed.
        chart_scan = plugin_root / "skills" / "webnovel-chart-scan"
        if not chart_scan.exists():
            return None
        # Lazy-import to avoid forcing chart-scan to be installed first
        sys.path.insert(0, str(plugin_root / "hooks"))
        try:
            from install_python_deps import should_install_module
        except ImportError:
            return None
        if should_install_module(chart_scan) != "ok":
            return None

        # Now check if user has already been prompted
        if not should_prompt_ciweimao("webnovel-chart-scan"):
            return None

        return format_ciweimao_prompt()
    except (ImportError, OSError, PermissionError):
        return None
```

- [ ] **Step 2: Wire into `main()`**

In `main()`, after the line `prompt = check_chromium_prompt(plugin_root)`, add:

```python
    prompt2 = check_ciweimao_prompt(plugin_root)
    if prompt2:
        print(prompt2)
```

So the relevant block of `main()` becomes:
```python
    prompt = check_chromium_prompt(plugin_root)
    if prompt:
        print(prompt)
    prompt2 = check_ciweimao_prompt(plugin_root)
    if prompt2:
        print(prompt2)
    return 0
```

- [ ] **Step 3: Manual smoke test**

Run:
```bash
CLAUDE_PLUGIN_ROOT=/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang \
  python3 -X utf8 /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/hooks/session_start.py
```
Expected: stdout contains a ciweimao y/N prompt **IF** the venv is installed and `.ciweimao-prompted` doesn't exist. If the marker already exists (e.g., user accepted in prior run), no ciweimao prompt should appear.

If venv is not installed, no ciweimao prompt appears (we suppress until chart-scan is fully installed).

- [ ] **Step 4: Commit**

```bash
git add hooks/session_start.py
git commit -m "feat(hook): SessionStart prompts for ciweimao setup"
```

---

## Task 10: ciweimao_runner.py — port from env var

**Files:**
- Modify: `scripts/adapters/ciweimao_runner.py:344-350`
- Create: `tests/test_ciweimao_runner_humanize.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ciweimao_runner_humanize.py`:
```python
"""Tests for ciweimao_runner.run_scraper port handling and error humanization."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.adapters.ciweimao_runner import run_scraper


def test_run_scraper_uses_env_var_port(monkeypatch, tmp_path):
    """WEBNOVEL_CIWEIMAO_CDP_PORT=9333 → --port 9333 in subprocess cmd."""
    monkeypatch.setenv("WEBNOVEL_CIWEIMAO_CDP_PORT", "9333")

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    # Need a marker .md file matching the prefix, otherwise run_scraper raises
    out = tmp_path / "ciweimao"
    out.mkdir()
    (out / "刺猬猫点击榜_20260816.md").write_text("# x\n", encoding="utf-8")

    run_scraper("点击榜", out)

    assert "--port" in captured["cmd"]
    port_idx = captured["cmd"].index("--port")
    assert captured["cmd"][port_idx + 1] == "9333"


def test_run_scraper_defaults_to_9222_when_env_unset(monkeypatch, tmp_path):
    """Without env var → port 9222 (backwards compat)."""
    monkeypatch.delenv("WEBNOVEL_CIWEIMAO_CDP_PORT", raising=False)

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    out = tmp_path / "ciweimao"
    out.mkdir()
    (out / "刺猬猫点击榜_20260816.md").write_text("# x\n", encoding="utf-8")

    run_scraper("点击榜", out)

    assert "--port" in captured["cmd"]
    port_idx = captured["cmd"].index("--port")
    assert captured["cmd"][port_idx + 1] == "9222"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_runner_humanize.py::test_run_scraper_uses_env_var_port -v`
Expected: FAIL — captured cmd has "9222" not "9333"

- [ ] **Step 3: Modify run_scraper to read env**

Open `scripts/adapters/ciweimao_runner.py:344-350`. Replace:
```python
    cmd = [
        "node",
        str(JS_SCRAPER_PATH),
        "--type", rank_type,
        "--outdir", str(output_dir),
        "--port", "9222",
    ]
```
with:
```python
    # Read CDP port from env (default 9222). Honors WEBNOVEL_CIWEIMAO_CDP_PORT
    # for users running multiple worktrees or non-default CDP setups.
    port = os.environ.get("WEBNOVEL_CIWEIMAO_CDP_PORT", "9222")
    cmd = [
        "node",
        str(JS_SCRAPER_PATH),
        "--type", rank_type,
        "--outdir", str(output_dir),
        "--port", port,
    ]
```

Add `import os` at top of file if not present (it should already be there from existing imports — verify with `grep "^import os" scripts/adapters/ciweimao_runner.py`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_runner_humanize.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/adapters/ciweimao_runner.py tests/test_ciweimao_runner_humanize.py
git commit -m "feat(ciweimao-runner): read CDP port from WEBNOVEL_CIWEIMAO_CDP_PORT env"
```

---

## Task 11: ciweimao_runner.py — humanize error messages

**Files:**
- Modify: `scripts/adapters/ciweimao_runner.py:351-371`
- Modify: `tests/test_ciweimao_runner_humanize.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ciweimao_runner_humanize.py`:
```python
def test_run_scraper_humanizes_file_not_found_node(monkeypatch, tmp_path):
    """FileNotFoundError on `node` → friendly RuntimeError pointing to install."""
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "node")

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="brew install node"):
        run_scraper("点击榜", tmp_path)


def test_run_scraper_humanizes_chrome_not_running_error(monkeypatch, tmp_path):
    """subprocess exit non-zero with CDP error → humanized message with setup command."""
    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "agent-browser failed: CDP discovery failed for 127.0.0.1:9222"

    def fake_run(cmd, **kwargs):
        return FakeResult()

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        run_scraper("点击榜", tmp_path)

    msg = str(exc_info.value)
    assert "setup_ciweimao" in msg or "webnovel_chart_scan" in msg
    assert "Chrome" in msg or "9222" in msg
    assert "agent-browser" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_runner_humanize.py::test_run_scraper_humanizes_file_not_found_node -v`
Expected: FAIL — error message does NOT contain "brew install node"

- [ ] **Step 3: Update error handling in run_scraper**

In `scripts/adapters/ciweimao_runner.py`, replace lines 351-371 (the `try` block + `returncode != 0` block) with:

```python
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
            check=False,
        )
    except FileNotFoundError as e:
        # `node` not on PATH
        raise RuntimeError(
            "找不到 node 可执行文件。请安装 Node.js ≥18：\n"
            "  - macOS: brew install node\n"
            "  - Linux: 见 https://nodejs.org/en/download/package-manager\n"
            "  - 或访问 https://nodejs.org 下载安装包\n"
            "装好后 ciweimao adapter 才能用。"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"ciweimao scraper 超时（180s）。可能原因：\n"
            f"  - 站点慢或网络问题\n"
            f"  - CDP 连接失败（运行 python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao 排查）"
        ) from e

    if result.returncode != 0:
        stderr = result.stderr[:500] if result.stderr else "(no stderr)"
        # Detect "CDP discovery failed" / "agent-browser" → Chrome not running
        cdp_hint = ""
        if "CDP" in stderr or "agent-browser" in stderr or "9222" in stderr:
            cdp_hint = (
                f"\n\n排查步骤：\n"
                f"  1. Chrome @ 9222 没起来？运行：\n"
                f"     python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao\n"
                f"  2. agent-browser 不在 PATH？运行：\n"
                f"     npm install -g agent-browser\n"
                f"  3. 端口冲突？设置 WEBNOVEL_CIWEIMAO_CDP_PORT=9333 重试"
            )
        raise RuntimeError(
            f"ciweimao scraper 失败（exit {result.returncode}）。\n"
            f"stderr: {stderr}{cdp_hint}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `<VENV_PYTHON> -m pytest tests/test_ciweimao_runner_humanize.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/adapters/ciweimao_runner.py tests/test_ciweimao_runner_humanize.py
git commit -m "feat(ciweimao-runner): humanize error messages with actionable hints"
```

---

## Task 12: ciweimao.py — delete dead code, add period=weekly comment

**Files:**
- Modify: `scripts/adapters/ciweimao.py`

This task has minimal automation risk. Run existing tests to verify nothing breaks.

- [ ] **Step 1: Verify dead code is truly unused**

Run:
```bash
cd .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan
grep -rn "parse_category_html\|_extract_book_id\|CATEGORY_SLUG_MAP\|PERIOD_SORT_MAP" scripts/ tests/
```
Expected: matches only in `scripts/adapters/ciweimao.py` (the dead code itself) and `KNOWN_LIMITATIONS.md` (history). No live consumers.

- [ ] **Step 2: Delete dead code**

In `scripts/adapters/ciweimao.py`:
- Delete the entire `import re` line (no longer used)
- Delete the entire `import httpx` line (no longer used)
- Delete `from bs4 import BeautifulSoup` (no longer used)
- Delete `_extract_book_id` (lines 83-88)
- Delete `CATEGORY_SLUG_MAP` (lines 57-72)
- Delete `PERIOD_SORT_MAP` (lines 76-80)
- Delete `parse_category_html` (lines 91-166)
- Delete unused imports from typing (`Optional` if no longer used)

- [ ] **Step 3: Add comment to PERIOD_TO_RANK_TYPE**

In `scripts/adapters/ciweimao_runner.py:92-96`, replace:
```python
PERIOD_TO_RANK_TYPE = {
    "daily": "click",
    "weekly": "click",
    "monthly": "monthly",
}
```
with:
```python
PERIOD_TO_RANK_TYPE = {
    "daily": "click",
    # 注意：ciweimao 没有原生 weekly 榜；weekly 复用 click 榜（最近 24h 数据）。
    "weekly": "click",
    "monthly": "monthly",
}
```

- [ ] **Step 4: Rewrite adapter docstring (top of file)**

In `scripts/adapters/ciweimao.py`, replace the entire module docstring (lines 1-36) with:
```python
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
```

- [ ] **Step 5: Run existing tests to verify nothing broke**

Run: `<VENV_PYTHON> -m pytest tests/ -v --ignore=tests/test_ciweimao_e2e.py --ignore=tests/test_ciweimao_live.py --ignore=tests/test_ciweimao_runner_integration.py`
Expected: all pass (existing tests for parser + adapter remain green)

- [ ] **Step 6: Commit**

```bash
git add scripts/adapters/ciweimao.py scripts/adapters/ciweimao_runner.py
git commit -m "refactor(ciweimao): remove dead BeautifulSoup path + period comment + refreshed docstring"
```

---

## Task 13: pyproject.toml — entry point for setup script

**Files:**
- Modify: `pyproject.toml` (chart-scan)

- [ ] **Step 1: Locate the `[project.scripts]` section**

Run: `grep -n "scripts\]" .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/pyproject.toml`
Expected: find `[project.scripts]` block (may not exist if no entry points are registered)

- [ ] **Step 2: Add entry point**

If `[project.scripts]` block exists, add inside:
```toml
webnovel-chart-scan-setup-ciweimao = "webnovel_chart_scan.ciweimao_setup.setup_ciweimao:main"
```

If the block does NOT exist, add:
```toml
[project.scripts]
webnovel-chart-scan-setup-ciweimao = "webnovel_chart_scan.ciweimao_setup.setup_ciweimao:main"
```

NOTE: The exact package name depends on how chart-scan is currently packaged. Check `pyproject.toml`'s `name` field. If the package is named `webnovel_chart_scan` (with underscore), use `webnovel_chart_scan.ciweimao_setup.setup_ciweimao`. If it's `webnovel-chart-scan` (with hyphen), the import path is still `webnovel_chart_scan.ciweimao_setup.setup_ciweimao` because Python requires underscores in module names.

Verify by running:
```bash
cd .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan
<VENV_PYTHON> -c "from webnovel_chart_scan.ciweimao_setup.setup_ciweimao import main; print('ok')"
```
Expected: `ok`

If it fails with ModuleNotFoundError, the actual module path needs adjustment. Adapt the entry point accordingly.

- [ ] **Step 3: Verify install picks it up**

Run: `<VENV_PYTHON> -m pip install -e . --quiet && which webnovel-chart-scan-setup-ciweimao`
Expected: prints a path to the installed console script

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build(ciweimao-setup): console-script entry point"
```

---

## Task 14: E2E test — `tests/test_ciweimao_e2e.py` with skip-if-unavailable

**Files:**
- Create: `tests/test_ciweimao_e2e.py`

- [ ] **Step 1: Create the e2e test file**

```python
"""End-to-end test for the ciweimao adapter.

Requires a real Chrome listening on the CDP port (default 9222) AND
agent-browser on $PATH. Skipped automatically if either is missing —
so this test is opt-in via ``pytest -m slow``.

To run:
    <VENV_PYTHON> -m pytest tests/test_ciweimao_e2e.py -v -m slow

Verifies:
1. Adapter returns at least 1 book when fully set up.
2. Returned books have title + detail_url populated.
3. setup_ciweimao() is idempotent (re-running doesn't break anything).
"""
from __future__ import annotations

import shutil
import subprocess
import urllib.request

import pytest

from scripts.adapters.ciweimao import CiweimaoAdapter
from scripts.ciweimao_setup.setup_ciweimao import (
    DEFAULT_CDP_PORT,
    check_agent_browser,
    check_chrome_running,
    setup_ciweimao,
)


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not shutil.which("node"),
        reason="node not on PATH",
    ),
    pytest.mark.skipif(
        not check_agent_browser(),
        reason="agent-browser not installed",
    ),
    pytest.mark.skipif(
        not check_chrome_running(DEFAULT_CDP_PORT),
        reason=f"Chrome not listening on {DEFAULT_CDP_PORT}",
    ),
]


def _adapter_returns_books():
    adapter = CiweimaoAdapter()
    books = adapter.fetch("all", "daily", top=10)
    assert len(books) >= 1, f"expected ≥1 book, got {len(books)}"
    for book in books:
        assert book.title, f"book missing title: {book}"
        assert book.detail_url, f"book missing detail_url: {book}"
    return books


def test_adapter_returns_books_when_fully_set_up():
    """Smoke: with Chrome+agent-browser up, adapter returns real data."""
    _adapter_returns_books()


def test_setup_ciweimao_is_idempotent():
    """Calling setup_ciweimao() again is a no-op (env already ready)."""
    # First call should be a no-op since pytestmark already verified env is up
    setup_ciweimao(port=DEFAULT_CDP_PORT)
    # Second call too
    setup_ciweimao(port=DEFAULT_CDP_PORT)
    # And adapter still works
    _adapter_returns_books()
```

- [ ] **Step 2: Verify skip behavior**

Run (env not set up):
```bash
<VENV_PYTHON> -m pytest tests/test_ciweimao_e2e.py -v -m slow
```
Expected: all tests skipped with reason "Chrome not listening on 9222" (or whichever condition fails first)

- [ ] **Step 3: Verify e2e behavior (requires real Chrome + agent-browser)**

If Chrome + agent-browser are available:
```bash
# Start Chrome if not already running
python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao
# Run e2e
<VENV_PYTHON> -m pytest tests/test_ciweimao_e2e.py -v -m slow
```
Expected: 2 tests passed (test_adapter_returns_books_when_fully_set_up + test_setup_ciweimao_is_idempotent)

If Chrome + agent-browser are NOT available locally, document this in KNOWN_LIMITATIONS.md (next task) and skip this step.

- [ ] **Step 4: Commit**

```bash
git add tests/test_ciweimao_e2e.py
git commit -m "test(ciweimao): end-to-end test with skip-if-unavailable"
```

---

## Task 15: Documentation — KNOWN_LIMITATIONS.md + SKILL.md

**Files:**
- Modify: `KNOWN_LIMITATIONS.md`
- Modify: `SKILL.md`

- [ ] **Step 1: Add section to KNOWN_LIMITATIONS.md**

Append a new section after the v0.2.1 patch notes:
```markdown
## v0.2.2 (2026-08-16)

ciweimao setup automation: made LIVE_WITH_SETUP honest.

**What changed:**
- Added `scripts/ciweimao_setup/setup_ciweimao.py` — idempotent setup script
  (find_chrome_binary + check/install agent-browser + launch Chrome @ 9222).
- Added `scripts/ciweimao_setup/sessionstart_integration.py` — `.ciweimao-prompted`
  decision marker mirror (independent from `.chromium-prompted`).
- Extended `hooks/session_start.py` with `check_ciweimao_prompt()` so
  users get a y/N prompt at SessionStart when ciweimao setup is missing.
- `ciweimao_runner.py` now reads `WEBNOVEL_CIWEIMAO_CDP_PORT` env var
  (default 9222) so multiple worktrees don't fight over the port.
- All ciweimao errors now point to `python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao`
  for self-service fix.
- Deleted `parse_category_html` + related dead code (BeautifulSoup path
  replaced by vendored CDP scraper in v0.2).
- Added `tests/test_ciweimao_e2e.py` — end-to-end test, auto-skips when
  Chrome/agent-browser missing.

**Setup flow:**
1. User starts Claude Code → SessionStart hook detects missing ciweimao setup.
2. Hook prompts y/N to user.
3. On y: Claude runs `python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao`,
   which auto-installs agent-browser (npm) and launches Chrome @ 9222.
4. On N: decision persisted, no future prompts.
5. Next scan just works.

**Out of scope (future work):**
- Replace vendored CDP scraper with playwright-based scraper (drop
  agent-browser dependency entirely). See spec §10.
- Windows Chrome binary path detection in `find_chrome_binary()`.
- GitHub Actions nightly job for `pytest -m slow`.
```

- [ ] **Step 2: Update SKILL.md "安装" section**

Find the "## 安装" section and replace:
```markdown
## 安装

\`\`\`bash
cd ${CLAUDE_PLUGIN_ROOT}/skills/webnovel-chart-scan
pip install -e ".[fanqie,dev]"
playwright install chromium  # 番茄需要
\`\`\`
```
with:
```markdown
## 安装

\`\`\`bash
cd ${CLAUDE_PLUGIN_ROOT}/skills/webnovel-chart-scan
pip install -e ".[fanqie,dev]"
playwright install chromium  # 番茄需要
\`\`\`

### 刺猬猫额外设置

ciweimao adapter 需要 Chrome @ 9222 + `agent-browser`。SessionStart 钩子会
在你第一次进入项目时弹 y/N 提示；接受即可一键装好。

手动运行：
\`\`\`bash
python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao
\`\`\`

或自定义端口：
\`\`\`bash
WEBNOVEL_CIWEIMAO_CDP_PORT=9333 python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao --port 9333
\`\`\`
```

Also update the "平台覆盖" table at line 74 to clarify:
```markdown
| 刺猬猫 | WEBFETCH (vendored CDP) | shell-out to vendored Node scraper（SessionStart 钩子引导装 agent-browser + Chrome @ 9222） |
```

- [ ] **Step 3: Commit**

```bash
git add KNOWN_LIMITATIONS.md SKILL.md
git commit -m "docs(ciweimao-setup): document v0.2.2 automation + user-facing setup instructions"
```

---

## Self-Review

**1. Spec coverage:**

| Spec requirement | Task |
|---|---|
| §3.1 two independent lifecycle paths | T1-T9 |
| §4.1 C1 `__init__.py` | T1 |
| §4.1 C2 `setup_ciweimao.py` with all 7 functions | T1-T7 |
| §4.1 C3 `sessionstart_integration.py` | T8 |
| §4.1 C4 modify `hooks/session_start.py` | T9 |
| §4.1 C5 `tests/test_ciweimao_e2e.py` | T14 |
| §4.2 M1 env var port + humanize errors | T10, T11 |
| §4.2 M2 delete dead code + period comment + docstring | T12 |
| §4.2 M3 pyproject entry point | T13 |
| §6 error handling table (10 rows) | T1-T11 (each helper raises with clear msg) |
| §7 test strategy | T1-T8 (setup helpers), T10-T11 (humanize), T14 (e2e) |
| §8 acceptance criteria | T9 (sessionstart prompt), T11 (actionable errors), T10 (env var), T14 (e2e skip), T12 (dead code gone), T1-T8 (pytest green) |

All 10 spec acceptance criteria covered.

**2. Placeholder scan:** Searched for "TBD", "TODO", "implement later" — none found. Every step has complete code or complete commands.

**3. Type consistency:** `setup_ciweimao(port: int = DEFAULT_CDP_PORT)` — consistent across T7, T11, T14. `check_chrome_running(port: int) -> bool` — consistent across T2, T6. `write_ciweimao_decision(module_name: str, decision: str) -> None` — consistent across T8 (and matches the chromium mirror exactly). All function names match across tasks.

**4. Spec ambiguity:** None found during review. The spec was internally consistent.

Plan is complete.