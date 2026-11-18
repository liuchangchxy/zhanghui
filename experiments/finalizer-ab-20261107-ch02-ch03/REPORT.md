# Literary Finalizer 三章真实章节验证报告

- 实验日期：2026-11-07
- 分支：`experiment/finalizer-ch02-ch03-20261107`
- PRIMARY QUESTION：**Literary Finalizer 是否能在两个新的真实章节上稳定提高整章总体文学质量？**
- 机制：ch02、ch03 使用完全相同的冻结机制；未改 Writer Prompt、Finalizer Prompt、五条文学原则、semantic acceptance、Reviewer、Writing Skill，未新增 Agent / Gate。
- 文学裁定均发生在 Reviewer 修改正文之前；raw / candidate 在任何生产修复前已冻结并计算 SHA-256。

---

## 第 2 章

- raw：`ch02/raw.md`（SHA `830b41a2…`，2005 汉字）
- candidate：`ch02/candidate.md`（SHA `cedf0087…`，1925 汉字，96.0%）
- diff：`ch02/diff.txt`；盲评：`ch02/blind/`

### 12 项盲评（已归一）

| 维度 | J1（Gemini） | J2（proxy） |
|---|---|---|
| OVERALL_PREFERENCE | CANDIDATE (0.85) | CANDIDATE (0.62) |
| READING_APPEAL | CANDIDATE (0.80) | CANDIDATE (0.58) |
| LOW_AUTHOR_EXPLANATION | CANDIDATE (0.95) | CANDIDATE (0.86) |
| SENTENCE_NATURALNESS | CANDIDATE (0.80) | TIE (0.55) |
| SCENE_IMMERSION | CANDIDATE (0.80) | CANDIDATE (0.60) |
| SUBTEXT | CANDIDATE (0.90) | CANDIDATE (0.80) |

计数：candidate 11 / raw 0 / TIE 1。J1 甲=RAW、乙=CANDIDATE；J2 甲=CANDIDATE、乙=RAW。

### 最终裁定：**CANDIDATE_BETTER（小幅）**

决定性改动是 5 组删除：

1. 删“他知道这种池子，前几次给的东西不会太好……”——抽卡心理预判，四次空抽已经展示。
2. “四次，四百碎片” → “四次”——总额可由 4×100 直接算出。
3. 删“木盾能挡，但不能打”——卡面“防具 / 格挡 +1”且无攻击栏已承载。
4. 删“也没有安慰他”——对 NPC 非动作的拟人化解读。
5. 删“这七个词他闭着眼都能背出来”、重复的“余额是十八个碎片”、“没有说明”——重复与总结。

### Story-state

全部 7 条 Judge change 为 `DISCOURSE`；事件、知情、决定、行动对象、物品归属、时间地点数字、唯一因果与线索均未变。**无 Finalizer 引入的 story-state 损失。**（两路 Judge 独立发现的“121 vs 118”是 raw 共有的原文算术问题，不属于 Finalizer。）

### O2

**未复现。** 退款与继续抽卡、引导员两句异常提示、卖卡与抽卡均保持分离。

---

## 第 3 章

- raw：`ch03/raw.md`（SHA `de8575b3…`，1881 汉字）
- candidate：`ch03/candidate.md`（SHA `9264f97f…`，1867 汉字，99.3%）
- diff：`ch03/diff.txt`；盲评：`ch03/blind/`

### 12 项盲评（已归一）

| 维度 | J1（Gemini） | J2（proxy） |
|---|---|---|
| OVERALL_PREFERENCE | CANDIDATE (0.85) | CANDIDATE (0.58) |
| READING_APPEAL | CANDIDATE (0.80) | TIE (0.62) |
| LOW_AUTHOR_EXPLANATION | CANDIDATE (0.90) | CANDIDATE (0.82) |
| SENTENCE_NATURALNESS | TIE (0.75) | TIE (0.66) |
| SCENE_IMMERSION | CANDIDATE (0.80) | TIE (0.72) |
| SUBTEXT | CANDIDATE (0.85) | CANDIDATE (0.74) |

计数：candidate 8 / raw 0 / TIE 4。J1 甲=RAW、乙=CANDIDATE；J2 甲=CANDIDATE、乙=RAW。

### 最终裁定：**ROUGHLY_TIED**

