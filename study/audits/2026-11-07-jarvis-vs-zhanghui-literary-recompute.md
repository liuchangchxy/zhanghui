# Jarvis vs Zhanghui 最终稿：纯文学性重算（只读核验）

- 日期：2026-11-07
- 仓库：`/Users/chang/Desktop/Code/zhanghui`
- Benchmark：`/Users/chang/Desktop/Code/zhanghui-benchmark/runs/clean-e2e-jarvis-vs-zhanghui-2026-10-29`
- 性质：只读重算。未修改生产代码、未调用 Finalizer、未改门禁、未重跑生成、未重新定义评审标准。
- 本报告只回答一个问题：**不看事实一致性、设定遵守、连续性等非文学指标，只看文学性，Jarvis 最终稿和 Zhanghui 最终稿谁更强？**

---

## 0. 结论先行

| 口径 | Jarvis | Zhanghui | SPLIT | TIE | 判定 |
|---|---:|---:|---:|---:|---|
| 严格文学口径（12 维） | **46** | **36** | 38 | 0 | 方向偏 Jarvis，但不显著（p=0.32） |
| 宽松文学口径（14 维） | **49** | **44** | 47 | 0 | 基本持平（p=0.68） |
| 原 16 维全部（对照） | 52 | 50 | 57 | 1 | 持平（p=0.92） |

- 十章逐章看，严格文学口径是 **Jarvis 5 章 / Zhanghui 5 章**；评委自己的 `OVERALL_PREFERENCE` 维度是 **Jarvis 2 / Zhanghui 2 / SPLIT 6**。
- 严格口径的 +10 净胜**完全由两个维度撑起**：`READING_APPEAL`（6:0）和 `LOW_AUTHOR_EXPLANATION`（6:2）。把这两维拿掉，剩下 10 个严格文学维度是 **34:34**，正好打平。
- 因此答案是：**基本打平**。不是“Jarvis 明显更强”，也不是“Zhanghui 明显更强”。严格口径存在一个不显著的 Jarvis 弱倾向，但不足以称为优势。

---

## 1. 原始评测结构核验

### 1.1 数据源

本轮只使用以下既有产物，没有新增生成：

- `REPORT.md`（10-29 run 的主报告）
- `scores/blind-summary.json`（聚合结果）
- `blind/identity-map/key.json`（X/Y 与真实臂的映射）
- `blind/results/e2e.chNN.final/pass1|pass2/judgement.json`（逐章、逐维原始判定）
- `blind/results/e2e.chNN.final/pass1|pass2/call.json`（judge 模型与调用记录）
- `blind/comparisons.json`（比较清单与文本路径）
- `_harness/blind_eval.py`（rubric / prompt / 判定协议）
- `scores/fingerprint-sensitivity.json`、`blind/comparisons-nofp.json`（H6 敏感性）

最终稿的文本对确实是：

- Jarvis：`e2e/jarvis-write/chNN/final.prose.md`
- Zhanghui：`e2e/zhanghui/chNN/published.md`

`blind/comparisons.json` 里 `e2e.chNN.final` 的 `arm_a=jarvis_final`、`arm_b=zhanghui_final`，与上文一致。十章齐全。

### 1.2 判定协议

`_harness/blind_eval.py` 的协议是：

- 同一对文本跑两遍；pass1 的 `LEFT = X`，pass2 的 `LEFT = Y`（强制位置反转）。
- 每个维度只能给出 `LEFT / RIGHT / TIE` 之一。
- 只有当两遍都指向**同一真实臂**时，才计为该臂获胜；否则记 `SPLIT`。
- `TIE` 只有在两遍都判 `TIE` 时才成立。

因此本报告里的 `SPLIT` **不是“两版一样好”**，而是“位置反转后评委改判了”。这是理解后面所有数字的前提。

### 1.3 16 个维度与分类

rubric 原文见 `_harness/blind_eval.py:43-80`。分类是本报告在查看结果之前按维度定义做的，不是按结果反推的。

