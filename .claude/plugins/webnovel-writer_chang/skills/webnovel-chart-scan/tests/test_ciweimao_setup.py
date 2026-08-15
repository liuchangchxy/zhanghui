"""Unit tests for scripts/ciweimao_setup.setup_ciweimao helpers.

These tests cover the pure-Python helpers without launching actual Chrome
or running npm. Subprocess-touching helpers are tested with unittest.mock.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

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


def test_check_agent_browser_returns_true_when_on_path(monkeypatch):
    from scripts.ciweimao_setup.setup_ciweimao import check_agent_browser
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/agent-browser" if cmd == "agent-browser" else None)
    assert check_agent_browser() is True


def test_check_agent_browser_returns_false_when_missing(monkeypatch):
    from scripts.ciweimao_setup.setup_ciweimao import check_agent_browser
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert check_agent_browser() is False


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
        return R()

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
        "scripts.ciweimao_setup.setup_ciweimao.check_chrome_running",
        lambda port: False,
    )
    monkeypatch.setattr("scripts.ciweimao_setup.setup_ciweimao.time.sleep", lambda *_: None)
    with pytest.raises(RuntimeError, match="未就绪"):
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
