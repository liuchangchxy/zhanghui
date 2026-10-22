# Reader Pull 机制盘点（只读）

日期：2026-10-22
基线：`main` @ `35c5a4b`（含 PR #59）
范围：`.claude/plugins/zhanghui/`（排除 `6.4.0/` 版本快照）
证据：源码、真实 Writer Prompt（`study/experiments/2026-10-22-scene-layer-ab/prompt_B.txt`）、
`海港旧信` 的 `governed_context_0002.json`、上一轮审计 `study/audits/2026-10-22-writing-theory-audit.html`

## 一、实际进入 Writer 的追读信息

第3章的 Writer Prompt（`prompt_B.txt`，20,300 B）里与追读有关的只有这些：

| Prompt 行 | 内容 | 性质 |
|---|---|---|
| 9 | `章末钩子/未决问题：是谁让老周去报的？…` | 章纲字段，自然语言 |
| 10 | `预设钩子设计：回到工位，他发现…（类型：留白式）` | 章纲字段，指定了章末动作 |
| 96-141 | 整个 `mystery` 题材 YAML：`hook_config` / `coolpoint_config` / `micropayoff_config` / `pacing_config` / `override_config` | 原始配置，含 `strength_baseline`、`density_per_chapter`、`min_per_chapter`、`stagnation_threshold`、`debt_multiplier` 等 |
| 135-137 | `逻辑完整性优先于爽点密度` 等三句 | 题材文档散文 |
| 150-151 | `hook_type: "悬念式"` / `hook_strength: "strong"` | 前情摘要里的裸 YAML |

**没有进入 Writer Prompt 的**（只到 `governed-context` / `WriterPackage` JSON）：
`writing_guidance`（含“章首300字/每600-900字微兑现/钩子差异化”）、方法论策略卡、
`checklist`、`reader_signal`、`expectation_debt`、`promise_ledger`、`rhythm_curve`（永远为空）、
`pacing_config`（无代码消费者）、`taxonomy_excerpt`（读了但从不渲染）。

原因是渲染器与生产者的键名不一致：

- 生产 `context_manager.py:735` `guidance_items` / `:738` `methodology`
- 消费 `chapter_runtime.py:615` `guidance.get("items")` / `:621` `guidance.get("strategy_card")`

所以“每600-900字微兑现”这类指令目前只污染 Context Agent 可见的 governed JSON，
没有直接落到 Writer 眼前。这是**偶然的保护**，不是设计；任何人“修好”键名都会把它们灌进 Writer。

## 二、机制总表

