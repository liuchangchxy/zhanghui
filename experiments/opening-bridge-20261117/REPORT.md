# Opening Bridge（Brief 之后、封口之前追加开场承接）— 正式 A/B 报告

**日期**：2026-11-17
**分支**：`feat/story-pressure-bridge`
**样本**：`根源牌序`（第 1–3 章 durable accepted；第 4–24 章有既有章纲但未写作）
**被测章节**：第 4、5、6 章（未参与本实现设计的新连续章节）
**结论**：`STORY_CAUSALITY_OPENING_BRIDGE_PASS`

---

## 1. PRIMARY QUESTION

> 在 Context Agent 按原章纲正常产出完整 Creative Brief 之后、Native Writer Package 封口之前，
> 只追加一个**开场承接**（本章开场立刻回应上一章 durable accepted 的一件具体事），
> 是否能在**不重新规划本章**的前提下，让连续 3 章的跨章因果承接明显强于原流程，
> 且不增加 Canon / 人物不变量冲突？

## 2. 机制

```text
章纲 → Governed Context → Step 1B Context Agent → 原始 Creative Brief 完成
     → Step 1B3 Opening Bridge → Step 1C attach-creative-brief → Writer
```

- 新增 CLI：`runtime opening-bridge --chapter N`（只读投影，`available` / `reason` / `source.commit_sha256`）
- 新增参数：`runtime attach-creative-brief --opening-bridge-file <body>`（在封口前把承接块拼到原任务书**前面**）
- 封口后的 Creative Brief 结构固定：

```text
【开场承接】
上一章 accepted：……
本章开场：……

作用范围仅限开场：完成这个回应后，继续执行下方原任务书；本章目标、阻力、代价、情节节点与结尾仍以下方原任务书为准。

【原 Creative Brief】
（Context Agent 原始输出，逐字保留）
```

- 投影只读 `.story-system/commits/chapter_{N-1}.commit.json` 且要求 `meta.status == "accepted"`；
  上一章未 accepted → `available=false`，不生成承接，流程与原流程逐字节一致（无回退到更早章节，有测试锁定）。
- 承接正文由 `_check_bridge_body` 做**形状**校验（恰好两行、≤220 字、两个必需前缀、不得含小节标题），
  所以「只影响开场」由封口强制执行，而不是靠编排纪律。

## 3. 实验设置

| | Baseline | After |
|---|---|---|
| 代码 | 本分支，**不传** `--opening-bridge-file` | 同一份代码，传 `--opening-bridge-file` |
| 章纲 | 既有，不改 | 同左（`sha256 = 0d7d9683…`，两臂逐字相同） |
| Context Agent 输入 | 同一 `runtime governed-context` | 同左 |
| Brief / Writer 模型 | 同一模型 | 同左 |
| 字数目标 | 2000–2500 | 2000–2500 |
| 上一章事实 | durable accepted commit | 同左（After 额外读它生成承接） |

两臂起点为同一份 `根源牌序` 副本；第 1–3 章正文与 `chapter_00{1,2,3}.commit.json` 逐字节相同。
每章走完整真实链（`prepare → governed-context → Brief → 封口 → Writer → Reviewer → Data Agent →
reconcile → write-gate precommit → runtime commit → publish-draft → postcommit`），
**每章必须 accepted 后才写下一章**。

## 4. 判定结果

### 条件 1 — 来源正确 ✅

| 章 | 承接包来源 | `commit_sha256` 与实际文件 |
|---|---|---|
| 4 | `chapter_003.commit.json` | 一致 |
| 5 | `chapter_004.commit.json` | 一致 |
| 6 | `chapter_005.commit.json` | 一致 |

三章均可追溯到上一章 durable accepted commit；无未提交提取、无临时摘要、无 Planner 预期。
另有两项负向验证：上一章 rejected → `available=false` 且**不回退**到更早的 accepted 章节；
只存在未提交的 `extraction_result.json` 时投影仍为 `available=false`。

### 条件 2 — 规划未被改写 ✅

- 两臂章纲 `sha256 = 0d7d9683d741e21d00f9353de2d02a8a6ac41fd3bac2152652dabb0a769618ba`（逐字相同）；
  其余 8 个 `大纲/*.md` 亦相同。
