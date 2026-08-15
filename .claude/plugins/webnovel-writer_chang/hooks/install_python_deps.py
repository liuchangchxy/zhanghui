"""install_python_deps.py — 实际跑 uv 安装 Python 依赖。

被 SessionStart hook 后台调用，也可独立运行做诊断。
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def compute_install_stamp(module_dir: Path) -> str:
    """计算 <module_dir>/{pyproject.toml,requirements.txt} 的 sha256 stamp。

    Args:
        module_dir: 含 pyproject.toml 或 requirements.txt（或两者）的目录；
                    不存在的文件被跳过。

    Returns:
        64-char hex sha256。如果两个文件都不存在，返回 sha256(b"")。
    """
    h = hashlib.sha256()
    for fname in ("pyproject.toml", "requirements.txt"):
        f = module_dir / fname
        if f.exists():
            h.update(f.read_bytes())
    return h.hexdigest()


import platform as _platform


# (system, machine) -> filename
UV_BINARY_MAP: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "uv-darwin-arm64",
    ("darwin", "x86_64"): "uv-darwin-x86_64",
    ("linux", "x86_64"): "uv-linux-x86_64",
    ("linux", "aarch64"): "uv-linux-x86_64",  # 后续 Phase 再补 linux-arm64 二进制
    ("win32", "AMD64"): "uv-windows-x86_64.exe",
    ("win32", "x86"): "uv-windows-x86_64.exe",
}


def select_uv_binary(vendor_uv_dir: Path) -> Path:
    """根据当前平台选 vendor/uv/ 下的对应 uv 二进制路径。

    Args:
        vendor_uv_dir: plugin 的 vendor/uv/ 目录。

    Returns:
        uv 二进制的完整 Path。

    Raises:
        RuntimeError: 当前平台不在 4 个支持范围内。
    """
    key = (sys.platform, _platform.machine())
    name = UV_BINARY_MAP.get(key)
    if name is None:
        raise RuntimeError(
            f"找不到匹配的 uv ({sys.platform}/{_platform.machine()})，"
            f"请检查 vendor/uv/ 目录；支持：{sorted(UV_BINARY_MAP.keys())}"
        )
    return vendor_uv_dir / name
