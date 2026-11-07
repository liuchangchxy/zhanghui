# Jarvis 文学收益来源归因（只读分析）

- 日期：2026-11-07
- 范围：`/Users/chang/Desktop/Code/zhanghui`（分支 `feat/writer-freedom`）与
  `/Users/chang/Desktop/Code/zhanghui-benchmark/runs/clean-e2e-jarvis-vs-zhanghui-2026-10-29`
- 性质：只读归因。未修改生产代码、未修改已有实验结果、未重跑完整 E2E、未调 Finalizer Prompt、
  未新增事实安全规则、未扩建 Reviewer、未开 PR。
- 结论先行：**“Jarvis 的定稿步稳定优于它自己的粗稿”有强证据；“Jarvis 的最终稿稳定优于章回的最终稿”没有。**
  最新干净 E2E 的 `e2e.final` 是 52:50 的平手。真正的可复用差异不在 Writer、不在模型，
  而在“草稿之后有没有一个有文学编辑权、有完整上下文、且门禁不把‘少解释’当成‘改事实’的定稿层”。

---

## 0. 先修正一个前提

用户问题中的“Jarvis 最终 prose 更好”，在最新干净 E2E 里**不成立为全链结论**。

`REPORT.md` §8 第 5 题与 `scores/blind-summary.json`：

- `e2e.final`（Jarvis 最终稿 vs 章回最终稿，10 对 / 160 维）：
  Jarvis 52 / 章回 50 / SPLIT 57 / TIE 1；总体偏好 Jarvis 2 / 章回 2 / SPLIT 6。
  **没有稳定赢家。**
- `e2e.raw`（两边粗稿）：
  **章回 63 / Jarvis 40** / SPLIT 53 / TIE 4；总体偏好章回 4 / Jarvis 2 / SPLIT 4。
  粗稿层反而是章回略占优。
- 差异真正出现的地方是“各自的后处理”：
  - `jarvis_raw_vs_final`：**100:15**（SPLIT 36、TIE 9），总体偏好 **8 章 final / 2 章 SPLIT / 0 章 raw**；
  - `zhanghui_raw_vs_final`：56:1（**TIE 80**、SPLIT 23），总体偏好 7 章 final、3 章 TIE、0 章 raw；
  - `crossfinalize`（同一粗稿交给两边各自的后处理，18 样本 / 288 维）：
    **Jarvis finalize 177 : 章回 finalize 28**（SPLIT 71、TIE 12），总体偏好 **14:1:3**。

因果链因此是：章回粗稿不差（63:40）→ Jarvis 的定稿步把它自己的粗稿拉起来（100:15）→
章回的定稿步几乎不动（56:1，80 个 TIE）→ 最终稿打平（52:50）。

`runs/clean-e2e-jarvis-vs-zhanghui-2026-10-28` 是 `PARTIAL_RUN`，评委就是生成模型，
报告自己写明“不能回答 Jarvis 为什么 prose 更好”，本报告不把它当证据。

---

## 1. 可比性检查（先确认能不能比）

| 项 | 结论 | 证据 |
|---|---|---|
| Writer 模型 | **同一模型、同一端点**：`commandcode/deepseek/deepseek-v4.1-flash[1m]`，实际响应 `deepseek-v4.1-flash-1017` | `_harness/writer.py:31-36`；每次调用 `traces/calls/*/call.json` |
| 采样 | 两边 draft 均 temperature 0.95、finalize/润色 0.7 | `_harness/e2e_jarvis.py:89-99`；`_harness/e2e_zhanghui_native.py:586-588` |
| 作者输入 | **逐字相同**的 962 字符作者级要求；每章作者目标相同 | `e2e/zhanghui/ch01/author-requirements.md`；`e2e/jarvis-write/ch01/prepare.json` 的 `author_objective` |
| 章节 | 同一部《潮汐档案》第 1–10 章 | 两边 `ch01..ch10` |
| 工作流 | 各自原生；**不是同一数量的阶段**，这正是研究对象 | 见 §3 |
| 上下文 | **不同**：Jarvis finalize 有蓝图/戏剧任务/张力/前情/名册/账本/AI 味命中/成对反例；章回 Step 2B 只有 style adapter + 草稿 | `chapter_compose.py:176-215`；`e2e/zhanghui/ch01/step2b.prompt.txt` |
| 长度指令 | **不同**：Jarvis 原生模板“硬上限约 3000 字（2400–3600）”，章回“1800–2600” | `e2e/jarvis-write/ch01/writer.prompt.txt:140`；`e2e/zhanghui/ch01/writer.prompt.txt:143` |
| 实际长度 | Jarvis 粗稿均值 3891 字，章回 3056 字（**+27%**）；最终稿 3796 vs 3003 | 本报告统计 `raw.prose.md` / `final.prose.md` 字符数 |
| 历史 | 各自写各自的前十章；history-swap 只证明“换历史会改变输出”，**没有稳定方向** | `REPORT.md` §5.2 |
| 评委 | `codex/gpt-6.1-terra`，与生成模型不同；匿名 + 强制位置反转 + 两轮一致才计分；16 维 | `REPORT.md` §7；`scores/blind-summary.json` |
| 生成次数 | E2E 每章 1 次；finalize 对照 3 章 × 2 输入 × 3 次 | `REPORT.md` §5.1 |
| 生产模型档位 | Jarvis 生产是 `DRAFT: FAST`、`FINALIZE: QUALITY`；benchmark 把所有阶段压成同一模型 | `backend/app/llm/router.py:92,96,158-159`；`_harness/writer.py:31` |

