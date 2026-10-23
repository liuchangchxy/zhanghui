# Lean Skill Delivery — 第三轮 A/B

## 问题

第二轮（`../2026-10-23-hard-facts-soft-craft-ab/`）把硬事实钉住了，但文学质量没有提升：
盲评 A 4 : B 2，调整后均分 A 7.82 / B 7.49，而且**两项反向指标 B 更差**——
「规则太多」4.50→5.00，「生硬执行技巧」4.58→5.42（低分好）。

那一轮 B 的 Skill 段是 1597–1738 字，A 是 630–801 字。B 的总 prompt 只有 A 的一半，
但 Writer 读到的「文学方法论」比 A 多一倍多。B 的 Skill 段由两部分组成：

| 组成 | 第二轮实测（每章） |
|---|---|
| Router 的一句相关性说明 | 339–440 字 |
| 附带的 Skill 正文（核心原则 + 一个例子） | 1110–1153 字 |

本轮只验证一个假设：

> **Writer 不应该看到完整 Skill body。** 一句核心原则 + 一句本章相关性就够了。

## 两臂

| 臂 | 代码 | Skill 如何到达 Writer |
|---|---|---|
| A | `.worktrees/wf-code-A` @ `82e496d`（未改） | 只有 Router 的一句 `chapter_guidance`，不附 Skill 正文 |
| B | `feat/writer-freedom` 本轮 | 名称 + **一句**核心原则（`purpose` 首句）+ Router 的一句相关性 |

**A 臂全部产物沿用第一、二轮归档**（brief / prompt / sel / draft / review 五个文件
sha256 逐一核对相同），不重跑，避免引入新噪声。

## 本轮唯一改动

`writing_skill_registry.py`：

- `attach_skill_bodies()` 不再附 `## 方法` 条目、正反例、`applies_when` / `avoid_when`；
- 只取 Skill 自己的 `purpose`（它本来就是一句话），确定性提取，不调用 LLM、不新增字段；
- `TOTAL_SKILL_CONTENT_BUDGET = 700` 现在是**整段渲染结果**的上限，含标题、说明行、
  `【名称】` 与 `本章相关：`；
- 预算不够时**先压相关性说明**（按标点整句截断），核心原则只保底 40 字、不删。

`render_writer_skills()` 每个 Skill 输出两行：

```
1. 【情绪与内心】让读者感到"这个人此刻就是这样"，而不是"作者在写一段情绪戏"；……
   本章相关：这一章他整天一个人，情绪没有对话可以承载……
```

## 固定不变

| 项 | 值 |
|---|---|
| 书 / Canon | 《海港旧信》，第 1–2 章 accepted（`.tmp/wf-ab/book_B`） |
| 章纲 / 设定 / 时间线 | 同一份 `大纲/`、`.story-system/` |
| 受治理上下文 | 与第二轮逐字节相同 |
| Creative Brief | 第二轮同一份（1661–1783 字），未改 |
| Router 选择与说明 | 第二轮同一份 `sel_B.json`，未重跑 Router |
| `## 本章必须写对` | 与第二轮**逐字节相同**（已核） |
| Writer 模型 / 参数 | 同一模型，独立起草会话 |
| 字数目标 | 2000–2500 汉字 |
| Reviewer | 同一 `zhanghui:reviewer`，full 模式 |
| 盲评 | 每章两名评委、阅读顺序相反、X/Y 随机映射、13 项同一量尺 |

## 样本

| 章 | 关注点 |
|---|---|
| 第 6 章《修设备的人》 | 上一轮 A 赢 2:0；看 Skill 正文撤出后规则感是否下降 |
| 第 7 章《潮位不会说谎》 | 上一轮 B 赢 2:0；看 B 的优势是否还在 |
| 第 10 章《值班表上的空白》 | 上一轮 A 赢 2:0；硬事实是年份缺口 |

## 判定

- `LEAN_SKILL_DELIVERY_SUPPORTED`：硬事实不下降 + 规则感明显改善 + 文学质量整体优于上一轮 B 且至少不弱于 A。
- `LEAN_SKILL_DELIVERY_PARTIAL`：规则感改善，但文学质量仍接近 A / 无明显净提升。
- `LEAN_SKILL_DELIVERY_NEUTRAL`：Skill 段显著缩短，正文基本不变。
- `LEAN_SKILL_DELIVERY_FAILED`：硬事实下降，或文学质量继续恶化。

先看硬条件（ch7 方向、ch10 缺口类型），再看两项反向指标，最后才看文学质量。

## 结果

**`LEAN_SKILL_DELIVERY_PARTIAL`** —— 见 `result.md`。

Skill 段 1738/1613/1597 → **622/634/631**（−64%/−61%/−60%），prompt 再降 13–15%。
「规则太多」5.00 → 4.25、「生硬执行技巧」5.42 → 4.08，两项都从落后 A 变成领先 A；
但六次盲评 A 3 : B 3、调整后均分 A 7.81 / B 7.80，文学质量没有动。
ch10 出现 1 条 critical 连续性错误（旧报库地点与第 2 章冲突），记为风险不记为因果。
