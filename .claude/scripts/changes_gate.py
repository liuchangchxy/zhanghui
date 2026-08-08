#!/usr/bin/env python3
"""CHANGES 协议门禁校验。

在 webnovel-write skill 的 Step 2A 之后被调用：
    python3 changes_gate.py --chapter-file CH.md --db index.db --json

返回 JSON：{"passed": bool, "failures": [{"rule_id", "severity", "message", "location"}]}
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# 8 个顶级字段，借鉴天命 12 字段砍到核心 8 个
REQUIRED_TOP_LEVEL_FIELDS = frozenset({
    "character_state_changes",
    "new_plot_points",
    "foreshadowing_actions",
    "location_state_changes",
    "faction_state_changes",
    "time_progression",
    "item_transfers",
    "unresolved_questions",
})

# 容器形式优先级
CHANGE_PATTERNS = [
    re.compile(r"<chapter_changes>(.*?)</chapter_changes>", re.DOTALL | re.IGNORECASE),
    re.compile(r"---CHANGES---(.*?)(?=---|\Z)", re.DOTALL),
    re.compile(r"^#\s*CHANGES\s*\n(.*?)(?=^#|\Z)", re.DOTALL | re.MULTILINE | re.IGNORECASE),
]


@dataclass
class Failure:
    rule_id: str
    severity: str  # "blocking" | "advisory"
    message: str
    location: str = ""


@dataclass
class GateResult:
    passed: bool
    failures: list[Failure] = field(default_factory=list)
    parsed_changes: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failures": [asdict(f) for f in self.failures],
        }


def extract_changes_block(chapter_text: str) -> str | None:
    """从章节文本里识别 CHANGES 容器。"""
    for pattern in CHANGE_PATTERNS:
        m = pattern.search(chapter_text)
        if m:
            return m.group(1).strip()
    # 兜底：末尾 JSON
    tail = chapter_text.rstrip().split("\n\n")[-1].strip()
    if tail.startswith("{") and tail.endswith("}"):
        candidate_keys = REQUIRED_TOP_LEVEL_FIELDS
        matched = sum(1 for k in candidate_keys if f'"{k}"' in tail)
        if matched >= 4:
            return tail
    return None


def repair_changes_json(raw: str) -> str:
    """借鉴天命的 9 类字符修复。"""
    s = raw
    # 中文标点 → 半角
    s = s.replace("，", ",").replace("：", ":").replace("（", "(").replace("）", ")")
    s = s.replace("；", ";").replace("？", "?").replace("！", "!").replace("「", '"').replace("」", '"')
    # 单引号 → 双引号（仅在键/值的引号位置）
    s = re.sub(r"'([^'\n]+?)'\s*:", r'"\1":', s)
    s = re.sub(r":\s*'([^'\n]+?)'", r': "\1"', s)
    # 缺尾引号自动闭合：扫描所有 key 后面是否缺引号
    # （简化版：依赖 LLM 输出时遵守 json 格式；此处不实现复杂修复）
    return s


def parse_changes(chapter_text: str) -> tuple[dict[str, Any] | None, str | None]:
    """返回 (parsed_dict, error_message)。"""
    block = extract_changes_block(chapter_text)
    if block is None:
        return None, "未找到 CHANGES 容器（支持 <chapter_changes>、---CHANGES---、# CHANGES、末尾 JSON 兜底）"
    repaired = repair_changes_json(block)
    try:
        parsed = json.loads(repaired)
    except json.JSONDecodeError as e:
        return None, f"CHANGES JSON 解析失败：{e}"
    return parsed, None


def main() -> int:
    parser = argparse.ArgumentParser(description="CHANGES 协议门禁")
    parser.add_argument("--chapter-file", required=True, help="章节文件路径")
    parser.add_argument("--db", required=True, help="webnovel-writer index.db 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--rule", help="只跑指定规则（如 R1）")
    parser.add_argument("--strict", action="store_true", help="advisory 也算 blocking")
    args = parser.parse_args()

    chapter_text = Path(args.chapter_file).read_text(encoding="utf-8")
    parsed, err = parse_changes(chapter_text)
    result = GateResult(passed=True, parsed_changes=parsed)
    if err:
        result.passed = False
        result.failures.append(Failure(rule_id="R0", severity="blocking", message=err))

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("PASSED" if result.passed else f"FAILED: {len(result.failures)} failure(s)")
        for f in result.failures:
            print(f"  [{f.rule_id}/{f.severity}] {f.message}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())