| # | 维度 | rubric 定义（摘要） | 分类 | 理由 |
|---:|---|---|---|---|
| 1 | `OVERALL_PREFERENCE` | 作为读者更愿意读哪一版 | **C 有争议** | 全局偏好，可能混入连续性/意图/事实判断，且与其他维度重复计分 |
| 2 | `LITERARY_QUALITY` | 用词、白描、叙事质感 | A 严格 | 纯文学 |
| 3 | `READING_APPEAL` | 是否抓人、是否想继续读 | A 严格 | 纯阅读效果；但它也可能被情节/信息量带动，见 §4.5 |
| 4 | `CHARACTER_VOICE` | 人物说话/思考是否区分得开 | A 严格 | 纯文学 |
| 5 | `SUBTEXT` | 该藏的话有没有被说破 | A 严格 | 纯文学 |
| 6 | `EMOTION` | 情绪是否被写出来而非宣布 | A 严格 | 纯文学 |
| 7 | `DESCRIPTION` | 环境、动作、器物是否具体、准确、有画面 | A 严格 | 纯文学；“准确”按描写精度读，不按 canon 读 |
| 8 | `SENTENCE_NATURALNESS` | 句子是否顺、节奏 | A 严格 | 纯文学 |
| 9 | `LOW_AI_FLAVOR` | 套话、套路比喻、机械排比更少 | A 严格 | 纯文学 |
| 10 | `LOW_AUTHOR_EXPLANATION` | 作者直接解释更少 | A 严格 | 纯文学 |
| 11 | `LOW_RULE_FEEL` | 更少“在生硬执行写作技巧”的痕迹 | A 严格 | 纯文学 |
| 12 | `CHAPTER_OPENING_NATURALNESS` | 章首是否像一个故事自然往下走 | **C 有争议** | “自然度”是文学，但“往下走”隐含与上文的连续性 |
| 13 | `SCENE_IMMERSION` | 读者是否被放进具体时空 | A 严格 | 纯文学 |
| 14 | `INTENT_COMPLIANCE` | 应发生的关键事件/决定/状态变化是否齐全 | **B 非文学** | 内容/意图合规，不是文体 |
| 15 | `CONTINUITY` | 与上文的时间、地点、身体状态、已知信息是否衔接 | **B 非文学** | 明确的事实连续性 |
| 16 | `DENSITY_JUDGEMENT` | 更少文字承载更多有效故事信息，且不像摘要 | A 严格 | 纯文学（叙事密度） |

由此得到：

- **严格文学口径 A = 12 维**：2–11、13，以及 16（共 12 维）。
- **宽松文学口径 A+C = 14 维**：再加 `OVERALL_PREFERENCE`、`CHAPTER_OPENING_NATURALNESS`。
- **非文学 B = 2 维**：`CONTINUITY`、`INTENT_COMPLIANCE`。

`DESCRIPTION` 的“准确”如果被读成事实准确性，严格口径会缩成 11 维；§4.1 做了敏感性检验，结论不变。

---

## 2. 重算方法

对每个 `e2e.chNN.final`：

1. 从 `blind/identity-map/key.json` 读 `X` / `Y` 的真实臂。
2. 读 `pass1` 与 `pass2` 的 `judgement.json`。
3. 把每遍的 `LEFT/RIGHT` 映射回真实臂：
   - pass1：`LEFT=X`，`RIGHT=Y`
   - pass2：`LEFT=Y`，`RIGHT=X`
4. 两遍同臂 → 该臂；否则 `SPLIT`；两遍都 `TIE` → `TIE`。
5. 按 A / A+C / 全部 16 维分别汇总。

核验：把逐对结果与 `scores/blind-summary.json` 的 `per_pair` 逐项比对，**10 对 × 4 个计数全部一致，0 处不匹配**。这也确认了原始 52:50 的聚合没有算错；问题只在“52:50 该不该被当作文学性结论”。

---

## 3. 只重算 final vs final

**主结论只用 `Jarvis final vs Zhanghui final`。** 不混入 raw vs raw、raw vs final、crossfinalize。

