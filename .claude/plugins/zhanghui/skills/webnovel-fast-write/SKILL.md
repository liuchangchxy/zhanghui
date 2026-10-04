---
name: webnovel-fast-write
description: 跳过 reviewer 和 polish 完整流程的快车道写章节。保留 CHANGES 校验 + anti-slop 扫描 + data-agent。Use when you trust the direction of a single chapter and don't need 5-dimension subjective review. Runs Step 0/1/2A/4.5/4.6/5/6.
allowed-tools: Read Write Edit Grep Bash
---

# Fast Chapter Writing (Skip Reviewer)

## 目标

写一章并通过 CHANGES 校验 + anti-slop 扫描 + data-agent，**不调 reviewer、不跑完整 polish**。
相比 `/webnovel-write` 节省一次 subagent 调用（reviewer 是 5 维串行，最耗时）。

## 适用场景

- 你信任本章的方向（章节大纲清楚、伏笔命中明确）
- 不想为单章花 5+ 分钟等 reviewer 审查
- 已写过至少 3 章 /webnovel-write，对 webnovel-writer 的节奏有感觉

## 不适用场景

- 第一次写新项目（先跑 `/webnovel-write` 摸清边界）
- 重大剧情转折（用 `/webnovel-write`，reviewer 兜底）
- 用户明确要求"严格审查"

## 执行流程

按顺序执行：

1. **Step 0 预检**：调用 `${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py preflight` + `placeholder-scan`。
2. **Step 0.5 placeholders 校验**（PR 1 引入）：调用 `webnovel.py placeholders list` 与 `state status`；exit 0 继续；exit 1 仅记录 warning 不阻断。
3. **Step 1 context-agent**：调用 `webnovel-writer:context-agent` subagent 生成 7 段任务书。
4. **Step 2A 起草**：主流程生成正文 + 末尾追加 `<chapter_changes>...</chapter_changes>` 块。
   - **PR 2 接入**：在喂给主 LLM 之前，按白名单加载 writer slice 的文件作为 context 注入。
   - context-agent 的"五段写作任务书"作为 instruction 不变；writer slice 的文件作为参考输入。
   - 不再一次性 Read 全本大纲/设定/所有章节。
5. **刷新 ProposedChanges + Step 4.5 校验**：按最终正文重新生成 `<chapter_changes>` 后调用 `changes_gate.py`（详见主 skill 的 Step 4.5）。后续任何正文 rewrite 都必须再刷新。
6. **Step 4.6 anti-slop 扫描**：调用 `text_humanizer.py` + `check-ai-patterns.js`（详见主 skill 的 Step 4.6）。
7. **Step 5 data-agent**：先用 `prepare_data_agent_input.py` 将最终章节拆成 `.webnovel/tmp/data_agent_prose.md` 与 `.webnovel/tmp/proposed_changes.json`，再调用 `webnovel-writer:data-agent`，`chapter_file` 只传 prose-only 文件路径。正文后续变更时必须重新拆分、提取和对账。
8. **Reconciliation**：运行主 skill Step 5 中的 `reconcile_changes.py` 命令，生成 `.webnovel/tmp/reconciliation_result.json`。conflict 或 schema 失败时不得 commit。
9. **Step 5.2 chapter-commit**：调用 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py chapter-commit`，必须传 reconciliation artifact 与同一最终正文文件。
10. **Step 6 备份**：调用 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py backup`。
11. **Step 7 可选修订**（PR 3 引入）：如果存在 `.webnovel/review/ch${NNNN}.json` 且含 blocking issue，询问用户是否走 `/webnovel-revise`。默认不调——因为本 skill 是"信任方向的快车道"，重写交还用户决策。

## 跳过步骤

- **Step 2B 风格转译**（可选）
- **Step 3 reviewer 5 维审查**（主流程跳过）
- **Step 4 polish 完整流程**（只保留 4.5 + 4.6 两道门禁）

## 失败处理

- Step 4.5 失败：退回 Step 2A 重写 CHANGES 块（最多 2 次）
- Step 4.6 blocking：退回 Step 2A 重写正文，然后重新生成 CHANGES 并重跑 gate，最多 2 次
- Step 5 schema 失败：退回 Step 2A 全章重写

## 退出条件

跑 5-10 章后评估：
- 如果感觉与 `/webnovel-write` 质量持平 → 改用本 skill 作为默认
- 如果某章明显需要 reviewer 介入 → 临时回退到 `/webnovel-write`