**必须随结论读的三个不对称**：

1. **长度指令不对称**：Jarvis 被要求写 2400–3600，章回被要求 1800–2600。`e2e.final` 的
   成对比较因此可能受“更长=更可读”的评委先验影响。`crossfinalize` 两边输入同一份粗稿，
   控制了这个混淆，所以 finalize 层的 177:28 比 `e2e.final` 的 52:50 更可信。
2. **生产档位未复现**：如果真实部署给 Jarvis 配了独立的 fast 模型，benchmark 会低估生产 Jarvis。
   本环境无法确认是否配置了独立 fast 模型，标 **UNKNOWN**。

3. **章回后处理臂是“单次调用”的重建，不是生产 agent 会话**：
   benchmark 的 Step 2B/Step 4 是 fresh call，只喂 style adapter + 草稿；
   生产里这两步由宿主 agent 在会话内执行，能看到本章意图、前情、Canon 等上下文。
   因此 `crossfinalize` 的 177:28 应读作“**Jarvis 完整后处理 vs 章回的单次风格转译调用**”，
   不能直接读作“Jarvis vs 章回生产 agent”。这条会放大“章回上下文贫瘠”的效应，
   但不改变 Step 2B 的 rewrite-only/±10% 契约限制——后者不依赖上下文多少。

---

## 2. 五问

### Q1. Jarvis final 相对 raw 好在哪里？

**先说不是什么**：不是“描写更漂亮”。`jarvis_raw_vs_final` 的维度分布是：

| 维度 | final | raw | SPLIT/TIE |
|---|---:|---:|---:|
| LOW_AUTHOR_EXPLANATION | 9 | 0 | 1 |
| DENSITY_JUDGEMENT | 9 | 0 | 1 |
| LOW_AI_FLAVOR | 9 | 0 | 1 |
| SUBTEXT | 7 | 0 | 3 |
| EMOTION | 7 | 0 | 3 |
| READING_APPEAL | 7 | 0 | 3 |
| SENTENCE_NATURALNESS | 7 | 1 | 2 |
| LOW_RULE_FEEL | 8 | 0 | 2 |
| DESCRIPTION | 4 | 4 | 2 |
| CONTINUITY | 3 | 3 | 4 |

即：**去作者解释、提密度、去 AI 腔、加潜台词、提阅读吸引力**；
**描写与连续性并没有变好**。这与“Jarvis 文字更华丽”的直觉相反。

#### 按文学收益排序（章内 16 维判定 + 总体偏好）

| 排名 | 章 | 维比分 | 总体 | 主要收益类型 |
|---:|---|---|---|---|
| 1 | ch04 | 16:0 | final | 把“差点掉出来”的转述改成当场掉出、被捡到；补签名动作；医学表述精确化 |
| 2 | ch06 | 14:1 | final | 把“梅叔打了个电话”扩写成一场完整电话；+962 字（+24.1%）——**收益最大，也最像二次创作** |
| 3 | ch02 | 12:0（3 TIE/1 SPLIT） | final | 删“眼珠子动了两下/瞳仁聚得紧”这类作者解剖；删“问了他也不会答”的解释 |
| 4 | ch05 | 12:2 | final | 3335→2792（-16.3%）；删口号“纸在人在”；“电话说不清”→“电话不方便”；新结尾钩子 |
| 5 | ch01 | 10:1 | final | 删比喻叠用与伪精确数字；把“嘴角动了一下，不算笑”换成“没接这个话茬” |
| 6 | ch07 | 10:5 | final | 压缩与删复述；但 raw 在 5 个维度反胜，属混合收益 |
| 7 | ch08 | 9:1 | final | 小幅收紧，收益较薄 |
| 8 | ch03 | 6:0（10 SPLIT） | final | 大幅压缩（-10.7%），但 10 个维度两轮判定不一致；方向弱 |
| 9 | ch09 | 6:3（7 SPLIT） | SPLIT | 删“有人试过/铜锈刚蹭掉…几个月”的近期尝试线索；方向不确定 |
| 10 | ch10 | 5:2（8 SPLIT） | SPLIT | 删章末任务清单式收尾；加钥匙插入阻力；方向不确定 |

#### 代表性原文对比

**ch01（去比喻、去伪精确、去微表情套话）**

- raw：“声儿不大，但密，**跟有人拿指甲弹名片似的**。”
  final：“声儿不大，但密。”
