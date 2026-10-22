---
name: scene-sequel
purpose: Dwight Swain Scene-Sequel 章内节拍定义
---

# Scene-Sequel (Chapter Level)

> **来源**：Dwight Swain《Techniques of the Selling Writer》

## Scene 4 步（场戏）

1. **Goal** — 主角本场戏明确目标
2. **Conflict** — 阻碍/对手出现
3. **Setback** — 挫败或失败
4. **Resolution** — 暂时结果（未必成功）

## Sequel 3 步（后续）

1. **Reaction** — 主角反应
2. **Dilemma** — 主角面对的困境
3. **Decision** — 主角决定 = 下章 Scene 的 Goal

## 与网文章节对应

每章 = 1 Scene + 1 Sequel（或压缩）

**BLOCKER 字段**（缺失即警告）：
- scene_goal
- scene_conflict
- sequel_decision

**WARNING 字段**（缺失仅提示）：
- scene_setback
- scene_resolution
- sequel_reaction
- sequel_dilemma

## state.json 字段

`chapter_meta.{N}.scene_*` 和 `chapter_meta.{N}.sequel_*`

## 校验

`story_craft.check_scene_sequel(chapter_meta)` 返回 issue 列表

## 执行形态：四个创作问题

七个字段是**规划检查表**，不是写作指令。Writer 不应该在正文里“填字段”，也不应该
背术语。规划完成后，把字段翻译成四个问题来执行：

1. **这一场主角现在具体想得到什么？**（scene_goal）
2. **什么力量在现场真正阻止他？**（scene_conflict）
   - 阻止力量不一定是反派人物：可以是制度、时间、证据矛盾、关系冲突、风险。
3. **主角因此被迫采取什么行动或选择？**（scene_setback → sequel_decision）
4. **场景结束后，人物/关系/局势/认知中什么已经发生实质变化？**（scene_resolution /
   chapter_change）
   - 信息发现本身可以构成变化，但不能只是“又知道了一条信息”。

约束：

- 不要求每章大高潮，也不要求每章不可逆灾难。
- `sequel_reaction` 若只写“见 story_craft 第N章 reaction 字段”，是悬空指针，不构成内容。
- `sequel_decision` 若指向“下章目标/下章钩子”，不属于本章结尾的决定，不要当作已填。
- 四问是创作指导，不是 gate、不是 Reviewer 维度、不产生评分。

