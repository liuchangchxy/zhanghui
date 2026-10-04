"""install_python_deps.py — 实际跑 uv 安装 Python 依赖。

被 SessionStart hook 后台调用，也可独立运行做诊断。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform as _platform
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


PIP_MIRRORS_CN = [
    "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://pypi.mirrors.ustc.edu.cn/simple/",
]


def _is_china_ip() -> bool:
    """简单启发式：通过访问 ip.cn 看返回是否包含 '中国' / 'China'。

    返回 True 视为 CN 网络。失败兜底 False。
    """
    try:
        with urllib.request.urlopen("https://ip.cn", timeout=2) as r:
            body = r.read().decode("utf-8", errors="ignore")
        return "中国" in body or "China" in body
    except Exception:
        return False


def pick_pip_index_url() -> str:
    """决定 uv pip install 使用的 index URL。

    优先级：
    1. $WEBNOVEL_PIP_INDEX（用户显式指定）
    2. CN IP 检测为 True → 清华镜像
    3. 默认 PyPI 官方
    """
    custom = os.environ.get("WEBNOVEL_PIP_INDEX")
    if custom:
        return custom
    if _is_china_ip():
        return PIP_MIRRORS_CN[0]
    return "https://pypi.org/simple"


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
        以下 5 个字符串之一:
            - "ok"                       venv 存在且 stamp 匹配
            - "missing venv"             venv 目录不存在
            - "corrupted venv"           venv 存在但 python 二进制缺失或 --version 失败
                                         (已 nuke，下次 install_module 会重建)
            - "missing stamp"            venv 目录存在但 .install-stamp 文件不存在
            - "stale stamp (disk=X expected=Y)"  venv+stamp 都存在但内容不匹配
                                         (X, Y 是 sha256 前 8 字符用于调试)
    """
    cache = resolve_cache_dir()
    venv = cache / "venvs" / module_dir.name
    if not venv.exists():
        return "missing venv"
    if is_venv_corrupted(module_dir.name):
        nuke_venv(module_dir.name)
        return "corrupted venv"
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


DEFAULT_INSTALL_TIMEOUT = 300  # 5 min


