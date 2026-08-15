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
