#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read/write/validate chart-scan marked-references.json files.

Implements 2026-08-16-webnovel-deconstruct-standalone-design §D4.
"""

from __future__ import annotations

import json
from pathlib import Path


CURRENT_SCHEMA_VERSION = 1


def validate_marked_references(data: dict) -> dict:
    """Validate marked-references.json payload dict.

    Required schema:
      - schema_version == 1
      - references: list of {platform, title, author?, category?}

    Raises ValueError on any miss. Returns the input dict on success.
    """
    if not isinstance(data, dict):
        raise ValueError("marked-references.json must be a JSON object")

    if data.get("schema_version") != CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f"marked-references.json schema_version must be {CURRENT_SCHEMA_VERSION}, "
            f"got {data.get('schema_version')!r}"
        )

    references = data.get("references")
    if not isinstance(references, list):
        raise ValueError("marked-references.json references must be a list")

    for i, ref in enumerate(references):
        if not isinstance(ref, dict):
            raise ValueError(f"marked-references.json references[{i}] must be an object")
        # I1 fix: strict type/format validation — empty/whitespace/non-string must raise
        platform = ref.get("platform")
        if not isinstance(platform, str) or not platform.strip():
            raise ValueError(
                f"marked-references.json references[{i}] missing or invalid 'platform'"
            )
        title = ref.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(
                f"marked-references.json references[{i}] missing or invalid 'title'"
            )

    return data


def load_marked_references(path: Path) -> dict | None:
    """Load and validate marked-references.json from path.

    Returns the parsed dict, or None if file does not exist.
    Raises ValueError on schema mismatch.
    """
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return None
    raw = p.read_text(encoding="utf-8")
    data = json.loads(raw)
    return validate_marked_references(data)


def write_marked_references(payload: dict, path: Path) -> Path:
    """Validate and write marked-references.json to path.

    Returns the resolved path. Raises ValueError on schema mismatch.
    """
    validated = validate_marked_references(payload)
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(validated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return p
