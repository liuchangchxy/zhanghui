---
name: webnovel-fast-write
description: 快车道写章节（跳过非必需的文风适配与定向润色环节，运行最小核心审查）。必须通过受治理运行时事实提交与正式发布门禁。Use when you trust the direction of a single chapter and want a fast-track workflow. Runs Step 0/1/2A/3(core)/4.5/4.6/5/5.5/6.
allowed-tools: Read Write Edit Grep Bash Agent
---

# Fast Chapter Writing (Fast-Track Convergence Workflow)

## 目标

以高吞吐流程快速产出可发布章节：
- **跳过非必需环节**：跳过 Step 2B（文风适配）与 Step 4（定向润色）；
- **保留必要审查与治理门禁**：运行 Step 3 最小核心客观审查（consistency、continuity、ooc），杜绝跳过审查引发的提交拒收与伪造审查风险；
- **严格遵守事务权威**：工作草稿严格隔离，草稿由 `runtime ingest-draft` 登记，经 `runtime commit` 事实提交 accepted 后，由 `runtime publish-draft` 剥离协议发布 100% 纯正文到 `正文/` 目录；
- **严禁双重权威**：不得发明第二套 commit 或 publication 绕过机制。

## 适用场景

- 你信任本章的方向（章节大纲清楚、伏笔命中明确）
- 追求写作推进速度，不想耗费时间在逐段文风调优与定向小修上
- 仍需确保设定一致性、连续性、角色不 OOC 与事实提交完整性

## 不适用场景

- 第一次写新项目（先跑 `/webnovel-write` 摸清边界）
- 重大高潮、卷末高光或复杂多线交汇章（建议使用 `/webnovel-write`，开启完整审查与文风调优）
- 用户明确要求"严格全维审查"或"深度润色"

## 执行流程

### Step 0：预检与环境设置

```bash
export WORKSPACE_ROOT="${CLAUDE_PLUGIN_ROOT:-${PWD}}"
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT}/scripts"
export SKILL_ROOT="${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is required}/skills/webnovel-fast-write"

python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" preflight
export PROJECT_ROOT="$(python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"

python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" placeholder-scan --format text
```

`preflight` 校验环境与项目根，`placeholder-scan` 确保大纲/设定无未补齐占位。任一失败立即阻断。

### Step 1：写前准备与 Native Writer Package 封口

统一执行收敛后的 Native Writer Workflow，杜绝主流程手工拼装 prompt：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime prepare --chapter {chapter_num} --format json
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime governed-context --chapter {chapter_num} --format json
```

1. 使用 Agent 工具调用 `webnovel-writer:context-agent`（传入 `chapter`、`project_root` 等），产出文学创作任务书（Creative Brief）；
2. 调用 `runtime attach-creative-brief` 签名封口，生成唯一 Canonical Writer Prompt：
```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime attach-creative-brief \
  --chapter {chapter_num} \
  --brief "{context_agent_creative_brief}" \
  --format prompt
