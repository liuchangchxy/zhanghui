#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime guardrail: block direct writes / bypasses of Story System read-model files.

Design note (why this file is a classifier and not a shell parser):
The guard used to decide purely by substring match — any Bash command that mentioned
`<project>/.webnovel/index.db` *and* the word `python3` was denied. That caught the
Skill's own read-only `changes_gate.py ... --db .webnovel/index.db --json` call and
forced people to work around their own guardrail with relative paths.

The replacement keeps the same protection surface but classifies commands explicitly:

  * known official **read-only** invocations  -> allow
  * known official **controlled-write** entry points (webnovel.py / chapter-commit /
    write-gate / projections retry|replay)    -> allow
  * direct writes to protected files (redirect, rm/cp/mv/tee/dd onto them, Editor
    tools pointed at them)                    -> deny
  * compound commands (pipes / `;` / `&&` / redirection / `$( )`) -> conservative
    substring heuristic, so a legal fragment cannot smuggle a write that follows it
  * anything else                             -> allow (unchanged legacy surface)

This is a guardrail against accidental self-inflicted damage, not a sandbox: it does not
resolve environment variables and does not attempt to model arbitrary shell semantics.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


DISABLE_ENV = "WEBNOVEL_DISABLE_RUNTIME_GUARD_HOOK"
# state.json is intentionally NOT protected: audits routinely require bulk
# fixes that update_state.py flags cannot express, and state.json has its own
# backup + rebuild path (issue #113).
PROTECTED_SUFFIXES = (
    ".story-system/commits/",
    ".webnovel/index.db",
    ".webnovel/vectors.db",
    ".webnovel/memory_scratchpad.json",
    ".webnovel/projection_log.jsonl",
)

# `webnovel.py` is the sanctioned entry point for every controlled write.
RUNTIME_ENTRY_SCRIPTS = ("webnovel.py", "chapter_commit.py")
RUNTIME_SUBCOMMAND_MARKERS = (
    "chapter-commit",
    "write-gate",
    "projections",
    "runtime",
)

# Official scripts that only *read* protected files. Their invocations never write
# the read model, so the Skill must be able to run them verbatim.
OFFICIAL_READONLY_SCRIPTS = frozenset(
    {
        "changes_gate.py",
        "reconcile_changes.py",
        "check_plan_artifacts.py",
        "extract_chapter_context.py",
        "prepare_data_agent_input.py",
        "status_reporter.py",
        "story_craft.py",
        "rejection_contract.py",
        "validate_plugin_package.py",
        "quality_trend_report.py",
        "chapter_outline_loader.py",
        "chapter_paths.py",
        "project_locator.py",
    }
)

# Flags whose value is a write target. If one of them names a protected file we deny,
# even inside an otherwise-official invocation.
_OUTPUT_FLAGS = frozenset({"--output", "--out", "-o", "--target", "--dest", "--destination"})

# Commands that write their path arguments in place.
_INPLACE_WRITE_COMMANDS = frozenset(
    {"rm", "unlink", "mv", "cp", "dd", "truncate", "tee", "install", "ln", "shred"}
)

# Shell metacharacters that make a command "compound". For these we fall back to the
# conservative substring heuristic so that a legal fragment cannot whitelist a write
# glued onto it.
_COMPOUND_RE = re.compile(r"[|;&<>`\n\r]|\$\(")

# NOTE: `>` / `>>` deliberately carry no leading word boundary — `echo x > db` has a space
# before the redirect, and anchoring on a word boundary silently missed it, so a plain
# `echo x > <project>/.webnovel/index.db` used to sail straight through.
_LEGACY_WRITE_TOKEN_RE = re.compile(
    r"(>>?|\bout-file\b|\bset-content\b|\badd-content\b|\bcopy-item\b|\bmove-item\b"
    r"|\bpython3?\b|\btee\b|\bdd\b)",
    re.IGNORECASE,
)

