---
name: polish-guide
purpose: Step 4 定向润色与事实安全编辑参考 (Targeted Fact-Safe Editing)，基于审查诊断实施局部干预与事实安全回滚保护
---

# 定向润色与事实安全编辑指南（Targeted Fact-Safe Editing）

## 1. 核心定位与原则

<context>
本文件用于 **Step 4 润色阶段**。目标是“修复已诊断的具体问题”与“网文质感精修”，**绝对禁止“重写剧情”或“擅自创造新故事事实”**。

输入来自两部分：
1. 章节正文（Step 2 输出）
2. 审查与诊断报告（Step 3 聚合结果 + `prose diagnose` 输出）

核心职责划分：
- **Writer**：负责在 Intent 范围内进行文学创作，丰富细节，形成正文草稿。
- **Editor**：仅负责表达优化、节奏调谐、删除重复解释与修复被诊断出的模板腔。
- **严禁 Editor 充当 Story Repairer**：Editor 严禁自行编造新人物履历、新技能、新世界规则来修补剧情合理性漏洞。
</context>

## 2. 四大执行支柱

### 支柱一：Diagnose First（先诊断再修改）
- 不得对全篇无差别执行所有规则或通篇推倒重写。
- 必须基于 Step 3 Reviewer 报告与诊断器（`python3 -m data_modules.webnovel prose diagnose --file <path>`）输出的结构化问题清单行动。
- 诊断覆盖：
  * `stock_phrase`: 模板套话（眸中闪过、嘴角勾起冷笑、倒吸凉气等）
  * `narrator_over_explanation`: 旁白过度解释与元叙述（展示之后立即加解释句、"总而言之"、"可以说"等）
  * `repetitive_sentence_shape`: 机械句式重复（连续对仗"不是...而是..."）
  * `dialogue_exposition`: 对白背景说明书化（"正如你所知..."）
  * `character_voice_flattening`: 角色口吻扁平化（全员书面语或公文腔）
  * `micro_action_template`: 机械微动作套路（指节发白+深吸一口气+冷冷道）

### 支柱二：Targeted Editing（局部最小干预）
- **修改范围约束**：仅修改被诊断出的具体段落及其最小必要上下文。
- **保留文本呼吸感**：
  * 保留自然文本中的普通句与中长句。
  * 保留直接、真挚的情绪流露（不强行全换成生理微动作）。
  * 保留安静沉浸的场景过渡与非功能性氛围。
  * 不追求句句高信息密度的压缩电报体。

### 支柱三：Fact-Safe Semantic Diff（事实安全语义比对）
- 每次编辑完成后，必须执行语义对账：
  `python3 -m data_modules.webnovel prose diff-semantic --before <raw> --after <edited>`
- **事实边界红线**（命中任何一项立即拒绝覆盖）：
  * ❌ **人物履历**：严禁无中生有编造新经历（例如原文无"当过三年机修学徒"，Editor 为了合理性自行补入）。
  * ❌ **动机篡改**：严禁将"偶然/碰巧"的被动事件篡改为角色的"主动试探/心机设局"（例如"梅叔偶然露出钥匙"被篡改为"梅叔主动把钥匙拍到桌边试探林越"）。
  * ❌ **能力与技能**：严禁凭空赋予未建立的能力、境界或精通属性。
  * ❌ **事后补丁**：严禁加入"其实早已知晓/出门前偷偷准备"等全知补丁。
- **三态结论**：
  * `STYLE_ONLY_SAFE`：纯修辞与语感提升，允许接受。
  * `SEMANTIC_CHANGE_PROPOSED`：存在事实或动机篡改，**严禁覆盖正文**，保留原稿并提请故事层审议。
  * `UNCERTAIN`：改写幅度过大无法证明安全，保留原稿。

### 支柱四：Quality Regression Check & Rollback（退化回滚保护）
- 综合质检执行：
  `python3 -m data_modules.webnovel prose validate --before <raw> --after <edited>`
- **触发回滚的硬指标**：
  1. 语义漂移（`SEMANTIC_CHANGE_PROPOSED` 或 `UNCERTAIN`）。
  2. 篇幅异常缩水：字数减少超过 20%（`shrinkage > 0.20`）。
  3. 电报体节奏退化：平均句长骤跌 > 40% 且短句占比 > 60%（口吃碎片化）。
- **回滚机制**：
  * 若触发回滚，系统将正文重置为修改前文本（`final_prose = before_text`）。
  * 完整落库审计记录（`before`、`diagnosis`、`edit_plan`、`after`、`validation`、`decision`）。

## 3. 执行顺序

1. 修复审查报告中的 `critical`（必须）与 `high`（不能修复则记录 deviation）。
2. 处理已被实际诊断出的 `medium/low` 与模板套话。
3. 执行事实安全语义比对（`prose diff-semantic`）。
4. 执行退化回滚裁决（`prose validate`）。
5. 成功则输出润色后正文；失败则保留原稿并报告 `rollback_reason`。