### 3.1 严格文学口径：逐章比分

| 章 | Jarvis | Zhanghui | SPLIT | 严格口径多数 | rubric `OVERALL_PREFERENCE` |
|---:|---:|---:|---:|---|---|
| 1 | 11 | 0 | 1 | **Jarvis** | SPLIT |
| 2 | 1 | 9 | 2 | **Zhanghui** | SPLIT |
| 3 | 9 | 1 | 2 | **Jarvis** | Jarvis |
| 4 | 1 | 2 | 9 | Zhanghui（弱） | SPLIT |
| 5 | 12 | 0 | 0 | **Jarvis** | Jarvis |
| 6 | 1 | 7 | 4 | **Zhanghui** | Zhanghui |
| 7 | 2 | 3 | 7 | Zhanghui（弱） | SPLIT |
| 8 | 1 | 10 | 1 | **Zhanghui** | Zhanghui |
| 9 | 6 | 4 | 2 | **Jarvis** | SPLIT |
| 10 | 2 | 0 | 10 | Jarvis（极弱） | SPLIT |
| **合计** | **46** | **36** | **38** | **5 : 5** | **2 : 2 : 6** |

读表要点：

- 逐章多数是 **5:5**，整体没有系统方向。
- `ch04 / ch07 / ch10` 的 SPLIT 分别是 9 / 7 / 10，这三章实际上没有可用的章级结论。
- 评委自己的全局维度 `OVERALL_PREFERENCE` 只有 4 章有方向（Jarvis 2、Zhanghui 2），其余 6 章两遍改判。**连“哪一章整体更好”都不稳定。**

### 3.2 各文学维度累计比分

严格文学维度（A）：

| 维度 | Jarvis | Zhanghui | SPLIT | 净胜 (J−Z) | 单维 SPLIT 率 |
|---|---:|---:|---:|---:|---:|
| `READING_APPEAL` | **6** | **0** | 4 | **+6** | 40% |
| `LOW_AUTHOR_EXPLANATION` | **6** | **2** | 2 | **+4** | 20% |
| `SUBTEXT` | 5 | 3 | 2 | +2 | 20% |
| `DESCRIPTION` | 4 | 3 | 3 | +1 | 30% |
| `LOW_AI_FLAVOR` | 4 | 3 | 3 | +1 | 30% |
| `LOW_RULE_FEEL` | 4 | 3 | 3 | +1 | 30% |
| `DENSITY_JUDGEMENT` | 4 | 3 | 3 | +1 | 30% |
| `CHARACTER_VOICE` | 3 | 3 | 4 | 0 | 40% |
| `LITERARY_QUALITY` | 3 | 4 | 3 | −1 | 30% |
| `EMOTION` | 3 | 4 | 3 | −1 | 30% |
| `SENTENCE_NATURALNESS` | 2 | 4 | 4 | −2 | 40% |
| `SCENE_IMMERSION` | 2 | 4 | 4 | −2 | 40% |
| **严格合计** | **46** | **36** | **38** | **+10** | **31.7%** |

有争议与非文学维度（只作解释，不进入严格口径）：

| 维度 | 分类 | Jarvis | Zhanghui | SPLIT | TIE | 净胜 |
|---|---|---:|---:|---:|---:|---:|
| `OVERALL_PREFERENCE` | C | 2 | 2 | 6 | 0 | 0 |
| `CHAPTER_OPENING_NATURALNESS` | C | 1 | 6 | 3 | 0 | −5 |
| `INTENT_COMPLIANCE` | B | 2 | 1 | 6 | 1 | +1 |
| `CONTINUITY` | B | 1 | 5 | 4 | 0 | −4 |

**维度层面的画像**：

- Jarvis 的可复现优势集中在 **阅读吸引力** 和 **少作者解释**。
- Zhanghui 的优势集中在 **场景沉浸**、**句段自然度**、**章首自然度**、**连续性**。
- `CHARACTER_VOICE` 与 `OVERALL_PREFERENCE` 完全打平；`LITERARY_QUALITY` / `EMOTION` 甚至略偏 Zhanghui。

