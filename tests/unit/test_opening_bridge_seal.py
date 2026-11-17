#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 1C seal contract for the Opening Bridge (`--opening-bridge-file`).

The bridge must ride the *existing* seal chain: it prepends a fixed block to the
Creative Brief, the original brief stays byte-for-byte intact, and everything else
(writer package, fingerprint, canonical prompt) is exactly the same code path.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from data_modules.opening_bridge import (
    BRIDGE_HEADER,
    ORIGINAL_HEADER,
    SCOPE_LINE,
    split_composed_brief,
)
from test_workflow_convergence import _setup_book_project

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "plugins" / "zhanghui" / "scripts"
WEBNOVEL_PY = SCRIPTS_DIR / "webnovel.py"

BRIEF = (
    "1. 开篇委托：《问道青云》第1章，一句话目标：通过试炼考核。\n"
    "2. 这章的故事：石阶问心、身份青牌。\n"
    "3. 收在哪里：他拿到玉牌，注意到暗纹。"
)
BRIDGE = "上一章 accepted：林凡答应了替执事保管青牌。\n本章开场：执事当众把青牌收回，问他为什么少了一块。"


def _seal(project_root: Path, extra: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable, "-X", "utf8", str(WEBNOVEL_PY),
            "--project-root", str(project_root),
            "runtime", "attach-creative-brief",
            "--chapter", "1",
            "--brief", BRIEF,
            *extra,
            "--format", "prompt",
        ],
        capture_output=True, text=True,
    )


def _package(project_root: Path) -> dict:
    path = project_root / ".webnovel" / "runtime" / "chapter_001" / "writer_package.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_bridge_seals_the_unmodified_brief_behind_a_fixed_header(tmp_path):
    project_root = _setup_book_project(tmp_path, chapter=1)
    bridge_file = tmp_path / "bridge.body.txt"
    bridge_file.write_text(BRIDGE, encoding="utf-8")

    res = _seal(project_root, ["--opening-bridge-file", str(bridge_file)])
    assert res.returncode == 0, res.stderr

    prompt = res.stdout
    assert prompt.index(BRIDGE_HEADER) < prompt.index(ORIGINAL_HEADER) < prompt.index("开篇委托")
    assert SCOPE_LINE in prompt
    assert BRIDGE in prompt

    body, original = split_composed_brief(_package(project_root)["creative_brief"])
    assert original == BRIEF, "the Context Agent brief must be preserved byte-for-byte"
    assert body == BRIDGE


def test_without_the_flag_the_seal_is_unchanged(tmp_path):
    plain_root = _setup_book_project(tmp_path / "plain", chapter=1)
    plain = _seal(plain_root, [])
    assert plain.returncode == 0, plain.stderr
    assert BRIDGE_HEADER not in plain.stdout
    assert _package(plain_root)["creative_brief"] == BRIEF

    bridged_root = _setup_book_project(tmp_path / "bridged", chapter=1)
    bridge_file = tmp_path / "bridge.body.txt"
    bridge_file.write_text(BRIDGE, encoding="utf-8")
    bridged = _seal(bridged_root, ["--opening-bridge-file", str(bridge_file)])
    assert bridged.returncode == 0, bridged.stderr

    assert (
        _package(plain_root)["package_fingerprint"]
        != _package(bridged_root)["package_fingerprint"]
    ), "the sealed brief changed, so the package fingerprint must change"
    assert _package(bridged_root)["is_writer_ready"] is True


def test_empty_bridge_file_means_no_bridge(tmp_path):
    """An empty bridge file is the flow's "no bridge this chapter" signal, not an error."""
    project_root = _setup_book_project(tmp_path, chapter=1)
    bridge_file = tmp_path / "empty.txt"
    bridge_file.write_text("  \n", encoding="utf-8")

    res = _seal(project_root, ["--opening-bridge-file", str(bridge_file)])
    assert res.returncode == 0, res.stderr
    assert BRIDGE_HEADER not in res.stdout
    assert _package(project_root)["creative_brief"] == BRIEF


def test_missing_bridge_file_fails_closed(tmp_path):
    project_root = _setup_book_project(tmp_path, chapter=1)
    res = _seal(project_root, ["--opening-bridge-file", str(tmp_path / "nope.txt")])
    assert res.returncode == 1
    assert "opening bridge file not found" in (res.stderr + res.stdout)
