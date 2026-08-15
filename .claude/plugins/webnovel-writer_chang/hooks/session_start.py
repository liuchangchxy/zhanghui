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
    return 0


def trigger_background_python_install(plugin_root: Path) -> None:
    """扫描 plugin 的 Python module，对需要重装的 fork 后台进程跑 install_python_deps.py。

    主 hook 不等子进程完成；子进程日志写到 ~/.cache/.../logs/。
    """
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
    subprocess.Popen(
        [sys.executable, str(install_script), "--plugin-root", str(plugin_root)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, close_fds=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
