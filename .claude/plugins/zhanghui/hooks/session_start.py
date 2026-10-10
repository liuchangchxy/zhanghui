#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


MAX_LINES = 8
MAX_CHARS = 1000
DISABLE_ENV = "WEBNOVEL_DISABLE_SESSION_STATUS_HOOK"

# Cache symlink path (per spec §2.3 — cache must be ln -sfn to dev workspace)
# When not a symlink, dev code changes won't be picked up by Claude Code.
CACHE_SYMLINK_PATH = (
    Path.home() / ".claude" / "plugins" / "cache"
    / "webnovel-chang-marketplace" / "zhanghui"
)


def verify_cache_symlink(plugin_root: Path) -> None:
    """Check that the plugin cache is a symlink to dev workspace (per spec §2.3).

    If cache is a regular directory or missing, dev modifications won't be picked
    up by Claude Code. Print warning to stderr (not stdout) so it doesn't pollute
    Claude's hook output. Silent on cache symlink (correct state) or fresh install.

    Without this guard, the same "edit code → plugin breaks silently" failure mode
    has bitten us repeatedly. The warning fires on every SessionStart until fixed.
    """
    try:
        if not CACHE_SYMLINK_PATH.exists():
            return  # Fresh install; cache symlink not set up yet; silent
        if CACHE_SYMLINK_PATH.is_symlink():
            return  # Correct state; silent
    except OSError:
        return  # Path resolution failed; don't crash hook

    # Cache exists but is NOT a symlink — broken state
    target = CACHE_SYMLINK_PATH
    print(
        f"WARNING: legacy marketplace plugin cache found: {target}\n"
        f"  Claude Code now loads Zhanghui directly from the canonical repository.\n"
        f"  Fix: rm -rf {target}\n"
        f"  And run bin/install-plugin.sh to ensure canonical registration.",
        file=sys.stderr,
        flush=True,
    )


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clip(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()][:MAX_LINES]
    clipped = "\n".join(lines).strip()
    if len(clipped) > MAX_CHARS:
        clipped = clipped[: MAX_CHARS - 3].rstrip() + "..."
    return clipped


def main() -> int:
    if _truthy(os.environ.get(DISABLE_ENV)):
        return 0

    plugin_root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1])

    # Check cache symlink FIRST (before any other work) so the user sees the warning
    # even if the rest of the hook fails. Per spec §2.3: cache must be symlink.
    verify_cache_symlink(plugin_root)
    workspace_root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    webnovel = plugin_root / "scripts" / "webnovel.py"
    if not webnovel.is_file():
        return 0

    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(webnovel),
                "--project-root",
                str(workspace_root),
                "project-status",
                "--format",
                "summary",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=4,
        )
    except Exception:
        return 0

    output = _clip(proc.stdout or proc.stderr or "")
    if output:
        print(output)

    trigger_background_python_install(plugin_root)

    prompt = check_chromium_prompt(plugin_root)
    if prompt:
        print(prompt)
    prompt2 = check_ciweimao_prompt(plugin_root)
    if prompt2:
        print(prompt2)
    return 0


def check_chromium_prompt(plugin_root: Path) -> str | None:
    """检查 webnovel-chart-scan 是否需要 chromium 弹窗。

    Returns:
        需要弹窗时返回 prompt 文本（给 Claude）；否则 None。

    整个函数体都被 try/except 包住：chromium nag 永远不应该 crash SessionStart hook。
    缓存路径通过 install_python_deps.resolve_cache_dir()（spec §4.6.5 fallback chain）
    解析，**不要**硬编码 ~/.cache/webnovel-writer-chang。
    """
    try:
        sys.path.insert(0, str(plugin_root / "hooks"))
        try:
            from install_python_deps import (
                should_prompt_chromium,
                format_chromium_prompt,
                should_install_module,
            )
        except (ImportError, OSError, PermissionError):
            return None  # install_python_deps.py 还没部署或导入失败；静默 skip

        # Suppress unless install_python_deps.py has marked chart-scan as fully installed.
        # Use should_install_module()'s "ok" check (not raw stamp existence, which can be stale).
        chart_scan = plugin_root / "skills" / "webnovel-chart-scan"
        if not chart_scan.exists():
            return None
        if should_install_module(chart_scan) != "ok":
            return None

        # Now check if user has already been prompted
        if not should_prompt_chromium("webnovel-chart-scan"):
            return None

        return format_chromium_prompt()
    except (ImportError, OSError, PermissionError):
        # chromium nag must never crash a session hook — 包括 should_install_module
        # 内部调用 resolve_cache_dir() 抛 PermissionError 的情况。
        return None


def check_ciweimao_prompt(plugin_root: Path) -> str | None:
    """检查 webnovel-chart-scan 是否需要 ciweimao SETUP 弹窗。

    Returns:
        需要弹窗时返回 prompt 文本（给 Claude）；否则 None。

    整个函数体都被 try/except 包住：ciweimao nag 永远不应该 crash SessionStart hook。
    缓存路径通过 install_python_deps.resolve_cache_dir()（spec §4.6.5 fallback chain）
    解析，和 chromium 模式共用同一套 cache 根。
    """
    try:
        sys.path.insert(0, str(plugin_root / "skills" / "webnovel-chart-scan" / "scripts"))
        try:
            from ciweimao_setup.sessionstart_integration import (
                should_prompt_ciweimao,
                format_ciweimao_prompt,
            )
        except (ImportError, OSError, PermissionError):
            return None  # sessionstart_integration.py 还没部署；静默 skip

        # Suppress unless install_python_deps.py has marked chart-scan as fully installed.
        chart_scan = plugin_root / "skills" / "webnovel-chart-scan"
        if not chart_scan.exists():
            return None
        # Lazy-import to avoid forcing chart-scan to be installed first
        sys.path.insert(0, str(plugin_root / "hooks"))
        try:
            from install_python_deps import should_install_module
        except ImportError:
            return None
        if should_install_module(chart_scan) != "ok":
            return None

        # Now check if user has already been prompted
        if not should_prompt_ciweimao("webnovel-chart-scan"):
            return None

        return format_ciweimao_prompt()
    except (ImportError, OSError, PermissionError):
        return None


def trigger_background_python_install(plugin_root) -> None:
    """扫描 plugin_root 下属的 Python module，对需要重装的 fork 后台进程跑 install_python_deps.py。

    主 hook 不等子进程完成；子进程日志写到 ~/.cache/.../logs/。

    Args:
        plugin_root: plugin 根目录 Path；如果为 None 则跳过。
    """
    if plugin_root is None:
        return
    sys.path.insert(0, str(plugin_root / "hooks"))
    try:
        from install_python_deps import find_python_modules, should_install_module
    except ImportError:
        return  # install_python_deps.py 还没部署；静默 skip

    pending = [m for m in find_python_modules(plugin_root)
               if should_install_module(m) != "ok"]
    if not pending:
        return

    install_script = plugin_root / "hooks" / "install_python_deps.py"
    if not install_script.exists():
        return

    # Detach：用 subprocess.Popen + start_new_session=True 让子进程脱离父 hook 的生命周期
    try:
        subprocess.Popen(
            [sys.executable, str(install_script), "--plugin-root", str(plugin_root)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, close_fds=True,
        )
    except (OSError, FileNotFoundError, PermissionError) as e:
        # 资源耗尽 / 可执行文件丢失 / 权限拒绝 — 静默失败
        # 下次 SessionStart 会重新检测；spec §4.6.5 允许
        print(f"trigger_background_python_install: Popen failed: {e}", file=sys.stderr, flush=True)
        return


if __name__ == "__main__":
    raise SystemExit(main())
