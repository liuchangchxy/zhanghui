"""Unit tests for scripts/ciweimao_setup.setup_ciweimao helpers.

These tests cover the pure-Python helpers without launching actual Chrome
or running npm. Subprocess-touching helpers are tested with unittest.mock.
"""
from __future__ import annotations

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