def install_module(module_dir: Path) -> None:
    """为单个 module 创建 venv + uv pip install + 写 stamp。

    Args:
        module_dir: 含 pyproject.toml 的目录。

    环境变量:
        WEBNOVEL_INSTALL_TIMEOUT: subprocess 单次调用超时（秒，默认 300）

    Raises:
        RuntimeError: uv venv 或 uv pip install 返回非 0；log 写到 logs/。
        FileNotFoundError => RuntimeError: uv 二进制不存在（spec §4.6.5）。
    """
    install_timeout = int(os.environ.get("WEBNOVEL_INSTALL_TIMEOUT", str(DEFAULT_INSTALL_TIMEOUT)))

    cache = resolve_cache_dir()
    venv = cache / "venvs" / module_dir.name
    logs = cache / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    log_path = logs / f"install-{module_dir.name}-{timestamp}.log"

    # Locate uv via $CLAUDE_PLUGIN_ROOT/vendor/uv (set by Claude Code).
    plugin_root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root_env:
        raise RuntimeError("CLAUDE_PLUGIN_ROOT 未设置；这个脚本必须在 plugin hook 里跑")
    uv = select_uv_binary(Path(plugin_root_env) / "vendor" / "uv")

    venv.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: uv venv
    try:
        r = subprocess.run(
            [str(uv), "venv", str(venv), "--python", "3.11"],
            capture_output=True, text=True, timeout=install_timeout,
        )
    except FileNotFoundError as e:
        log_path.write_text(f"uv binary not found: {uv}\n{e}\n")
        raise RuntimeError(f"uv 二进制不存在：{uv}（请重新安装 plugin 或 vendor uv）") from e
    except subprocess.TimeoutExpired:
        log_path.write_text(f"uv venv timeout after {install_timeout}s\n")
        raise RuntimeError(f"uv venv 超时（{install_timeout}s）")
    if r.returncode != 0:
        log_path.write_text(f"uv venv failed:\n{r.stderr}\n")
        raise RuntimeError(f"uv venv 失败：{r.stderr[:200]}")

    # Step 2: uv pip install with URL fallback chain (spec §4.6.5)
    # Build URL chain: primary + fallback mirrors depending on what primary is.
    primary = pick_pip_index_url()
    url_chain = [primary]
    if "pypi.org" in primary:
        # Primary is PyPI official; fall back to CN mirrors (TUNA, aliyun, USTC)
        url_chain.extend(PIP_MIRRORS_CN)
    elif primary == PIP_MIRRORS_CN[0]:
        # Primary is TUNA; fall back to aliyun, then USTC
        url_chain.extend(PIP_MIRRORS_CN[1:])

    MAX_RETRIES_PER_URL = 3
    last_error: str | None = None
    attempt_log: list[str] = []

    for url in url_chain:
        for attempt in range(1, MAX_RETRIES_PER_URL + 1):
            try:
                r = subprocess.run(
                    [str(uv), "pip", "install", "-e", str(module_dir),
                     "--index-url", url],
                    capture_output=True, text=True, timeout=install_timeout,
                    env={**os.environ, "VIRTUAL_ENV": str(venv)},
                )
            except FileNotFoundError as e:
                attempt_log.append(f"attempt {attempt} on {url}: FileNotFoundError: {e}")
                last_error = "uv 二进制不存在"
                break  # Don't retry on FileNotFoundError — binary is missing
            except subprocess.TimeoutExpired:
                # Treat timeout as a failed attempt; continue to next retry/URL
                attempt_log.append(
                    f"attempt {attempt} on {url}: TimeoutExpired after {install_timeout}s"
                )
                last_error = f"uv pip install 超时（{install_timeout}s）"
                continue  # Next attempt within this URL
            if r.returncode == 0:
                # Success
                attempt_log.append(f"OK on {url} (attempt {attempt})")
                break  # exit inner loop
            attempt_log.append(
                f"attempt {attempt} on {url}: returncode={r.returncode}, "
                f"stderr={r.stderr[:100]}"
            )
            last_error = f"uv pip install 失败：{r.stderr[:200]}"
        else:
            # Inner loop completed without break (all 3 attempts failed for this URL)
            continue  # try next URL
        # If we got here via break from inner loop, determine why
        if last_error == "uv 二进制不存在":
            break  # Cannot recover; exit outer loop
        # Otherwise: success — exit outer loop
        break

    # Write log with attempt history (spec §4.6.5: failed attempts logged for retry)
    log_path.write_text("\n".join(attempt_log) + "\n")

    if not attempt_log or not attempt_log[-1].startswith("OK"):
        raise RuntimeError(
            f"uv pip install 在 {sum(1 for l in attempt_log if 'attempt' in l)} "
            f"次尝试后失败。Last error: {last_error}"
        )

    # Step 3: write stamp
    stamp = compute_install_stamp(module_dir)
    (venv / ".install-stamp").write_text(stamp + "\n")
    log_path.write_text(f"OK: installed {module_dir.name}, stamp={stamp[:8]}\n")


def is_venv_corrupted(module_name: str) -> bool:
    """检测 venv 是否损坏（python 二进制是否存在）。

    仅做轻量存在性检查，不跑 ``python --version``。原因：

    - ``python --version`` 子进程会被 sandbox / 动态链接问题阻塞，
      违反 spec §4.6.4 "main hook <2s" 承诺。
    - 二次校验（binary 存在但 --version 失败）改由 background
      ``install_module`` 处理；main hook 只负责发现明显损坏（binary 缺失）。
    - 平台感知：Windows 上 uv 创建 ``Scripts/python.exe`` 而非
      ``bin/python``，否则 Windows 永远视为损坏，导致死循环删 / 重建 venv。

    Args:
        module_name: venv 名（对应 modules/<name> 目录）。

    Returns:
        True = 损坏（需要重建）；False = 健康。
    """
    venv = resolve_cache_dir() / "venvs" / module_name
    if sys.platform == "win32":
        py = venv / "Scripts" / "python.exe"
    else:
        py = venv / "bin" / "python"
    return not py.exists()


def nuke_venv(module_name: str) -> None:
    """删掉损坏的 venv（让 install_module 重建）。

    Args:
        module_name: venv 名（对应 modules/<name> 目录）。

    Side Effects:
        删除 <cache>/venvs/<module_name> 整个目录树。如果目录不存在则 no-op。
    """
    venv = resolve_cache_dir() / "venvs" / module_name
    if venv.exists():
        shutil.rmtree(venv)


