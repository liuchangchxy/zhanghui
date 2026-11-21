# 文学编辑器 Held-out 外部验证（PR #66 原则）

- 日期：2026-11-07
- 分支：`feat/jarvis-literary-heldout-20261107`
- 完整报告与产物：`experiments/jarvis-literary-heldout-20261107/`
- 性质：独立实验。未修改正式主链、Canon、Data Agent、reconciliation、Step 2B / Step 4；
  未新增 Agent；未重跑完整 E2E。

## 问题

PR #66 的五条文学编辑原则在 ch03/ch04/ch05/ch08 上得到 48/48 偏 B，但那四章参与了
原则提炼。本轮把原则冻结，只在未参与提炼的六章上测试：

> 这些原则是否还能稳定提高文学性，同时不损坏内容？

## 样本（生成前冻结）

ch01、ch02、ch06、ch07、ch09、ch10。六章全部使用，不允许换章。
ch01/ch02/ch06 曾在 PR #66 的归因阶段作为补充材料读过（五条原则不由它们提炼），
作为外部有效性限制记录。

## 机制

- 五条原则逐字复用 PR #66。
- 只新增三个来自上一轮真实失败的护栏：推进信息保护、必要推理连接保护、90% 长度硬约束。
- 编辑器：`group/mac-deepseek4.1-gpt[1m]`，temperature 0.4，每章只生成一次。

## 结果

- 六章全部通过长度护栏（92.50%–98.02%），无重试、无截断。
- 两位不同模型族评委、每章两遍位置反转、六维：
  **72/72 个稳定判定全部偏 B；0 SPLIT、0 TIE、0 A 胜。**
- 章级 `OVERALL`：6/6 严格偏 B。
- `READING_APPEAL`、`LOW_AUTHOR_EXPLANATION`、`SENTENCE_NATURALNESS`、
  `SCENE_IMMERSION` 均 12/12 B。

## 内容检查

- **HARD：0。** 没有改变事件结果、知情状态、物品归属、数字/日期/编号、专业术语；
  没有删掉唯一的下一步动作/调查方向/时间地点硬限制；没有长度违规。
- **SOFT：6 章均有。** 最明显：
  - ch02 章末独立成段的“明天。”被删（信息仍在对白中，章末落点丢失）；
  - ch06 “不是问。”与“他换到的，比交出去的少。”被删；
  - ch09 结尾唯一感官记忆句被删；
  - ch07 “乔宁的手没把它推回来”的谈判动作被删。
- 三个护栏挡住了 PR #66 式的 HARD 误删，但没有保护章末钩子、情绪结算与结尾感官承载；
  评委有时把这类删减当作优点，说明盲评不能替代内容检查。

## 判定

**PARTIAL**：文学收益稳定且可泛化，事实/功能层无 HARD 损失；但章末钩子与文学承载层
出现少量可定位的 SOFT 损失，不能判 PASS；没有 HARD 损失与 SN/SI 系统性下降，也不判 FAIL。

下一轮只需补一条窄护栏：独立成段的章末短钩子、情绪结算句、结尾感官句不得删。
不需要新架构、新 Agent 或语义门禁。

## 证据

- 报告：`experiments/jarvis-literary-heldout-20261107/report/REPORT.md`
- 内容检查：`.../analysis/CONTENT_CHECK.md`、`.../analysis/MANUAL_REVIEW.md`
- 盲评：`.../blind/aggregate.md`、`.../blind/EVIDENCE.md`
- 冻结：`.../FREEZE.json`、`.../ANALYSIS_PLAN.lock.json`、`.../MANIFEST.json`
