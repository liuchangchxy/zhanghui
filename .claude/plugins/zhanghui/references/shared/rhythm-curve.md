---
name: rhythm-curve
purpose: 节奏曲线 — 1.8 章/情绪高峰，平路 ≤3 章
---

# 节奏曲线 (Rhythm Curve)

> **来源**：马良写作《网文节奏与爽点设计》（基于追读 top10% 数据分析）

## 核心定义

> "网文的节奏是信息投放和情绪刺激的频率。"

> "平路走超过 3 章，追读就开始掉。"

## 数据基准

| 指标 | 追读率 top 10% | 追读率 bottom 10% |
|---|---|---|
| 平均情绪高峰间隔 | 1.8 章 | 4.7 章 |

## 阈值

- **warning_threshold** = 3 章（连续 3 章无高峰 → WARNING）
- **block_threshold** = 5 章（连续 5 章无高峰 → BLOCKER）

## 三级爽点

| 级别 | 频率 | 例子 |
|---|---|---|
| 小爽点 | 每章 ≥1 | 一句机智台词、一个小反转 |
| 中爽点 | 每 3-5 章 1 | 完整打脸流程、关系突破 |
| 大爽点 | 每卷高潮 1 | Boss 战逆转、身份曝光 |

## 与工具集成

- state.json：`story_craft.rhythm_curve`
- 字段：`chapters_since_peak` / `warning_threshold` / `block_threshold` / `history`
- 检查：`check_rhythm_status(state)` 返回 `ok | warning | block`
- 记录：`record_emotion_peak(state, chapter, intensity, type)`
