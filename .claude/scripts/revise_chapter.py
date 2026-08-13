#!/usr/bin/env python3
"""根据 RejectionContract 局部重写章节。

用法:
    python3 revise_chapter.py \\
        --chapter-file 正/第0005章.md \\
        --contract .webnovel/rejection/ch0005.json \\
        [--dry-run] [--model claude-sonnet-4-5]

退出码:
    0 = 成功（生成 .revised.md）
    1 = 输入合法但 contract 校验失败
    2 = infrastructure error（文件缺失 / JSON 损坏）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# 把同目录下的 rejection_contract.py 加进来
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rejection_contract import (  # noqa: E402
    RejectionContract,
    build_contract_from_reviewer_output,
    targets_text,
    validate_contract,
)


EXIT_OK = 0
EXIT_INVALID = 1
EXIT_INFRA = 2


# §N 段的标题正则：## §N 标题 / ## §N
SECTION_PATTERN = re.compile(r"^##\s+(§\d+)\b", re.MULTILINE)


def extract_section(text: str, section_id: str) -> str:
    """从正文中提取 §N 段（从 ## §N 行到下一个 ## 之前）。"""
    pattern = re.compile(
        rf"^(##\s+{re.escape(section_id)}\b.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return ""
    return m.group(1).rstrip() + "\n"


def build_revise_plan(
    chapter_text: str,
    contract: RejectionContract,
) -> dict[str, str]:
    """返回 {section_id: 原内容} —— 只包含 contract 里出现的段。"""
    plan: dict[str, str] = {}
    for issue in contract.issues:
        loc = issue.location.strip()
        if loc.startswith("§"):
            section_id = loc.split()[0]  # "§2-§5" → "§2-§5"
            if section_id not in plan:
                content = extract_section(chapter_text, section_id)
                if content:
                    plan[section_id] = content
    return plan


def apply_revised_sections(
    original: str,
    revised: dict[str, str],
) -> str:
    """把原文中标记的段替换成 revised[section_id]，其他原样。"""
    out = original
    for section_id, new_content in revised.items():
        pattern = re.compile(
            rf"^(##\s+{re.escape(section_id)}\b.*?)(?=^##\s|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        if pattern.search(out):
            out = pattern.sub(new_content.rstrip() + "\n\n", out, count=1)
        else:
            # §N 段在原文里找不到 —— 追加到末尾（罕见，但要兜底）
            out = out.rstrip() + "\n\n" + new_content
    return out


# === LLM 调用（PR 3 阶段先做占位，真实 prompt 在 smoke test 时调） ===
def call_llm_for_revision(
    section_id: str,
    original: str,
    instruction: str,
    model: str,
) -> str:
    """调 LLM 重写一个段。返回新段（不含 markdown 标题之外的元数据）。

    PR 3 阶段：先返回原内容 + 一行 marker，证明链路通。
    TODO: 替换为真实 Claude API 调用（用 anthropic SDK 或 curl）。
    """
    # 占位：直接拼一个标记，便于 smoke test 验证替换发生
    return f"## {section_id}（待 LLM 重写）\n\n[REVISE-MARKER] 收到 instruction: {instruction[:50]}\n\n原内容前 30 字: {original[:30]}\n"


# === CLI ===
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="根据 RejectionContract 局部重写章节")
    parser.add_argument("--chapter-file", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path,
                        help="reviewer JSON 或 RejectionContract JSON")
    parser.add_argument("--dry-run", action="store_true",
                        help="不调 LLM，只输出 plan")
    parser.add_argument("--output", type=Path, default=None,
                        help="输出文件（默认 <chapter>.revised.md）")
    parser.add_argument("--model", default="claude-sonnet-4-5")
    args = parser.parse_args(argv)

    if not args.chapter_file.is_file():
        print(f"[revise] 章节文件不存在: {args.chapter_file}", file=sys.stderr)
        return EXIT_INFRA
    if not args.contract.is_file():
        print(f"[revise] contract 文件不存在: {args.contract}", file=sys.stderr)
        return EXIT_INFRA

    try:
        raw = json.loads(args.contract.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[revise] contract JSON 损坏: {e}", file=sys.stderr)
        return EXIT_INFRA

    # 兼容两种输入：
    # 1) reviewer JSON（issues[] 里每项含 severity 字段）
    # 2) RejectionContract JSON（顶层有 chapter + issues，每项含 severity）
    # 区分：用 issues[0] 是否含 fix_hint 字段判断（reviewer JSON 有，contract 也有；
    # 但 reviewer 的 description 是长文本，contract 的是短文本 — 不易区分）。
    # 实用策略：都走 build_contract_from_reviewer_output，它能容忍两种形态（contract JSON 缺字段时会填空）。
    contract = build_contract_from_reviewer_output(raw, include_advisory=True)

    try:
        validate_contract(contract)
    except ValueError as e:
        print(f"[revise] contract 校验失败: {e}", file=sys.stderr)
        return EXIT_INVALID

    chapter_text = args.chapter_file.read_text(encoding="utf-8")
    plan = build_revise_plan(chapter_text, contract)
    target_text = targets_text(contract)

    output_payload: dict[str, Any] = {
        "dry_run": args.dry_run,
        "chapter_file": str(args.chapter_file),
        "contract_chapter": contract.chapter,
        "target_sections": sorted(plan.keys()),
        "targets_text": target_text,
        "plan": {k: v[:200] + "..." if len(v) > 200 else v for k, v in plan.items()},
    }

    if args.dry_run:
        print(json.dumps(output_payload, ensure_ascii=False, indent=2))
        return EXIT_OK

    # 真实重写：每个 section 单独调 LLM
    revised: dict[str, str] = {}
    for issue in contract.issues:
        loc = issue.location.strip()
        section_id = loc.split()[0]
        if section_id in revised:
            # 同一段有多个 issue，合并 fix_hint
            existing = revised[section_id]
            revised[section_id] = call_llm_for_revision(
                section_id, plan.get(section_id, ""),
                f"{existing}\n[附加] {issue.fix_hint}",
                args.model,
            )
        elif section_id in plan:
            revised[section_id] = call_llm_for_revision(
                section_id, plan[section_id], issue.fix_hint, args.model,
            )

    new_text = apply_revised_sections(chapter_text, revised)
    out_path = args.output or args.chapter_file.with_suffix(".revised.md")
    out_path.write_text(new_text, encoding="utf-8")

    output_payload["output_file"] = str(out_path)
    output_payload["revised_sections"] = sorted(revised.keys())
    print(json.dumps(output_payload, ensure_ascii=False, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
