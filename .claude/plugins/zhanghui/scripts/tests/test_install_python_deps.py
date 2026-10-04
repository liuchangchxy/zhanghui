"""install_python_deps.py 的单元测试。"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _make_healthy_venv(venv: Path) -> None:
    """Create a fake bin/python so ``is_venv_corrupted`` returns False.

    Tests that exercise stamp logic (missing/stale/ok/corrupt-stamp) want a
    structurally valid venv — only the .install-stamp varies. A real venv
    always has bin/python; absence is the corrupted-venv case (tested by the
    is_venv_corrupted_* tests below).
    """
    fake_py = venv / "bin" / "python"
    fake_py.parent.mkdir(parents=True, exist_ok=True)
    fake_py.write_text("#!/bin/sh\nexit 0\n")
    fake_py.chmod(0o755)


# 让 hooks/ 包能从 tests 目录被发现：hooks/ 在 zhanghui/hooks/，
# 需要把 zhanghui/ 加进 sys.path。
_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


# --- compute_install_stamp ---

def test_compute_install_stamp_returns_sha256(tmp_path):
    from hooks.install_python_deps import compute_install_stamp
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    expected = hashlib.sha256(b"[project]\nname='x'\n").hexdigest()
    assert compute_install_stamp(tmp_path) == expected


def test_compute_install_stamp_includes_requirements_txt(tmp_path):
    from hooks.install_python_deps import compute_install_stamp
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "requirements.txt").write_text("foo>=1.0\n")
    base = hashlib.sha256(b"[project]\n").hexdigest()
    with_reqs = compute_install_stamp(tmp_path)
    assert with_reqs != base
    assert len(with_reqs) == 64  # sha256 hex
    # Exact value pins the iteration order — if implementation reorders (pyproject, requirements) vs (requirements, pyproject),
    # stamp value changes and existing venvs get re-installed. Catch this contract.
    expected = hashlib.sha256(b"[project]\n" + b"foo>=1.0\n").hexdigest()
    assert with_reqs == expected


# --- select_uv_binary ---

def test_select_uv_binary_darwin_arm64(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    from hooks.install_python_deps import select_uv_binary
    vendor_dir = tmp_path / "uv"
    binary = select_uv_binary(vendor_dir)
    assert binary.name == "uv-darwin-arm64"
    assert binary.parent == vendor_dir


def test_select_uv_binary_linux_x86_64(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    from hooks.install_python_deps import select_uv_binary
    binary = select_uv_binary(tmp_path)
    assert binary.name == "uv-linux-x86_64"


def test_select_uv_binary_windows_x86_64(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("platform.machine", lambda: "AMD64")
    from hooks.install_python_deps import select_uv_binary
    binary = select_uv_binary(tmp_path)
    assert binary.name == "uv-windows-x86_64.exe"


def test_select_uv_binary_unsupported_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "powerpc")
    from hooks.install_python_deps import select_uv_binary
    with pytest.raises(RuntimeError, match="找不到匹配的 uv"):
        select_uv_binary(tmp_path)


# --- resolve_cache_dir ---

# Skip chmod-based tests on Windows (chmod semantics differ)
_skip_unix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="chmod-based unwritable tests are Unix-only",
)


def test_resolve_cache_dir_uses_expanduser(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("WEBNOVEL_CACHE_DIR", raising=False)
    from hooks.install_python_deps import resolve_cache_dir
    cache = resolve_cache_dir()
    assert cache == tmp_path / ".cache" / "webnovel-writer-chang"


def test_resolve_cache_dir_env_override(monkeypatch, tmp_path):
    custom = tmp_path / "custom"
    monkeypatch.setenv("WEBNOVEL_CACHE_DIR", str(custom))
    from hooks.install_python_deps import resolve_cache_dir
    assert resolve_cache_dir() == custom


def test_resolve_cache_dir_creates_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("WEBNOVEL_CACHE_DIR", raising=False)
    from hooks.install_python_deps import resolve_cache_dir
    cache = resolve_cache_dir()
    assert cache.exists()
    assert cache.is_dir()


@_skip_unix_only
def test_resolve_cache_dir_fallback_when_default_unwritable(monkeypatch, tmp_path):
    """如果 ~/.cache 不可写，应该 fallback 到下一个候选。

    注意：chmod 555 在 leaf 已存在时，mkdir(exist_ok=True) 不会失败；
    所以必须 chmod 在 PARENT (.cache/) 上，这样 mkdir 想创建
    webnovel-writer-chang/ 时会因为父目录不可写而 PermissionError。
    """
    unwritable_home = tmp_path / "home"
    unwritable_home.mkdir()
    # Pre-create the parent .cache/ and lock it
    cache_parent = unwritable_home / ".cache"
    cache_parent.mkdir()
    # Do NOT pre-create the leaf — we want mkdir to fail trying to create it
    os.chmod(cache_parent, 0o555)

    monkeypatch.setenv("HOME", str(unwritable_home))
    monkeypatch.setenv("USERPROFILE", str(unwritable_home))
    monkeypatch.delenv("WEBNOVEL_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")  # skip mac fallback; use linux xdg path
    # Point cwd somewhere safe + writable so .webnovel/venv fallback can succeed
    safe_cwd = tmp_path / "safe_cwd"
    safe_cwd.mkdir()
    monkeypatch.setattr("hooks.install_python_deps.Path.cwd", lambda: safe_cwd)

    try:
        from hooks.install_python_deps import resolve_cache_dir
        result = resolve_cache_dir()
        # Should NOT be the locked-down default — must fall through
        assert result != cache_parent / "webnovel-writer-chang", \
            f"expected fallback, but got {result}"
    finally:
        os.chmod(cache_parent, 0o755)  # restore for cleanup


@_skip_unix_only
def test_resolve_cache_dir_env_override_unwritable_raises(monkeypatch, tmp_path):
    """用户显式 WEBNOVEL_CACHE_DIR 但不可写 → 直接报错（不 fallback）。

    chmod 555 必须放在 parent 上而不是 leaf——leaf 已存在时 mkdir(exist_ok=True)
    不会失败。
    """
    parent = tmp_path / "readonly_parent"
    parent.mkdir()
    inner = parent / "cache"  # doesn't exist
    os.chmod(parent, 0o555)

    monkeypatch.setenv("WEBNOVEL_CACHE_DIR", str(inner))

    try:
        from hooks.install_python_deps import resolve_cache_dir
        with pytest.raises(PermissionError, match="WEBNOVEL_CACHE_DIR"):
            resolve_cache_dir()
    finally:
        os.chmod(parent, 0o755)


@_skip_unix_only
def test_resolve_cache_dir_all_unwritable_raises(monkeypatch, tmp_path):
    """全部 fallback 都失败 → raise PermissionError 提示 export WEBNOVEL_CACHE_DIR。

    每个候选的 *parent* 都要锁住，mkdir(exist_ok=True) 才能真的 PermissionError。
    """
    unwritable_home = tmp_path / "home"
    unwritable_home.mkdir()

    # Lock ~/.cache/ — leaf won't be created, so we lock the parent
    cache_parent = unwritable_home / ".cache"
    cache_parent.mkdir()
    os.chmod(cache_parent, 0o555)

    # Lock $XDG_CACHE_HOME/ — same trick
    xdg_parent = unwritable_home / "xdg"
    xdg_parent.mkdir()
    os.chmod(xdg_parent, 0o555)

    # Lock cwd so .webnovel/ can't be created
    locked_cwd = tmp_path / "locked_cwd"
    locked_cwd.mkdir()
    os.chmod(locked_cwd, 0o555)

    monkeypatch.setenv("HOME", str(unwritable_home))
    monkeypatch.setenv("USERPROFILE", str(unwritable_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_parent))
    monkeypatch.delenv("WEBNOVEL_CACHE_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("hooks.install_python_deps.Path.cwd", lambda: locked_cwd)

    try:
        from hooks.install_python_deps import resolve_cache_dir
        with pytest.raises(PermissionError, match="WEBNOVEL_CACHE_DIR"):
            resolve_cache_dir()
    finally:
        os.chmod(cache_parent, 0o755)
        os.chmod(xdg_parent, 0o755)
        os.chmod(locked_cwd, 0o755)


# --- should_install_module ---

def test_should_install_module_no_venv(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    from hooks.install_python_deps import should_install_module
    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\n")
    assert should_install_module(module) == "missing venv"


def test_should_install_module_stale_stamp(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    from hooks.install_python_deps import should_install_module, compute_install_stamp
    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='x'\n")
    venv = tmp_path / "cache" / "venvs" / "m"
    venv.mkdir(parents=True)
    _make_healthy_venv(venv)
    (venv / ".install-stamp").write_text("stale-stamp-not-matching\n")
    assert should_install_module(module).startswith("stale stamp")


def test_should_install_module_up_to_date(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    from hooks.install_python_deps import should_install_module, compute_install_stamp
    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='x'\n")
    venv = tmp_path / "cache" / "venvs" / "m"
    venv.mkdir(parents=True)
    _make_healthy_venv(venv)
    stamp = compute_install_stamp(module)
    (venv / ".install-stamp").write_text(stamp + "\n")
    assert should_install_module(module) == "ok"


def test_should_install_module_missing_stamp(tmp_path, monkeypatch):
    from hooks.install_python_deps import should_install_module
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='x'\n")
    venv = tmp_path / "cache" / "venvs" / "m"
    venv.mkdir(parents=True)
    _make_healthy_venv(venv)
    # Deliberately do NOT create .install-stamp
    assert should_install_module(module) == "missing stamp"


@pytest.mark.parametrize("stamp_content", [
    "",                    # empty file
    "   \n",               # whitespace only
    "valid-stamp\r\n",     # Windows CRLF (should still work via .strip())
    "valid-stamp",         # no trailing newline
])
def test_should_install_module_stamp_content_variants(tmp_path, monkeypatch, stamp_content):
    """Verify stamp file content variants are handled correctly."""
    from hooks.install_python_deps import should_install_module, compute_install_stamp
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='x'\n")
    venv = tmp_path / "cache" / "venvs" / "m"
    venv.mkdir(parents=True)
    _make_healthy_venv(venv)
    (venv / ".install-stamp").write_text(stamp_content)
    result = should_install_module(module)
    # Either matches (ok) or is stale stamp — never missing stamp (file exists)
    assert result != "missing stamp"
    assert result != "missing venv"
    # If stamp_content (after strip) matches expected, should be ok
    expected = compute_install_stamp(module)
    if stamp_content.strip() == expected:
        assert result == "ok"
    else:
        assert result.startswith("stale stamp")


def test_should_install_module_corrupt_stamp_does_not_crash(tmp_path, monkeypatch):
    """Corrupted stamp (non-UTF-8 bytes) should not crash the function."""
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    from hooks.install_python_deps import should_install_module
    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='x'\n")
    venv = tmp_path / "cache" / "venvs" / "m"
    venv.mkdir(parents=True)
    _make_healthy_venv(venv)
    # Write non-UTF-8 bytes directly
    (venv / ".install-stamp").write_bytes(b"\xff\xfe\xfd")
    # Should NOT raise UnicodeDecodeError after the fix
    result = should_install_module(module)
    # Should be classified as stale stamp (content doesn't match expected)
    assert result.startswith("stale stamp")


@pytest.mark.parametrize("platform,venv_python_path", [
    ("linux", "bin/python"),
    ("darwin", "bin/python"),
    ("win32", "Scripts/python.exe"),
])
def test_should_install_module_corrupted_venv_deletes_and_returns_corrupted(
    tmp_path, monkeypatch, platform, venv_python_path
):
    """corrupted venv (missing python binary) → nuke + 'corrupted venv' (cross-platform)."""
    monkeypatch.setattr(sys, "platform", platform)
    from hooks.install_python_deps import should_install_module
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='x'\n")
    venv = tmp_path / "cache" / "venvs" / "m"
    venv.mkdir(parents=True)
    # Create the parent dir (bin/ or Scripts/) but NOT the python binary — that's
    # the corrupted-venv state after our existence-only is_venv_corrupted refactor.
    (venv / venv_python_path).parent.mkdir(parents=True)
    # Optionally add a fresh stamp to verify nuke removes EVERYTHING (not just bin/)
    (venv / ".install-stamp").write_text("stale-stamp-should-be-deleted")

    result = should_install_module(module)
    assert result == "corrupted venv"

    # Verify venv was deleted (nuke_venv should have removed the whole dir)
    assert not venv.exists()


# --- find_python_modules ---

def test_find_python_modules_finds_pyproject_toml(tmp_path):
    from hooks.install_python_deps import find_python_modules
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "chart-scan").mkdir()
    (tmp_path / "skills" / "chart-scan" / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "skills" / "write").mkdir()  # no pyproject → ignore
    (tmp_path / "dashboard").mkdir()
    (tmp_path / "dashboard" / "pyproject.toml").write_text("[project]\n")
    modules = find_python_modules(tmp_path)
    names = sorted(m.name for m in modules)
    assert names == ["chart-scan", "dashboard"]


# --- install_module ---

def test_install_module_creates_venv_and_stamp(tmp_path, monkeypatch):
    """集成测试：mock uv subprocess 调用，验证 venv + stamp 创建。"""
    from hooks import install_python_deps as ipd
    monkeypatch.setattr(ipd, "resolve_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    fake_uv_calls = []

    def fake_uv_run(argv, **kwargs):
        fake_uv_calls.append(argv)
        # 模拟 uv venv 创建目录
        if "venv" in argv:
            venv_idx = argv.index("venv") + 1
            Path(argv[venv_idx]).mkdir(parents=True, exist_ok=True)
            # 创建 site-packages 父目录
            (Path(argv[venv_idx]) / "lib" / "site-packages").mkdir(parents=True, exist_ok=True)
            (Path(argv[venv_idx]) / "lib" / "site-packages" / "foo.py").write_text("# ok")
        return type("R", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(ipd.subprocess, "run", fake_uv_run)

    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='m'\n")
    ipd.install_module(module)

    venv = tmp_path / "cache" / "venvs" / "m"
    assert venv.exists()
    assert (venv / ".install-stamp").exists()
    assert (venv / ".install-stamp").read_text().strip() == ipd.compute_install_stamp(module)
    assert len(fake_uv_calls) == 2  # uv venv + uv pip install


def test_install_module_failure_writes_log(tmp_path, monkeypatch):
    """uv 失败的场景：写 log + 尝试多 URL。"""
    from hooks import install_python_deps as ipd
    monkeypatch.setattr(ipd, "resolve_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))

    def fake_uv_fail(argv, **kwargs):
        # uv venv 成功；uv pip install 失败（这才触发目标 RuntimeError 消息）
        if "pip" in argv:
            return type("R", (), {"returncode": 1, "stderr": "ERROR: package 'foo' not found"})()
        return type("R", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(ipd.subprocess, "run", fake_uv_fail)
    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='m'\n")

    with pytest.raises(RuntimeError, match="uv pip install"):
        ipd.install_module(module)

    venv = tmp_path / "cache" / "venvs" / "m"
    assert not (venv / ".install-stamp").exists()

    # Log file present with attempt history
    logs = tmp_path / "cache" / "logs"
    log_files = list(logs.glob("install-m-*.log"))
    assert len(log_files) == 1
    log_content = log_files[0].read_text()
    # Should have attempted multiple URLs (PyPI + TUNA + aliyun at minimum)
    assert "attempt" in log_content
    assert "ERROR: package 'foo' not found" in log_content


def test_install_module_missing_uv_raises_runtime_error(tmp_path, monkeypatch):
    """uv 二进制不存在 → RuntimeError (不是 FileNotFoundError)。"""
    from hooks import install_python_deps as ipd
    # Point CLAUDE_PLUGIN_ROOT at a path with NO vendor/uv/ to force missing-binary
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "no-such-plugin"))
    monkeypatch.setattr(ipd, "resolve_cache_dir", lambda: tmp_path / "cache")

    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='m'\n")

    with pytest.raises(RuntimeError, match="uv 二进制不存在"):
        ipd.install_module(module)

    # No stamp should be written
    venv = tmp_path / "cache" / "venvs" / "m"
    assert not (venv / ".install-stamp").exists()

    # Log file should be written
    logs = tmp_path / "cache" / "logs"
    log_files = list(logs.glob("install-m-*.log"))
    assert len(log_files) == 1


def test_install_module_venv_timeout_raises_runtime_error(tmp_path, monkeypatch):
    """uv venv 超时 → 写 log + 抛 RuntimeError（spec §4.6.5 logging-on-failure）。"""
    from hooks import install_python_deps as ipd
    monkeypatch.setattr(ipd, "resolve_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))

    def fake_uv_timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv[0] if argv else "uv", timeout=300)

    monkeypatch.setattr(ipd.subprocess, "run", fake_uv_timeout)

    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='m'\n")

    with pytest.raises(RuntimeError, match="uv venv 超时"):
        ipd.install_module(module)

    # Log file should be written with the timeout marker (spec §4.6.5)
    logs = tmp_path / "cache" / "logs"
    log_files = list(logs.glob("install-m-*.log"))
    assert len(log_files) == 1
    assert "timeout" in log_files[0].read_text().lower()


def test_install_module_pip_timeout_continues_to_next_attempt(tmp_path, monkeypatch):
    """uv pip install 超时 → 视为失败 attempt，继续 URL 重试链。"""
    from hooks import install_python_deps as ipd
    monkeypatch.setattr(ipd, "resolve_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))

    call_count = {"venv": 0, "pip": 0}

    def fake_uv(argv, **kwargs):
        # uv venv: 成功（一次）
        if "venv" in argv:
            call_count["venv"] += 1
            venv_path = Path(argv[argv.index("venv") + 1])
            venv_path.mkdir(parents=True, exist_ok=True)
            (venv_path / "lib" / "site-packages").mkdir(parents=True, exist_ok=True)
            return type("R", (), {"returncode": 0, "stderr": ""})()
        # uv pip install: 全部超时
        call_count["pip"] += 1
        raise subprocess.TimeoutExpired(cmd="uv pip", timeout=300)

    monkeypatch.setattr(ipd.subprocess, "run", fake_uv)

    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='m'\n")

    with pytest.raises(RuntimeError, match="uv pip install"):
        ipd.install_module(module)

    # 1 venv call + 12 pip install calls (4 URLs × 3 retries = 12)
    assert call_count["venv"] == 1
    assert call_count["pip"] == 12

    # Log file should be written with TimeoutExpired history
    logs = tmp_path / "cache" / "logs"
    log_files = list(logs.glob("install-m-*.log"))
    assert len(log_files) == 1
    log_content = log_files[0].read_text()
    assert log_content.count("TimeoutExpired") == 12  # each attempt logged


def test_is_venv_corrupted_under_2s_with_hung_binary(tmp_path, monkeypatch):
    """is_venv_corrupted must not invoke python --version — verify it's fast even
    when the venv 'binary' would block. Per spec §4.6.4 main hook <2s promise.
    """
    import time
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    venv = tmp_path / "cache" / "venvs" / "x"
    venv.mkdir(parents=True)
    (venv / "bin").mkdir(parents=True)
    # Write a python that would block forever IF called. Existence check should
    # short-circuit and never invoke it.
    py_path = venv / "bin" / "python"
    py_path.write_text("#!/bin/sh\nsleep 999\n")
    py_path.chmod(0o755)

    from hooks.install_python_deps import is_venv_corrupted
    start = time.monotonic()
    result = is_venv_corrupted("x")
    elapsed = time.monotonic() - start
    assert result is False  # binary exists → not corrupted
    assert elapsed < 0.5, f"is_venv_corrupted took {elapsed:.3f}s — must be <0.5s"


# --- is_venv_corrupted ---
#
# Cross-platform: existence-only check. Parametrize covers Unix vs Windows venv
# layouts (uv creates bin/python on *nix, Scripts/python.exe on Windows).

@pytest.mark.parametrize("platform,venv_python_path", [
    ("linux", "bin/python"),
    ("darwin", "bin/python"),
    ("win32", "Scripts/python.exe"),
])
def test_is_venv_corrupted_missing_python_bin(tmp_path, monkeypatch, platform, venv_python_path):
    """venv 目录存在但 python 二进制不存在 → corrupted（覆盖全平台）。"""
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    venv = tmp_path / "cache" / "venvs" / "x"
    # Create the parent dir (bin/ or Scripts/) but NOT the python binary itself
    (venv / venv_python_path).parent.mkdir(parents=True)
    from hooks.install_python_deps import is_venv_corrupted
    assert is_venv_corrupted("x") is True


@pytest.mark.parametrize("platform,venv_python_path", [
    ("linux", "bin/python"),
    ("darwin", "bin/python"),
    ("win32", "Scripts/python.exe"),
])
def test_is_venv_corrupted_healthy(tmp_path, monkeypatch, platform, venv_python_path):
    """python 二进制存在 → not corrupted（覆盖全平台）。"""
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    venv = tmp_path / "cache" / "venvs" / "x"
    py_path = venv / venv_python_path
    py_path.parent.mkdir(parents=True)
    # Content doesn't matter — only existence is checked (per spec §4.6.4 <2s promise)
    py_path.write_text("#!/bin/sh\necho Python 3.11.0\nexit 0\n")
    from hooks.install_python_deps import is_venv_corrupted
    assert is_venv_corrupted("x") is False


# --- nuke_venv ---

def test_nuke_venv_removes_existing_dir(tmp_path, monkeypatch):
    """nuke_venv should remove the venv directory entirely."""
    from hooks.install_python_deps import nuke_venv
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    venv = tmp_path / "cache" / "venvs" / "x"
    venv.mkdir(parents=True)
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("fake")
    assert venv.exists()
    nuke_venv("x")
    assert not venv.exists()


def test_nuke_venv_noop_on_missing(tmp_path, monkeypatch):
    """nuke_venv should not raise when venv doesn't exist."""
    from hooks.install_python_deps import nuke_venv
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    # Don't create venv at all
    nuke_venv("x")  # should not raise