- raw：“可每回听见还是觉得**像有人拿低频音叉抵着后脑勺**。”
  final：“可每回听见，**后脑勺还是发紧**。”
- raw：“手指头无意识地搓着一枚硬币，**搓到第三十七下**的时候，门开了。”
  final：“手指头搓着一枚硬币，**搓了没一会儿**，门开了。”
- raw：“韩策**嘴角动了一下，不算笑**。”
  final：“韩策**没接这个话茬**。”

这几处是典型的“把作者替读者做的比喻/计数/表情判断拿掉，换成一个可演的动作”。
它们不改变事件，但显著降低“作者解释”和“AI 味”。

**ch02（删作者解剖、删心理旁白）**

- raw：“他的老花镜架在鼻尖上，**镜片后面的眼珠子动了两下，跟上次看缺页纸时一样——瞳仁聚得紧**。”
  final：“老花镜架在鼻尖上，**他没推上去**。”
- raw：“他抬起眼，**老年环围着的瞳仁对准林越**。”
  final：“他抬起眼。”
- raw：“**梅叔这个态度，问了他也不会答，只会拿“记不清”挡回来。**他换了一个问法：”
  final：“他把复印件折好，装进工具箱侧兜。“维护处那年收到的钥匙——是不是在你手里？””

**ch04（把转述改成当场发生；本章 16:0）**

- raw：“你兜里那个信封，刚才在泵组间**差点掉出来**。”
  final 新增：“他弯下腰，**夹克内袋里的信封滑出来，落在管道底座旁边。他没看见。**”
  后面乔宁捡到并归还——原文已有“我在冲压管旁边捡到的”，final 只是把“报告事件”改成“演出事件”。
- raw：“**轻度灼伤，没到真皮。**”
  final：“**浅二度。水泡别挑。**”

**ch05（压缩、去口号、加潜台词）**

- raw：“**纸在人在**，纸上的字比网络多一行——乔宁把话说得够直了。”
  final：“乔宁把话说得够直，**纸不在系统里，改不到**。”
- raw：“林越打了三个字：“查完了。”发出去之前补了半句：“**纸上有东西，电话说不清。**””
  final：“发出去之前删掉，改成：“**电话不方便。**””
- final 新增结尾：“韩策：“**十二点。别迟到。**” / 林越没回。他把手机翻过去，屏幕扣在箱盖上。”

**ch06（把一句转述扩成一场戏；收益与风险并存）**

- raw 只有一句：“**梅叔昨晚给我打了个电话。**”
  final 新增约 1000 字的电话场景，包含“**我焊的**”“雨衣左肩那道刮痕，白的，露底漆”“1989 年十一月”等新信息。
- 这一章 14:1 是收益最大的章节之一，但它**不是“修订”，是二次创作**：
  新增信息不在 raw、也不在 finalize prompt 的蓝图里（蓝图“核心作用/伏笔操作”为空，只有一句本章简述）。
  新增的“左肩补漆”在后续 ch07–ch10 没有被真正使用，属于悬空伏笔；
  更关键的是，ch07 的 raw 已经把这段新增当成前情复述（“梅叔的话从脑子里过了一遍：
  左肩刮痕露白底，编号被刮掉，补漆只补正面”），说明**定稿阶段的新增会进入下一章的 canon**。

**ch09 / ch10（方向不确定，含事实风险）**

- ch09 raw：“**“有人试过。”林越说。 / “铜锈刚蹭掉这层，没回氧化。几个月，短的话几周。”**”
  final：“**“不是门。”乔宁说。 / “道岔。”林越盯着那根连杆。**”
  物理擦痕还在，但“最近有人试过”的推断被删掉。这是线索层变化，不是措辞；评委也给了 SPLIT。
- ch10 raw 章末是一串任务清单：“你查档案室封存记录……我回站里查……晚上对。”
  final 收成“**“晚上对。”**”，并新增“钥匙进了一半，卡住”“纸边刮了一下指腹”这类动作/触感。

#### 四类归类（不是按编辑次数，而是按“是否真的改善阅读体验”）

| 类别 | 代表 | 判断 |
|---|---|---|
| 1. 明确文学收益 | ch01 删比喻/伪精确/微表情；ch02 删作者解剖；ch04 转述改演出；ch05 压缩+潜台词；ch10 删任务清单 | 评委偏好主要来自这一类 |
| 2. 主要是事实修正 | ch01 “修了八年”→“修了三年”（原文另有“过去三年”，自相矛盾）；ch04 “轻度灼伤，没到真皮”→“浅二度”；ch09 “八分钟后”→“八点四十六” | 不构成文学收益，但解释了部分“更顺” |
| 3. 仅措辞 | 大量“攥拳时绷得慌，但比昨天强得多”→“攥拳绷得慌，比昨天强”；“搁”→“放” | 数量最多，但不能解释 100:15 |
| 4. 文学退步或事实风险 | ch09 删“最近有人试过”线索；ch06 新增电话与左肩信息；ch05 新增短信时间；ch04 新增信封掉落（同章回收） | ch06/ch09 是真实风险点；评委对 ch09/ch10 也只给 SPLIT |

