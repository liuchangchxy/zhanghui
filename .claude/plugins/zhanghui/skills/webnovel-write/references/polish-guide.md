---
name: polish-guide
purpose: Step 4 表达层定向润色指南（Style-Only Targeted Polish）：诊断驱动、最小干预、语义零漂移
---

# 表达层定向润色指南（Style-Only Targeted Polish）

## 1. 核心定位与原则

<context>
本文件用于 **Step 4 润色阶段**。目标是"把已经写对的事说得更好"，不是"把事改对"。

输入来自两部分：
1. 章节正文（Step 2 输出）
2. `prose diagnose` 的结构化病灶清单（Step 4 的修订目标来源）

职责划分：
- **Writer**：在 Intent 范围内创作，决定"发生什么"。
- **Editor**：只改"怎么说"——措辞、句式、节奏、段落切分、描写方式、对话表达、反 AI 痕迹。
- **Editor 不得充当 Fact Repairer / Story Repairer**：事实、设定、时间线、逻辑问题不属于本步。
  Reviewer 报出的这类问题会以 `owner=FACT_REVIEW` 进入 `plan.deferred`，由 Canon gate 阻断或在显式事实纠错路径处理。
  把"修事实"塞进润色，正是 Step 4 语义漂移的来源。
</context>

### 允许 / 禁止（硬边界）

| 允许 | 禁止 |
|---|---|
| 措辞替换、同义改写 | 人物已知信息、知情状态 |
| 句式与句长调整 | 事实真伪、时间、地点 |
| 节奏与段落切分 | 事件顺序、行为结果 |
| 描写方式与感官细节重述（不新增信息） | 物品归属、能力、境界 |
| 对话表达与角色口吻贴合 | Canon 设定、世界规则 |
| 去 AI 痕迹、去套话 | 新增线索、人物互动、因果 |

判断标准：改写前后必须仍是**同一件事的不同说法**。若某条病灶只能靠"补一句事实"来消除，
说明它不是表达问题——跳过该目标，不要硬改。

## 2. 四大执行支柱

### 支柱一：Diagnose First（先诊断再修改）
- 不得对全篇无差别执行所有规则或通篇推倒重写。
- 以 `prose diagnose --file <path> --format json` 的结构化输出为唯一病灶来源；
  再用 `revise plan --style-only --diagnosis-file <diagnosis.json>` 把可定位病灶转成定向修订目标。
- 诊断覆盖：
  * `stock_phrase`: 模板套话（眸中闪过、嘴角勾起冷笑、倒吸凉气等）
  * `narrator_over_explanation`: 旁白过度解释与元叙述（展示之后立即加解释句、"总而言之"、"可以说"等）
  * `repetitive_sentence_shape`: 机械句式重复（连续对仗"不是...而是..."）
  * `dialogue_exposition`: 对白背景说明书化（"正如你所知..."）
  * `character_voice_flattening`: 角色口吻扁平化（全员书面语或公文腔）
  * `micro_action_template`: 机械微动作套路（指节发白+深吸一口气+冷冷道）

### 支柱二：Targeted Editing（局部最小干预）
- **修改范围约束**：仅修改计划命中的具体段落及其最小必要上下文；计划外的句子不动。
- **保留文本呼吸感**：
  * 保留自然文本中的普通句与中长句。
  * 保留直接、真挚的情绪流露（不强行全换成生理微动作）。
  * 保留安静沉浸的场景过渡与非功能性氛围。
  * 不追求句句高信息密度的压缩电报体。

### 支柱三：Semantic Zero-Drift（语义零漂移校验）
- 每次编辑完成后，必须用绑定的 Semantic Judge 做语义对账：
  `prose validate --before-file <raw> --after-file <edited> --judge-file <judge_verdict.json>`
- Step 4 的自动润色**不传** `--revision-plan`：纯表达改动没有事实可纠，声明事实纠错是另一条路径。
- **事实边界红线**（命中任何一项立即拒绝覆盖）：
  * ❌ **人物履历**：严禁无中生有编造新经历（例如原文无"当过三年机修学徒"，Editor 为了合理性自行补入）。
  * ❌ **动机篡改**：严禁将"偶然/碰巧"的被动事件篡改为角色的"主动试探/心机设局"。
  * ❌ **能力与技能**：严禁凭空赋予未建立的能力、境界或精通属性。
  * ❌ **事后补丁**：严禁加入"其实早已知晓/出门前偷偷准备"等全知补丁。
  * ❌ **事实改口**：严禁把"十年前"改成别的年数、把受伤改成无伤、把物品换到另一个人手里。
- **三态结论**：
  * `STYLE_ONLY_SAFE`：纯修辞与语感提升，允许接受。
  * `SEMANTIC_CHANGE_PROPOSED`：存在事实或动机篡改，**严禁覆盖正文**，保留原稿。
  * `UNCERTAIN`：改写幅度过大无法证明安全，保留原稿（不得伪造 Judge 裁决强行放行）。

### 支柱四：Quality Regression Check & Rollback（退化回滚保护）
- 综合质检与语义校验同一条命令完成（见支柱三）。
- **触发回滚的硬指标**：
  1. 语义漂移（`SEMANTIC_CHANGE_PROPOSED` 或 `UNCERTAIN`）。
  2. 篇幅异常缩水：字数减少超过 20%（`shrinkage > 0.20`）。
  3. 电报体节奏退化：平均句长骤跌 > 40% 且短句占比 > 60%（口吃碎片化）。
- **回滚机制**：
  * 若触发回滚，系统将正文重置为修改前文本（`final_prose = before_text`）。
  * 完整落库审计记录（`before`、`diagnosis`、`edit_plan`、`after`、`validation`、`decision`）。

## 3. 执行顺序

1. 运行 `prose diagnose --file <path> --format json`，落盘病灶清单。
2. 运行 `revise plan --style-only --diagnosis-file <diagnosis.json>`，得到定向修订目标；
   `deferred` 中的 `FACT_REVIEW` / `ADVISORY` / `ARTIFACT_REPAIR` / `GOVERNANCE_REPAIR` 不在本步改正文。
3. 按目标逐条改写对应句段；做不到就跳过（记为 `untouched_targets`），不硬改。
4. `revise apply` 应用替换，`revise verify` 校验改动只落在计划区间。
5. `prose validate` + 绑定 Judge 做语义与退化裁决；必须 `ACCEPTED` / `STYLE_ONLY_SAFE`。
6. 成功则输出润色后正文；失败则保留原稿并报告 `rollback_reason`。
