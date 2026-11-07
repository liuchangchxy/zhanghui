# 文学减法编辑正式集成 — 决策记录

- 日期：2026-11-07
- 依据：PR #66（五条原则推导）+ PR #67（6 章 held-out，72/72 稳定 B，PARTIAL）
- 本轮目标：把已验证的减法编辑接入正式 `webnovel-write`，用最小代码与一次短 E2E 验收。

## 1. 为什么不重做 Prompt 研究

PR #67 已经冻结了五条原则、三条护栏与输入结构，并在 6 个未参与推导的章节上完成
两评审 × 正反两次的盲评。本轮不再比较不同 prompt，也不重新研究 Jarvis 架构。
唯一的变化是把同一套原则接到正式流程，并复用既有 governed-context / VoiceTarget / Judge。

## 2. 最小实现

新增：

- `scripts/data_modules/literary_finalizer.py`
  - 冻结的五条原则、三条护栏、保护清单；
  - prompt 组装（outline / 硬约束 / 下一章开头 / VoiceTarget）；
  - 确定性护栏：正文 ≥90%、数字/日期/编号按值集合比对、受保护术语；
  - 复用 `evaluate_prose_quality_and_decide` 做现有语义门禁；
  - 任何失败返回 Writer 原稿（含 CHANGES）。
- `prose literary-finalize-prompt`
- `prose literary-finalize-validate`
- 5 类机制测试（`tests/unit/test_literary_finalizer.py`）。

没有新增 Agent、Router、数据库、状态系统、文学评分或新的语义分类框架。

## 3. Step 2B / Step 4 的最终处理

| 原职责 | 处理 | 理由 |
|---|---|---|
| Step 2B 文风适配（rewrite-only，只改措辞，不得增删动作/线索） | **替换为文学减法定稿** | rewrite-only 从定义上无法改善场景张力或减少作者解释；held-out 已证明减法有效 |
| Step 2B 的 `prose validate` 独立命令 | **合并进 `literary-finalize-validate`** | 同一对 before/after 只跑一次；保留原有 `compare_semantic_facts` + 宿主 Judge |
| Step 4 加载 `polish-guide.md`、诊断驱动整章润色 | **删除** | 与 Step 2B 重复；同一正文不应连续跑多次文学润色 |
| Step 4 Reviewer 问题路由 / `revise plan/apply/verify` | **保留** | Reviewer 定位的问题仍需最小修复 |
| Step 4 事实纠错 `PENDING_REREVIEW` 路径 / 重审 | **保留** | 独立、必要，不属于文学润色 |
| Step 4 `typesetting.md` | **保留** | 移动端排版是独立职责 |
| Step 3 Reviewer | **不扩权** | Reviewer 判“是否有真问题”；Finalizer 判“怎么写更好” |
| `--fast` / `--minimal` 跳过 2B | **保留** | 快车道明确不做文学定稿；Step 4 也不再做文学润色 |

## 4. 安全结构

- 长度：正文（去空白、去标题、去 CHANGES/封包指纹）不得低于 90%。
- 事实：数字/日期/编号按**值集合**比较，新增、缺失、替换都拒绝。用集合而不是出现次数，
  是因为删除重复转述时可能减少同一数字的出现次数；值本身不能消失。
- 术语：可选 `--term` / `--terms-file`，出现即不得缺失。
- 语义：复用现有 `compare_semantic_facts`；`STYLE_ONLY_SAFE` 才放行，其余 fail-closed。
- 回退：`--raw-draft-file` 保证拒绝时保留含 `<chapter_changes>` 的完整工作草稿。
- 不重试：一次生成；截断/空输出才允许机械重试。门禁失败直接进入 Step 3。

## 5. 验收边界修正（v2）

第一轮 E2E 暴露的问题不是“Judge 误报”，而是 acceptance 层把 Judge 找出的
**话语层压缩**也当成故事状态变化整体回滚。修正只改 literary finalizer 的 acceptance：

- Judge 仍然是唯一的差异发现者。
- `prose judge-request --state-impact`（仅 Step 2B 使用）要求 Judge 给每条 change 标注
  `STORY_STATE | DISCOURSE | UNKNOWN`。默认请求的输出与旧行为完全一致。
- Finalizer 只把 `STORY_STATE`、`UNKNOWN`、未标注、无法绑定、Judge 失败、确定性 claim 差异
  当作 blocker；只有明确 `DISCOURSE` 的 change 才允许。
- `ownership / world_rule / capability` 即使被误标为 `DISCOURSE` 仍然硬拒绝；
  `event_outcome / location_or_state / clue / causality` 由 Judge 按“保留正文是否仍承载同一状态”
  判断——删除已被动作/对白展示的总结、调整同一组动作顺序，属于话语层压缩。
- 删掉了 v1 的“SEMANTIC_CHANGE_PROPOSED 一律回退”；未标注、`UNKNOWN`、无法绑定、Judge 失败、
  确定性 claim 差异仍然 fail-closed。
- Step 2B 的 Judge 请求额外读入精简的 `current_intent` + `governed_canon`，用于识别
  “前文/Canon 已建立、此处只是复述”的事实（例如“隐瞒缺页暂不登记”）。

**v2 短 E2E 结果**（复用同一批候选，不重新生成正文）：

| 章 | 长度比 | change 分类 | 最终 |
|---|---:|---|---|
| ch03 | 91.53% | 14 条全部 DISCOURSE | 采用候选 |
| ch05 | 90.66% | 6 条全部 DISCOURSE | 采用候选 |
| ch07 | 93.88% | 3 DISCOURSE + 1 STORY_STATE + 1 硬保护 | 回退 Writer raw |

- ch03 / ch05 逐项核对无真实 story-state loss；
- ch07 拒绝“一登记就等于当众揭了梅叔的盖子”（必要因果）与“唯一能带出档案屋的实物”
  （ownership 硬保护），危险变化未进入最终正文；
- 判定 PASS，未自行合并。
- 没有新增 Agent、Router、分类框架或白名单；只是给现有 Judge 输出多一个可选字段，
  并在 finalizer 内部过滤。

## 6. 已知限制

- 确定性护栏不能证明“事件结果/知情状态/推理连接”未变；这部分仍依赖现有语义 Judge 与
  独立内容检查。不能把 judge 的偏好当事实核查。
- 90% 下限是硬门槛，短章或本来就冗长的章节可能直接回退；回退是设计行为，不是缺陷。
- E2E 使用已写好的真实 Writer 草稿，不是从 Step 1 重跑整条 10 章链；它验证的是新阶段的
  实际输入/输出与门禁，不验证耗时或完整项目状态迁移。