# --- pick_pip_index_url ---

def test_pick_pip_index_url_default_no_env(monkeypatch):
    monkeypatch.delenv("WEBNOVEL_PIP_INDEX", raising=False)
    monkeypatch.setattr("hooks.install_python_deps._is_china_ip", lambda: False)
    from hooks.install_python_deps import pick_pip_index_url
    assert pick_pip_index_url() == "https://pypi.org/simple"


def test_pick_pip_index_url_env_override(monkeypatch):
    monkeypatch.setenv("WEBNOVEL_PIP_INDEX", "https://mirrors.aliyun.com/pypi/simple/")
    from hooks.install_python_deps import pick_pip_index_url
    assert pick_pip_index_url() == "https://mirrors.aliyun.com/pypi/simple/"


def test_pick_pip_index_url_china_detected(monkeypatch):
    """模拟 CN 检测（IP 库查 cn → 返回清华镜像）。"""
    monkeypatch.delenv("WEBNOVEL_PIP_INDEX", raising=False)
    monkeypatch.setattr("hooks.install_python_deps._is_china_ip", lambda: True)
    from hooks.install_python_deps import pick_pip_index_url
    url = pick_pip_index_url()
    assert "tsinghua" in url or "aliyun" in url or "ustc" in url


# --- main ---