- 用 `split_composed_brief()` 拆 After 三章的封口 Brief，拆出的原任务书与其 Context Agent 原始输出
  **逐字节相同**（ch4/ch5/ch6 均为 `True`）。
- 承接是唯一额外创作输入：每章恰好 2 行（100 / 87 / 94 字符）。
- Baseline 三章封口 Brief 与 brief 文件一致，且不含 `【开场承接】`。

### 条件 3 — 核心剧情不漂移 ✅

独立结构审计：两臂第 4–6 章的目标 / 阻力 / 代价 / 本章变化 / 章末未闭合问题指向的**核心动作与对象相同**，
未换成另一个核心事件。两臂节点覆盖均为 `missed = 0`（Baseline 10/10 每章；After 15/15 每章）。

> 两臂第 4 章的副本实体不同（Baseline 是城西废矿的绞盘/水闸，After 是铁廊的冲压锤/断龙闸），
> 但章纲未指定副本名，核心动作与对象仍是「陈默邀请 + 完成副本首通」，不构成 CEN 漂移。

### 条件 4 — 因果承接提高 ✅（3/3）

| 评委 | 甲 = | 乙 = | 结论 |
|---|---|---|---|
| judge1 | Baseline | After | `CLOSER = 乙` → After |
| judge2 | Baseline | After | `CLOSER = 乙` → After |
| judge3 | **After** | Baseline | `CLOSER = 甲` → After |

含位置反转（judge3 的甲/乙顺序相反）后，**3/3 认为 After 更紧密地承接上一章**。

评委给出的可引用证据（After）：

- 第 4 章：「昨天矿道里跟你动手的是谁？」「我昨晚回来，看见你屏幕上一只青铜狗，还有个人躺地上」
  「你就一张卡，把灰獾打回城了……我认识的人里，没第二个」
- 第 5 章：「铁廊，首通，两人，用时两小时四十七分。ID 那一栏，归乡人。」→「你就是那个通关的？」
- 第 6 章：「矿道还去不去？昨天说好的，两个人。」→「你自己去。」；
  「收过他钱的那个……把面板翻开，低头看一眼，又合上。」

评委对 Baseline 的批评（判定其承接更弱的原因）：

- 「甲的第 4 章前三段是静态账目复述，真正发动情节的第一个事件（陈默邀他下本）理由是
  『你昨天在线到后半夜』——作息，不是行为」
- 「甲第 4 章的『长期』队伍、『明天矿道』、灰框在第 5、6 章全部悬空」
- 「甲把第 3 章的 `耐久 0/3` 写成 `0/100`，且重复两次」

### 条件 5 — Canon 不恶化 ✅

两名互不通信的独立审计员（各自只读一臂）：

| 臂 | `TOTAL` |
|---|---|
| Baseline | `hard=3 soft=5 invariant=1 knowledge=1` |
| After | `hard=2 soft=7 invariant=1 knowledge=1` |

硬冲突：**After 2 ≤ Baseline 3**。Baseline 的 3 个硬冲突中有 2 个是同一处
「木盾耐久写成 `0/100`，与共用第 3 章 `0/3` 冲突」（第 4、5 章各一次），第 3 个是
「火折子在第 2 章已卖出，第 4 章又直接使用」；After 的 2 个是「两组材料归属」与
「主角独自行动违反双星平等底线」。

**承接本身未发明新的世界事实**：三条承接正文逐条可回溯到承接包所列事实——

| 章 | 承接里的事实 | 承接包出处 | 判定 |
|---|---|---|---|
| 4 | 林川在旧矿道击败灰獾 | 关系：灰獾抢怪被击败后放话报复 | 无越界 |
| 4 | 木盾耐久归零、维修 120 | 状态：木盾 0/3 已损毁，维修 120 | 无越界 |
| 4 | 账上只有九十八 | 状态：`game_account.fragments = 98` | 无越界 |
| 5 | 首通成立并记下用时 | 规则：首次通关成立「首通」并记录用时 | 无越界 |
| 6 | 「清剿行动……一并清」 | 关系：赵公子当众宣布，原文一致 | 无越界 |

第 5 章的承接由赵公子回应（该角色来自本章章纲的「关键实体」，符合机制自带的
「或由本章原任务书已经存在的角色承受」约束），未引入新机构、栏目、流程、登记簿、定量数据或新人物。

---

## 5. 必须记录的保留意见

判定为 PASS，但以下问题真实存在，不做粉饰：