CHROMIUM_PROMPT_FILENAME = ".chromium-prompted"


def _chromium_marker(module_name: str) -> Path:
    return resolve_cache_dir() / "venvs" / module_name / CHROMIUM_PROMPT_FILENAME


def should_prompt_chromium(module_name: str) -> bool:
    """判断是否需要弹 chromium 安装提示。

    仅 webnovel-chart-scan（fanqie adapter）会触发。
    """
    return not _chromium_marker(module_name).exists()


def write_chromium_decision(module_name: str, decision: str) -> None:
    """记录用户对 chromium 弹窗的选择：'yes' 或 'no'。

    'no' 意味着 chart-scan 永久 skip fanqie。
    """
    marker = _chromium_marker(module_name)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(decision.strip().lower() + "\n")


def format_chromium_prompt() -> str:
    """生成发给 Claude prompt 的消息文本。"""
    return (
        "fanqie adapter 需要下载 chromium 浏览器（~150MB）。\n"
        "装好后可用 fanqie 平台榜单扫描；不装也能用其它 4 个平台。\n"
        "是否安装？(y/N)\n"
        "\n"
        "【Claude 指引】用户回答后请执行以下操作之一完成决策持久化，避免下次 SessionStart 再问：\n"
        "  - 用户接受 y: cd $CLAUDE_PLUGIN_ROOT/skills/webnovel-chart-scan && "
        "$VENV_BIN/playwright install chromium"
        "（VENV_BIN 路径：$WEBNOVEL_CACHE_DIR/venvs/webnovel-chart-scan/bin/，"
        "resolve_cache_dir() 解析）\n"
        "  - 用户拒绝 N: write_chromium_decision('webnovel-chart-scan', 'no') "
        "（写在 venv 旁的 .chromium-prompted 标记，永久 skip fanqie）"
    )


def main() -> int:
    """CLI 入口：python3 install_python_deps.py [--module NAME]。

    无参数：扫描 CLAUDE_PLUGIN_ROOT 下所有 Python module 并 install。
    有参数：只装指定 module。

    Returns:
        0 全部成功 / 1 至少一个失败 / 2 调用错误。
    """
    parser = argparse.ArgumentParser(description="Install Python deps for plugin modules.")
    parser.add_argument("--module", help="只装指定 module 名（skills/<name> 或 dashboard）")
    parser.add_argument("--plugin-root", default=os.environ.get("CLAUDE_PLUGIN_ROOT"),
                        help="plugin 根目录（默认从 CLAUDE_PLUGIN_ROOT 环境变量读）")
    args = parser.parse_args()

    if not args.plugin_root:
        print("ERROR: --plugin-root 未指定且 CLAUDE_PLUGIN_ROOT 未设置", file=sys.stderr, flush=True)
        return 2

    # Ensure CLAUDE_PLUGIN_ROOT is set so install_module can find vendor/uv
    os.environ["CLAUDE_PLUGIN_ROOT"] = args.plugin_root
    plugin_root = Path(args.plugin_root)
    if args.module:
        target = plugin_root / "skills" / args.module
        if not target.exists():
            target = plugin_root / args.module
        # Validate target is under plugin_root (prevent path traversal/escape)
        target = target.resolve()
        if not target.is_relative_to(plugin_root.resolve()):
            print(f"ERROR: --module {args.module} escaped plugin root", file=sys.stderr, flush=True)
            return 2
        if not (target / "pyproject.toml").exists():
            print(f"ERROR: {target} 没有 pyproject.toml", file=sys.stderr, flush=True)
            return 2
        modules = [target]
    else:
        modules = find_python_modules(plugin_root)

    failures = 0
    for module in modules:
        reason = should_install_module(module)
        if reason == "ok":
            print(f"SKIP: {module.name} (venv up to date)", flush=True)
            continue
        print(f"INSTALL: {module.name} ({reason})", flush=True)
        try:
            install_module(module)
            print(f"OK: {module.name}", flush=True)
        except Exception as e:
            print(f"FAIL: {module.name}: {e}", file=sys.stderr, flush=True)
            failures += 1

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

