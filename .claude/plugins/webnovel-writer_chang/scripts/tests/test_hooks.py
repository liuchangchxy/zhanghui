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


# --- check_chromium_prompt ---


@pytest.fixture
def chromium_setup():
    """Set up `import install_python_deps` and `from session_start import ...` correctly.

    Note: We patch `install_python_deps.<attr>` (top-level module) because that's
    what session_start.py's `from install_python_deps import ...` resolves to.
    `hooks.install_python_deps` would be a DIFFERENT module object — patching
    that name wouldn't affect what session_start sees.
    """
    hooks_dir = PLUGIN_ROOT / "hooks"
    if str(hooks_dir) not in sys.path:
        sys.path.insert(0, str(hooks_dir))
    if "install_python_deps" not in sys.modules:
        import install_python_deps  # noqa: F401
    if "session_start" not in sys.modules:
        import session_start  # noqa: F401
    from session_start import check_chromium_prompt
    import install_python_deps as ipd
    return check_chromium_prompt, ipd


def _fake_python_shim(venv: Path) -> None:
    """Create a fake bin/python that exits 0 — so is_venv_corrupted returns False."""
    py = venv / "bin" / "python"
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_text("#!/bin/sh\necho 3.11\nexit 0\n")
    py.chmod(0o755)


def _seed_chart_scan(plugin_root: Path, ipd, cache: Path) -> None:
    """Create plugin_root/skills/webnovel-chart-scan and a matching stamp + shim."""
    chart_scan = plugin_root / "skills" / "webnovel-chart-scan"
    chart_scan.mkdir(parents=True)
    (chart_scan / "pyproject.toml").write_text("[project]\n")
    venv = cache / "venvs" / "webnovel-chart-scan"
    venv.mkdir(parents=True, exist_ok=True)
    _fake_python_shim(venv)
    # Stamp must MATCH pyproject.toml content sha256 — else should_install_module
    # returns "stale stamp" and check_chromium_prompt returns None.
    expected = ipd.compute_install_stamp(chart_scan)
    (venv / ".install-stamp").write_text(expected + "\n")


def test_check_chromium_prompt_emits_when_stamp_present_no_marker(chromium_setup, monkeypatch, tmp_path):
    """Should emit prompt when chart-scan install is complete and no .chromium-prompted marker."""
    check_chromium_prompt, ipd = chromium_setup
    plugin_root = tmp_path / "plugin"
    cache = tmp_path / "cache"
    monkeypatch.setattr(ipd, "resolve_cache_dir", lambda: cache)
    _seed_chart_scan(plugin_root, ipd, cache)
    result = check_chromium_prompt(plugin_root)
    assert result is not None
    assert "fanqie adapter" in result


def test_check_chromium_prompt_suppresses_when_marker_yes(chromium_setup, monkeypatch, tmp_path):
    """Should not emit prompt when .chromium-prompted=yes exists."""
    check_chromium_prompt, ipd = chromium_setup
    plugin_root = tmp_path / "plugin"
    cache = tmp_path / "cache"
    monkeypatch.setattr(ipd, "resolve_cache_dir", lambda: cache)
    _seed_chart_scan(plugin_root, ipd, cache)
    (cache / "venvs" / "webnovel-chart-scan" / ".chromium-prompted").write_text("yes")
    assert check_chromium_prompt(plugin_root) is None


def test_check_chromium_prompt_suppresses_when_stamp_missing(chromium_setup, monkeypatch, tmp_path):
    """Should not emit prompt when chart-scan install not yet complete."""
    check_chromium_prompt, ipd = chromium_setup
    plugin_root = tmp_path / "plugin"
    cache = tmp_path / "cache"
    monkeypatch.setattr(ipd, "resolve_cache_dir", lambda: cache)
    # Skill exists but no venv / stamp — should_install_module returns "missing venv"
    chart_scan = plugin_root / "skills" / "webnovel-chart-scan"
    chart_scan.mkdir(parents=True)
    (chart_scan / "pyproject.toml").write_text("[project]\n")
    assert check_chromium_prompt(plugin_root) is None


def test_check_chromium_prompt_uses_custom_cache_dir(chromium_setup, monkeypatch, tmp_path):
    """Should resolve cache via resolve_cache_dir, not hardcoded ~/.cache path.

    Sets WEBNOVEL_CACHE_DIR to a tmp location and verifies the function finds
    the venv there — proving it does NOT hardcode ~/.cache/webnovel-writer-chang.
    """
    check_chromium_prompt, ipd = chromium_setup
    custom_cache = tmp_path / "custom-cache"
    monkeypatch.setenv("WEBNOVEL_CACHE_DIR", str(custom_cache))
    # Belt-and-suspenders: also make HOME point away from real ~/.cache
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    plugin_root = tmp_path / "plugin"
    _seed_chart_scan(plugin_root, ipd, custom_cache)
    result = check_chromium_prompt(plugin_root)
    assert result is not None
    assert "fanqie adapter" in result


def test_check_chromium_prompt_swallows_permission_error(chromium_setup, monkeypatch, tmp_path):
    """PermissionError from resolve_cache_dir should be swallowed (not crash hook)."""
    check_chromium_prompt, ipd = chromium_setup
    plugin_root = tmp_path / "plugin"

    def fake_raise(*args, **kwargs):
        raise PermissionError("WEBNOVEL_CACHE_DIR=... 不可写")

    monkeypatch.setattr(ipd, "resolve_cache_dir", fake_raise)
    # Should NOT raise
    assert check_chromium_prompt(plugin_root) is None