_PYTHON_BASENAMES = re.compile(r"^(python|python3|python3\.\d+|py)$", re.IGNORECASE)
_ENV_PREFIX_COMMANDS = frozenset({"env", "command", "nohup", "time", "exec"})
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _load_input() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalized_path(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = raw.replace("\\", "/")
    try:
        if ":" in raw[:3]:
            raw = PureWindowsPath(str(value)).as_posix()
        else:
            raw = PurePosixPath(raw).as_posix()
    except Exception:
        pass
    return raw.lower()


def _deny(message: str) -> int:
    payload = {
        "hookSpecificOutput": {"permissionDecision": "deny"},
        "systemMessage": message,
    }
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
    return 2


def _tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("tool_input") or payload.get("toolInput") or payload.get("input") or {}
    return value if isinstance(value, dict) else {}


def _tool_name(payload: dict[str, Any]) -> str:
    return str(payload.get("tool_name") or payload.get("toolName") or payload.get("tool") or "").strip()


def _file_path_from_tool_input(tool_input: dict[str, Any]) -> str:
    for key in ("file_path", "path", "filename"):
        value = tool_input.get(key)
        if value:
            return str(value)
    return ""


def _is_protected_path(path: str) -> bool:
    normalized = _normalized_path(path)
    if not normalized:
        return False
    return any(suffix in normalized for suffix in PROTECTED_SUFFIXES)


def _looks_like_direct_projection_write(command: str) -> bool:
    """Conservative heuristic for compound / unrecognised commands (legacy behaviour)."""
    lowered = command.lower().replace("\\", "/")
    protected_hit = any(suffix in lowered for suffix in PROTECTED_SUFFIXES)
    if protected_hit and _LEGACY_WRITE_TOKEN_RE.search(lowered):
        return True
    if "chapter_commit.py" in lowered and "webnovel.py" not in lowered:
        return True
    return False


def _is_compound(command: str) -> bool:
    return bool(_COMPOUND_RE.search(command))


def _tokenize(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return []


def _strip_command_prefix(tokens: list[str]) -> list[str]:
    """Drop leading `env`-style wrappers and `VAR=value` assignments."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if _ASSIGNMENT_RE.match(token):
            index += 1
            continue
        if os.path.basename(token).lower() in _ENV_PREFIX_COMMANDS:
            index += 1
            continue
        break
    return tokens[index:]


def _script_basename(tokens: list[str]) -> str:
    """Basename of the first python script argument, if the command is a python invocation."""
    if not tokens:
        return ""
    executable = os.path.basename(tokens[0]).lower()
    if not _PYTHON_BASENAMES.match(executable):
        return ""
    for token in tokens[1:]:
        if token == "-m":
            # `python -m <module>` is not an official entry point.
            return ""
        if token.startswith("-"):
            continue
        return os.path.basename(token)
    return ""


def _output_flag_values(tokens: list[str]) -> list[str]:
    values: list[str] = []
    for index, token in enumerate(tokens):
        if token in _OUTPUT_FLAGS and index + 1 < len(tokens):
            values.append(tokens[index + 1])
            continue
        for flag in _OUTPUT_FLAGS:
            prefix = f"{flag}="
            if token.startswith(prefix):
                values.append(token[len(prefix):])
    return values


def _writes_protected_target(tokens: list[str]) -> bool:
    if any(_is_protected_path(value) for value in _output_flag_values(tokens)):
        return True
    if not tokens:
        return False
    executable = os.path.basename(tokens[0]).lower()
    if executable in _INPLACE_WRITE_COMMANDS:
        return any(_is_protected_path(token) for token in tokens[1:])
    return False


def _is_official_invocation(tokens: list[str]) -> bool:
    """True when the command is a single, recognised official invocation of a plugin script."""
    script = _script_basename(tokens)
    if not script:
        return False
    if script in OFFICIAL_READONLY_SCRIPTS:
        return True
    if script in RUNTIME_ENTRY_SCRIPTS:
        return True
    return False


def classify_command(command: str) -> str:
    """Classify a Bash command string.

    Returns one of: "official_readonly", "official_runtime", "direct_write", "unknown".
    """
    if not command.strip():
        return "unknown"

    if _is_compound(command):
        if _looks_like_direct_projection_write(command):
            return "direct_write"
        return "unknown"

    tokens = _strip_command_prefix(_tokenize(command))
    if not tokens:
        return "unknown"

    if _writes_protected_target(tokens):
        return "direct_write"

    script = _script_basename(tokens)
    if script in OFFICIAL_READONLY_SCRIPTS:
        return "official_readonly"

    if script in RUNTIME_ENTRY_SCRIPTS:
        lowered = [token.lower() for token in tokens]
        if any(marker in lowered for marker in RUNTIME_SUBCOMMAND_MARKERS):
            return "official_runtime"
        # `webnovel.py <other-subcommand> ...` is still the sanctioned entry point.
        if script == "webnovel.py":
            return "official_runtime"

    if _looks_like_direct_projection_write(command):
        return "direct_write"
    return "unknown"


def _decide_bash(command: str) -> int:
    decision = classify_command(command)
    if decision == "direct_write":
        return _deny(
            "webnovel-writer blocked a direct write or bypass command for Story System/read-model "
            "files. Use webnovel.py write-gate, chapter-commit, or projections retry/replay instead."
        )
    return 0


def main() -> int:
    if _truthy(os.environ.get(DISABLE_ENV)):
        return 0

    payload = _load_input()
    tool_input = _tool_input(payload)
    tool = _tool_name(payload)

    command = str(tool_input.get("command") or "")
    if tool.lower() == "bash" or command:
        return _decide_bash(command)

    path = _file_path_from_tool_input(tool_input)
    if _is_protected_path(path):
        return _deny(
            "webnovel-writer blocked a direct edit to Story System/read-model files. Use runtime "
            "commands so commit/projection invariants stay consistent."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
