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
    assert "webnovel_chart_scan" not in text
    assert "webnovel-chart-scan-setup-ciweimao" in text or "python -m scripts.ciweimao_setup.setup_ciweimao" in text
    assert "y/N" in text
