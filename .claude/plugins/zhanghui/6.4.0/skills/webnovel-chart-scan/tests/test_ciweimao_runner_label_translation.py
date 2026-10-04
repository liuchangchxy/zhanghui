"""Regression test for rank_type EN→CN label translation.

E2E run on 2026-08-16 caught a real bug: run_scraper() takes rank_type="click"
(English, from PERIOD_TO_RANK_TYPE) but globs for "刺猬猫click_*" while the
vendored JS scraper writes "刺猬猫点击榜_*" (Chinese label). This test
exercises the full adapter flow with the English rank_type.
"""
from __future__ import annotations

from pathlib import Path


def test_run_scraper_uses_chinese_label_for_glob(monkeypatch, tmp_path):
    """run_scraper(rank_type="click") must look for 刺猬猫点击榜_* not 刺猬猫click_*."""
    from scripts.adapters.ciweimao_runner import run_scraper

    # Simulate the JS scraper writing the file with the Chinese label
    output_dir = tmp_path / "ciweimao"
    output_dir.mkdir()
    written = output_dir / "刺猬猫点击榜_20260816.md"
    written.write_text("# x\n", encoding="utf-8")

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    result = run_scraper("click", output_dir)
    assert result == written, f"expected {written}, got {result}"
    # And verify the JS got the English --type (this is the contract)
    assert "--type" in captured["cmd"]
    type_idx = captured["cmd"].index("--type")
    assert captured["cmd"][type_idx + 1] == "click"


def test_run_scraper_handles_monthly_label(monkeypatch, tmp_path):
    """run_scraper(rank_type="monthly") must look for 刺猬猫月票榜_*."""
    from scripts.adapters.ciweimao_runner import run_scraper

    output_dir = tmp_path / "ciweimao"
    output_dir.mkdir()
    written = output_dir / "刺猬猫月票榜_20260816.md"
    written.write_text("# x\n", encoding="utf-8")

    monkeypatch.setattr("subprocess.run", lambda *a, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    result = run_scraper("monthly", output_dir)
    assert result == written


def test_run_scraper_falls_back_to_raw_rank_type_when_no_label_mapping(monkeypatch, tmp_path):
    """If rank_type isn't in the label map, glob using the raw value (defensive)."""
    from scripts.adapters.ciweimao_runner import run_scraper

    output_dir = tmp_path / "ciweimao"
    output_dir.mkdir()
    written = output_dir / "刺猬猫unknown_X.md"
    written.write_text("# x\n", encoding="utf-8")

    monkeypatch.setattr("subprocess.run", lambda *a, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    # An unknown rank_type — should not crash, should fall back to raw glob
    result = run_scraper("unknown", output_dir)
    assert result == written