这不是“一方全面更强”，而是**两种不同的文学 profile**。

### 3.3 逐章“总体文学偏好”的两种读法

| 读法 | Jarvis | Zhanghui | SPLIT/TIE |
|---|---:|---:|---:|
| 严格 12 维的章级多数 | 5 章 | 5 章 | — |
| rubric 自带 `OVERALL_PREFERENCE` | 2 章 | 2 章 | 6 章 |

两种读法都没有方向。章级多数与全局维度不一致的章（ch01、ch02、ch04、ch07、ch09、ch10）说明：**评委可以在一章里让多数具体维度偏向一方，但在“整体更喜欢哪版”上仍然改判。**

### 3.4 章内极化：维度不是独立观测

严格口径下，十章共 82 个“两遍一致”的判定；其中 **71 个（86.6%）落在该章的多数方向**。逐章多数占比：

| 章 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 多数占比 | 100% | 90% | 90% | 67% | 100% | 88% | 60% | 91% | 60% | 100% |

这意味着 16 个维度在同一章内高度相关：评委往往是先形成“这一章哪版更好”的整体印象，再把 16 个维度大多填成同一方向。**有效的独立样本更接近 10 章，而不是 120 或 160 个维度判定。** 任何把维度当独立观测的显著性检验都会高估证据量。

---

## 4. 结论稳定性

### 4.1 分类敏感性：所有合理口径方向一致，但都不显著

| 口径 | 判定数 n | J | Z | SPLIT | TIE | 已决 J% | 双侧精确 p |
|---|---:|---:|---:|---:|---:|---:|---:|
| A 严格 12 维（主口径） | 120 | 46 | 36 | 38 | 0 | 56.1% | 0.320 |
| B 严格 11 维（去掉 `DESCRIPTION`） | 110 | 42 | 33 | 35 | 0 | 56.0% | 0.356 |
| C 严格 13 维（加 `CHAPTER_OPENING`） | 130 | 47 | 42 | 41 | 0 | 52.8% | 0.672 |
| D 严格 13 维（加 `OVERALL`） | 130 | 48 | 38 | 44 | 0 | 55.8% | 0.332 |
| E 宽松 14 维（A + 2 个 C） | 140 | 49 | 44 | 47 | 0 | 52.7% | 0.679 |
| F 宽松 15 维（E + `INTENT`） | 150 | 51 | 45 | 53 | 1 | 53.1% | 0.610 |
| G 全部 16 维（原口径） | 160 | 52 | 50 | 57 | 1 | 51.0% | 0.921 |
| H 核心 9 维（去 `DESCRIPTION`/`DENSITY`） | 100 | 38 | 30 | 32 | 0 | 55.9% | 0.396 |

- **方向一致**：所有口径都是 Jarvis 略多，净胜 +4 到 +10。
- **强度不一致**：加上有争议维度后，净胜从 +10 缩到 +5；全部 16 维只剩 +2。
- **没有任何一个口径达到显著**（最小 p=0.320；全部 16 维 p=0.921）。

严格口径的 95% Wilson 置信区间是 **[45.3%, 66.3%]**；宽松口径是 **[42.6%, 62.5%]**。两套区间都跨过 50%，且宽到无法排除“基本持平”甚至“Zhanghui 略好”。

### 4.2 是不是一两个维度决定结果？

**是。** 严格口径的 +10 净胜完全来自两维：

| 操作 | J | Z | SPLIT | 净胜 |
|---|---:|---:|---:|---:|
| 严格 12 维 | 46 | 36 | 38 | +10 |
| 去掉 `READING_APPEAL` | 40 | 36 | 34 | +4 |
| 去掉 `LOW_AUTHOR_EXPLANATION` | 40 | 34 | 36 | +6 |
| **同时去掉这两维** | **34** | **34** | **32** | **0** |