**Q1 的结论**：Jarvis finalize 的稳定收益是“**少解释、更密、更有潜台词、更像人说话**”，
不是“描写更好”。其中一部分是纯编辑收益，另一部分是**在定稿阶段继续写新内容**；
后者被评委奖励，但不能被当作“安全修订”来复制。

---

### Q2. 改善真正来自哪个环节？

#### 已证（proven）

1. **在 benchmark 的 Jarvis 链里，文字变化只来自 FINALIZE 一次调用。**
   `_harness/e2e_jarvis.py` 的链路是：`prepare-package → writer(DRAFT) → finalize-prompt →
   finalize(FINALIZE) → deai → ingest-native`。
   它**没有**跑 `review_and_rework`、`word_count_guard`、`dedup`。
   十章的 `deai.json` 全部 `changed=false`（ch01 4.0→4.0，其余 5.0→5.0），所以 finalize 就是净效果。
   证据：`e2e/jarvis-write/ch01..ch10/deai.json`；`REPORT.md` §4 表注。

2. **这个收益能在章回的粗稿上复现，不是“Jarvis 的粗稿本来就好”。**
   `crossfinalize` 用同一份输入分别走两边后处理：18 样本 177:28，总体 14:1:3。
   分输入看，**没有任何一个输入组判章回 finalize 更好**：
   `zhanghui_ch01` 3/3、`zhanghui_ch02` 3/3、`zhanghui_ch03` 2/3 判 Jarvis；
   `jarvis_ch01` 3/3、`jarvis_ch02` 2/3（1 SPLIT）、`jarvis_ch03` 1/3（2 SPLIT）判 Jarvis。
   证据：`controls/cross-finalize/*/s*/sample.json`；`REPORT.md` §5.1。

3. **不是采样抖动。** 3 章 × 2 输入 × 3 次独立生成，14:1 的总体方向没有翻转。

#### 有支持但未完全证明（supported, not fully proven）

1. **“完整上下文”是收益的一部分，但没被单独隔离。**
   `crossfinalize` 的 Jarvis 臂走原生 `finalize-prompt`（蓝图/戏剧任务/张力/前情/名册/账本/
   AI 味命中/成对反例），章回臂只有 `style-adapter.md` + 草稿（`_harness/cross_finalize.py:32-50`）。
   所以 177:28 证明的是“**Jarvis 的完整后处理（含上下文）**优于章回的后处理”，
   不是“只换 finalize 提示词就能赢”。缺一个“Jarvis finalize prompt + 只有 style adapter 上下文”的臂。

2. **三步 prompt 与硬保全条款的贡献未被消融。**
   `backend/app/prompts/chapter.py:165-211` 的三步（修正硬伤 → 去 AI 腔 → 克制提升）和
   “保持剧情走向、人物动机、时空因果、关键道具、伏笔与有效落点不变”是设计核心，
   但没有“去掉某一步/某条保全”的 ablation。

3. **生产档位差可能是真实收益的一部分。**
   生产 Jarvis `FINALIZE: Tier.QUALITY`、`DRAFT: Tier.FAST`（`router.py:92,96,158-159`），
   benchmark 两段都用同一模型。若部署时确实把 fast 档配成更小模型，benchmark 会低估 Jarvis。
   是否配置了独立 fast 模型：**UNKNOWN**。

#### 无法判定（undeterminable）

- `review_and_rework`（门禁 + 四维主编审 + 定向返工 + proofread）对最终稿的贡献：
  **benchmark 没跑，生产也没有这次运行的记录**。不能把源码里的存在当成收益证据。
- `word_count_guard` / `dedup` 的贡献：同样没跑。
- 收益是否跨书、跨题材、跨模型稳定：只有一本 10 章、一个场景、一个种子。
- 评委的“文学偏好”与真实读者偏好是否一致：评委是 `gpt-6.1-terra`，有自己的风格先验；
  H6 敏感性重判显示 15 对里 45 个维度判定会变，只有 1 个跨臂翻转——**只能读总体方向，不能读单维**。

#### 混淆项清单（逐条说明控制到什么程度）

| 混淆 | 是否控制 | 说明 |
|---|---|---|
| 模型不同 | 已控制 | 同一端点、同一模型 ID，逐调用记录 |
| 写作任务不同 | 已控制 | 同一作者要求、同一章目标 |
| 输入上下文不同 | **未完全控制** | 两边原生上下文本就不同；crossfinalize 的 Jarvis 臂仍拿全上下文 |
| 长度指令不同 | **未完全控制** | Jarvis 2400–3600 vs 章回 1800–2600；crossfinalize 控制输入但不控制输出长度 |
| 采样 | 部分控制 | E2E 单次；finalize 对照 3 次 |
| 评委偏好 | 部分控制 | 不同模型 + 位置反转；单维仍不稳 |
| 前章历史 | 部分控制 | history-swap 无稳定方向 |
| 生产档位 | **未控制** | benchmark 压平档位 |

