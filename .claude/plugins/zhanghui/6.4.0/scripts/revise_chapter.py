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
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import anthropic  # type: ignore
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

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
    r"""从正文中提取 §N 段（从 ## §N 行到下一个 ## 之前）。

    用 (?!\d) 而非 \b 作为边界 —— CJK 字符在 Python re 里被当作 \w，
    所以 "§2冲突" 在 §2 后是 \w 字符，\b 不会触发；用 (?!\d) 防止 §2 匹配到 §20。
    """
    pattern = re.compile(
        rf"^(##\s+{re.escape(section_id)}(?!\d).*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return ""
    return m.group(1).rstrip() + "\n"


_RANGE_PATTERN = re.compile(r"^§(\d+)\s*-\s*§(\d+)$")


def _expand_section_id(loc: str) -> list[str]:
    """把 location 展开为 §N 段 ID 列表。

    - '§3' → ['§3']
    - '§2-§5' → ['§2', '§3', '§4', '§5']
    - '§2-§5 第2-5段' → ['§2', '§3', '§4', '§5']
    - '第3段' → []
    """
    loc = loc.strip()
    if not loc.startswith("§"):
        return []

    # 取第一个 token（处理 "§2-§5 第2-5段说明" 这类带说明的）
    head = loc.split()[0]

    # 范围：§2-§5
    m = _RANGE_PATTERN.match(head)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            lo, hi = hi, lo  # 容错：颠倒顺序
        return [f"§{n}" for n in range(lo, hi + 1)]

    # 单个 §N（后面可能紧跟中文，如 "§2冲突"）
    m2 = re.match(r"^(§\d+)", head)
    if m2:
        return [m2.group(1)]
    return []


def build_revise_plan(
    chapter_text: str,
    contract: RejectionContract,
) -> dict[str, str]:
    """返回 {section_id: 原内容} —— 只包含 contract 里出现的段。

    §2-§5 范围会展开为 §2/§3/§4/§5。
    """
    plan: dict[str, str] = {}
    for issue in contract.issues:
        for section_id in _expand_section_id(issue.location):
            if section_id not in plan:
                content = extract_section(chapter_text, section_id)
                if content:
                    plan[section_id] = content
    return plan


def apply_revised_sections(
    original: str,
    revised: dict[str, str],
) -> str:
    r"""把原文中标记的段替换成 revised[section_id]，其他原样。

    用 (?!\d) 而非 \b —— CJK 字符在 Python re 里被当作 \w，
    所以 "§2冲突" 在 §2 后是 \w 字符，\b 不会触发；用 (?!\d) 防止 §2 匹配到 §20。
    """
    out = original
    for section_id, new_content in revised.items():
        pattern = re.compile(
            rf"^(##\s+{re.escape(section_id)}(?!\d).*?)(?=^##\s|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        if pattern.search(out):
            # 用 lambda 防止 backslash/group reference 在 re.sub 里被展开
            replacement = new_content.rstrip() + "\n\n"
            out = pattern.sub(lambda _: replacement, out, count=1)
        else:
            # §N 段在原文里找不到 —— 追加到末尾（罕见，但要兜底）
            out = out.rstrip() + "\n\n" + new_content
    return out


# === LLM 调用（PR 3 阶段先做占位，真实 prompt 在 smoke test 时调） ===
# 真实 LLM 调用（通过 anthropic SDK）
REVISION_SYSTEM_PROMPT = """你是网文局部重写器。
输入是一章正文的某个段落（## §N 标题）和一条修复指令。
要求：
1. 只输出重写后的段落，必须保留 ## §N 标题
2. 保持原文风格一致（不要 AI 化、不要加入未声明的设定）
3. 严格遵循 fix_hint，不要扩大改动范围
4. 修复完成后，整段字数与原段差距控制在 ±30% 以内
"""


def call_llm_for_revision(
    section_id: str,
    original: str,
    instruction: str,
    model: str,
) -> str:
    """调 Claude API 重写一个段。

    Raises:
        RuntimeError: 缺 ANTHROPIC_API_KEY / SDK 未安装 / LLM 返回空 / 被截断 / 拒绝
    """
    if not _HAS_ANTHROPIC:
        raise RuntimeError(
            "需要 anthropic SDK：pip install anthropic"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY 环境变量未设置或为空。"
            "请设置你的 Anthropic API key：\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "（不要把 key 直接写在代码里）"
        )

    client = anthropic.Anthropic()
    user_msg = (
        f"## 待重写段: {section_id}\n\n"
        f"### 原文\n{original}\n\n"
        f"### 修复指令\n{instruction}\n\n"
        f"请只输出重写后的段落（含 ## {section_id} 标题），不要输出其他文本。"
    )
    resp = client.messages.create(
        model=model,
        max_tokens=8192,
        system=REVISION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    # C6: 检查 stop_reason —— 拒绝 / 截断 → 抛错，不静默吞掉
    if getattr(resp, "stop_reason", None) in ("refusal", "max_tokens"):
        raise RuntimeError(
            f"LLM 重写 §{section_id} 失败: stop_reason={resp.stop_reason}（refusal 或截断）"
        )

    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    text = text.strip()

    # C6: 拒绝空响应
    if not text:
        raise RuntimeError(
            f"LLM 重写 §{section_id} 返回空内容（可能 refusal 或 SDK 异常）"
        )

    # C6: 拒绝无标题的响应（apply_revised_sections 无法定位段）
    # 宽松匹配：## §N ... / ## §N: ... / ## §N标题（中文紧跟也行）
    if not re.search(rf"^##\s+{re.escape(section_id)}\b", text, re.MULTILINE):
        # 兜底：section_id 是 "§N"，再试不带 \b 的中文紧跟情形
        if f"## {section_id}" not in text:
            raise RuntimeError(
                f"LLM 重写 §{section_id} 的输出不含 ## {section_id} 标题，无法替换。响应前 80 字: {text[:80]!r}"
            )

    return text


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
    parser.add_argument(
        "--include-advisory",
        action="store_true",
        default=False,
        help="包含非 blocking 的建议性 issue（默认 False：只处理 blocking）",
    )
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
    contract = build_contract_from_reviewer_output(
        raw, include_advisory=args.include_advisory,
    )

    try:
        validate_contract(contract)
    except ValueError as e:
        print(f"[revise] contract 校验失败: {e}", file=sys.stderr)
        return EXIT_INVALID

    chapter_text = args.chapter_file.read_text(encoding="utf-8")
    plan = build_revise_plan(chapter_text, contract)
    target_text = targets_text(contract)

    # I5: contract 有 issue 但一个 §N 都没解析出来 → 退出非零
    has_resolvable_sections = bool(plan)
    has_any_issues = bool(contract.issues)

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
        if has_any_issues and not has_resolvable_sections:
            print("[revise] contract 有 issue 但没有 §N 段能解析", file=sys.stderr)
            return EXIT_INVALID
        return EXIT_OK

    if has_any_issues and not has_resolvable_sections:
        print("[revise] contract 有 issue 但没有 §N 段能解析", file=sys.stderr)
        return EXIT_INVALID

    # 真实重写：每个 section 调一次 LLM（同一段的所有 fix_hint 合并为一条指令）
    # 复用 rejection_contract.targets_text() 的按 location 聚合模式
    revised: dict[str, str] = {}
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for issue in contract.issues:
        # 把 location 展开为段 ID 列表（§2-§5 → §2..§5）
        for section_id in _expand_section_id(issue.location):
            if section_id not in grouped:
                order.append(section_id)
                grouped[section_id] = []
            grouped[section_id].append(
                f"[{issue.severity.value}/{issue.category}] {issue.fix_hint}"
            )

    for section_id in order:
        if section_id not in plan:
            continue
        joined_hints = "\n".join(grouped[section_id])
        revised[section_id] = call_llm_for_revision(
            section_id, plan[section_id], joined_hints, args.model,
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
