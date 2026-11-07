# 文学减法编辑正式集成 — 短 E2E 验收报告（v2）

- 日期：2026-11-07
- PR：https://github.com/liuchangchxy/zhanghui/pull/68
- 分支：`feat/literary-finalizer-integration`
- 基线：`a41ac35`
- 判定：**PASS**
- 合并条件：**满足**（未自行合并）

---

## 1. 结论

文学减法作为正式 Step 2B 的唯一文学编辑环节，已经能在**不改变故事状态**的前提下进入最终正文：

- ch03、ch05 的候选通过 acceptance，成为最终正文；
- ch07 因删除“为什么不能登记”的必要因果被拒绝，回退 Writer raw；
- 采用候选的两章无真实 story-state loss；危险变化仍被拒绝；
- 没有新增 Agent / Router / 数据库 / 状态系统 / 语义分类框架。

核心修正只有一处：Acceptance 不再把 Judge 找到的所有差异都当成 blocker，而是只把
`impact=STORY_STATE`（或未标注 / `UNKNOWN` / 无法绑定 / Judge 失败）的差异当成 blocker；
明确标为 `DISCOURSE` 的话语层压缩可以放行。

---

## 2. 修改文件

| 文件 | 内容 |
|---|---|
| `scripts/data_modules/literary_finalizer.py` | 过滤 Judge findings：仅 `STORY_STATE`/未分类阻断；`ownership`/`world_rule` 硬保护；记录 allowed/blocking |
| `scripts/data_modules/prose_semantic_diff.py` | Finalizer-only `state_impact` 判据；`parse_semantic_judge_response` 保留 `impact`；Judge finding 标记 `semantic_judge_discourse` |
| `scripts/data_modules/prose_judge_host.py` | `build_judge_request(state_impact=True)`；默认请求不变 |
| `scripts/data_modules/webnovel.py` | `judge-request --state-impact`；`literary-finalize-prompt --context-output` 输出 Judge 参考用 Canon/Intent |
| `skills/webnovel-write/SKILL.md` | Step 2B 使用 `--state-impact` + `--constraints-file`；更新 acceptance 判定表与边界 |
| `tests/unit/test_literary_finalizer.py` | 16 个测试（新增 8 个边界测试） |
| `study/audits/2026-11-07-...md` | 记录 acceptance 边界修正 |
| `experiments/...` | v2 重新裁决、逐条分类、内容复检 |

---

## 3. Acceptance 逻辑修改前后

**修改前（v1）**

```
compare_semantic_facts -> 任一 SEMANTIC_CHANGE_PROPOSED / UNCERTAIN -> 整章回退
```

结果：Judge 只要找到“删了一句解释”，就 `SEMANTIC_CHANGE_PROPOSED`，3/3 整章回滚，
文学增益无法进入最终正文。

**修改后（v2）**

```
Judge（仍负责找差异）:
  每条 change 标注 impact = STORY_STATE | DISCOURSE | UNKNOWN
        ↓
Literary Finalizer（只决定是否阻断）:
  - STORY_STATE / UNKNOWN / 未标注 / 绑定失败 / Judge 失败 -> BLOCK
  - DISCOURSE + 非硬保护维度 -> ALLOW
  - ownership / world_rule 即使标 DISCOURSE -> BLOCK（第二道保险）
        ↓
确定性护栏仍然先行：正文 >=90%、数字/日期/编号值集合、受保护术语
```

- 其他流程的 Judge 请求与行为**完全不变**（`state_impact` 默认关闭；`impact` 默认 `UNKNOWN`，
  仍按原逻辑阻断）。
- 没有白名单、没有按例句硬编码、没有新增分类框架。

---

## 4. ch03 / ch05 / ch07 最终结果

| 章 | 类型 | 长度比 | Judge changes | 采用 | 最终正文 |
|---|---|---:|---|---|---|
| ch03 | 信息/推理密集 | 91.53% | 14 条，全部 DISCOURSE | **是** | 候选 |
| ch05 | 对话/人物冲突 | 90.66% | 6 条，全部 DISCOURSE | **是** | 候选 |
| ch07 | 章末钩子 | 93.88% | 3 条 DISCOURSE + 1 条 STORY_STATE + 1 条硬保护 | 否 | Writer raw |

逐条重新分类见 `analysis/RECLASSIFICATION.md`。摘要：

- ch03：删除“他没问”“那是他自己瞒下的”“林越没觉得他在撒谎”“像说了什么很对的话”等 14 处，
  均为叙述层压缩；Canon 已记载“隐瞒缺页暂不登记”，行动、调查方向与章末钩子不变。
