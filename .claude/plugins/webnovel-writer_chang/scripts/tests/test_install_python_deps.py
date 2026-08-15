"""install_python_deps.py 的单元测试。"""
import hashlib
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
