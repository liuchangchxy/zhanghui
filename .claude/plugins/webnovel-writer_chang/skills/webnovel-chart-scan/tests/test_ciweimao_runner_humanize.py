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
