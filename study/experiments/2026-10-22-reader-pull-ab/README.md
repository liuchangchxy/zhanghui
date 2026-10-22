# Reader Pull 层单变量 A/B（第3章《只负责看站的人》）

## 问题

在 Scene 四问已经生效的前提下，把散落的追读机制（钩子/悬念/信息差/爽点/微兑现/期待债务/节奏压力）
收敛成一组自然语言的“期待 → 当章回报 → 新期待”指导，是否能让同一章更好读、更想让人继续读？

## 固定不变

| 项 | 值 |
|---|---|
| 书 / Canon | 《海港旧信》，第1–2章已 accepted |
| 章节任务 | 第3章，10月10日周六上午，约两小时 |
| Writer 模型 | 同一会话模型，两次生成 |
| 模型参数 | 相同（不调 temperature / 采样参数） |
| 字数目标 | 2000–2500 汉字 |
| 章纲 / 人物状态 / 世界状态 | 同一 `runtime governed-context` |
| Scene 设计 | 两稿都使用 Scene 四问（`--scene-design`） |
| 信息释放边界 | 相同（不提前揭示寄信人，不新增设定） |
| Creative Brief | 完全相同的 `creative_brief.md` |

## 唯一变量

Writer Prompt 中“追读”这一块的表达方式：

- **A**：现状。`hook_type` / 预设钩子设计 / 题材 `hook_config`、`coolpoint_config`、
  `micropayoff_config`、`pacing_config` 原始 YAML / “每600-900字一次微兑现” / 方法论策略卡。
- **B**：新的 Reader Pull 三问，取代上述参数块：
  1. 本章开始时，读者主要期待什么？
  2. 本章实际满足、改变或反转了什么期待？
  3. 因为本章发生的事情，读者现在更想知道/看到什么？

两份 Prompt 的 diff 只有这一个块。B 不增加世界观、剧情素材、答案、字数或人物状态。

## 判定规则（事先写定）

- B 明显更好 → `READER_PULL_LAYER_SUPPORTED`
- 基本持平 → `READER_PULL_LAYER_NOT_PRIMARY`
- B 更差或套路感更强 → `READER_PULL_LAYER_OVERCONSTRAINED`

盲评维度：阅读吸引力、是否更想继续读、当章回报是否足够、章末期待是否自然产生、
剧情推进、人物主动性、总体文学质量、是否出现人为制造悬念/套路感/机械钩子。

## 产物

- `00-inventory.md`：只读机制盘点与 KEEP/MERGE/DEMOTE/DORMANT/REMOVE 判定
- `prompt_A.txt` / `prompt_B.txt` / `prompt_diff.txt`
- `draft_A.md` / `draft_B.md`、`draft_X.md` / `draft_Y.md`、`judge_packet_*.md`、`blind_key.json`
- `eval/`：两名独立评委的原始评分
- `result.md`：评分、结论与限制