| 机制 | 原始作用 | 当前落点 | Writer 可执行？ | 与谁重复 / 冲突 | 真实可观察效果 | 保留判断 |
|---|---|---|---|---|---|---|
| `open_loop_created` / `urgent_loops`（Canon 派生） | 记录“未回答的问题”，形成下一章动机 | data-agent 事件 → memory 投影 → `urgent_loops` → Context Agent 的 INTENT | 间接（经任务书） | 与 `foreshadow_chain`、`promise_ledger`、`reader_contract` 四套并行 | 第1章真实写入 2 条（匿名信、手写日期），第2章任务书引用了它 | **KEEP**（第1问的主要素材） |
| 章纲 `未闭合问题` / `ending_question` | 章末留一个可复述的问题 | `chapter_runtime.py:441,474-476` 直接渲染 | 是 | 与 `hook` / `hook_type` 重复描述章末 | 第3章 Prompt 可见；正文里表现为一句台词后继续拧螺丝 | **KEEP + 改写为第3问**（新期待必须来自本章已发生的事） |
| 6 种章末钩子 `hook_type` | 每章结尾给一个可复述的下章理由 | 章纲解析 → `chapter_intent_sync` → Prompt 474-482；Reviewer warning（`review_pipeline.py:559`）；索引统计（`index_reading_mixin.py:115`） | 是（类型名 + 预设动作） | 与 taxonomy 5 类、chapter-planning 5 类开头钩子、`story_craft.py:265-274` 别名集**四套枚举互不一致**；`story_craft` 没有“选择钩” | 钩子被写出来，但没有被评估“是否真的拉人” | **MERGE** 进第3问；类型表只留作参考 |
| `hook_strength`（strong/medium/weak） | 标注钩子强度 | 章纲可解析（`chapter_outline_loader.py:193`）→ 前情摘要 YAML；**无任何代码消费者** | 否（只是裸值） | — | 无 | **REMOVE_FROM_RUNTIME**（任务明确点名的“抽象 strong”） |
| 题材 `hook_config`（`preferred_types` / `strength_baseline` / `chapter_end_required` / `transition_allowance`） | 按题材给钩子偏好 | `genre-profiles.md` → `profile_excerpt` 原样注入 Prompt（`chapter_runtime.py:612`） | 否（配置项，不是写作指导） | 与 `genre_profile` 散文重复；与 `pacing_config` 同属装饰 | 无；文档自称 “Fallback Only” | **REMOVE_FROM_RUNTIME**（不进 Writer） |
| 爽点 `coolpoint_config` + `cool-points-guide.md` | 每章给一次可感知收益/反转 | 同上注入 Prompt；`status_reporter` 统计；guidance “主爽点+副爽点组合”；checklist `coolpoint_combo` | 部分是（“叠加一个副轴”） | 与 `rhythm-curve` 三级爽点、`chapter-planning` S/A/B/C、`constants` 频率**四套阶梯冲突** | 第2章的“收益”只是抄到一行日期；审计判 NOT_REACHED | **DEMOTE**（文档保留，不进 Writer） |
| 微兑现 `micropayoff_config` + `每600-900字一次微兑现` | 维持短周期反馈 | `micropayoff_config` 随题材 YAML 进入 Prompt；硬编码 guidance 条目与 checklist 留在 governed JSON | 配置项是；字数位指令否（键名不匹配，未渲染） | 与“章首300字/章末留钩”同属无依据字数位 | 无可归因效果 | **REMOVE_FROM_RUNTIME**（概念 MERGE 进第2问） |
| 节奏曲线 `rhythm_curve`（3/5 章阈值） | 防止连续平路 | `story_craft.py`；`chapter_runtime.py:639-647` 警示分支 | 理论上 | 与 `constants.md` “每章≥1爽点”冲突 | `record_emotion_peak` / `increment_chapters_since_peak` 运行时**无调用者**，`history=[]`，分支永不触发 | **DORMANT** |
| `pacing_config`（`stagnation_threshold` 等） | 停滞检测（文档称 HARD-003） | `genre-profiles.md`；注入 Prompt | 否 | 与 `rhythm_curve` 冲突 | 代码零消费者；Reviewer 无 stagnation 维度 | **DORMANT / REMOVE_FROM_RUNTIME** |
| 方法论策略卡（`pressure_source` / `release_target` / `observability`） | 题材施压-释放锚点 + 可观测分 | `writing_guidance_builder.py:81-210`；生产为 `methodology`，渲染器找 `strategy_card`，**从未渲染** | 否（键名 + 结构双重不匹配） | 与题材 YAML、`rhythm_curve` 重复 | `observability` 三个分数由常量推导（`70.0 + …`），不是测量；`next_reason=78.0` 若被渲染会直接误导 Writer | **MERGE**（施压/释放可为题材倾向，分数 **REMOVE**） |
| 写作指导基线（章首300字 / 600-900字微兑现 / 信息后置 / 段末留钩） | “高可读”默认策略 | `writing_guidance_builder.py:261-274`；生产为 `guidance_items`，渲染器找 `items`，**从未渲染**；仍在 governed JSON | 否（当前未渲染） | 互相重复，且与章纲的 Transition/Setup 定位冲突 | 无理论来源；第3章被标为 Setup 章，这些指令仍在要求“章末留钩” | **REMOVE_FROM_RUNTIME**（并加回归测试防止“修好键名”后复活） |
| 题材参考提取 `reference_hints[0]` | 给一条题材策略 | `writing_guidance_builder.py:258-259` → guidance 条目（未渲染） | 否 | — | 真实产物里是 `题材策略可执行提示：```yaml`——只提取到代码围栏 | **REMOVE_FROM_RUNTIME**（实现缺陷） |
| 写作清单 `checklist` + `checklist_score` | 记录“写作要求完成度” | `context_manager.py:748-810`；SQLite `writing_checklist_scores`；`quality_trend_report` | 否（不进 Prompt） | 与 Reviewer 分数、`review_trend` 重复 | 分数在**写作前**由历史信号计算，不衡量本章质量；却以“清单平均分”出现在趋势报告 | **DEMOTE**（降为内部诊断，不作质量信号） |
| `reader_signal`（`hook_type_usage` / `pattern_usage` / `review_trend` / `low_score_ranges`） | 让下一章避开高频钩子/爽点、修复低分段 | `context_manager.py:522-564` → guidance/checklist（均未渲染进 Prompt） | 否 | 与方法论 `pattern_overuse_watch` 重复 | 写章主链没有调用 `save-chapter-reading-power`，钩子/爽点统计很可能长期为空；`dimension_scores`（爽点密度/追读力）并非 Reviewer 真实产出 | **DEMOTE**（只作内部信号） |
| 期待债务 `reader_contract.expectation_debt` | 记账“欠读者的期待” | `story_craft.py`；`consistency/patches/p6_reader_contract.py` | 否 | 与 `open_loops`、`promise_ledger` 重复 | 恒为 `[]`；没有写入者；不进入 Writer | **DORMANT**（不复活） |
| `promise_ledger`（cross-volume） | 跨卷伏笔/承诺到期管理 | 仅 `volume_state.py`；planning-owned | 否 | 与 `foreshadow_chain` 字段名/类型/状态全部不一致 | 海港旧信为空；Writer 从不读取 | **DORMANT** |
| `foreshadow_chain` | 埋设-提醒-回收形成可追踪期待 | Prompt Writer Context 伏笔段，但只在 `expected_payoff_chapter == 本章` 时渲染回收项 | 部分是 | 与 `promise_ledger`、`open_loops`、`foreshadow-chain.md` 四套表示 | 第3章埋设 FS-001，Writer 看不到“本章要埋”；第1章的两条 open loop 反而可见 | **KEEP**（回收章可见），**DORMANT** 其余 |
| `thematic_echoes` | 主题在多章回响 | Prompt 命中章渲染 | 是 | — | 回声点在第 5/12/19/24 章，前四章不触发 | **DORMANT** |
| Strand Weave | 三线交替防疲劳 | 仅 `status_reporter.analyze_strand_weave` | 否 | 与 `pacing_config` 的 strand 阈值重复 | 无 | **DORMANT** |
| `reading-power-taxonomy.md`（361 行） | 追读力分类学（钩子/爽点/微兑现/HARD 约束） | `context_manager.py:589-619` 读取并生成 `taxonomy_excerpt`，但**从不渲染**；仅 write/plan SKILL 有“按需加载”指令 | 间接（靠模型自觉去读） | 与 `chapter-hook-types`、`cool-points-guide`、`scene-sequel` 重叠；文内“不做硬性裁决”与 HARD-001~004 “MUST_FIX”自相矛盾 | 无 | **DEMOTE**（保留文档，改为三问的执行说明） |
| `chapter-planning.md` 的爽点/结尾钩子/字数/主线剧情字段 | 章纲细化 | plan Step 7；**parser 不识别**（`结尾钩子` 不匹配 `^钩子`，`爽点`/`字数`/`主线剧情` 零映射） | 否 | 与 15-beat 前四章铺陈冲突；3000 字与 `constants.md` 2000-2500 冲突 | 无 | **DORMANT**（不在本轮改规划层） |
| `constants.md` | “所有阈值单一真源” | 无人引用，`[CONST:…]` 零命中 | 否 | 与 chapter-planning / rhythm / cool-points 的数字不一致 | 无 | **DORMANT** |
| 3000 字章高光结构（10/50/33/7） | 每章是一个小故事 | `chapter-planning.md` 文档；无校验 | 否 | 与 15-beat 直接冲突 | 无 | **DORMANT**（本轮明确不改规划层） |
| MRU / McKee value± / Mystery Box / Truby / Hero’s Journey | 更丰富的结构工具 | 设计稿 Tier 2/3；代码 0 引用 | 否 | — | 无 | **DORMANT** |

## 三、重复与冲突清单

**四套钩子枚举**

1. `chapter-hook-types.md`：悬念式 / 反转式 / 情绪炸弹式 / 信息投放式 / 留白式 / 反讽式（代码枚举，`story_craft.py:265-274`，另含别名“悬念钩/危机钩/选择钩/情绪钩/爽点钩”）。
2. `reading-power-taxonomy.md`：危机钩 / 悬念钩 / 渴望钩 + 情绪钩 / 选择钩。
3. `chapter-planning.md`：开头钩子 5 类（悬念/冲突/信息差/倒叙/承接），代码无字段。
4. 题材 `hook_config.preferred_types`：按题材各写一套（悬疑用“悬念钩/危机钩/选择钩”，其中“选择钩”不在代码枚举里）。

**四套“期待/伏笔”账本**：`foreshadow_chain`（`buried_chapter`、字符串 depth、7 载体）、
`promise_ledger`（`planted_chapter`、int depth、3 type）、Canon `open_loops/reader_promises`、
`reader_contract.expectation_debt`（空）。

**四套兑现频率**：`rhythm-curve` 小/中/大爽点、`cool-points-guide` 每 5 章组合/每 10-15 章里程碑、
`chapter-planning` S/A/B/C、`constants.md` 每章≥1 关键章 5-8 章。四套数字互不引用。

**两处直接矛盾**

- `scene-sequel.md` 说 `scene_goal/scene_conflict/sequel_decision` 缺失是 BLOCKER，
  `review_pipeline.py:552-558` 一律记 warning；文档自己也声明“不是 gate”。
- `reading-power-taxonomy.md:9` 说“不做硬性评分裁决”，`:305-314` 又定义 HARD-001~004 “MUST_FIX，不可申诉跳过”。

## 四、结论

1. **机制数量多，但真正抵达 Writer 的只有三类**：章纲的 `钩子/未闭合问题` 字段、
   题材 `profile_excerpt`（整段 YAML 参数）、以及 `urgent_loops` / `foreshadow` 素材。
2. **可执行性最差的恰恰是参数最多的那部分**：`hook_config`、`coolpoint_config`、
   `micropayoff_config`、`pacing_config`、`debt_multiplier` 在代码里没有消费者，
   却原样出现在 Writer Prompt 里。
3. **写作指导/方法论/checklist 目前没有进入 Writer**，原因是键名不匹配。这是偶然，
   不是设计；修键名会让“每600-900字微兑现”等无依据指令复活。
4. **真正有数据支撑的“期待”只有 Canon 派生的 `open_loops`**（第1章两条），
   它没有被组织成“读者现在最想知道什么”，而是散在伏笔段里。
5. 因此本轮不新增机制，只做三件事：**收敛表达（三问）、切断参数注入、把已有素材接到三问上**。
