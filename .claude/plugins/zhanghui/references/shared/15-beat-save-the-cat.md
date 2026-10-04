---
name: 15-beat-save-the-cat
purpose: Save the Cat 15-beat 卷级节拍表定义与网文/卷映射
---

# Save the Cat 15-Beat (Volume Level)

> **来源**：Jessica Brody《Save the Cat! Writes a Novel》(2018)
> **网文适配**：每卷 50-80 章 = 一本"小说"

## 15 个 Beat

| # | Beat | 卷内占比 | 50 章卷位置 |
|---|---|---|---|
| 1 | Opening Image | 0-1% | 第 1 章 |
| 2 | Theme Stated | 5% | 第 3 章 |
| 3 | Setup | 1-10% | 第 5 章 |
| 4 | Catalyst | 10% | 第 5 章 |
| 5 | Debate | 10-20% | 第 10 章 |
| 6 | Break Into Two | 20% | 第 10 章 |
| 7 | B Story | 22% | 第 11 章 |
| 8 | Fun and Games | 20-50% | 第 25 章 |
| 9 | **Midpoint** | 50% | **第 25 章（BLOCKER 必填）** |
| 10 | Bad Guys Close In | 50-75% | 第 37 章 |
| 11 | **All Is Lost** | 75% | **第 37 章（BLOCKER 必填）** |
| 12 | Dark Night of the Soul | 75-80% | 第 40 章 |
| 13 | Break Into Three | 80% | 第 40 章 |
| 14 | Finale | 80-99% | 第 49 章 |
| 15 | Final Image | 99-100% | 第 50 章 |

## 网文特殊说明

- **卷首章** = 第 1 章前 1-3% 必为 Opening Image（卷前主角状态快照）
- **Midpoint** 必须有反转或假胜利/假失败
- **All Is Lost** 是卷末最低点，没有 = 不叫卷
- **Final Image** 必须与下卷 Opening Image 形成呼应

## 与现有工具集成

- state.json 字段：`story_craft.volume_beat`
- 自动检查：Midpoint + All Is Lost 缺失 = BLOCKER
- 模板：见 `skills/webnovel-plan/references/outlining/volume-beat-sheet.md`