1. **结构审计认为 After 第 5 章的开场不算「承接」**：回应者赵公子在本章才首次上页，
   按「上一章或更早已出场」的严格口径不成立。第 4、6 章成立。也就是说三章里只有 2/3
   严格满足「已出场角色回应」的形式要求——这不影响条件 4（盲评 3/3），但说明承接的
   形式强度并不均匀。
2. **After 第 4 章正文有承接之外的越界**：Writer 自行补了「高难。两个人才能开」（副本准入规则）、
   「我原来那个搭档放我鸽子了」（新前情）、「我昨晚回来，看见……一个人躺地上」（幕后目击事件，
   与第 3 章「陈默还没回来」有张力）。这三项**不在承接正文里**，是 Writer 依据承接自行展开的，
   属 Writer 的普通事实错误，按本轮约束不予顺手修正。但它是承接带来的副作用，必须记录。
3. **After 第 6 章被判 `invariant hard`**（林川拒绝陈默同行、独自定计划，触碰「双星平等」底线）。
   该判断来自 **Context Agent 自己的 Brief**（「他不肯把陈默拖进来——他习惯一个人打」），
   两臂 Brief 由同一流程独立生成，不是承接写的。Baseline 第 6 章是陈默完全缺席（同样孤立主角，
   但因为没有「当面拒绝」的场面而未被计为越线）。
4. **After 第 6 章整章偏静态**（观察 + 摆石子推演），三名评委中有两人主动指出节奏问题；
   第 4 章副本三段机关同构（阀 / 棘轮 / 锁扣）也被指出。
5. **n=1**：每臂每章一次生成，不估计 Writer 方差；这是结构判定，不是文学分差判定。
6. **两臂 Brief 不逐字相同**（同一模型独立生成）。条件 2 按「After 的原任务书未被改写 +
   两臂章纲相同 + 节点覆盖无缺失」判定，已在实验设计里预先声明。
7. **第 5、6 章的起点自然分叉**（上一章正文不同 → 余额 198 vs 116）。这是机制在真实链上的
   正常行为，不是输入不对等。

## 6. 结论

五项条件全部满足：

| 条件 | 结果 |
|---|---|
| 1 来源正确 | ✅ 三章均对上 N-1 accepted commit 的 sha256 |
| 2 规划未被改写 | ✅ 章纲逐字相同；原任务书逐字节保留；承接是唯一额外输入 |
| 3 核心剧情不漂移 | ✅ CEN 相同；节点覆盖无缺失 |
| 4 因果承接提高 | ✅ 3/3 盲评（含位置反转） |
| 5 Canon 不恶化 | ✅ 硬冲突 2 ≤ 3；承接本身无新增世界事实 |

**`STORY_CAUSALITY_OPENING_BRIDGE_PASS`**

保留实现：`scripts/data_modules/opening_bridge.py`、`webnovel.py` 的两个 CLI 入口、
`skills/webnovel-write` 的 Step 1B3 与 Step 1C、`skills/webnovel-fast-write` 的 2b、
`docs/ownership-inventory.json` 的两条读边声明，以及 17 个测试。

## 7. 复现与材料位置

- 实现：`.claude/plugins/zhanghui/scripts/data_modules/opening_bridge.py`
- 测试：`.claude/plugins/zhanghui/scripts/data_modules/tests/test_opening_bridge.py`（13）、
  `tests/unit/test_opening_bridge_seal.py`（4，走真实 CLI）
- 运行记录：`.tmp/opening-bridge-20261117/RUN_LOG.md`（逐章实际执行）
- 冻结设计：`.tmp/opening-bridge-20261117/PRIMARY_QUESTION.md`
- 盲评材料与结论：`.tmp/opening-bridge-20261117/judging/`（`judge{1,2,3}.md`、`*.order.json`、`VERDICTS.md`）
- 两臂样本：`.tmp/opening-bridge-20261117/arm-baseline/`、`arm-after/`（各含完整 commit 链与正文）

`.tmp/` 下的两臂是完整项目副本（约 283 MB），仅作本机证据，不进 git；
`RUN_LOG.md`、`PRIMARY_QUESTION.md` 与 `judging/` 的全部材料同样留在本机 `.tmp/` 下，
所以本报告里的逐条数字（字符数、指纹、sha256）由本机材料核对。
