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

### O3 — 「Brief 完成后、封口前只追加开场承接」能否在不重规划本章的前提下获得跨章因果收益

> 在 Context Agent 按原章纲产出完整 Creative Brief 之后、Native Writer Package 封口之前，
> 只追加两行「开场承接」（本章开场立刻回应上一章 durable accepted 的一件具体事），
> 是否能让连续章节的跨章因果承接明显强于原流程，且不增加 Canon / 人物不变量冲突？

当前证据（2026-11-17，新样本第 4–6 章，未参与该实现的设计）：

- **判定 PASS**（五项预定义条件全部满足，报告见 `experiments/opening-bridge-20261117/REPORT.md`）。
- **来源可验证**：三章承接均追溯到上一章 accepted commit 的 `sha256`；
  上一章 rejected → `available=false` 且**不回退**到更早的 accepted 章节（有测试锁定）。
  不使用未提交的 Data Agent 提取、临时摘要或规划者对上一章的预期。
- **原任务书逐字节保留**：`split_composed_brief()` 拆出的原任务书与 Context Agent 原始输出
  完全相同；两臂章纲 `sha256` 逐字相同；承接是唯一额外创作输入（2 行，≤220 字）。
- **核心剧情不漂移**：两臂核心动作与对象相同，节点覆盖 `missed = 0`。
- **因果承接**：3/3 独立盲评（含位置反转）判「加了承接」的一臂更强。
- **Canon**：独立双审计硬冲突 2 vs 3（加承接的一臂不多）；承接正文本身未发明新的世界事实。
- **必须记录的代价与副作用**：
  1. 承接的形式强度不均匀——结构审计认为其中一章的开场回应者是本章才首次上页的角色，
     严格口径下不算「已出场角色回应」；三章里只有两章成立。
  2. **承接会放大 Writer 的普通事实错误**：为了让上一章的角色问出上一章的事，
     Writer 自行补了副本准入规则、「原来的搭档放鸽子」、与上一章「室友还没回来」相抵的
     幕后目击事件。这些不在承接正文里，是 Writer 依据承接展开的，属普通事实错误，
     本轮按约束未修。
  3. 另一章被判人物不变量硬冲突（主角独自定计划），但该判断来自 Context Agent 自己的
     Brief，不是承接写的。
- 状态：**已进生产**（`scripts/data_modules/opening_bridge.py`、`runtime opening-bridge`、
  `attach-creative-brief --opening-bridge-file`、`webnovel-write` Step 1B3/1C、
  `webnovel-fast-write` 2b）。
- **可以宣称**：承接来源可以是 durable accepted commit 且无回退；原任务书可逐字节保留；
  三章内跨章因果承接在盲评中稳定更强；硬冲突数不高于原流程。
- **不得宣称**：它消除了 Writer 的普通事实错误（已证伪，见副作用 2）；
  它消除了人物不变量越界；它在 n=1 之外稳定（每臂每章只生成一次，未估计 Writer 方差）；
  它改善整体文学质量（本轮未测文学分差）。
- **下次若重开**：先回答「承接带来的新场景触发，如何不把 Writer 推向补造准入规则/前情」。
  不要因为 PASS 就扩大承接权限（例如让它改本章目标或结尾）。

约束：

- 承接只允许两行、≤220 字、只作用于开场；形状由封口时的 `_check_bridge_body` 强制
  （恰好两行、必需前缀、不得含 `【…】` 段标题），不依赖编排纪律。
- 不要为它新增 Gate、Reviewer、Planner 或第二份 Writer Prompt。

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
| O3 Brief 后开场承接 | `experiments/opening-bridge-20261117/REPORT.md` |

---

## 6. 维护规则

- 本文是唯一 canonical 副本；其它文件只能引用，不能复述为第二份“真相”。
- 修改 CONFIRMED / REJECTED 必须同时给出：新的独立样本、直接反证、日期。
- OPEN 项在没有复现前保持 OPEN，不因单次观察升级为规则。
- 实验报告可以引用本文，但不得把本文当作可以绕过 PRIMARY QUESTION 与 Stop Rule 的许可证。