---

### Q3. 为什么章回没有拿到同样的收益？

**不是模型问题，不是 Writer 问题，也不是“prompt 写得不够好”。**
三条反证：

- 同一 Writer 模型；`e2e.raw` 章回 63:40 领先。
- 章回 Writer prompt 很完整：本章意图、绝对禁区、剧情推进义务、governed canon facts、
  完整 Creative Brief（`e2e/zhanghui/ch06/writer.prompt.txt`）。
- 已有的 Writer 侧实验全部平或更差：`study/experiments/2026-10-23-writer-freedom-ab`、
  `2026-10-23-hard-facts-soft-craft-ab`、`2026-10-24-lean-skill-delivery-ab`、
  `2026-10-24-lean-continuity-postedit-ab`。

真正的差距是：**章回的主链没有任何一个环节“有权把一章写得更好”，
而它的门禁又把 Jarvis 用来产生收益的动作判成违规。**

#### 原因 1：Step 2B 的 rewrite-only 契约从定义上排除了文学编辑

- `skills/webnovel-write/SKILL.md:464-465`：
  “只改写已有内容的措辞、句式与节奏；保持事件、动作、对话信息、感官与环境细节、
  人物心理及其顺序和因果。不得新增、删除或改变任何情节动作、互动、发现、线索、设定、
  心理推断或环境细节，即使看似合理、无害或不改变结果也不行。”
  契约反例甚至写到“原文仅写「手心压在封皮上」，候选不得增加「压了很久」”。
- `references/style-adapter.md:21`：字数波动 ±10%；
  `:35`：“保留场景氛围与非功能性过渡，不追求极端信息密度的压缩文本。”
- 后果在产物里：本章最终稿 = Step 2B 采纳稿（10/10），而 Step 2B 的编辑量极小：
  ch01 -4.5%、ch03 -6.9%、ch04 -4.0%、ch06 -1.5%、ch07 -0.4%、ch08 -0.1%、ch09 +0.8%；
  ch02/ch05/ch10 被门禁回滚（0%）。`zhanghui_raw_vs_final` 因此是 56:1 但 **80 个 TIE**。
- 对照 Jarvis：`chapter.py:165-211` 明确允许合并被拆开的句子、删重复解释、
  “允许合理缩短，不补动作凑字数”，并允许在既有事件内部加动作/心理/感官。
  Q1 里被评委奖励的改动，几乎全部落在这个“允许”区间。

#### 原因 2：Step 2B / Step 4 的上下文贫瘠，编辑无法判断“什么是承重的”

- `e2e/zhanghui/ch01/step2b.prompt.txt` 约 3.4k–5.4k 字符（ch01 4.9k）：style adapter + 草稿，
  **没有蓝图、没有前情摘要、没有人物名册、没有资源账本、没有伏笔状态、
  没有确定性 AI 味命中、没有成对反例**。
- `e2e/zhanghui/ch01/step4.prompt.txt` 约 6.6k–11k 字符（ch01 6.6k，ch06/ch10 约 10.6k–11k）：
  reviewer issues + typesetting + polish-guide + 草稿；同样没有蓝图/声音锚点/账本。
- Jarvis finalize prompt（`chapter_compose.py:176-215`）恰好把这些全部给到：
  蓝图、戏剧任务、张力总线、伏笔、章节摘要、滚动摘要、已登场名册、资源账本、
  草稿、`flavor_hits`、风格指令 + `pairwise_examples_block()`（AI 腔→人话成对反例）。
- 这不是“token 多就好”，而是**编辑必须知道哪些细节承重、哪些可以删**。
  上下文不足时，保守不动是理性选择；这解释了为什么章回的编辑量趋近于零。

**公平性限定**：这条原因在 benchmark 里被放大了。生产 Step 2B/Step 4 由宿主 agent 执行，
能看到本章意图、前情摘要、Canon 等会话上下文；benchmark 的单次调用只给 style adapter + 草稿。
所以“上下文贫瘠”是**benchmark 的编辑器上下文**，不是生产 agent 的全部上下文。
但即使给足上下文，rewrite-only + ±10% + 只能改已有内容，仍然不允许 Q1 里的那些增删；
因此原因 1 和原因 3 不依赖这条，原因 2 只能算“放大器”，不能单独当主因。

#### 原因 3：二元语义门禁把“叙述层变化”当成“故事层变化”

门禁只接受 `STYLE_ONLY_SAFE`；`SEMANTIC_CHANGE_PROPOSED` / `UNCERTAIN` 一律回滚
（`SKILL.md:481-486,532`）。具体判词：

