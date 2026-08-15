"""install_python_deps.py — 实际跑 uv 安装 Python 依赖。

被 SessionStart hook 后台调用，也可独立运行做诊断。
"""
from __future__ import annotations

import hashlib
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