也就是说：**其余 10 个严格文学维度正好 34:34。** Jarvis 的“严格口径领先”不是广泛的能力优势，而是“阅读吸引力 + 少作者解释”这两项。

单维精确检验（未做多重比较校正）：

- 只有 `READING_APPEAL` 的 6:0 达到名义显著（p=0.031）。
- 12 个维度做 Bonferroni 校正后阈值为 0.0042，**6:0 也不再显著**。
- 其余所有维度 p≥0.29。

所以“某一两个维度决定结果”成立，但这些维度本身也不足以支撑“Jarvis 文学性明显更强”。

对“是否只是总分接近、但某些核心文学能力明显偏向一方”的直接回答：**不是。** 唯一明显偏向一方的是 `READING_APPEAL`（6:0），而它恰好是最接近内容层、口径最可疑的一维；其余核心维度要么接近 50:50（`DESCRIPTION` 4:3、`LOW_AI_FLAVOR` 4:3、`LOW_RULE_FEEL` 4:3、`DENSITY_JUDGEMENT` 4:3、`CHARACTER_VOICE` 3:3），要么略偏 Zhanghui（`SENTENCE_NATURALNESS` 2:4、`SCENE_IMMERSION` 2:4）。

### 4.3 评委内部一致性（SPLIT 率）

| 维度 | 两遍一致 | SPLIT 率 |
|---|---:|---:|
| `READING_APPEAL` | 6/10 | 40% |
| `LOW_AUTHOR_EXPLANATION` | 8/10 | 20% |
| `SUBTEXT` | 8/10 | 20% |
| `CHARACTER_VOICE` | 6/10 | 40% |
| `SENTENCE_NATURALNESS` | 6/10 | 40% |
| `SCENE_IMMERSION` | 6/10 | 40% |
| `OVERALL_PREFERENCE` | 4/10 | **60%** |
| `INTENT_COMPLIANCE` | 4/10 | **60%** |
| 严格口径合计 | 82/120 | **31.7%** |

三成以上的维度判定在位置反转后改判；全局偏好维度高达六成。**单维判定不可当作稳定信号**，只能读“两遍一致”后的总体方向——而总体方向也不显著。

### 4.4 长度混淆

两边最终稿长度差异很大：

- Jarvis 十章平均 3,796 字符；Zhanghui 3,006 字符（Jarvis **+26%**）。
- 但长度比与严格口径净胜的相关系数是 **Pearson −0.62 / Spearman −0.71**。

也就是说，**Jarvis 相对更长的章反而更容易是 Zhanghui 在具体文学维度上胜出或 SPLIT 的章**（ch02 1.68× → −8；ch04 2.34× → −1；ch06 1.60× → −6；ch08 1.42× → −9）。长度不能解释 Jarvis 的严格口径 +10；如果只看长度，方向甚至是反的。

一个例外是 `READING_APPEAL`：Jarvis 在这一维 6:0，而这 6 章里有 4 章 Jarvis 更长（ch02/ch06/ch07/ch08），2 章更短（ch03/ch05）。这提示 `READING_APPEAL` 可能部分被“信息量/情节推进”带动，而不是纯文体。见 §4.5。

### 4.5 `READING_APPEAL` 是不是纯文学？

这是本报告最重要的口径争议。

- rubric 把它定义为“是否抓人、是否想继续往下读”，属于阅读效果，不是事实/设定。
- 但在十章数据里，Jarvis 在 `READING_APPEAL` 赢的 6 章中，有 4 章是 Zhanghui 在其余严格维度大幅胜出的章（ch02、ch06、ch08，以及 ch07 的弱多数）。
- 在 ch02 / ch06 / ch08，Jarvis 的**唯一**严格维度胜绩就是 `READING_APPEAL`；Zhanghui 则赢下 7–10 个其他维度。

两种解释都说得通：

1. Jarvis 的文本确实更“抓人”（更强的悬念/推进/章末钩子），即使具体文体维度不如 Zhanghui。
2. `READING_APPEAL` 被更长的文本、更多的事件/信息量带动，属于“内容吸引力”而非纯文体。

