# Judge change 逐条重新分类（v2 acceptance）

对象：PR #68 已生成的 ch03 / ch05 / ch07 候选稿（未重新生成正文）。
Judge：`codex/gpt-6.1-terra`，同一 before/after，新增 `--state-impact` 与受治理 Canon 参考。

判定口径：
- `ALLOW` = 不改变故事状态，只是话语层压缩。
- `BLOCK` = 真实故事状态变化，或属于硬保护维度（`ownership` / `world_rule`）。
- 未标注 / `UNKNOWN` / 绑定失败 / Judge 失败一律 BLOCK（fail-closed）。

汇总：25 条 change；23 条 `DISCOURSE`，2 条 `STORY_STATE`；最终 2 章采用候选，1 章回退原稿。

## ch03（ACCEPTED）

| change（原文摘要） | Judge 类型 | impact | 新判定 | 原因 |
|---|---|---|---|---|
| “这个由头不算牵强” | motivation | DISCOURSE | ALLOW | 删旁白注解，动作“去东街配鱼胶”保留 |
| “他没问。脚下一转，出了巷子。”→“脚下一转，出了巷子。” | event_outcome | DISCOURSE | ALLOW | 同一行动仍由保留动作表明；没有改成“他问了” |
| “意识到这片地界上大小事都收在一个人手里” | epistemic | DISCOURSE | ALLOW | 信息仍由老板对白直接给出 |
| “不重，但够用” | relationship | DISCOURSE | ALLOW | 语气注解；目光动作保留 |
| “韩策说的不是问句。” | epistemic | DISCOURSE | ALLOW | 对白的语气已能表明，不再点破 |
| “缺页的事不能说，那是他自己瞒下的。” | causality | DISCOURSE | ALLOW | Canon 已记载“隐瞒缺页暂不登记”；只删提醒，事实不变 |
| “像林越说了什么很对的话” | relationship | DISCOURSE | ALLOW | 点头动作保留 |
| “一个凭空掉下来的名字” | epistemic | DISCOURSE | ALLOW | 前句“没听过/没提过/没出现过”保留 |
| “像是要确认他把话听到了什么程度” | motivation | DISCOURSE | ALLOW | 看了一眼的动作保留 |
| “整段话搭在另一个人的记忆上……” | epistemic | DISCOURSE | ALLOW | “师父看过、他本人没经手”保留 |
| 庙里逐条复盘乔宁/安全阀/确认单 | epistemic | DISCOURSE | ALLOW | 重复复盘；事实在韩策对白中 |
| “林越没觉得他在撒谎……” | epistemic | DISCOURSE | ALLOW | 判断未反转，后续调查方向不变；保留“每条都卡在没法核实” |
| “所有能作证的东西都不在” | clue | DISCOURSE | ALLOW | 师父死了/原件没了/调令没登记保留；移交单仍在 |
| 章末“先揣笔记本/开始补纸”与“明天问梅叔”换序 | motivation | DISCOURSE | ALLOW | 同一组动作与下一步行动均在，仅顺序调整 |

## ch05（ACCEPTED）

| change（原文摘要） | Judge 类型 | impact | 新判定 | 原因 |
|---|---|---|---|---|
| “不问比问更压人……只是被存下了” | epistemic | DISCOURSE | ALLOW | 情绪判断；梅叔“看了左手两秒”动作保留，未改成“追问/放心” |
| “林越听懂了。放在网上的东西……” | epistemic | DISCOURSE | ALLOW | 系统/纸面机制已在乔宁对白中完整给出 |
| “昨天防备生人，今天辨认对手” | relationship | DISCOURSE | ALLOW | 潜台词点破；乔宁看他一眼的动作保留 |
| “这在乔宁身上是头一回” | relationship | DISCOURSE | ALLOW | 强调性限定；压低声音的动作保留，不影响后续关系 |
| 离开时逐条复盘线索 | clue | DISCOURSE | ALLOW | 日期、泵房、铅笔字均在前文对白/台账；只删复盘 |
| “他得找到……手写的。纸做的。” | motivation | DISCOURSE | ALLOW | 决定仍以“交接班登记簿。”收束，方向未变 |

## ch07（FALLBACK_RAW）

| change（原文摘要） | Judge 类型 | impact | 新判定 | 原因 |
|---|---|---|---|---|
| “但这句话他没处说去。” | epistemic | DISCOURSE | ALLOW | 短情绪落点；前句“不止他一个人在盯柜子”保留 |
| “一登记就等于当众揭了梅叔的盖子。” | causality | STORY_STATE | **BLOCK** | 删除后正文不再说明“为什么不能登记”；该原因支撑当前行动，且不能从保留正文恢复。不因提高通过率放行 |
| “这已经是讨价的第一步。” | epistemic | DISCOURSE | ALLOW | 潜台词点破；“手没把钥匙推回来”保留 |
| “钥匙不在他身上了。唯一能带出档案屋的实物……” | ownership | DISCOURSE | **BLOCK** | Judge 标 DISCOURSE（前文已写“放进工装口袋”“口袋空了”），但 `ownership` 是硬保护维度；该句同时是唯一实物线索/归属总结，保留拒绝 |
| “明天三点之前……乔宁不会替他扛。” | clue | DISCOURSE | ALLOW | 三点、旧图纸、不替他扛均在乔宁对白中；只删重复复盘 |

ch07 最终回退 Writer raw。即使去掉 ownership 硬保护，ch07 仍会因 causality 这条真实状态变化被拒；
硬保护只是额外的第二道保险，不是本章结论的原因。
