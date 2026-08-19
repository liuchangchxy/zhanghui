"""统一覆盖守卫：所有写入路径在重跑前必须经过此层。"""
from __future__ import annotations

import json
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Callable


class ConflictMode(str, Enum):
    """三态 + ASK（让 Claude Code 主流程询问用户）。"""
    OVERWRITE = "overwrite"
    APPEND = "append"
    SKIP = "skip"
    ASK = "ask"


def _in_claude_code_context() -> bool:
    """检测是否在 Claude Code Skill 上下文。"""
    return os.environ.get("CLAUDE_PLUGIN_ROOT") is not None


def resolve_conflict(
    exists: bool,
    path: Path | None = None,
    mode: str | None = None,
    *,
    append_op: Callable[[Path], None] | None = None,
) -> None:
    """如果 exists=True 且 mode=None → raise FileExistsError。

    Args:
        exists: 目标是否已存在（调用方负责检测）。
        path: 仅用于报错信息；逻辑冲突也可用虚拟路径。
        mode: None → 报错；'overwrite'/'append'/'skip' → 显式三态；
              'ask' → ASK 模式（仅 Claude Code 内可用；打印 JSON 后 sys.exit(0)）。
        append_op: 当 mode='append' 时执行的合并函数。
    """
    if not exists:
        return

    display = str(path) if path else "<未指定路径>"
    if mode is None:
        raise FileExistsError(
            f"{display} 已存在。请传 --on-conflict=overwrite|append|skip|ask"
        )

    parsed = ConflictMode(mode)

    if parsed == ConflictMode.SKIP:
        print(f"SKIP: {display} 已存在，未修改", file=sys.stderr)
        return

    if parsed == ConflictMode.OVERWRITE:
        print(f"OVERWRITE: {display}", file=sys.stderr)
        return

    if parsed == ConflictMode.APPEND:
        if append_op is None:
            raise ValueError(
                f"mode=append 但未传 append_op（{display} 不支持 append）"
            )
        print(f"APPEND: {display}", file=sys.stderr)
        append_op(path)
        return

    if parsed == ConflictMode.ASK:
        if not _in_claude_code_context():
            raise RuntimeError(
                f"mode=ask 仅在 Claude Code Skill 上下文可用。"
                f"独立脚本请传 overwrite/append/skip。"
            )
        # 输出结构化 JSON，由 Claude Code 主流程捕获并 AskUserQuestion
        print(json.dumps({
            "ask": True,
            "question": f"{display} 已存在，如何处理？",
            "options": ["overwrite", "append", "skip"],
            "default": "skip",
        }, ensure_ascii=False))
        # HALT: 退出脚本，等 Claude Code 用用户选择的 mode 重跑
        sys.exit(0)
