#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Validate and enumerate reference_research trees under <project>/.webnovel/reference_research/.

Implements 2026-08-16-p0-full-p1-p2-adversarial-fixes-design I5.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union


REQUIRED_FILES = ("_schema.json", "report.md", "do_not_copy.md",
                  "canon_contamination_warnings.md", "_progress.json")


def validate_idea_bank_pointer(value: Union[str, None]) -> str:
    """Validate idea_bank.json.reference_research_path value.

    Rules:
      - Must be a non-empty string
      - Must be a relative path (not absolute)
      - Must not contain '..' components

    Returns the validated string. Raises ValueError on any miss.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"idea_bank.reference_research_path must be a string, got {type(value).__name__}"
        )
    if not value.strip():
        raise ValueError("idea_bank.reference_research_path must not be empty")
    p = Path(value)
    if p.is_absolute():
        raise ValueError(
            f"idea_bank.reference_research_path must not be absolute, got {value!r}"
        )
    if ".." in p.parts:
        raise ValueError(
            f"idea_bank.reference_research_path must not contain '..', got {value!r}"
        )
    return value


def scan_reference_research_trees(project_root: Path) -> list[Path]:
    """Scan <project_root>/.webnovel/reference_research/*/ for valid trees.

    Returns paths to subdirectories that contain ALL required files.
    Returns [] if the directory doesn't exist or contains no valid trees.
    Skips symlinks (defense in depth — primary check is in build_reference_tree).
    """
    root = Path(project_root).expanduser().resolve()
    base = root / ".webnovel" / "reference_research"
    if not base.is_dir():
        return []

    valid: list[Path] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir() or entry.is_symlink():
            continue
        if all((entry / name).is_file() for name in REQUIRED_FILES):
            valid.append(entry)
    return valid