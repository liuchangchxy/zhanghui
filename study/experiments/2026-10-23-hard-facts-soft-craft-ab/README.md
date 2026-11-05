# Hard Facts, Soft Craft — 第二轮 A/B

## 问题

第一轮「writer-freedom」（`study/experiments/2026-10-23-writer-freedom-ab/`）证明：
简单删重复会让**关键事实失去冗余纠错**。ch7 的潮位差方向被写反（低 → 高），
ch10 的「年份连续性有缺口」被 Context Agent 理解成「月份空白」，Writer 忠实执行了
错误转述。同时 Brief、Router 说明和 Skill 原文都没有真的变短，prompt 总量反而上升。

本轮只验证一个更窄的命题：

> **事实要硬，写法要松。** 把一错毁章的事实放进 Writer 无法被改写的受保护区，
> 同时让 Brief / Router / Skill 真正变短，能否既保住章回控制力，又换回正文自由度。

## 两臂

| 臂 | 代码 | 含义 |
|---|---|---|
| A | `.worktrees/wf-code-A` @ `82e496d`（PR #62 HEAD，本轮未改） | 当前正式 Writer-facing 流程：旧 Context Agent 五段任务书、Router 二次编导、含规划术语与重复问句的 Writer Package |
| B | `feat/writer-freedom` 本轮修正 | 受保护硬事实 + Brief 1800 硬上限 + Router 120 硬上限 + Skill 共享预算 |

**A 臂的 Brief、Router 选择、封口 prompt、正文与 Reviewer 结果全部沿用第一轮同书同章的
归档产物**；A 的代码与输入没有变化，重跑只会引入新的随机噪声。B 臂全部从头生成。

## 固定不变

| 项 | 值 |
|---|---|
| 书 / Canon | 《海港旧信》，第 1–2 章已 accepted（`.tmp/wf-ab/book_B`） |
| 章纲 / 设定 / 时间线 | 同一份 `大纲/`、`.story-system/` |
| 受治理上下文 | 两臂来自同一 ContextManager 构建（第一轮已记录逐字节一致） |
| Writer 模型 | 同一模型、同一参数、各自独立起草会话 |
| 字数目标 | 2000–2500 汉字 |
| Reviewer | 同一 `zhanghui:reviewer`，full 模式 |
| 盲评 | 每章两名评委，阅读顺序相反，X/Y 随机映射；13 项评分 |

## 样本

| 章 | 类型 | 本轮关注点 |
|---|---|---|
| 第 6 章《修设备的人》 | 试探/交换，偏文学 | Writer 是否更自然、更少任务感 |
| 第 7 章《潮位不会说谎》 | 独处 + 程序/计算 | 「比官方记录低约 1 米」方向不能丢 |
| 第 10 章《值班表上的空白》 | 对峙 + 信息受限 | 「年份连续性缺口」不能被改成月份问题 |

## 判定

- `HARD_FACTS_SOFT_CRAFT_SUPPORTED`：关键事实不下降，文学质量明显改善。
- `HARD_FACTS_SOFT_CRAFT_NEUTRAL`：事实控制恢复，文学质量没有明显提升。
- `HARD_FACTS_SOFT_CRAFT_FAILED`：事实仍丢失，或文学质量继续下降。
- `CURRENT_DESIGN_STILL_BETTER`：当前正式设计仍整体更优。

先看硬条件（ch7 方向、ch10 缺口类型、Canon/timeline/causality 不比 A 差）；硬条件失败
直接判 B 不合格，再看文学质量。

**结果：`HARD_FACTS_SOFT_CRAFT_NEUTRAL`。** 硬条件全过（ch7 方向正确、ch10 缺口类型
正确、Reviewer 严重度加权 32→25），Writer prompt 缩短 46–49%，但盲评 A 4 : B 2，
调整后均分 A 7.82 / B 7.49，反向指标 B 更差。详见 `result.md`。
