#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The declared Python floor must actually be importable (task M / packaging contract).

`scripts/pyproject.toml` declares `requires-python = ">=3.11"`. A backslash inside an f-string
*expression* is a Python 3.12+ feature, and one such line in `prose_voice_target.py` made
`prose_pipeline` un-importable on 3.11 — i.e. on the very floor the plugin advertises, the
whole prose validation path (Step 2B / Step 4 / Semantic Judge) failed at import time.

This test scans the plugin sources for that construct so it cannot silently come back.
"""

from __future__ import annotations

import io
import tokenize
from pathlib import Path

import pytest

PLUGIN_SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "plugins" / "zhanghui" / "scripts"


def _iter_python_files() -> list[Path]:
    return sorted(
        path
        for path in PLUGIN_SCRIPTS.rglob("*.py")
        if "__pycache__" not in path.parts and ".tmp" not in path.parts
    )


def _fstring_expression_tokens(source: str):
    """Yield tokens that belong to an f-string's replacement-field expression."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return
    stack: list[bool] = []
    for token in tokens:
        if token.type == tokenize.FSTRING_START:
            stack.append(False)
            continue
        if token.type == tokenize.FSTRING_END:
            if stack:
                stack.pop()
            continue
        if not stack:
            continue
        depth = stack[-1]
        if token.type == tokenize.OP and token.string == "{":
            stack[-1] = True
            continue
        if token.type == tokenize.OP and token.string == "}":
            stack[-1] = False
            continue
        if depth:
            yield token


def test_no_backslash_inside_fstring_expressions():
    offenders: list[str] = []
    for path in _iter_python_files():
        source = path.read_text(encoding="utf-8")
        if "f'" not in source and 'f"' not in source:
            continue
        for token in _fstring_expression_tokens(source):
            if token.type == tokenize.STRING and "\\" in token.string:
                offenders.append(f"{path.relative_to(PLUGIN_SCRIPTS)}:{token.start[0]}")
    assert not offenders, (
        "backslash inside an f-string expression requires Python 3.12+ but "
        f"scripts/pyproject.toml declares >=3.11: {offenders}"
    )


def test_declared_python_floor_matches_the_installed_interpreters_expectation():
    """Guard the declaration itself: the floor must be the low bound, not something higher."""
    import re
    import sys

    pyproject = PLUGIN_SCRIPTS / "pyproject.toml"
    match = re.search(r'requires-python\s*=\s*">=(\d+)\.(\d+)"', pyproject.read_text(encoding="utf-8"))
    assert match, "scripts/pyproject.toml must declare requires-python"
    floor = (int(match.group(1)), int(match.group(2)))
    assert floor <= (3, 11), "the declared floor is the contract; raise it deliberately, not silently"
    assert sys.version_info[:2] >= floor


@pytest.mark.parametrize("module", ["prose_pipeline", "prose_semantic_diff", "prose_judge_host"])
def test_prose_pipeline_modules_are_importable(module: str):
    import importlib

    importlib.import_module(f"data_modules.{module}")
