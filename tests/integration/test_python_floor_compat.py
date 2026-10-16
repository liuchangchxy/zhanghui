#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The declared Python floor must actually be importable (task M / packaging contract).

`scripts/pyproject.toml` declares `requires-python = ">=3.11"`. A backslash inside an f-string
*expression* is a Python 3.12+ feature, and one such line in `prose_voice_target.py` made
`prose_pipeline` un-importable on 3.11 — i.e. on the very floor the plugin advertises, the
whole prose validation path (Step 2B / Step 4 / Semantic Judge) failed at import time.

The scan is a hand-rolled literal walker rather than `tokenize.FSTRING_START`, because that
token type only exists from Python 3.12 — using it would make this guard itself un-runnable on
the interpreter it is meant to protect.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN_SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "plugins" / "zhanghui" / "scripts"

_FSTRING_OPEN_RE = re.compile(r"""(?<![A-Za-z0-9_])[fF](?P<quote>'''|\"\"\"|'|\")""")
_TRIPLE = ("'''", '"""')


def _iter_python_files() -> list[Path]:
    return sorted(
        path
        for path in PLUGIN_SCRIPTS.rglob("*.py")
        if "__pycache__" not in path.parts and ".tmp" not in path.parts
    )


def fstring_fields_with_backslash(source: str) -> list[tuple[int, str]]:
    """Return `(line, field_text)` for every f-string replacement field containing a backslash."""
    offenders: list[tuple[int, str]] = []
    for match in _FSTRING_OPEN_RE.finditer(source):
        quote = match.group("quote")
        index = match.end()
        depth = 0
        field_start = index
        inner_quote = ""
        while index < len(source):
            char = source[index]
            if inner_quote:
                if char == "\\":
                    index += 2
                    continue
                if char == inner_quote:
                    inner_quote = ""
                index += 1
                continue
            if depth == 0:
                if char == "\\" and quote not in _TRIPLE:
                    index += 2
                    continue
                if source.startswith(quote, index):
                    break
                if char in "'\"":
                    inner_quote = char
                elif char == "{":
                    if index + 1 < len(source) and source[index + 1] == "{":
                        index += 2
                        continue
                    depth = 1
                    field_start = index + 1
            else:
                if char in "'\"":
                    inner_quote = char
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        field = source[field_start:index]
                        if "\\" in field:
                            line = source.count("\n", 0, field_start) + 1
                            offenders.append((line, field.strip()))
            index += 1
    return offenders


def test_no_backslash_inside_fstring_expressions():
    offenders: list[str] = []
    for path in _iter_python_files():
        source = path.read_text(encoding="utf-8")
        if "f'" not in source and 'f"' not in source:
            continue
        for line, field in fstring_fields_with_backslash(source):
            offenders.append(f"{path.relative_to(PLUGIN_SCRIPTS)}:{line}: {{{field}}}")
    assert not offenders, (
        "backslash inside an f-string expression requires Python 3.12+ but "
        f"scripts/pyproject.toml declares >=3.11: {offenders}"
    )


def test_the_scanner_actually_detects_the_original_defect():
    """Negative control: the guard must fail on the construct it exists for."""
    broken = 'x = f"  * {r.lstrip(\'#-*\\t \').strip()}"\n'
    assert fstring_fields_with_backslash(broken)
    healthy = 'rule = r.lstrip("#-*\\t ").strip()\nx = f"  * {rule}"\n'
    assert fstring_fields_with_backslash(healthy) == []


def test_declared_python_floor_matches_the_contract():
    """Guard the declaration itself: the floor must be the low bound, not raised silently."""
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
