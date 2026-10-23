# Lean Continuity + Post-edit — 第四轮 A/B

## 问题

第三轮（`../2026-10-24-lean-skill-delivery-ab/`）把 Skill 正文撤出 Writer 之后，
「规则太多」5.00→4.25、「生硬执行技巧」5.42→4.08 都回落了，但留下两个明确缺陷：

1. **连续性事实漂移。** ch10 把旧报库从「报社后院 + 登记簿 + 纸质原报」改成
   「图书馆地下室 + 缩微阅读机」，同时改了地方志办公室的位置与准入流程；Reviewer 判
   1 条 critical + 4 条 high。ch7 也多了一条「上章约定未回应」。
2. **作者替读者总结。** 「作者直接解释」B 比 A 低 0.75，是第三轮唯一稳定退步的文学维度。
   而且它是在 Skill 正文撤掉之后**变得更差**的——说明它不是"写前规则太少"，而是写后没人管。

本轮只解决这两件事，不碰 Skill、不碰 Router、不碰 Brief 结构。

> **结果见 [`result.md`](result.md)：`LEAN_CONTINUITY_SUPPORTED_POSTEDIT_NEUTRAL`。**
> 连续性恢复（ch10 Reviewer 24→11，硬验收全过）；写后修复 0 命中 0 修改（召回不足）；
> 盲评 A 7.97 / B 7.23，选稿 4:1。

## 两个改动

| # | 改动 | 位置 |
|---|---|---|
| 1 | 新增写作前区域 `## 本章相关既有事实`（300–700 字，只放已 accepted 的地点/流程/物品/关系/世界规则） | `chapter_runtime.py` |
| 2 | 新增写后诊断 `show_then_explain` + 最小局部删除，复用现有 prose pipeline 与质检门禁 | `prose_diagnostics.py` / `prose_postedit.py` / `prose_pipeline.py` |

## 两臂

| 臂 | 代码 | 内容 |
|---|---|---|
| A | 原正式基线（第一轮归档，未改） | 强治理、完整 Brief、无受保护区、无连续性块 |
| B | `feat/writer-freedom` 本轮 | lean + 硬事实受保护区 + lean Skill + `本章相关既有事实` + 写后 show-then-explain 局部修复 |

**A 臂全部产物沿用前几轮归档**（brief / prompt / draft / review 逐字节复用），不重跑。

## 固定不变

- 同一 Governed Context、同一 Canon、同一章纲、同一模型与参数
- 同一 Creative Brief（1741–1783 字）
- 同一 Router 选择（`sel_B.json` 沿用，三章 Skill 与第三轮完全相同）
- 同一 Skill 交付形式（名称 + 一句原则 + 一句相关性，622–634 字）
- 同一 Reviewer（full 模式）、同一 2000–2500 字目标
- 同一 13 项盲评表（11 正向 + 2 反向）

## 样本

| 章 | 本轮重点 |
|---|---|
| ch6 | 上一轮 A/B 平手；连续性块是否干扰谈话章 |
| ch7 | 上一轮平手；潮位方向 + 上章约定承接 |
| ch10 | 上一轮 B 输掉两票且 Reviewer 1 critical；旧报库地点/流程/介质是否恢复 |

## 判定

- `LEAN_CONTINUITY_AND_POSTEDIT_SUPPORTED`：连续性恢复 + 作者直接解释明显减少 + 文学质量不弱于 A 且优于第三轮 B。
- `LEAN_CONTINUITY_SUPPORTED_POSTEDIT_NEUTRAL`：连续性明显恢复，后置解释腔没有稳定文学收益。
- `POSTEDIT_SUPPORTED_CONTINUITY_NEUTRAL`：解释腔改善，连续性仍无明显提升。
- `NEUTRAL`：两项都没有稳定变化。
- `FAILED`：连续性继续严重漂移，或后置修复明显伤害正文。

先看硬条件（ch7 方向与约定、ch10 地点/流程/介质/时间锚点），再看「作者直接解释」，最后看总体文学质量。