如果把 `READING_APPEAL` 也归入“有争议”，严格口径会变成 **40:36（净胜 +4，p=0.73）**，与“基本打平”更接近。本报告按用户示例把它留在严格口径，但必须把这条敏感性写清楚：**Jarvis 的唯一显著单维优势，恰好是最接近内容层的那一维。**

### 4.6 H6 指纹污染是否影响 final 盲评？

**不影响。**

- `blind_eval.py:93-109` 的 `split_prose()` 会删除 `封包验证指纹` 行与 64 位 hex 行。
- 直接 grep `blind/inputs/e2e.ch*.final.*.txt`：**0 个文件含“指纹”或 64 位 hex**。
- `blind/comparisons-nofp.json` 的 final 对（ch02/ch05）与原始 blind input 的差异只有章标题（如 `## 第二章 钥匙`），正文逐字相同；H6 的“去指纹重判”实际上是**同一文本的重复判定**，衡量的是评委重测稳定性，不是污染校正。
- 该重测本身（REPORT §7）显示 15 对 / 240 维里 45 个判定变化，只有 1 个跨臂翻转——再次说明单维不稳。
- ch05 的 nofp 结果标记 `INCOMPLETE`，不能用于敏感性结论。

因此，**H6 不能解释 e2e.final 的平手，也不能解释严格口径的 +10。**

---

## 5. 特别回答

### 5.1 Jarvis 最终稿在纯文学性上是否明确强于 Zhanghui？

**基本打平。**

数字依据：

- 严格 12 维：**46 : 36**，SPLIT 38，已决 82 维中 Jarvis 占 56.1%，双侧精确 **p=0.320**，95% CI **[45.3%, 66.3%]**。
- 宽松 14 维：**49 : 44**，SPLIT 47，p=**0.679**，95% CI **[42.6%, 62.5%]**。
- 原 16 维：52 : 50，p=**0.921**。
- 章级：**5 : 5**；评委自己的 `OVERALL_PREFERENCE`：**2 : 2 : 6**。
- 严格口径的 +10 全部来自两维；去掉这两维是 **34 : 34**。

严格说，这是一个“**方向略偏 Jarvis、但统计上无法与持平区分**”的结果。若必须在四个选项里选一个：**基本打平**，不是“证据不足到无法比较”，也不是“Jarvis 明显更强”。

### 5.2 如果 Jarvis 更强，强在哪里？

只有两项，且都带条件：

1. **`READING_APPEAL`（6:0，4 SPLIT）**——唯一的名义显著单维（未校正 p=0.031；Bonferroni 阈值 0.0042 下不显著）。而且它是 ch02/ch06/ch08 里 Jarvis 的唯一胜绩，这三章 Zhanghui 在其余维度大幅领先。
2. **`LOW_AUTHOR_EXPLANATION`（6:2，2 SPLIT）**——Jarvis 更少替读者总结、点题、下结论；这一项与“少解释”的编辑方向一致。

**不强的方面**：`LITERARY_QUALITY`（3:4）、`CHARACTER_VOICE`（3:3）、`EMOTION`（3:4）、`DESCRIPTION`（4:3）、`LOW_AI_FLAVOR`（4:3）、`LOW_RULE_FEEL`（4:3）、`DENSITY_JUDGEMENT`（4:3）都接近持平；`SENTENCE_NATURALNESS`（2:4）和 `SCENE_IMMERSION`（2:4）反而偏 Zhanghui。

所以更准确的说法是：**Jarvis 的最终稿更“抓人”、更少解释；Zhanghui 的最终稿更“沉浸”、句子更自然、章首和连续性更好。** 这是 profile 差异，不是水平差异。

### 5.3 如果基本打平，为什么之前会形成“Jarvis 文学性碾压”的印象？

印象不是凭空来的，主要来自四类证据，但它们回答的不是同一个问题：