- ch02：
  before“林越没接话。**他不知道梅叔看见了什么，也不敢问。**”
  after“林越没接话。梅叔那一眼落在他工具箱上，他心里咯噔了一下。”
  judge：“改写删去了林越‘不知道梅叔看见了什么’的明确不知情状态。”
- ch05：
  after 新增“他坐到工作台前，**后颈的汗还没干透**。”
  judge：“新增了林越后颈出汗未干的身体状态，属于原文未交代的新状态细节。”
- ch10：
  before“**林越听明白了**，梅叔在递话，也在赶人。”
  after“林越没接话，低头收拾东西。梅叔在递话，也在赶人。”
  judge：“删除了‘林越听明白了’，不再明确林越是否知晓……”

这三条恰好是 Q1 里收益最大的三类动作：**删解释、补感官、把“明白了”改成动作**。
门禁把它们读成“知情状态变化”，但从叙事学看，改变的是**话语层（discourse）**，
不是**故事层（story）**：读者获得的信息没有变，只是不再由叙述者代说。
这是当前门禁最根本的错位：它用“事实不变”的尺子量“叙述方式”。

**必须同时写明的公平性限定**：benchmark 的 Step 4 **不是生产 Step 4**。
`_harness/e2e_zhanghui_native.py:569-586` 手写的 prompt 说“必须优先修复下列审查报告问题”，
并把 reviewer 的全部 issues 喂进去；而这 10 章的 reviewer issues **全是事实/合规类**
（logic/setting/continuity/timeline/character/foreshadow/do_not_copy），没有一条 `ai_flavor`。
生产契约则明确“事实类问题不是 Step 4 的表达润色目标”，`--style-only` 会把它们放进
`plan.deferred(owner=FACT_REVIEW)`（`SKILL.md:625-650`）。
所以 `STEP4_SEMANTIC_DRIFT` 10/10 回滚里，有一部分是 harness 让模型去改事实、再用禁止改事实的门禁回滚它。
**但这不改变结论**：在生产契约下，这 10 章的 Step 4 因为没有表达目标而会 `changed=false`，
净效果仍然是零。差别只是“因漂移回滚”还是“无目标不动”。

#### 原因 4：Reviewer 没有文学维度，Step 4 拿不到文学目标

- `agents/reviewer.md:13` 自述“你是章节**事实审查员**”；
  `:17`“你只查 8 个维度：设定一致性、时间线、叙事连贯、角色一致性、逻辑、
  节拍合规性、草蛇灰线合规性、对标书禁抄合规性。”
- `e2e/zhanghui/ch*/reviewer.output.json` 的 issue 类型实测全部落在上述 8 类，
  **没有一条是文笔/节奏/潜台词/作者解释**。
- 对照 Jarvis `backend/app/prompts/templates/editorial/review.txt:1-40`：
  四维打分 plot / prose / pacing / character，7 分=合格发布线，
  每条建议必须逐字引用正文 15–40 字，并检查“叙述者点题、结局三脚架、情绪单一化、模板转折”。
- 后果：章回的 “审 → 改” 闭环里，反馈是事实清单，不是文学意见；
  Step 4 即使想改表达，也没有目标可依据。

#### 原因 5：一次性 Finalizer 会过度删减，说明“放权”本身不够

`experiments/finalizer-ab-20261107/REPORT.md` 的原型结果：

- ch03：C 臂两位评委都排第一，修正 07:50/07:58 内部矛盾，对白“我没问那些”更符合分寸——**真实收益**。
- ch06：C 臂 2763→2358（85.34%，低于自设 90% 下限），删掉“清点问不到设备型号”的攻防、
  梁沐口误后的推论、章末钩子；J1 排最后、J2 排第一——**过度删减**。
- ch07：C 把 6 处“高潮”改成“高值”、1 处“低潮”改成“低值”；J1 视为术语硬伤，J2 视为更精确——
  **术语失守**。
- 结论：机制值得吸收，但不能原样替换 Step 2B + Step 4；必须带“内容保全/字数下限/术语保护”。

这解释了 Jarvis 为什么是“三件套”而不是“一个更会写的 prompt”：
`finalize`（有文学编辑权）+ 硬保全条款 + 之后的 `review_and_rework` / `word_count_guard`。
章回只学了第一件，会把 ch06/ch07 的失败模式带进来。

#### 小结：真正的能力缺口

不是“章回的 prompt 不够好”，而是：

> 章回没有一个**上下文完整、有权删改、但被硬不变量约束**的定稿层；
> 它只有一个 rewrite-only 的风格转译层（Step 2B）和一个被事实门禁回滚的表达润色层（Step 4）。
> 前者从定义上不能改善场景张力/人物表演；后者在事实类输入下必然空转。
> 所以章回的“最终稿”实际上一直是**未经有效后处理的粗稿**。

---

### Q4. 下一版最值得借的三件事

只列三个机制；每个都给预期收益、证据、实现成本、风险。

#### 机制 A：上下文完整的独立 FINALIZE 层，授予“有边界的文学编辑权”