def test_main_returns_2_when_no_plugin_root(monkeypatch, tmp_path):
    """main() returns 2 when --plugin-root and CLAUDE_PLUGIN_ROOT are both unset."""
    from hooks.install_python_deps import main
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setattr(sys, "argv", ["install_python_deps.py"])
    assert main() == 2


def test_main_returns_2_for_nonexistent_module(monkeypatch, tmp_path):
    """main() returns 2 when --module target has no pyproject.toml."""
    from hooks.install_python_deps import main
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    # Create skills/ dir but no skill with that name
    (plugin_root / "skills").mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
    monkeypatch.setattr(sys, "argv", [
        "install_python_deps.py",
        "--plugin-root", str(plugin_root),
        "--module", "nonexistent",
    ])
    assert main() == 2


def test_main_returns_0_when_all_up_to_date(monkeypatch, tmp_path):
    """If should_install_module returns 'ok' for all modules, main returns 0."""
    from hooks.install_python_deps import main
    plugin_root = tmp_path / "plugin"
    (plugin_root / "skills" / "fake-skill").mkdir(parents=True)
    (plugin_root / "skills" / "fake-skill" / "pyproject.toml").write_text("[project]\n")

    # Mock should_install_module to always return 'ok'
    monkeypatch.setattr("hooks.install_python_deps.should_install_module", lambda m: "ok")
    # Mock find_python_modules to return our fake module
    fake_module = plugin_root / "skills" / "fake-skill"
    monkeypatch.setattr(
        "hooks.install_python_deps.find_python_modules",
        lambda r: [fake_module],
    )
    # Mock install_module so it isn't called (we said 'ok' for all)
    monkeypatch.setattr(
        "hooks.install_python_deps.install_module",
        lambda m: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    monkeypatch.setattr(sys, "argv", [
        "install_python_deps.py",
        "--plugin-root", str(plugin_root),
    ])
    assert main() == 0


def test_main_returns_1_when_install_fails(monkeypatch, tmp_path):
    """If install_module raises, main returns 1."""
    from hooks.install_python_deps import main
    plugin_root = tmp_path / "plugin"
    (plugin_root / "skills" / "fake-skill").mkdir(parents=True)
    (plugin_root / "skills" / "fake-skill" / "pyproject.toml").write_text("[project]\n")

    # Mock should_install_module to require install
    monkeypatch.setattr(
        "hooks.install_python_deps.should_install_module",
        lambda m: "missing venv",
    )
    fake_module = plugin_root / "skills" / "fake-skill"
    monkeypatch.setattr(
        "hooks.install_python_deps.find_python_modules",
        lambda r: [fake_module],
    )

    # Mock install_module to raise
    def fake_install(module):
        raise RuntimeError("install failed")
    monkeypatch.setattr("hooks.install_python_deps.install_module", fake_install)

    monkeypatch.setattr(sys, "argv", [
        "install_python_deps.py",
        "--plugin-root", str(plugin_root),
    ])
    assert main() == 1


def test_main_propagates_plugin_root_to_install_module(monkeypatch, tmp_path):
    """If --plugin-root is passed without env var, install_module can still find vendor/uv.

    Without the fix that sets CLAUDE_PLUGIN_ROOT from --plugin-root, this test would
    raise 'CLAUDE_PLUGIN_ROOT 未设置' instead of 'uv 二进制不存在'.
    """
    from hooks.install_python_deps import main
    plugin_root = tmp_path / "plugin"
    (plugin_root / "skills" / "fake-skill").mkdir(parents=True)
    (plugin_root / "skills" / "fake-skill" / "pyproject.toml").write_text("[project]\n")

    # CRITICAL: ensure env var is unset
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setattr(
        "hooks.install_python_deps.should_install_module",
        lambda m: "missing venv",
    )
    fake_module = plugin_root / "skills" / "fake-skill"
    monkeypatch.setattr(
        "hooks.install_python_deps.find_python_modules",
        lambda r: [fake_module],
    )

    captured_plugin_root = []

    def fake_install(module):
        # Read env var AFTER main() ran — verify it's set
        captured_plugin_root.append(os.environ.get("CLAUDE_PLUGIN_ROOT"))
        # Simulate missing uv binary so install_module raises immediately
        raise RuntimeError("uv 二进制不存在")

    monkeypatch.setattr("hooks.install_python_deps.install_module", fake_install)

    monkeypatch.setattr(sys, "argv", [
        "install_python_deps.py",
        "--plugin-root", str(plugin_root),
    ])
    exit_code = main()
    assert exit_code == 1
    # The env var should have been set from --plugin-root
    assert captured_plugin_root == [str(plugin_root)]


# --- chromium prompt ---

def test_should_prompt_chromium_first_time(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    venv = tmp_path / "cache" / "venvs" / "webnovel-chart-scan"
    venv.mkdir(parents=True)
    from hooks.install_python_deps import should_prompt_chromium
    assert should_prompt_chromium("webnovel-chart-scan") is True


def test_should_prompt_chromium_already_yes(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    venv = tmp_path / "cache" / "venvs" / "webnovel-chart-scan"
    venv.mkdir(parents=True)
    (venv / ".chromium-prompted").write_text("yes\n")
    from hooks.install_python_deps import should_prompt_chromium
    assert should_prompt_chromium("webnovel-chart-scan") is False


def test_should_prompt_chromium_already_no(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    venv = tmp_path / "cache" / "venvs" / "webnovel-chart-scan"
    venv.mkdir(parents=True)
    (venv / ".chromium-prompted").write_text("no\n")
    from hooks.install_python_deps import should_prompt_chromium
    assert should_prompt_chromium("webnovel-chart-scan") is False


def test_write_chromium_decision(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    from hooks.install_python_deps import write_chromium_decision
    write_chromium_decision("webnovel-chart-scan", "yes")
    f = tmp_path / "cache" / "venvs" / "webnovel-chart-scan" / ".chromium-prompted"
    assert f.read_text().strip() == "yes"