- ch05：删除“不问比问更压人”“林越听懂了”“昨天防备生人/今天辨认对手”“头一回”等 6 处；
  系统/纸面机制在对白中，决定仍以“交接班登记簿。”收束。
- ch07：允许“他没处说去”“讨价第一步”“明天三点复盘”；拒绝
  “一登记就等于当众揭了梅叔的盖子”（必要因果，无法从保留正文恢复）；
  “唯一能带出档案屋的实物……”虽被 Judge 标 DISCOURSE，但 `ownership` 硬保护，仍拒绝。

---

## 5. 是否存在真实 story-state loss

**采用候选的两章：没有。**

| 检查项 | ch03 | ch05 |
|---|---|---|
| 事件是否发生/结果 | 不变 | 不变 |
| 人物知情状态 | “不能说”保留；隐瞒缺页见 Canon；判断未反转 | 机制信息在对白中；未改成知道/不知道 |
| 决定 | 明天问梅叔移交单保留 | 找交接班登记簿保留 |
| 行动 | 刮痕、出门、见韩策、补纸全保留 | 看手、仓库对话、签字、换插销全保留 |
| 物品归属/位置 | 无变化 | 无变化 |
| 数字/日期/编号/术语 | 值集合不变 | 值集合不变（`八月八日` 少一次重复，值仍在） |
| 关键因果 | “理由太顺”等保留 | 系统覆盖/纸不改的因果在对白中 |
| 章末钩子 | “明天问梅叔”保留 | “交接班登记簿。”保留 |

ch07 的候选没有进入最终正文，因此最终正文层面同样没有故事损失；被拒绝的正是必要因果。

---

## 6. 测试结果

```
python3 -m pytest tests/unit/test_literary_finalizer.py -q
16 passed in 0.15s

python3 -m pytest tests/unit -q
1 failed, 394 passed in 8.4s
```

新增/覆盖的边界：

1. 删除“他听懂了”，信息在对白中 → 允许；
2. 删除潜台词解释，动作仍在 → 允许；
3. 删除重复复盘 → 允许；
4. 改变人物是否知道某事实（`STORY_STATE`）→ 拒绝；
5. 删除唯一关键因果（`STORY_STATE`）→ 拒绝；
6. 数字/日期/受保护术语变化 → 拒绝；
7. 未标注 / `UNKNOWN` → fail-closed 拒绝；
8. `ownership` 被误标 `DISCOURSE` → 仍拒绝；
9. acceptance 失败 → 回退含 CHANGES 的完整 Writer raw；
10. Step 2B 只保留一个文学环节，Step 4 不再整章润色。

唯一失败仍是既有用例 `test_stage2_repair_regression.py::test_canonical_cli_invocations_are_identical_across_skills`
（未跟踪的 `references/draft-review-lifecycle.md` 缺 `--enforce-auto-budget`），与本轮无关。

---

## 7. 文学盲评

候选文本本轮未重新生成，PR #68 的盲评仍成立：

- Writer raw（A）vs 候选（B），2 评审 × 正反两次 × 6 维：**36/36 全票 B**；
- 章级 OVERALL strict B **3/3**；
- 无 SPLIT / TIE，两个模型家族一致。

本轮修正后，ch03 / ch05 的候选**就是最终正文**，因此这两章的文学增益已进入正式输出；
ch07 仍是诊断性结果。

---

## 8. PASS / PARTIAL / FAIL

**PASS。**

- 文学候选能够进入最终正文：2/3（ch03、ch05）；
- 没有真实 story-state loss；
- 真正危险的 semantic change 仍能被拒绝（ch07 必要因果 + ownership 硬保护）；
- 不增加新的复杂系统（仅一个可选 `impact` 字段 + finalizer 内部过滤）。

ch07 未通过不是错误回滚，而是保留了一条无法从保留正文恢复的必要因果；
按用户规则“不要为了提高通过率强行放行”，保持拒绝。

---

## 9. 是否满足合并条件

**满足。** 本轮验收的两项同时成立：

1. 文学减法进入最终正文（2/3）；
2. 故事状态未被改变（采用的两章逐项核对通过）。

PR #68 更新后不自行合并，等待审查。

---

## 10. 最终回答

**文学减法能否在不改变故事状态的前提下真正进入最终正文，而不再被“删掉显式解释”这种变化错误回滚？**

能。Acceptance 现在只阻断真正改变故事状态的差异；ch03、ch05 的减法候选已成为最终正文，
故事状态逐项保持不变；ch07 因一条必要因果仍被正确拒绝。