```
记录返回的已封口 `package_fingerprint` 与 Canonical Writer Prompt。

### Step 2A：正文起草与草稿登记

1. **唯一输入**：Writer 严格且仅消费 Step 1C 生成的 Canonical Writer Prompt。
2. **工作草稿隔离（Working Draft Isolation）**：
   - 起草只输出到工作草稿文件：`${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md`。
   - **严禁在正式提交 accepted 前直接创建或覆盖正式 `正文/第{chapter_padded}章[-title].md` 文件**。
3. **CHANGES 协议声明**：正文末尾必须严格附带合法的 `<chapter_changes>...</chapter_changes>` 结构化变更提案块（8 个顶级标准字段）。
4. **登记草稿（Runtime Draft Ingestion）**：
   生成工作草稿后，立即调用 `runtime ingest-draft`：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime ingest-draft \
     --package-fingerprint {package_fingerprint} \
     --draft-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
     --format json
   ```
   记录返回的 `draft_id` 与 `draft_fingerprint`。后续审查、提炼、对账与提交均严格绑定此 `draft_id`。

### 跳过 Step 2B（文风适配与候选门禁）

快车道跳过 2B 风格微调，直接进入 Step 3。

### Step 3：快车道审查（核心 3 维度客观审查）

**审查必要性与闭环约束**：
- `ChapterCommitService` 与 `runtime commit` 将 `review_result` 作为必需语义产物（`required_artifacts: ["review_result"]`），且闸门决策依赖审查 findings。
- 若完全跳过审查，提交将因缺失关键产物被拒收；严禁主流程内联伪造审查结论，亦严禁绕过审查建立第二套 commit 机制。
- **快车道优化**：为确保速度，快车道跳过耗时的人工多轮审查与条件审查（`reader-pull`、`high-point`、`pacing`），仅执行 3 个核心客观检查器：
  - `consistency-checker`（设定一致性）
  - `continuity-checker`（叙事连贯与前情衔接）
  - `ooc-checker`（角色行为与性格一致性）

**执行流程**：
1. 预先获取受治理审查上下文：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime reviewer-context \
     --chapter {chapter_num} \
     --format json > "${PROJECT_ROOT}/.webnovel/tmp/reviewer_context_{chapter_padded}.json"
   ```
2. 使用 `Agent` 工具调用 `webnovel-writer:reviewer`：
   ```
   Use the Agent tool to run `webnovel-writer:reviewer`
   ```
   输入参数：
   - `chapter`: `{chapter_num}`
   - `chapter_file`: `"${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md"`
   - `reviewer_context_file`: `"${PROJECT_ROOT}/.webnovel/tmp/reviewer_context_{chapter_padded}.json"`
   - `project_root`: `"${PROJECT_ROOT}"`
   - `scripts_dir`: `"${SCRIPTS_DIR}"`
   - `draft_id`: `"{draft_id}"`
   - `draft_fingerprint`: `"{draft_fingerprint}"`
3. 审查结果落盘到 `${PROJECT_ROOT}/.webnovel/tmp/review_results.json`。
4. 审查指标落库：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" review-pipeline --save-metrics \
     --results "${PROJECT_ROOT}/.webnovel/tmp/review_results.json"
   ```
5. Craft advisory 约束：所有 raw findings 保持 `blocking=false`，Craft 建议不阻断提交。

### 跳过 Step 4（定向安全润色）

快车道跳过 Step 4 诊断与定向润色。

### Step 4.5：刷新 ProposedChanges 并校验协议

校验工作草稿末尾的 `<chapter_changes>` 提案块：
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/changes_gate.py \
    --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
    --db .webnovel/index.db \
    --json
```
若不通过，要求仅重写 `<chapter_changes>` 块，最多重试 2 次。

### Step 4.6：anti-slop 扫描（启发式建议，不阻断）

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/text_humanizer.py \
    detect --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md"

node ${CLAUDE_PLUGIN_ROOT}/scripts/check-ai-patterns.js \
    --check --json --fail-on=blocking \
    "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" || true
```
扫描命中默认作为 advisory 呈现，不单独阻断提交。

### Step 5：Data Agent 提取与对账（Reconciliation）

1. 拆分正文与 proposal：
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prepare_data_agent_input.py" \
     --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
     --prose-output "${PROJECT_ROOT}/.webnovel/tmp/data_agent_prose.md" \
     --changes-output "${PROJECT_ROOT}/.webnovel/tmp/proposed_changes.json"
   ```
2. 调用 `webnovel-writer:data-agent`（只传 `.webnovel/tmp/data_agent_prose.md`）。
3. 执行语义对账：
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reconcile_changes.py" \
     --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
     --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json" \
     --db "${PROJECT_ROOT}/.webnovel/index.db" \
     --output "${PROJECT_ROOT}/.webnovel/tmp/reconciliation_result.json"
   ```

### Step 5.5A：事实提交（Runtime Commit）

通过统一事务入口提交本章事实：
```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime commit \
  --chapter {chapter_num} \
  --draft-id {draft_id} \
  --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
  --fulfillment-result "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
  --disambiguation-result "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
  --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json" \
  --reconciliation-result "${PROJECT_ROOT}/.webnovel/tmp/reconciliation_result.json" \
  --format json
```
若 `chapter_outcome != "accepted"`，严禁进入发布环节。

### Step 5.5B：正文发布门禁（Publication Gate）

检查 5.5A 结果，**仅当 `chapter_outcome == "accepted"` 时**，调用发布入口：
```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime publish-draft \
  --chapter {chapter_num} \
  --draft-id {draft_id} \
  --format json
```
- 严格校验草稿完整 SHA-256 与纯正文 SHA-256 双重指纹；
- 剥离 `<chapter_changes>` 提案块，发布 100% 纯正文至 `正文/第{chapter_padded}章[-title].md`。

### Step 6：备份

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" backup
```
