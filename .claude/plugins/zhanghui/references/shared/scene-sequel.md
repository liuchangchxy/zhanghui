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