**做什么**：在 Writer 之后加一个定稿步（可替换 Step 2B 或作为其前置）。输入直接复用现有的
governed-context / Creative Brief，再加：本章蓝图、前情摘要、人物名册、资源账本、伏笔状态、
草稿、确定性 AI 味命中、声音锚点、1–2 个成对反例。

**允许**：压缩、删叙述者总结/解释、合并拆分句段、重写对白但不改说话人/信息/意图/结果、
在既有事件内部补动作/心理/感官、修原文内部自相矛盾。

**禁止**：改事件结果、人物知情状态、物品归属、时间线、地点状态、世界规则、
新增线索/人物互动/因果、删除关键对白/章末钩子/伏笔。

**预期收益**：最大。证据：`jarvis_raw_vs_final` 100:15（总体 8 章 final / 2 章 SPLIT / 0 章 raw）；
`crossfinalize` 177:28、总体 14:1:3；finalizer C 在 ch03 的跨评委收益。
**实现成本**：中。上下文已经存在，主要是新增一个 prompt + 一个阶段接线；不需要新 Agent/框架。
**风险**：ch06 式过度删减、ch06 式新增内容、ch07 式术语改写。必须配机制 C。

#### 机制 B：把二元语义门禁拆成“硬不变量 / 允许的编辑动作”两层

**做什么**：不再用 `STYLE_ONLY_SAFE` 一个桶。把 judge 的每条 change 分成：

- **硬不变量违反**（回滚）：事件结果、知情状态、物品归属、时间线、地点/状态、世界规则、
  线索、人物关系、因果、数字/日期/编号。
- **允许的编辑动作**（放行并记录）：删叙述者解释/总结、补既有事件内部的感官/动作、
  合并拆分句段、对白改写但不改信息、压缩重复。
- **不确定**：走一次定向重写或人工复核，不再一律 fail-closed。

**预期收益**：直接解锁 Q1 里被门禁挡掉的那批改动。证据：ch02/ch05/ch10 的三条判词
恰好是允许动作；`crossfinalize` 的章回臂 8/18 回滚；`zhanghui_raw_vs_final` 80 个 TIE。
**实现成本**：中。改 judge 输出的分类维度 + 门禁策略，不需要新 Agent。
**风险**：边界争议。必须把“允许”写成封闭清单，并保留机制 C 做最终内容核对。
**注意**：这不是“放宽事实安全”，而是把**话语层**和**故事层**分开；
当前门禁把“少解释”误判成“少知道”。

#### 机制 C：定稿后的内容保全审查 + 确定性护栏

**做什么**：定稿候选生成后，先跑确定性检查：

- 字数下限（例如 ≥90%）；
- 关键对白、章末钩子、伏笔埋设/回收、人物状态变化是否还在；
- 数字/日期/编号/术语是否被改写（ch07 的“高潮→高值”就是这一类）；
- 物品归属/知情状态/时间线是否变化（可用现有 `prose validate` 的硬维度子集）。
  违反则回滚或定向修复；不要再用“整章二元回滚”。

**预期收益**：不直接产生文学收益，但防止机制 A 在某些章变成净负。
证据：finalizer ch06 85.34% 且删钩子；ch07 六处术语改写；Jarvis 的
`word_count_guard`、压缩 prompt 的“不得删除”清单、`review_and_rework`。
**实现成本**：低–中。大部分是确定性文本检查，可复用现有 `prose_validate` / `revise verify`。
**风险**：检查过严会重新变成“什么都不过”；所以只保**关键内容**，不做逐句等价。

**三个机制的依赖关系**：A 是收益来源；B 是让 A 的改动不被误杀；
C 是防止 A 的失败模式。单独上 A，会重演 finalizer 的 ch06/ch07；单独上 B，没有 A 也没有内容可放行。

---

### Q5. 下一轮唯一值得做的实验

**假设（可证伪）**：

> 当前的二元语义门禁，会把 Jarvis finalize / Finalizer C 中**盲评更喜欢的那些改动**
> 判成 `SEMANTIC_CHANGE_PROPOSED` 并回滚；这些被回滚的改动里，
> “删作者解释 / 补既有事件内的感官动作 / 合并句段 / 对白改写”占多数，
> 真正的硬不变量违反只占少数。

如果这个假设成立，那么“章回拿不到收益”的主因就是门禁的**分类错误**，而不是模型、上下文或 Writer；
下一版应先改门禁的分类，而不是继续调 Writer 或 Finalizer prompt。

**设计（全部使用已有产物，不重跑 E2E，不改生产代码）**：

1. **样本**：
   - 10 对 Jarvis `raw.prose.md → final.prose.md`（已知 8 章总体 final、2 章 SPLIT）；
   - 3 对 finalizer `A(raw) → C`（已知 ch03 C 双评委第一、ch06/ch07 评委分歧）。
   共 13 对。
2. **跑门禁**：用 10-29 运行同一套 `prose validate` + semantic judge prompt/模型，
   对每对跑一次“before → after”，只记录 `outcome` 与每条 `changes`，**不应用、不改文本**。
