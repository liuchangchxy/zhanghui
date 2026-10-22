# 第二轮 A/B（规则显形修正后）

## 为什么有这一轮

第一轮 verdict 是 `LITERARY_SKILLS_QUALITY_UNPROVEN`。第 5 章的失败模式被评委指出：
Writer 把 Skill 的**方法步骤**当成了正文结构——判据编号变成小标题、推理链被完整摊开。

本轮唯一目标是验证：把 Skill 从“执行步骤”改写成“隐性写作指导”之后，
**规则显形是否消失、文学质量是否稳定提升**。

本轮不再调参、不再加 Skill、不再改 Router。只改了三个 Skill 的措辞与正反例。

## 固定不变

| 项 | 值 |
|---|---|
| 书 / Canon | 《海港旧信》，第1–2章已 accepted |
| 代码基线 | 臂 A `origin/main` (a41ac35)；臂 B 本分支 HEAD（Skill 措辞修正后） |
| 受治理上下文 | 两臂 `runtime governed-context` 逐字节相同（md5 见各章 README） |
| Creative Brief | 两臂同一文件，由同一 context-agent 产出后原样复制 |
| Scene 四问 / 追读三问 | 两臂都启用 |
| 字数目标 | 2000–2500 汉字 |
| 起草方式 | 两臂各一个独立起草会话，只读自己的 sealed prompt |

## 唯一变量

Skill 库：A 为 6 个，B 为 9 个，且 B 的三个新 Skill 是**修正后的措辞**。

## 样本

- 第 5 章（内省章）——与第一轮同一章，可对比“修正前后”。
- 第 4 章（对峙章）——双人物对话 + 试探，适合检验 `emotion-interiority` 与 `pov-distance`
  在对手戏里的规则显形。

两章，不扩大。

## 评价重点

除既有 13 项评分外，本轮额外人工判断：

1. B 是否还出现“规则写进正文”；
2. B 是否比 A 更自然；
3. 情绪表达是否更像人物而非作者解释；
4. 描写是否自然而非任务式插入；
5. Writer 是否明显受束缚。

## 判定（事先写定）

- `LITERARY_SKILLS_SUPPORTED`：B 稳定、可感知更好，且无规则显形。
- `LITERARY_SKILLS_QUALITY_UNPROVEN`：机械问题改善，但文学质量仍无稳定提升 → 停止调参。
- `LITERARY_SKILLS_OVERCONSTRAINED`：Writer 仍明显被规则控制，正文更刻意机械。