1. **`pilot-tide-archive-001/run-008-writer-contract-fix`（2026-10-12）——最强来源，但不是当前管线。**
   - 3 位 judge × 10 章，`PROSE_QUALITY` 合计 **26 : 4**，十章章级多数全部 Jarvis。
   - 但那轮 Zhanghui 是旧版 `dd1ad57`，发布正文就是 Writer 原始输出，**Step 2B / Step 4 一次都没跑**；30 份 prose 判定中有 **13 份明确提到 Zhanghui 文末混入 `<chapter_changes>` 元数据**并据此扣分。这 13 份判定**全部指向 Zhanghui 臂，且全部投给 Jarvis**。
   - `full-literary-root-cause-audit/ROOT_CAUSES.md` §0 的“Jarvis 的最终正文稳定优于 Zhanghui”就是建立在这轮上。**这句话不能平移到 10-29 的 6.5.0 管线。**
2. **`clean-e2e-...-2026-10-28`——方向一致，但运行无效。**
   - 报告自己写明 `PARTIAL_RUN`（Zhanghui 停在 ch05）、judge 就是生成模型（`judge_is_generator_model=true`）。
   - final 层“有效判定 9:2”是方向性观察，报告也写了“强度未定”。它不能当作“碾压”的证据。
3. **`clean-e2e-...-2026-10-29` 的 crossfinalize 177:28——真实、可复现，但问题不同。**
   - 它比较的是“同一份粗稿 → Jarvis 的 finalize 步 vs Zhanghui 的 finalize 步”，18 个样本 / 288 维，Jarvis 177 : 28。
   - 这证明的是**后处理层的差距**，不是“Jarvis final 稿件 vs Zhanghui final 稿件”的差距。两个 final 稿件各自还包含前面的 Writer 粗稿差异。
4. **`jarvis_raw_vs_final` 100:15——系统内提升，不是跨系统对比。**
   - 它说明 Jarvis 的 finalize 能稳定把自己的粗稿拉起来。
   - 同一轮的 `e2e.raw` 是 Zhanghui 63:40 领先；合起来正好解释“粗稿层 Zhanghui 略好 → Jarvis finalize 拉起 → 最终稿打平”。

**传播上的关键错位**：177:28 和 100:15 都是非常醒目的数字，容易被读成“Jarvis 的最终稿更好”；而 10-29 报告 §8 第 5 题其实已经写了 `e2e.final` 52:50“没有稳定方向”。**“finalize 完胜”被误读成了“final 完胜”。**

### 5.4 之前哪些结论需要撤回或修正？

| # | 旧结论 | 处理 | 理由 |
|---:|---|---|---|
| 1 | “Jarvis 的最终正文稳定优于 Zhanghui / 文学性碾压” | **撤回（对当前 6.5.0 最终稿）** | 严格 46:36（p=0.32）、宽松 49:44（p=0.68）、章级 5:5、全局偏好 2:2:6 |
| 2 | “52:50 是文学性总分” | **修正** | 52:50 是 16 维全量，含 `CONTINUITY`（1:5 偏 Zhanghui）和 `INTENT_COMPLIANCE`（2:1，另 6 SPLIT/1 TIE），以及复合计分的 `OVERALL_PREFERENCE`；纯文学严格口径是 46:36，宽松 49:44 |
| 3 | “177:28 证明 Jarvis 最终稿更好” | **限定范围** | 177:28 只证明“同一粗稿下，Jarvis finalize 步优于 Zhanghui finalize 步”；不能用于 final vs final |
| 4 | “10-28 的 final 9:2 支持 Jarvis” | **降级为弱证据** | `PARTIAL_RUN` + generator-as-judge；报告自身标“强度未定” |
| 5 | “H6 指纹污染影响了 final 盲评” | **修正** | `split_prose()` 已删除指纹行；blind inputs 中 0 个 final 文件含指纹/64-hex；nofp 重判是重测，不是污染校正 |
| 6 | “16 维 = 160 个独立观测” | **修正** | 章内 86.6% 的一致判定落在同一方向；有效独立样本接近 10 章 |
| 7 | “Jarvis 的文学优势是全面的” | **修正** | 优势只在 `READING_APPEAL` 与 `LOW_AUTHOR_EXPLANATION`；其余 10 个严格维度 34:34 |
| 8 | “Zhanghui 的文学能力弱” | **修正** | Zhanghui 在 `SCENE_IMMERSION`（4:2）、`SENTENCE_NATURALNESS`（4:2）、`CHAPTER_OPENING_NATURALNESS`（6:1）、`CONTINUITY`（5:1）领先；这是 profile 差异 |

