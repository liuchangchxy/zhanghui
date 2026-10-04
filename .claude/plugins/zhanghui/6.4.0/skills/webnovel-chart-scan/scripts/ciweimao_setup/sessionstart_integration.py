"""ciweimao-prompted decision mirror.

Mirrors the chromium-prompted pattern in install_python_deps.py, but for
the ciweimao adapter's setup (Chrome @ 9222 + agent-browser).

The decision is persisted in a separate file (.ciweimao-prompted) so
fanqie's chromium decision and ciweimao's setup decision are tracked
independently — a user accepting chromium for fanqie should not be
treated as having accepted ciweimao's setup.

Marker file location: ``<resolve_cache_dir()>/venvs/<module_name>/.ciweimao-prompted``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


CIWEIMAO_PROMPT_FILENAME = ".ciweimao-prompted"


def _resolve_cache_dir_via_hook() -> Path:
    """Best-effort: borrow install_python_deps.resolve_cache_dir if available.

    Falls back to ~/.cache/webnovel-writer-chang if not importable.
    """
    try:
        # Add <plugin>/hooks to sys.path so we can import install_python_deps
        # (which lives in .claude/plugins/zhanghui/hooks/).
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if plugin_root:
            sys.path.insert(0, str(Path(plugin_root) / "hooks"))
        from install_python_deps import resolve_cache_dir
        return resolve_cache_dir()
    except Exception:
        return Path.home() / ".cache" / "webnovel-writer-chang"


def _ciweimao_marker(module_name: str) -> Path:
    """Return path to the .ciweimao-prompted marker for `module_name`."""
    return _resolve_cache_dir_via_hook() / "venvs" / module_name / CIWEIMAO_PROMPT_FILENAME


def should_prompt_ciweimao(module_name: str) -> bool:
    """Return True iff the user has not yet been asked about ciweimao setup."""
    return not _ciweimao_marker(module_name).exists()


def write_ciweimao_decision(module_name: str, decision: str) -> None:
    """Persist the user's y/N choice for ciweimao setup.

    Args:
        module_name: typically "webnovel-chart-scan"
        decision: "yes" or "no" (case-insensitive, normalized to lowercase)
    """
    marker = _ciweimao_marker(module_name)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(decision.strip().lower() + "\n")


def format_ciweimao_prompt() -> str:
    """Generate the prompt text shown to Claude at SessionStart."""
    return (
        "ciweimao adapter 需要 Chrome @ 9222 + agent-browser（绕过验证码）。\n"
        "装好后可用刺猬猫平台榜单扫描；不装也能用其它 4 个平台。\n"
        "是否安装？(y/N)\n"
        "\n"
        "【Claude 指引】用户回答后请执行以下操作之一完成决策持久化，避免下次 SessionStart 再问：\n"
        "  - 用户接受 y: webnovel-chart-scan-setup-ciweimao\n"
        "    （自动检测/安装 agent-browser + 启动 Chrome @ 9222）\n"
        "    等价于: python -m scripts.ciweimao_setup.setup_ciweimao\n"
        "  - 然后调用 write_ciweimao_decision('webnovel-chart-scan', 'yes')\n"
        "    （写在 venv 旁的 .ciweimao-prompted 标记，永久 skip ciweimao 提示）\n"
        "  - 用户拒绝 N: write_ciweimao_decision('webnovel-chart-scan', 'no')\n"
        "    （永久 skip ciweimao adapter）"
    )
