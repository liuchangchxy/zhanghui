"""install_python_deps.py — 实际跑 uv 安装 Python 依赖。

被 SessionStart hook 后台调用，也可独立运行做诊断。
"""
from __future__ import annotations

import hashlib
import os
import platform as _platform
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


# (system, machine) -> filename
UV_BINARY_MAP: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "uv-darwin-arm64",
    ("darwin", "x86_64"): "uv-darwin-x86_64",
    ("linux", "x86_64"): "uv-linux-x86_64",
    ("win32", "AMD64"): "uv-windows-x86_64.exe",
}


def select_uv_binary(vendor_uv_dir: Path) -> Path:
    """根据当前平台选 vendor/uv/ 下的对应 uv 二进制路径。

    Args:
        vendor_uv_dir: plugin 的 vendor/uv/ 目录。

    Returns:
        uv 二进制的完整 Path。

    Raises:
        RuntimeError: 当前平台不在 vendored 二进制对应的 4 个平台组合内。
                    ARM Linux / 32 位 Windows 等未覆盖平台会清晰报错而不是静默跑错架构二进制。
    """
    key = (sys.platform, _platform.machine())
    name = UV_BINARY_MAP.get(key)
    if name is None:
        raise RuntimeError(
            f"找不到匹配的 uv ({sys.platform}/{_platform.machine()})，"
            f"请检查 vendor/uv/ 目录；支持：{sorted(UV_BINARY_MAP.keys())}"
        )
    return vendor_uv_dir / name


def _try_mkdir(path: Path) -> Path | None:
    """尝试创建目录；成功返回 Path，失败返回 None。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except (PermissionError, OSError):
        return None


def resolve_cache_dir() -> Path:
    """解析 plugin 跨平台缓存根目录，按 spec §4.6.5 fallback chain 尝试多个候选。

    优先级（前者失败才尝试后者）：
    1. $WEBNOVEL_CACHE_DIR（用户显式指定；权限不够会硬报错，不 fallback — 用户责任）
    2. ~/.cache/webnovel-writer-chang/（默认；mac/linux/win 通用）
    3. ~/Library/Caches/webnovel-writer-chang/（mac OS-specific）
    4. %LOCALAPPDATA%\\webnovel-writer-chang/（Windows-specific）
    5. $XDG_CACHE_HOME/webnovel-writer-chang/ 或 ~/.cache/webnovel-writer-chang/（Linux XDG）
    6. <cwd>/.webnovel/venv/（项目根兜底）
    7. 最后：raise PermissionError 提示用户 export WEBNOVEL_CACHE_DIR

    Returns:
        已创建的缓存根目录 Path。

    Raises:
        PermissionError: 全部候选都不可写。
    """
    # Priority 1: user-supplied WEBNOVEL_CACHE_DIR (hard error if unwritable — user chose it)
    custom = os.environ.get("WEBNOVEL_CACHE_DIR")
    if custom:
        cache = Path(custom)
        try:
            cache.mkdir(parents=True, exist_ok=True)
            return cache
        except (PermissionError, OSError) as e:
            raise PermissionError(
                f"WEBNOVEL_CACHE_DIR={custom} 不可写：{e}。"
                f"请检查权限或换其他路径"
            ) from e

    # Priority 2: ~/.cache/webnovel-writer-chang/ (default, cross-platform)
    candidates: list[Path] = [
        Path.home() / ".cache" / "webnovel-writer-chang",
    ]

    # Priority 3: mac OS-specific (only added if we're on darwin)
    if sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Caches" / "webnovel-writer-chang")

    # Priority 4: Windows %LOCALAPPDATA%
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "webnovel-writer-chang")

    # Priority 5: Linux $XDG_CACHE_HOME
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        candidates.append(Path(xdg_cache) / "webnovel-writer-chang")

    # Priority 6: project root .webnovel/venv/ (last resort)
    candidates.append(Path.cwd() / ".webnovel" / "venv")

    # Try each candidate
    for candidate in candidates:
        result = _try_mkdir(candidate)
        if result is not None:
            return result

    # Priority 7: all failed
    raise PermissionError(
        f"全部 cache 候选路径都不可写：{[str(c) for c in candidates]}。"
        f"请设置 WEBNOVEL_CACHE_DIR 指向可写目录后重试"
    )


def should_install_module(module_dir: Path) -> str:
    """判断某 module 是否需要重新安装。

    Args:
        module_dir: 含 pyproject.toml 的目录。

    Returns:
        以下 4 个字符串之一:
            - "ok"                       venv 存在且 stamp 匹配
            - "missing venv"             venv 目录不存在
            - "missing stamp"            venv 目录存在但 .install-stamp 文件不存在
            - "stale stamp (disk=X expected=Y)"  venv+stamp 都存在但内容不匹配
                                         (X, Y 是 sha256 前 8 字符用于调试)
    """
    cache = resolve_cache_dir()
    venv = cache / "venvs" / module_dir.name
    if not venv.exists():
        return "missing venv"
    stamp_path = venv / ".install-stamp"
    if not stamp_path.exists():
        return "missing stamp"
    # errors="replace" defends against corrupted stamp files (e.g., process
    # killed mid-write, disk corruption). Crash here would block SessionStart.
    on_disk = stamp_path.read_text(errors="replace").strip()
    expected = compute_install_stamp(module_dir)
    if on_disk != expected:
        return f"stale stamp (disk={on_disk[:8]} expected={expected[:8]})"
    return "ok"


def find_python_modules(plugin_root: Path) -> list[Path]:
    """扫描 plugin root 下所有 Python 模块（skills/<name>/pyproject.toml + dashboard/pyproject.toml）。

    Args:
        plugin_root: plugin 根目录（含 skills/ 与 dashboard/）。

    Returns:
        含 pyproject.toml 的目录 Path 列表。
    """
    modules: list[Path] = []
    skills = plugin_root / "skills"
    if skills.exists():
        for skill in sorted(skills.iterdir()):
            if (skill / "pyproject.toml").exists():
                modules.append(skill)
    dashboard = plugin_root / "dashboard"
    if (dashboard / "pyproject.toml").exists():
        modules.append(dashboard)
    return modules