**保留、不需要撤回的结论**：

- Jarvis finalize 稳定改善自己的粗稿（100:15）。
- 同一粗稿下，Jarvis finalize 步优于 Zhanghui finalize 步（177:28，crossfinalize）。
- Zhanghui 的最终稿在十章里近似“未有效后处理的粗稿”（Step 4 10/10 回滚；Step 2B 3/10 回滚且大量 TIE）。
- `e2e.final` 没有稳定赢家（10-29 REPORT §8 第 5 题、§9 的表述本身是正确的）。

---

## 6. 限制

1. **样本规模**：一本《潮汐档案》、十章、一个场景、一个种子；E2E 每章只生成一次。不能外推到其他书/题材/模型。
2. **评委可靠性**：单一 judge 模型 `gpt-6.1-terra`，两遍位置反转；严格口径 31.7% 的维度会改判，全局偏好 60%。单维判定不可用，只能读两遍一致的总体方向。
3. **维度不独立**：章内极化 86.6%，有效样本接近 10 章。本报告的 p 值按维度独立计算，已经偏乐观（anti-conservative）；按章聚类的检验只会更不显著。
4. **长度不对称**：Jarvis 平均长 26%。长度与严格净胜负相关（r=−0.62），所以不能解释 Jarvis 的领先；但它仍可能影响 `READING_APPEAL` 这一维。
5. **两个“最终稿”的后处理不同**：Jarvis = finalize 输出；Zhanghui = Step 2B 采纳稿，Step 2B 回滚时等于 raw。这回答的是“最终产品谁更文学”，不是“哪一方的 Writer 更强”或“哪一方的后处理更强”。
6. **`READING_APPEAL` 的分类争议**：它是最接近内容层的严格维度；把它移入“有争议”后，严格净胜从 +10 降到 +4。
7. **H6**：final 盲评输入已去指纹；但 ch01–ch05 的 raw 对照确实受污染，本报告不使用 raw 对照回答主问题。
8. **没有人类读者验证**：所有“文学性”判断来自一个 judge 模型，不是真实读者样本。

---

## 7. 复现

数据与算法都在报告中；本地复现脚本（未提交，仅用于核验）在：

- `/Users/chang/Desktop/Code/zhanghui/.tmp/recompute_literary.py`
- `/Users/chang/Desktop/Code/zhanghui/.tmp/recompute_robustness.py`
- `/Users/chang/Desktop/Code/zhanghui/.tmp/literary-recompute.json`

核心规则（伪代码）：

```python
for pair in e2e.ch01.final .. e2e.ch10.final:
    X, Y = identity_map[pair]            # X/Y -> real arm
    for dim in 16_dims:
        a1 = map(pass1[dim].winner, LEFT=X, RIGHT=Y)
        a2 = map(pass2[dim].winner, LEFT=Y, RIGHT=X)
        verdict[pair][dim] = a1 if a1 == a2 else "SPLIT"
```

校验：与 `scores/blind-summary.json` 的 `per_pair` 逐项比对，10 对 × 4 计数全部一致。

---

**一句话结论**：只看最终稿的纯文学性，Jarvis 与 Zhanghui 基本打平——严格口径 46:36（p=0.32）、宽松口径 49:44（p=0.68）、章级 5:5；“Jarvis 文学性碾压”是把 crossfinalize 的 177:28（后处理步对比）和旧版 pilot 的 26:4（含元数据泄漏、无 Step 2B/4）误读成当前最终稿对比的结果。
