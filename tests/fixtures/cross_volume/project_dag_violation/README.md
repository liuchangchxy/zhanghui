# project_dag_violation fixture

故意违反伏笔 DAG 规则，用于驱动 Task 7 的 foreshadow_dag patch 三条检测路径：

## 三类违规

1. **循环依赖（cycle）** — `fs_001` ↔ `fs_002`：两者相互 `depends_on`，形成 DFS 环。
2. **提前回收（premature payoff）** — `fs_003`：`planted_chapter=5` > `paid_off_chapter=3`，回收时间早于埋设时间。
3. **超期未收（overdue）** — `fs_004`：`status=active` 但 `paid_off_chapter=5` < 当前章节，且超出 OVERDUE_TOLERANCE 容忍窗口。

## 章节号敏感性

OVERDUE_TOLERANCE = 50（patch 中定义）。超期检测的判定条件是：

```
chapter_num > paid_off_chapter + OVERDUE_TOLERANCE
```

因此：

- **chapter = 5**：可触发 cycle + premature；fs_004 仍未超期（5 < 5 + 50）。
- **chapter = 100**：可同时触发 cycle + premature + overdue（100 > 5 + 50）。

## 预期

foreshadow_dag patch 在 chapter=100 时应至少报 3 个 BLOCKER，分别对应上述三类违规。

## 用法

```python
from pathlib import Path
state = json.loads((Path("tests/fixtures/cross_volume/project_dag_violation/.webnovel/state.json")).read_text())
# state["story_craft"]["foreshadow_chain"]["dag"] 即违规 DAG
```