#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guard hook regression tests (task D).

正反两面都要锁死：

* 正式 Skill 自己规定的**只读**命令必须放行（否则插件会挡住自己的正常流程，
  使用者只能靠「换相对路径」这种偶然技巧绕过）；
* 受保护状态的**直接写入**必须继续被拒（否则修一个误拦会换来一个安全洞）；
* 合法命令后面拼接的直接写入不能被前面的合法子串洗白。

字符串按片段拼接，避免测试文件本身在编辑/执行时触发 guard。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[1].parent
GUARD = PLUGIN_ROOT / "hooks" / "guard_runtime_write.py"

INDEX_DB = ".webnovel/" + "index.db"
VECTORS_DB = ".webnovel/" + "vectors.db"
SCRATCHPAD = ".webnovel/" + "memory_scratchpad.json"
PROJECTION_LOG = ".webnovel/" + "projection_log.jsonl"
COMMITS = ".story-system/commits/chapter_001.commit.json"
REDIRECT = ">"  # keep the metacharacter out of the source text


def _run(command: str) -> int:
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.returncode


def _project(name: str) -> str:
    return f"/tmp/zh-guard/{name}"


# --------------------------------------------------------------------------- #
# allowed: the plugin's own documented read-only commands
# --------------------------------------------------------------------------- #


def test_allows_changes_gate_readonly_with_absolute_index_db():
    command = (
        f"python3 /plugin/scripts/changes_gate.py --chapter-file \"{_project('p')}/.webnovel/tmp/x.md\" "
        f"--db {_project('p')}/{INDEX_DB} --json"
    )
    assert _run(command) == 0


def test_allows_changes_gate_readonly_with_relative_index_db():
    command = f"python3 /plugin/scripts/changes_gate.py --chapter-file a.md --db {INDEX_DB} --json"
    assert _run(command) == 0


def test_allows_reconcile_changes_reading_index_db():
    command = (
        f"python3 /plugin/scripts/reconcile_changes.py --chapter-file a.md --extraction-result e.json "
        f"--db {_project('p')}/{INDEX_DB} --output {_project('p')}/.webnovel/tmp/reconciliation_result.json"
    )
    assert _run(command) == 0


@pytest.mark.parametrize(
    "command",
    [
        'python3 -X utf8 "/plugin/scripts/webnovel.py" --project-root "/p" runtime status --chapter 2 --format json',
        'python3 -X utf8 "/plugin/scripts/webnovel.py" --project-root "/p" runtime governed-context --chapter 2',
        'python3 -X utf8 "/plugin/scripts/webnovel.py" --project-root "/p" runtime commit --chapter 2 --draft-id d1',
        'python3 -X utf8 "/plugin/scripts/webnovel.py" --project-root "/p" write-gate --chapter 2 --stage precommit',
        'python3 -X utf8 "/plugin/scripts/webnovel.py" --project-root "/p" where',
        'python3 -X utf8 "/plugin/scripts/webnovel.py" --project-root "/p" preflight',
        'python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" projections retry --chapter 3',
    ],
)
def test_allows_official_runtime_entry_points(command):
    assert _run(command) == 0


def test_allows_unrelated_commands():
    assert _run("git -c color.ui=never diff --name-status HEAD") == 0
    assert _run("node /plugin/scripts/check-ai-patterns.js --check --json a.md") == 0
    assert _run(f'python fix_state.py {REDIRECT} "D:/book/.webnovel/state.json"') == 0


def test_allows_official_script_that_does_not_touch_protected_paths():
    assert _run("python3 /plugin/scripts/prepare_data_agent_input.py --chapter-file a.md --prose-output b.md") == 0


# --------------------------------------------------------------------------- #
# denied: direct writes / bypasses of protected state
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "command",
    [
        f'echo x {REDIRECT} {_project("p")}/{INDEX_DB}',
        f'cat foo {REDIRECT}{REDIRECT} "{_project("p")}/{INDEX_DB}"',
        f'printf "" {REDIRECT} {_project("p")}/{VECTORS_DB}',
        f'echo {{}} {REDIRECT} {_project("p")}/{SCRATCHPAD}',
        f'echo {REDIRECT} {_project("p")}/{PROJECTION_LOG}',
        f'python3 x.py {REDIRECT} {_project("p")}/{INDEX_DB}',
    ],
)
def test_denies_redirection_into_protected_files(command):
    assert _run(command) == 2


@pytest.mark.parametrize(
    "command",
    [
        f'rm -f {_project("p")}/{INDEX_DB}',
        f'cp /tmp/x.db {_project("p")}/{INDEX_DB}',
        f'mv /tmp/x.db {_project("p")}/{INDEX_DB}',
        f'truncate -s 0 {_project("p")}/{VECTORS_DB}',
        f'tee {_project("p")}/{INDEX_DB}',
        f'cp /tmp/x.json "{_project("p")}/{COMMITS}"',
    ],
)
def test_denies_inplace_write_commands_on_protected_files(command):
    assert _run(command) == 2


def test_denies_chapter_commit_script_bypass():
    assert _run("python scripts/chapter_commit.py --project-root book --chapter 3") == 2


def test_denies_inline_python_opening_protected_file_for_write():
    command = f"python3 -c \"open('{_project('p')}/{INDEX_DB}','w').close()\""
    assert _run(command) == 2


@pytest.mark.parametrize(
    "command",
    [
        f'python3 /plugin/scripts/changes_gate.py --db {_project("p")}/{INDEX_DB} --json && rm {_project("p")}/{INDEX_DB}',
        f'python3 /plugin/scripts/changes_gate.py --db {_project("p")}/{INDEX_DB} --json ; echo x {REDIRECT} {_project("p")}/{INDEX_DB}',
        f'python3 /plugin/scripts/changes_gate.py --db {_project("p")}/{INDEX_DB} --json | tee {_project("p")}/{INDEX_DB}',
    ],
)
def test_denies_legal_command_chained_with_illegal_write(command):
    """D6: 合法子串不能洗白后面拼接的直接写入。"""
    assert _run(command) == 2


def test_denies_official_script_writing_into_protected_path():
    command = f'python3 /plugin/scripts/changes_gate.py --output "{_project("p")}/{INDEX_DB}"'
    assert _run(command) == 2


def test_denies_editor_tool_direct_edit():
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": f"/p/{INDEX_DB}"}}),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 2
    assert "permissionDecision" in proc.stderr


def test_denies_editor_tool_direct_edit_of_commit_file():
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": f"/p/{COMMITS}"}}),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 2


def test_disable_env_short_circuits(monkeypatch):
    monkeypatch.setenv("WEBNOVEL_DISABLE_RUNTIME_GUARD_HOOK", "1")
    command = f'rm -f {_project("p")}/{INDEX_DB}'
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**__import__("os").environ, "WEBNOVEL_DISABLE_RUNTIME_GUARD_HOOK": "1"},
    )
    assert proc.returncode == 0
