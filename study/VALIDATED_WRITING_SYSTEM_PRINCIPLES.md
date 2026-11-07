# 已验证的写作系统原则（Canonical）

> 本文是 Zhanghui 写作系统经验的**唯一 canonical 副本**。
> 禁止把全文复制进 Skill、Context Agent、Reviewer 或 Writer Prompt；入口文件只放指针。

- 状态：生效中
- 适用对象：修改 Zhanghui 写作链、Writer 输入、Writing Skill、Reviewer、Literary Finalizer、
  semantic acceptance，或开展写作质量实验 / benchmark 的 Agent 与开发者
- 强制读取：进入上述工作前必须先读本文
- 结论效力：标记为 CONFIRMED / REJECTED 的结论，在没有**新的直接反证**时不得重新推翻或重复实验
- 更新方式：只有新的独立样本提供直接反证时才修改；修改必须写明证据路径与日期，不另建副本

---

## 1. CONFIRMED — 已确认

以下结论已被多轮真实实验支持。

### 1.1 Writer 输入

- 硬事实必须明确。
- 文学方法应保持软约束。
- Writer 输入太少会增加剧情 / 事实错误。
- 把方法步骤写成施工单会增加机械执行感。
- Creative Brief 应告诉 Writer：本章必须发生什么、不能写什么、人物目前处于什么状态；
  它不是系统字段或 JSON 的堆砌。

### 1.2 Writing Skills

- 完整 Skill 方法正文直接给 Writer 容易增加规则感。
- 更有效的形式是：选择少量适用 Skill，只提供核心原则与本章相关性。
- 写作方法应被 Writer 内化，不能在正文表面留下“按步骤执行”的痕迹。

### 1.3 文学后处理

- 多轮整章文学润色没有已验证收益。
- 历史 Step 2B rewrite-only + Step 4 再润色属于重复后处理。
- 当前路线是一轮 Literary Finalizer。

### 1.4 Literary Finalizer

已经稳定验证：

- 减少作者替读者解释；
- 减少对白后的翻译层；
- 减少重复线索复盘；
- 提升潜台词表达。

目前仍未确认：

- 是否能够稳定提高**整章总体文学质量**。

### 1.5 Semantic safety

- story state 与 discourse expression 必须区分。
- 删除一句显式心理判断、总结或解释，不自动等于故事状态变化。
- 真正需要保护的是：
  - 事件结果；
  - 人物实际知道 / 不知道的事实；
  - 决定与行动；
  - 行动对象；
  - 物品归属；
  - 时间、地点、数字；
  - 唯一关键因果；
  - 唯一线索；
  - 必要下一步行动。

### 1.6 Reviewer

- Reviewer 的主要职责是事实、Canon、连续性、时间线、人物、逻辑等可验证问题。
- Reviewer 不负责文学润色。
- 一次 Reviewer 扫描可能漂移；不应把单次 finding 当成绝对文学判断。

### 1.7 评测

- 文学比较优先使用真实正文。
- A/B 必须匿名、位置反转，尽量使用不同模型族。
- 总票数不是最终裁定。
- 最终必须读取真实 diff，解释“为什么更好 / 更差”。
- 最终上线判断必须包含**完全新章节**，不能只在参与过规则推导的旧样本上验证。

---

## 2. REJECTED — 已确认不值得继续

以下路线已有反证，没有新的直接反证时不得重开同类实验：

- rewrite-only Step 2B 作为主要文学提升机制；
- Step 2B + Step 4 连续整章文学润色；
- “删掉任何显式认知句 = semantic change”的二元判断；
- 把完整 Skill 方法步骤直接塞给 Writer；
- 一个坏样本出现后立即新增特殊规则；
- 文学实验自动扩张成全仓 / 全生产链审计；
- 因为“还能继续检查”而无限延长实验。

---

## 3. OPEN — 当前真正未解决的问题

### O1 — 整章总体文学质量是否稳定提升？

> Literary Finalizer 是否能够稳定提高**整章总体文学质量**？

当前证据：

- 去作者解释、增加潜台词等局部收益稳定；
- 第一个真正全新的生产章节的文学裁定为 `ROUGHLY_TIED`（两评审总体偏好分裂）；
  该轮流程验收报告另判 `PARTIAL`，原因是正文残留事实 blocker，与本 O1 的文学裁定不是同一维度。

状态：未解决。不得据此宣称 Finalizer 已能稳定提升整章质量。

### O2 — 压缩是否抹平了不同语义角色？

> Finalizer 是否容易把“不同动作 / 不同对象 / 不同收件人 / 不同义务 / 不同心理压力”
> 压成一个更简洁但更扁平的表达？

当前证据：

- 目前只在第 1 个全新章节出现一次（截图收件人被合并）。

状态：观察中。

约束：

- **不得现在修改 Prompt。**
- 必须先看它是否在新的独立章节中复现；稳定复现后才修改机制。

---

## 4. 实验原则

本节与上面的结论同等重要。

### 4.1 Primary Question First

每轮实验开始前必须写出唯一的 `PRIMARY QUESTION`。
实验报告的主判定必须优先回答它。

### 4.2 当 PRIMARY QUESTION 是文学质量时的证据优先级

严格按以下顺序：

1. Writer raw vs candidate 的文学质量；
2. 是否产生真实 story-state 损失；
3. 流程是否能够承接该结果。

Reviewer / Data Agent / commit / publish 等检查：

- 如果直接阻断实验 → 写入主报告；
- 如果没有阻断 → 作为背景或附带发现；
- 不得因为普通 typo、metadata warning、projection warning 等，
  把文学实验改写成生产系统审计。

### 4.3 不过拟合

单个样本暴露问题后：

1. 先记录；
2. 在独立新样本中确认是否复现；
3. 只有稳定复现后才修改机制。

### 4.4 Stop Rule

实验达到预先定义的回答条件后立即停止。

不要因为“还能继续分析”而增加：

- 新 Judge；
- 新维度；
- 新 Agent；
- 新 Gate；
- 新样本。

---

## 5. 证据索引

以下路径用于核对，不在本文重复报告内容。

| 结论领域 | 证据 |
|---|---|
| Scene 软约束 | `study/experiments/2026-10-22-scene-layer-ab/result.md` |
| Reader Pull | `study/experiments/2026-10-22-reader-pull-ab/result.md` |
| 少量 Skill + 本章相关性 | `study/experiments/2026-10-23-writing-skill-router-ab/result.md` |
| 一轮文学减法与 acceptance 边界 | `experiments/literary-finalizer-integration-20261107/report/REPORT.md`、`study/audits/2026-11-07-literary-finalizer-integration.md` |
| Finalizer 收益与过度删减 | `experiments/finalizer-ab-20261107/REPORT.md`（实验目录，未入 main） |
| 全新生产章节与 O1 / O2 | `e2e/real-chapter-acceptance-20261107` @ `fcd9276`：`experiments/real-chapter-e2e-20261107/REPORT.md`、`.../blind/SUMMARY.md` |

---

## 6. 维护规则

- 本文是唯一 canonical 副本；其它文件只能引用，不能复述为第二份“真相”。
- 修改 CONFIRMED / REJECTED 必须同时给出：新的独立样本、直接反证、日期。
- OPEN 项在没有复现前保持 OPEN，不因单次观察升级为规则。
- 实验报告可以引用本文，但不得把本文当作可以绕过 PRIMARY QUESTION 与 Stop Rule 的许可证。