全章只删了两处否定式过渡，合计 16 字：

1. 删“林川没有急着上去。”——紧接的“他先看地形”已经展示同一行为；代价是“它们→他”的主语切换少一个锚点，J1 也把 SENTENCE_NATURALNESS 判 TIE。
2. 删“林川没有再踩。”——“插销锈死了”已经解释为何不再踩，直接接“把机关术拖到插销上”更紧。

两处都不承担独有信息，删除没有损失；但幅度太小，不改变整章阅读质量，故不是 CANDIDATE_BETTER。

### Story-state

两处均为 `DISCOURSE`；门禁数字值集合比对通过，事件、知情、决定、物品、时间地点、因果链、`伤害来源：未登记` 线索与章末威胁均保留。**无 story-state 损失。**

### O2

**未复现。** 两套机关、两次不同操作；木盾格挡与碎片反击；三段威胁台词；委托奖励与 PVP 奖励均保持分离。

---

## 三章总表

| Chapter | 文学裁定 | O2 | Story-state |
|---|---|---|---|
| 第 1 章 | ROUGHLY_TIED | 复现 1 次（截图收件人压缩） | 无 `STORY_STATE` 损失；该压缩记为话语层边界风险 |
| 第 2 章 | CANDIDATE_BETTER（小幅） | 未复现 | 无损失 |
| 第 3 章 | ROUGHLY_TIED | 未复现 | 无损失 |

---

## 四个最终问题

**1. Finalizer 是否稳定提高整章总体文学质量？**

没有。3 章中 1 章小幅更好、2 章基本持平；收益幅度随 raw 中“可删解释”的存量下降而趋近于零。ch03 的 raw 已接近 Finalizer 的目标形态，机制只剩两句否定式过渡可删。不存在稳定的整章级提升。

**2. 哪些文学维度被稳定提高？**

`LOW_AUTHOR_EXPLANATION` 是唯一稳定的方向性收益：三章两路 Judge 都指向 candidate 更少叙述者解释。`SUBTEXT` 次之，方向一致但证据多来自同一组删除，不是独立增益。`SENTENCE_NATURALNESS` 不稳定（多次 TIE），`SCENE_IMMERSION` 与 `READING_APPEAL` 在 ch03 出现 TIE 或分裂。没有稳定的句法、沉浸或总体阅读吸引力提升。

**3. O2 是否为可复现的失败模式？**

不是。3 章中仅 ch01 复现 1 次（把“给买家发截图”与“向客服报异常”压成同一收件人）；ch02、ch03 均未复现。它是一次边界压缩，不是冻结机制的稳定失败模式。

**4. Finalizer 阶段状态**

**`PARTIAL_VALUE_BUT_NO_OVERALL_GAIN`。**

它安全（无 story-state 损失）、便宜、方向正确；但在三章真实样本上只带来小而局部的解释删除收益，没有整章总体质量提升。

---

## 是否可以结束 Finalizer R&D 阶段

**可以。** 经过 3 个真正的新章节（ch01 基线 + ch02、ch03 同机制），证据已经一致：

- 文学裁定：1 次小幅 CANDIDATE_BETTER，2 次 ROUGHLY_TIED；
- 稳定收益只落在 `LOW_AUTHOR_EXPLANATION`（弱及 `SUBTEXT`）；
- O2 不再复现；
- ch02/ch03 均无 story-state 损失；
- 收益依赖 raw 中存在多余解释；当 Writer 已按已验证原则写作时，Finalizer 接近 no-op。

继续调 Prompt 只能在没有可测整章收益的目标上空转。建议保持现有机制、结束这一轮研发，不再开始下一轮优化。

---

## 生产附注（非 PRIMARY QUESTION）

- ch02：commit accepted、publish 成功、postcommit 通过、backup `ch0002`；vector projection skipped（本地 embedding 未启动）。残余非阻断问题见 `ch02/production_notes.md`。
- ch03：两轮 Reviewer、4 项定向修复、commit accepted、publish 成功、postcommit 通过、backup `ch0003`；vector skipped。残余 1 条 high（灰獾残血缺伤害数值/系统行）因自动预算 2/2 用尽未再修，non-blocking，见 `ch03/production_notes.md`。
- 文学裁定使用冻结 raw / candidate；ch03 的 Step 4 修复未参与 Finalizer 评价。
