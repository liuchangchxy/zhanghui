# Jarvis 文学增益迁移实验（最小编辑原型）

- 日期：2026-11-07
- 分支：`feat/jarvis-literary-gain-20261107`
- 完整报告与产物：`experiments/jarvis-literary-gain-20261107/`
- 性质：独立实验。未修改正式主链、Canon、Data Agent、reconciliation、Step 2B / Step 4；未新增 Agent；未重跑完整 E2E。

## 问题

在保住 Zhanghui 的句段自然度与场景沉浸的前提下，能否提高阅读吸引力、减少作者解释？
Jarvis final 只用于分析，不进入编辑器输入，也不进入 A/B。

## 样本（生成前冻结）

ch03、ch04、ch05、ch08。规则与原因见
`experiments/jarvis-literary-gain-20261107/SAMPLE_SELECTION.md`：

- ch05：Jarvis 最强章（严格 12:0），目标两维均 2/2。
- ch03：Jarvis 次强（9:1），目标两维 2/2，但章回章首/场景仍有优势。
- ch08：Zhanghui 优势章（10:1），SN/SI/SUBTEXT 均 Z 2/2，仅 RA 输。
- ch04：分歧章（9 SPLIT），无稳定基线。

## 最小编辑原则

只五条，来自 final-vs-final 实际正文：

1. 删叙述者对动作/对白的意义总结。
2. 对白说清的信息不再由叙述者翻译。
3. 同一信息只留一处，删“总结—再总结”。
4. 章末收在已有动作/画面/新消息上。
5. 用已有的时间/身体/危险限制组织节拍；不新增事实。

## 盲评

- 两位不同模型族评委：J1 `codex/gpt-6.1-terra`，J2 Gemini 3.8 Flash。
- 每章每位评委两遍，第二遍强制位置反转；两遍同臂才计胜。
- 六维：OVERALL、RA、LAE、SN、SI、SUBTEXT。

结果：**48/48 个稳定判定全部指向编辑后的 B；0 SPLIT、0 TIE、0 A 胜。**
包括需要保住的 SN 与 SI。

## 内容检查

- 没有数字、日期、编号、事件结果、物品归属、知情状态或术语改写。
- 两处真实内容损失：
  - ch04 删掉“19/7 → 门/阀/岗位变更”的推理收束，以及“原值班室他进不去。第二张单子也不会有。”
  - ch05 删掉章末“交接班登记簿”的推动力，正文压到 87.7%（低于自设 90% 下限）。
- 一处轻微场景变薄：ch05 删“像是在咽半句话回去”。

## 判定

**PARTIAL**：文本层收益明确且稳定，但第一版把“解释”与“承担下一步功能的信息”一起删掉。
不是第 6 章式的大段误删，但属于同一失败模式的轻量版。

下一轮只需两条护栏加长度硬约束：

- 保护章末的下一步动作/时间地点/硬限制；
- 保护“数字/物件 → 结论”的推理连接句；
- 低于 90% 视为编辑失败，回滚到 A。

并给编辑器补下一章开头 1–2 句与本章硬限制清单。不要重建 Finalizer，不要新增 Agent，不要建复杂语义门禁。

## 证据

- 全文报告：`experiments/jarvis-literary-gain-20261107/report/REPORT.md`
- 文本归因：`.../analysis/ANALYSIS.md`
- 人工检查：`.../analysis/MANUAL_REVIEW.md`
- 盲评证据：`.../blind/EVIDENCE.md`、`.../blind/aggregate.md`
- 冻结哈希：`.../FREEZE.json`、`.../MANIFEST.json`
