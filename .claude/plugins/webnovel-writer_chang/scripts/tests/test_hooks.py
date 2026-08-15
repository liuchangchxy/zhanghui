#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import subprocess
import sys
from pathlib import Path

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[1].parent
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"
GUARD = PLUGIN_ROOT / "hooks" / "guard_runtime_write.py"
SESSION_START = PLUGIN_ROOT / "hooks" / "session_start.py"


# --- trigger_background_python_install ---


@pytest.fixture
def trigger_setup():
    """确保 install_python_deps 在 sys.modules 中并返回 trigger 函数。

    trigger_background_python_install 内部 `from install_python_deps import ...`
    会先查 sys.modules；如果测试在 tmp_path/hooks 放了 placeholder 文件，
    函数的 sys.path.insert 会让 placeholder 排在前面，但其 import 会复用
    这里已经缓存的真实模块，从而保证 monkeypatch 生效。
    """
    hooks_dir = PLUGIN_ROOT / "hooks"
    if str(hooks_dir) not in sys.path:
        sys.path.insert(0, str(hooks_dir))
    if "install_python_deps" not in sys.modules:
        import install_python_deps  # noqa: F401
    from session_start import trigger_background_python_install
    return trigger_background_python_install


def _run_guard(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_hooks_json_uses_plugin_wrapper_and_plugin_root_paths():
    payload = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))

    assert "description" in payload
    assert "hooks" in payload
    assert "SessionStart" in payload["hooks"]
    assert "PreToolUse" in payload["hooks"]
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "${CLAUDE_PLUGIN_ROOT}" in serialized
    assert "C:\\Users" not in serialized


def test_guard_blocks_direct_commit_file_write():
    proc = _run_guard(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": r"D:\book\.story-system\commits\chapter_001.commit.json"},
        }
    )

    assert proc.returncode == 2
    assert "permissionDecision" in proc.stderr


def test_guard_allows_direct_state_write():
    # issue #113: audit fixes need direct state.json edits; the guard no
    # longer blocks them.
    proc = _run_guard(
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": r"D:\book\.webnovel\state.json"},
        }
    )

    assert proc.returncode == 0


def test_guard_allows_bash_state_write():
    proc = _run_guard(
        {
            "tool_name": "Bash",
            "tool_input": {"command": 'python fix_state.py > "D:/book/.webnovel/state.json"'},
        }
    )

    assert proc.returncode == 0


def test_guard_still_blocks_index_db_write():
    proc = _run_guard(
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": r"D:\book\.webnovel\index.db"},
        }
    )

    assert proc.returncode == 2


def test_guard_allows_runtime_projection_command():
    proc = _run_guard(
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": 'python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" projections retry --chapter 3'
            },
        }
    )

    assert proc.returncode == 0


def test_guard_blocks_direct_chapter_commit_script_bypass():
    proc = _run_guard(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python scripts/chapter_commit.py --project-root book --chapter 3"},
        }
    )

    assert proc.returncode == 2


def test_session_start_can_be_disabled(monkeypatch):
    monkeypatch.setenv("WEBNOVEL_DISABLE_SESSION_STATUS_HOOK", "1")
    proc = subprocess.run(
        [sys.executable, str(SESSION_START)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert proc.returncode == 0
    assert proc.stdout == ""


def test_trigger_silent_when_install_script_missing(trigger_setup, tmp_path):
    """trigger_background_python_install should silently skip when install_python_deps.py doesn't exist."""
    # tmp_path has no hooks/install_python_deps.py
    (tmp_path / "skills" / "fake").mkdir(parents=True)
    (tmp_path / "skills" / "fake" / "pyproject.toml").write_text("[project]")
    # Should not raise
    trigger_setup(tmp_path)


def test_trigger_silent_when_no_pending(trigger_setup, monkeypatch, tmp_path):
    """If no modules need install, no fork should happen."""
    popen_calls = []
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: popen_calls.append(a) or None)
    trigger_setup(tmp_path)
    assert popen_calls == []  # no fork needed


def test_trigger_silent_when_no_skills(trigger_setup, monkeypatch, tmp_path):
    """Empty plugin root: no fork."""
    popen_calls = []
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: popen_calls.append(a) or None)
    trigger_setup(tmp_path)
    assert popen_calls == []


def test_trigger_swallows_popen_oserror(trigger_setup, monkeypatch, tmp_path, capfd):
    """If Popen raises OSError, function should swallow and not crash."""
    import install_python_deps as ipd

    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "install_python_deps.py").write_text("# placeholder")
    (tmp_path / "skills" / "fake").mkdir(parents=True)
    (tmp_path / "skills" / "fake" / "pyproject.toml").write_text("[project]")
    # Make should_install_module return "missing venv" so we'd fork
    monkeypatch.setattr(ipd, "should_install_module", lambda m: "missing venv")
    monkeypatch.setattr(ipd, "find_python_modules", lambda r: [tmp_path / "skills" / "fake"])
    # Make Popen raise
    def fake_popen(*args, **kwargs):
        raise OSError("Resource temporarily unavailable")
    monkeypatch.setattr("subprocess.Popen", fake_popen)
    # Should NOT raise
    trigger_setup(tmp_path)
    # Should have logged to stderr
    captured = capfd.readouterr()
    assert "Popen failed" in captured.err


def test_trigger_none_plugin_root(trigger_setup):
    """plugin_root=None should silently skip (no exception)."""
    trigger_setup(None)  # should not raise


def test_trigger_popen_args(trigger_setup, monkeypatch, tmp_path):
    """Verify the exact argv passed to Popen."""
    import install_python_deps as ipd

    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "install_python_deps.py").write_text("# placeholder")
    (tmp_path / "skills" / "fake").mkdir(parents=True)
    (tmp_path / "skills" / "fake" / "pyproject.toml").write_text("[project]")
    monkeypatch.setattr(ipd, "should_install_module", lambda m: "missing venv")
    monkeypatch.setattr(ipd, "find_python_modules", lambda r: [tmp_path / "skills" / "fake"])
    popen_calls = []
    def fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return None
    monkeypatch.setattr("subprocess.Popen", fake_popen)
    trigger_setup(tmp_path)
    assert len(popen_calls) == 1
    argv, kwargs = popen_calls[0]
    # argv[0] is the program name (sys.executable), argv[1:] is the args
    assert len(argv) == 1
    args = argv[0]
    assert len(args) == 4
    assert args[0] == sys.executable
    assert args[1].endswith("install_python_deps.py")
    assert args[2] == "--plugin-root"
    assert args[3] == str(tmp_path)
    assert kwargs.get("start_new_session") is True
    assert kwargs.get("close_fds") is True
