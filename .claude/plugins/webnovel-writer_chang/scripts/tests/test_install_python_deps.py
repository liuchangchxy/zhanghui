"""install_python_deps.py 的单元测试。"""
import hashlib
import os
import sys
from pathlib import Path

import pytest


# 让 hooks/ 包能从 tests 目录被发现：hooks/ 在 webnovel-writer_chang/hooks/，
# 需要把 webnovel-writer_chang/ 加进 sys.path。
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
    # Write non-UTF-8 bytes directly
    (venv / ".install-stamp").write_bytes(b"\xff\xfe\xfd")
    # Should NOT raise UnicodeDecodeError after the fix
    result = should_install_module(module)
    # Should be classified as stale stamp (content doesn't match expected)
    assert result.startswith("stale stamp")


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
    """uv 失败的场景：写 log，不写 stamp。"""
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

    with pytest.raises(RuntimeError, match="uv pip install 失败"):
        ipd.install_module(module)

    venv = tmp_path / "cache" / "venvs" / "m"
    assert not (venv / ".install-stamp").exists()

