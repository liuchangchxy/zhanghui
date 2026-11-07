#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build and freeze the A-arm inputs for the six held-out chapters.

Inputs per chapter (frozen before generation):
  - source: Zhanghui final, packaging fingerprint removed
  - outline: governed-context current_intent.outline, verbatim
  - constraints: hard-limit list assembled from the same governed context
  - next opening: first 1-2 sentences of the next chapter (for hook protection)

No Jarvis text, no PR #66 edited output, and no blind result is read here.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (CHAPTERS, any_source_path, constraints_path,  # noqa: E402
                    governed_context_path, input_path, next_opening_path,
                    outline_path, source_path)


def strip_packaging(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"(?m)^\s*\*\*封包验证指纹[^\n]*\n?", "", text)
    text = re.sub(r"(?m)^\s*[0-9a-f]{64}\s*$\n?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def outline_field(outline: str, label: str) -> str:
    m = re.search(rf"(?m)^\s*-\s*{re.escape(label)}[：:]\s*(.+?)\s*$", outline)
    return m.group(1).strip() if m else ""


def first_sentences(text: str, limit: int = 2) -> str:
    prose = strip_packaging(text)
    lines = [ln.strip() for ln in prose.splitlines() if ln.strip()]
    if lines and re.match(r"^#{0,4}\s*第\s*[0-9零一二三四五六七八九十百千两]+章", lines[0]):
        lines = lines[1:]
    if not lines:
        return ""
    para = lines[0]
    parts = re.split(r"(?<=[。！？])", para)
    picked = "".join(parts[:limit]).strip()
    if not picked:
        picked = para
    return picked


def build_constraints(ch: int, ctx: dict) -> str:
    outline = ctx["current_intent"]["outline"].strip()
    directive = ctx["current_intent"].get("directive") or {}
    goal = directive.get("goal") or outline_field(outline, "目标")
    forbidden = directive.get("forbidden_zones") or []
    end_question = directive.get("chapter_end_open_question") or outline_field(
        outline, "章末未闭合问题")
    key_change = outline_field(outline, "关键变化")
    system = (ctx.get("constraints") or {}).get("system_constraints") or []

    lines = [
        "# 本章硬限制清单（生成前冻结，不可删除、不可写反）",
        "",
        "## 本章目标（结果不得改变）",
        f"- {goal}" if goal else "- （outline 未单列目标；按本章 outline 执行）",
        "",
        "## 本章必须发生的推进",
        "- 本章结束前，与目标直接相关的核心状态必须发生实质变化；"
        "不得只以“准备做某事”结束。",
    ]
    if key_change:
        lines.append(f"- 关键变化：{key_change}")
    lines += [
        "",
        "## 本章禁区（不得写出，不得提前揭示）",
    ]
    lines += [f"- {z}" for z in forbidden] if forbidden else ["- （无额外禁区）"]
    lines += [
        "",
        "## 章末未闭合问题（不得提前关闭）",
        f"- {end_question}" if end_question else "- 无",
        "",
        "## 系统约束",
    ]
    lines += [f"- {s}" for s in system] if system else ["- 无"]
    lines += [
        "",
        "## 事实层保护（硬）",
        "- 不得改动原文写出的数字、日期、编号、专业术语、事件结果、人物知情状态、"
        "物品归属、时间与地点。",
        "- 不得删除原文中明确的下一步动作、下一步调查方向、时间/地点硬限制、章末钩子、"
        "影响后续行动选择的信息。可以删它们前后的解释性总结，但不能删信息本身。",
        "- 对于“具体数字/物件/证据 → 角色得出的关键结论”，如果该结论不是读者可以立即、"
        "唯一推出的，必须保留连接句；允许压缩措辞，不允许整段删除。",
    ]
    return "\n".join(lines).strip() + "\n"


def next_chapter_opening(ch: int) -> tuple[str, str]:
    """Return (text, provenance). ch10 has no next chapter in this run."""
    nxt = ch + 1
    if nxt not in range(1, 11):
        return (
            "（本章是本次 run 的最后一章，没有下一章开头可用。"
            "章末保护信息请按原文最后一次明确的动作、新消息或下一步计划判断。）\n",
            "none: ch10 is the final chapter of the 2026-10-29 run",
        )
    p = any_source_path(nxt)
    text = first_sentences(p.read_text(encoding="utf-8"))
    return text + "\n", str(p)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> None:
    manifest = {}
    for ch, meta in CHAPTERS.items():
        src = source_path(ch)
        raw = src.read_text(encoding="utf-8")
        frozen = strip_packaging(raw)
        input_path(ch).parent.mkdir(parents=True, exist_ok=True)
        input_path(ch).write_text(frozen, encoding="utf-8")

        ctx = json.loads(governed_context_path(ch).read_text(encoding="utf-8"))
        outline = ctx["current_intent"]["outline"].strip() + "\n"
        outline_path(ch).write_text(outline, encoding="utf-8")

        constraints = build_constraints(ch, ctx)
        constraints_path(ch).write_text(constraints, encoding="utf-8")

        opening, opening_src = next_chapter_opening(ch)
        next_opening_path(ch).write_text(opening, encoding="utf-8")

        manifest[meta["key"]] = {
            "chapter": ch,
            "title": meta["title"],
            "source": str(src),
            "source_sha256": sha(raw),
            "frozen_input": str(input_path(ch).relative_to(Path(__file__).resolve().parents[1])),
            "frozen_sha256": sha(frozen),
            "outline": str(outline_path(ch).relative_to(Path(__file__).resolve().parents[1])),
            "outline_sha256": sha(outline),
            "constraints": str(constraints_path(ch).relative_to(Path(__file__).resolve().parents[1])),
            "constraints_sha256": sha(constraints),
            "next_opening": str(next_opening_path(ch).relative_to(Path(__file__).resolve().parents[1])),
            "next_opening_sha256": sha(opening),
            "next_opening_source": opening_src,
            "chars": len(frozen),
        }
        print(meta["key"], manifest[meta["key"]]["chars"],
              manifest[meta["key"]]["frozen_sha256"][:16])

    p = Path(__file__).resolve().parents[1] / "inputs/PROVENANCE.json"
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
