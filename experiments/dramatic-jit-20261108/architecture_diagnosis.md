# 架构诊断：戏剧决策当前由谁做

> 只读诊断，不改代码。目的：解释 A/B 差异，不升级为全面架构审计。

## 1. 本次第 4 章的真实输入状态

- `大纲/第1卷-详细大纲.md` 第 4 章只有 13 行自然语言字段：目标、阻力、代价、时间锚点、章内跨度、与上章时间差、倒计时、爽点、Strand、反派层级、视角、关键实体、本章变化、章末未闭合问题、钩子。
- 没有 `scene_goal` / `scene_conflict` / `scene_setback` / `scene_resolution`。
- 没有 `sequel_reaction` / `sequel_dilemma` / `sequel_decision`。
- 没有 `CBN` / `CPNs` / `CEN`，`plot_structure` 为 `{}`。
- `state.json` 的 `chapter_meta` 只有自然语言字段，没有结构化场景字段。

因此，Runtime 的 `build_scene_plan()` 只能回退到章级字段：

- 场景目标 ← `goal`
- 现场阻力 ← `obstacles`
- 场景挫折 ← `cost`
- 场景结果 ← `chapter_change`
- 后续反应 / 两难 / 决定 ← 空

`--scene-design` 渲染出的“场景四问”，实际上是把章级目标、阻力、代价、变化各重复一遍；`--reader-pull` 的“追读三问”也是同一批字段的另一种问法。它们没有提供新的场景设计。

## 2. 决策归属表

| 决策 | Current owner | B owner |
|---|---|---|
| Hard Intent | 章纲 / planner。本次第 4 章只有自然语言字段，缺结构化 must-cover / forbidden / scene 字段 | 实验固定，不变 |
| 人物即时目标 | Context Agent 给泛化动机；具体到“这一场想拿到什么”由 Writer 临场决定 | JIT Planner 具体化 |
| 冲突如何发生 | Writer 临场决定（副本类型、谁挡谁、机制如何咬合） | JIT Planner |
| 关键选择 | Writer 临场决定 | JIT Planner |
| 代价 | Writer 临场决定 | JIT Planner |
| Turn | Writer 临场决定 | JIT Planner |
| Consequence | Writer 临场决定 | JIT Planner |
| Reader payoff | Runtime 追读三问 + Writer；三问只重述章级字段 | JIT Planner 的 Creative Brief（不再注入三问） |
| 表现方法 | Writing Skill Router + Writer | Writing Skill Router + Writer（不变） |

## 3. 当前链路的具体观察

### 3.1 Context Agent 与 Runtime 重复表达同一内容

A 的 Context Agent 任务书写了：目标、阻力、代价、变化、读者期待、章末问题。Runtime 的 `--scene-design` 又把目标 / 阻力 / 代价 / 变化变成四问；`--reader-pull` 再把目标 / 阻力 / 代价 / 变化 / 未闭合问题变成三问。Writer 在同一份 Prompt 里至少三次看到同一批章级事实，但没有一次看到“这场戏谁先出招、谁阻止谁、主角有哪几个真实选项、代价是什么、什么让原计划失效、场景结束时什么已经改变”。

这不是“信息不足”，而是“信息类型不对”：有目标，没有戏剧动作；有代价标签，没有选择；有变化标签，没有 turn；有章末问题，没有 consequence。

### 3.2 Context Agent 被边界约束成“不能设计剧情”

A 的 Context Agent 明确写了：

> “副本名称、具体敌人、掉落及分配比例尚无确定依据，起草时不要把未经建立的细节当成既有设定。”

这句话本身是对的（不能伪造 Canon），但它暴露了一个结构问题：Context Agent 被要求“事实边界”，又被要求“认知创作规划”，而章纲没有给出任何场景级设计。结果是它只能给泛化建议，把具体的副本、冲突、选择、turn、consequence 全部留给 Writer 临场发明。

### 3.3 Skill Router 没有越权设计剧情（本次）

本次 Router 选了 4 个 Skill：`scene-sequel`、`character-agency`、`dialogue-subtext`、`reader-pull`。它的 `chapter_guidance` 主要是表现层：

- “副本拆成两到三次可追踪的交锋”
- “陈默不能只在旁边喊小心”
- “邀请那场别写成陈默介绍副本、林川点头”
- “开场从木盾耐久归零和九十八块碎片的窘迫接上”

其中有个别轻微的软动作建议（“陈默主动做一件只有他能做成的事”），但没有决定本章的关键选择、turn 或 consequence。因此本次不能把“Skill Router 越权设计剧情”当作主要问题；它只是表现方法层。

### 3.4 Writer 临场补关键选择

在 A 的输入里，Writer 拿到的是：

- 章级目标 / 阻力 / 代价 / 变化；
- 场景四问（同一批字段的重述）；
- 追读三问（同一批字段的重述）；
- 泛化人物动机；
- 4 条表现方法。

Writer 必须自己决定：副本是什么、谁先出招、两人怎么配合、哪里出问题、林川有什么选择、代价是什么、turn 是什么、consequence 是什么、章末怎么收。这是本章戏剧设计的实际发生位置。

### 3.5 8–12 章提前规划的 soft Scene 字段：不是过时，而是缺失

本次第 4 章没有可用的 `scene_*` / `sequel_*` 字段，`plot_structure` 为空。因此问题不是“提前规划的 soft Scene 字段已经过时”，而是“提前规划根本没有产出可执行的场景设计”。Runtime 的 fallback 只是把章级字段换一种问法，不能替代场景设计。

### 3.6 Reviewer / Finalizer / Data Agent 都不负责戏剧设计

- Reviewer：事实、Canon、连续性、时间线、人物一致性、逻辑、节拍合规、伏笔合规、禁抄。它可以在事后指出“战斗因果不清”，但不能在写前提供选择 / 代价 / turn。
- Literary Finalizer：删解释、删翻译层、删重复线索、提升潜台词。它不决定剧情。
- Data Agent / commit：记录已发生事实。它不决定剧情。

因此，如果本章的问题是“戏剧设计在写前没有被决定”，增加 Reviewer 维度、Finalizer 轮次或 Writer Prompt 规则都不能解决；它们都在下游。

## 4. 诊断结论（待 A/B 结果验证）

当前链路的戏剧设计所有权是错位的：

- 名义上：章纲 / Context Agent 负责规划。
- 实际上：Writer 在起草时临场决定最关键的冲突、选择、代价、turn、consequence。
- Runtime 的场景四问 / 追读三问只是把章级字段重述，不能替代场景设计。
- Context Agent 被事实边界约束，不能凭空发明副本细节；章纲又没有提供场景级设计，于是形成真空。
- Skill Router 只应管“已经确定的戏怎么表现”，本次没有越权；它不能填补戏剧设计的真空。

如果 A/B 结果显示 B 在人物主动性、选择/代价、因果推进、turn、consequence 上更好，那么问题不是“Writer 不够努力”，而是“这些决策发生得太晚、且由错误的角色做”。下一阶段应该改的是临写前的戏剧规划 owner / timing，而不是继续加 Writer Prompt、Finalizer 或 Reviewer。
