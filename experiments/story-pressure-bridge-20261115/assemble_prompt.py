#!/usr/bin/env python3
"""Assemble the After-arm prompt from the canonical pack plus a live pressure digest.

The first two rounds hand-copied the pack into a prompt file and hand-copied the digest
into it too. Both drifted from their sources, which is how the experiment ended up
testing a book that does not exist. This script removes the copy step: the prompt is
always exactly `CANON_PACK.md` + the current `story-pressure` output + the fixed
planning requirements.

Usage:
    python3 experiments/story-pressure-bridge-20261115/assemble_prompt.py > out.md
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
REPO = EXP_DIR.parents[1]
PACK = EXP_DIR / "CANON_PACK.md"
PROJECT = REPO / ".tmp" / "final-e2e-fresh-20261104"
CHAPTER = 7
LIMIT = 8

REQUIREMENTS = """### 规划要求

1. 从上面清单里挑出**本章真正要接住**的压力（1–3 条，不要机械消费全部），
   并在章纲里写一行 `**承接压力**：<ID>、<ID>`。
2. 章纲里要能看出**为什么是现在**：不早不晚。
3. 章末必须至少有一项真实状态改变（关系／权力／风险／承诺／信息分布），
   且不能在本章内被抹平。
   **注意**：不要靠「某人交出某物」或「发明一套新的行政流程」来制造改变。
   设定集或前文已经写死的人物既定立场与底线，不得为了让本章更有后果而被推翻——
   那不是承接故事，是拿 Canon 换戏剧性。
   改变也可以来自他知道了什么、怕什么、欠了什么、被谁盯上。
4. 不要重复最近三章的结构。
5. **不要重开已经结清的线**（见 Canon 第 4 节的「已结清的线」）。本章的冲突必须来自
   现在仍然活着的东西，不是把上一章已经办完的事再办一遍。
   清单里的条目是 `state.json` 的**原文摘录**，可能同时包含已办完的旧事（例如某条警告的
   原话里提到「清点单今天交齐」）。只接住那条压力**现在仍然活着的部分**。
6. 清单里的 `TL-` 是**卷级**里程碑（如 Midpoint、All Is Lost），不是本章能承接的压力；
   不要选它们来填 `**承接压力**`，也不要为了兑现它们而提前写后面的章。
7. 只输出一个章纲，格式如下（字段名必须一致）：

```
### 第7章：<标题>

**目标**：
**阻力**：
**代价**：
**核心冲突**：
**承接压力**：<ID>、<ID>
**本章变化**：
**未闭合问题**：
**钩子**：

**新增 craft 必填字段**：
- **beat_position**：
- **scene_goal**：
- **scene_conflict**：
- **scene_setback**：
- **scene_resolution**：
- **sequel_reaction**：
- **sequel_dilemma**：
- **sequel_decision**：
- **hook_type**：
- **foreshadow_buried**：
- **foreshadow_paid_off**：

**结构化节点**：
- **CBN**：主体 | 动作/变化 | 对象/结果
- **CPNs**：主体 | 动作/变化 | 对象/结果（2–4 条，按时间顺序）
- **CEN**：主体 | 动作/变化 | 对象/结果
- **必须覆盖节点**：
- **本章禁区**：
```
"""


def main() -> int:
    digest = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(REPO / ".claude/plugins/zhanghui/scripts/webnovel.py"),
            "--project-root",
            str(PROJECT),
            "story-pressure",
            "--chapter",
            str(CHAPTER),
            "--limit",
            str(LIMIT),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    pack = PACK.read_text(encoding="utf-8").strip()
    out = [
        "（以下为本次规划的全部输入。不要读取任何其它文件，不要查看既有第 7 章章纲。）",
        "",
        pack,
        "",
        "---",
        "",
        "## 本次规划",
        "",
        "上面第 9 节的任务不变。下面是系统在规划前自动派生的**故事压力清单**（从 state.json 的",
        "story_craft / plot_threads / entity_state / chapter_meta 机械提取，不是人工整理的）。",
        "条目文本是 `state.json` 的原文摘录，保留其原始措辞（含已经办完的旧事）。",
        "",
        digest,
        "",
        REQUIREMENTS,
    ]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
