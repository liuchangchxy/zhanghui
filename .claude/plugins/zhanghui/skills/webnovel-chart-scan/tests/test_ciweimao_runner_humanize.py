"""Tests for ciweimao_runner.run_scraper port handling and error humanization."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.adapters.ciweimao_runner import run_scraper


def test_run_scraper_uses_env_var_port(monkeypatch, tmp_path):
    """WEBNOVEL_CIWEIMAO_CDP_PORT=9333 -> --port 9333 in subprocess cmd."""
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
    """Without env var -> port 9222 (backwards compat)."""
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
    assert "webnovel_chart_scan" not in msg
    assert "setup_ciweimao" in msg or "webnovel_chart_scan" in msg
    assert "Chrome" in msg or "9222" in msg
    assert "agent-browser" in msg
