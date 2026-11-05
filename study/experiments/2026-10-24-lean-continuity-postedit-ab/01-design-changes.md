# 本轮改动

只有两处，都在 `.claude/plugins/zhanghui/scripts/data_modules/`。没有新增 Agent、数据库、
第二套 Context、第二套 Canon 或新的文学理论。

## 1. `## 本章相关既有事实`

### 为什么

第三轮 ch10 的 critical 不是硬事实错误：年份缺口、方向、数字都对。错的是**既有世界事实**——
旧报库从「报社后院」搬到「图书馆地下室」，从纸质原报变成缩微阅读机；地方志办公室从
「城西老楼三层、凭阅览单」变成「市政府西配楼三层、硬皮登记簿手写」。

这些事实**本来就在 Canon 里**：`canon_items` 第 16–19 项正是两条 `world_rule_revealed`
和两条关系。问题出在 lean 渲染器的 `【已确认前文事实】` 只取 `[:8]`，规则排在第 16 项之后，
被截断了。Writer 看不到，就只能凭印象重新发明。

### 怎么选

`select_continuity_facts(canon, prose_by_chapter, budget=700)`，确定性筛选，四类来源：

| 优先级 | 来源 | 规则 |
|---|---|---|
| 1 | accepted 章节正文 | 对登场的地点/物品，取最早一章里第一句"场景陈述句"：含该实体名、8–80 字、含位置/流程标记（在/位于/门口/登记/凭/须/开放/可以…）、不含人名（人名句是场景动作，不是设定） |
| 2 | Canon 世界规则 | `world_rule_revealed` 的 `rule_content`，按章节从新到旧，按分句裁到 170 字 |
| 3 | Canon 关系 | `from_entity`/`to_entity`，实体 id 映射成 Writer 能读的名字，裁到 110 字 |
| 4 | Canon 实体属性 | 只保留能映射到名字的实体；内部 id 永不进 prompt |

预算 700 字是**渲染结果**的上限：逐条累加，装不下的跳过（小条目仍可补位）。

正文来源只读 `.webnovel/runtime/chapter_XXX/draft.md`，且必须 `chapter_is_accepted()`
为真——在飞的草稿不是事实。

### 怎么进 prompt

放在 `## 本章必须写对` 之后、`## 当前人物状态与前文事实` 之前：

```
## 本章相关既有事实
（本节是本书前文已经确认、本章会用到的具体事实。地点、流程、物品、人物关系一律照此，
不要重新发明，也不要改写；本节不包含本章的剧情目标。）
- 地方志办公室在城西，一栋老楼的三层，下午两点半开门。
- 旧报库在报社后院，门口一本登记簿，写上日期就能进。
- 档案科的限制查阅卷宗须科级以上签字才能调阅；……
```

同时把世界规则、关系、`attributes.*` 从 `【已确认前文事实】` 里摘掉——同一事实说两遍，
Writer 会当成两件事。封包指纹新增 `continuity_facts_fingerprint`，B 臂三章实测 479 字。

## 2. 写后 `show_then_explain`

### 为什么

第三轮「作者直接解释」B 比 A 低 0.75。这不是写前约束不足，而是写完后没人删掉
「动作已经说完，又补一句总结」的句子。

### 怎么检测

`prose_diagnostics.detect_show_then_explain()`：

- 触发：句首/句内出现 **复述连接词**（也就是说 / 换句话说 / 换言之 / 意思是说 / 这表明 /
  这说明 / 这意味着）或 **叙述者理解框架**（他终于明白 / 他意识到 / 他知道 / 他清楚 /
  原来 / 显然 …）；
- 排除：对白；含数字（数字是新信息）；含新判断词（只能/必须/因为/所以/除非/如果/到底/
  为什么/谁/哪/是不是/多少/恐怕/很可能）；前面没有任何句子。
- 上下文取**跨段**的前两句——复述句经常是新段的第一句。

### 怎么修

`prose_postedit.apply_show_then_explain_edits()`：**只删命中的那一句**，其余字符不动；
句子在全文出现多次则跳过（删错比不删更糟）；含对白的整段不删空。
删除后仍走 `ProseQualityPipeline.process_and_validate()`：缩水率、电报体、语义漂移任一不过
就回滚到原稿。

CLI：`webnovel.py prose postedit --file X [--write] [--format json]`。

## 没动的

`## 本章必须写对`、lean 渲染器的排版、Creative Brief 结构与 1800 上限、Router 选择逻辑与
120 字上限、Skill 内容/数量/700 预算、Context Agent、Canon、ContextManager、Story System、
Reviewer、Data Agent、ChapterCommit、prose pipeline 的既有门禁、anti-slop、9 个 Skill 的
文学内容。

## 测试

- `tests/unit/test_continuity_and_postedit.py`（新增 6 项）：设定句只取场景陈述、人名句被排除、
  内部 id 不泄漏、预算上限、复述句删除、带新推理的总结句保留、对白不动。
- `tests/unit/test_writer_information_chain.py`：世界规则改由连续性块承载后，测试同步到新位置。
- 全量：`490 passed, 1 failed`，失败项 `test_canonical_cli_invocations_are_identical_across_skills`
  为 pre-existing。