3. **归类**：按预注册的封闭清单，把每条 change 标成：
   - `HARD`：事件结果/知情状态/归属/时间线/地点/世界规则/线索/关系/因果；
   - `EDIT`：删解释/补感官动作/合并拆分/对白改写不改信息/压缩重复；
   - `OTHER`：纯措辞、无法判定。
   由两个独立标注者做（可以是两个模型 + 人工抽查 20%），分歧由第三条规则裁决。
4. **对齐盲评**：把每对的盲评总体偏好（final vs raw、C vs A）与门禁结果连接。
5. **指标**：
   - (a) 盲评更喜欢的输出中，被门禁回滚的比例；
   - (b) 被回滚的 change 中 `EDIT` 的占比；
   - (c) 被回滚的 change 中 `HARD` 的占比。
6. **预注册判定**：
   - (a) ≥70% 且 (b) ≥50% → 假设成立，门禁是主因；下一版做机制 B。
   - (b) <30% → 假设被推翻：收益与事实漂移不可分，应优先做机制 C，而不是放权。
   - (b) 30–50% → 不确定，需要扩到 crossfinalize 的 18 个样本再判。

**成本**：13 次 judge 调用 + 标注；没有新 E2E、没有新 Finalizer 生成、没有生产代码改动。
**这个实验能决定的事**：下一版是“改门禁分类（B）”，还是“先加内容保全（C）”。
它不能决定“用哪个模型/写多长”，那些不是本假设的一部分。

---

## 3. 仍然不知道的事（UNKNOWN，不得推断）

1. **生产 Jarvis 的 `review_and_rework` 贡献**：benchmark 没跑；没有运行记录。
2. **生产 Jarvis 的 fast/quality 档是否真的用不同模型**：本环境无法确认。
3. **Jarvis finalize 的收益中，“完整上下文”与“prompt 结构”各占多少**：
   缺一个“完整 prompt + 贫瘠上下文”的对照臂。
4. **收益能否跨书/跨题材/跨语言**：单书 10 章、单场景、单种子。
5. **评委偏好是否等于真实读者偏好**：单维判定在 H6 敏感性重判里 45/240 会变；
   只能读总体方向。
6. **ch06 新增电话是否会造成后续 canon 冲突**：它新增了“梅叔焊柜子”“左肩补漆”等信息，
   后续章节没有使用，也没有权威 canon 核对；只能标为“未回收的新增内容”。

---

## 4. 证据索引

- 主报告：`zhanghui-benchmark/runs/clean-e2e-jarvis-vs-zhanghui-2026-10-29/REPORT.md`
- 盲评聚合：同上 `scores/blind-summary.json`
- Jarvis 定稿链：`_harness/e2e_jarvis.py:80-125`；`_harness/jarvis_worker_clean.py`
- 章回主链：`_harness/e2e_zhanghui_native.py:500-610`
- 章回 Step 4 prompt 构造：`_harness/e2e_zhanghui_native.py:569-586`
- cross-finalize：`_harness/cross_finalize.py:32-88`
- Jarvis 定稿 prompt：`sources/jarvis-write/backend/app/prompts/chapter.py:165-211`
- Jarvis 定稿上下文：`sources/jarvis-write/backend/app/engines/pipeline/chapter_compose.py:176-215`
- Jarvis 定稿后处理：`sources/jarvis-write/backend/app/engines/pipeline/chapter_finalize.py`
- Jarvis 复审返工：`sources/jarvis-write/backend/app/engines/pipeline/chapter_rework.py:440+`
- Jarvis 主编审：`sources/jarvis-write/backend/app/prompts/templates/editorial/review.txt:1-40`
- 章回 Step 2B 契约：`.claude/plugins/zhanghui/skills/webnovel-write/SKILL.md:464-486`
- 章回 Step 4 契约：同上 `:625-650, 689-699`
- 章回 style adapter：`.claude/plugins/zhanghui/skills/webnovel-write/references/style-adapter.md:11,21,35`
- 章回 Reviewer：`.claude/plugins/zhanghui/agents/reviewer.md:13,17`
- 章回语义判词：`e2e/zhanghui/ch02|ch05|ch10/step2b.semantic-judge.json`
- Finalizer 原型：`zhanghui/experiments/finalizer-ab-20261107/REPORT.md`
- 本次 diff 分析：`zhanghui/.tmp/jarvis-attribution/ch01-10.diff.txt`

---

**收口**：Jarvis 的最终稿优势主要来自**定稿阶段的文学编辑权 + 完整上下文 + 不被“事实不变”门禁误杀的叙述层改动**；
章回缺的不是 Writer 或模型，而是一个“有权改、知道该改什么、且不会把删解释判成改事实”的定稿层。
下一轮最值得验证的是：**当前门禁是否正在回滚盲评更喜欢的改动**——用已有 13 对文本做一次门禁重放即可，不需要重跑 E2E。
