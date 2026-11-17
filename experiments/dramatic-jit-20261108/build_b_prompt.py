#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build B's Writer prompt for the JIT dramatic-planning experiment.

B deliberately reuses A's governed Canon, constraints, prior-context and handoff
protocol verbatim, so the only differences are:
  1. Section 1 is a compact Hard Intent block instead of the runtime's
     Current Intent + Scene four questions + Reader Pull three questions.
  2. Section 3 is the JIT Creative Brief instead of the Context Agent brief.
Everything else is byte-identical to A's sealed prompt.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
A_PROMPT = HERE / "A_current_prompt.txt"
B_BRIEF = HERE / "B_jit_brief.md"
B_PROMPT = HERE / "B_jit_prompt.txt"

HARD_INTENT = """## 1. 本章硬性意图 (Hard Intent)
- 核心目标：室友陈默邀请林川组队，完成一个副本任务。
- 时间与地点：2026-05-03 下午；章内约 3 小时；现实地点为林川宿舍，游戏内为副本场景。
- 必须完成：陈默发出邀请；两人组队；完成副本首通。
- 必须到达的状态：林川与陈默建立首个固定队友关系。
- 必须覆盖：邀请、组队、副本难度高（单刷几乎不可能）、战利品分配、首通、陈默对林川“奇怪操作”的好奇。
- 本章禁区：不解释地球卡 / E-0001 / 记忆完整度 / 档案盒的来源；不让陈默知道林川的秘密；不提前引入赵公子或后续势力；不让木盾恢复或凭空换新盾；不让林川使用机关术卡面以外的技能。
- 信息释放边界：陈默只能观察到“操作不像新手”，不能得到原因；读者可以确认鲁班机关术在机关副本里的实战价值，但不能得到卡牌来源的解释。
- 剧情推进义务：本章结束前必须完成副本首通、交代分享战利品的代价，并让两人形成继续固定组队的关系；章末疑问不能替代本章实质兑现。
"""


def section(text: str, start: str, end: str) -> str:
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j]


def main() -> int:
    a = A_PROMPT.read_text(encoding="utf-8")
    brief = B_BRIEF.read_text(encoding="utf-8").strip()

    header = a[: a.index("## 1. 本章写作意图")]
    canon = section(a, "## 2. 治理事实与前情依据", "## 3. 创作策划任务书")
    constraints = section(a, "## 4. 调性、文风与避坑约束", "## 5. 关联前情线索")
    context = section(a, "## 5. 关联前情线索", "## 本章创作方法")
    skills = section(a, "## 本章创作方法", "## 6. 正文交付协议")
    handoff = a[a.index("## 6. 正文交付协议"):]

    b = (
        header
        + HARD_INTENT
        + "\n"
        + canon
        + "## 3. 创作策划任务书 (Creative Brief)\n"
        + brief
        + "\n\n"
        + constraints
        + context
        + skills
        + handoff
    )
    B_PROMPT.write_text(b, encoding="utf-8")
    digest = hashlib.sha256(b.encode("utf-8")).hexdigest()
    print(f"wrote {B_PROMPT} ({len(b.encode('utf-8'))} bytes)")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
