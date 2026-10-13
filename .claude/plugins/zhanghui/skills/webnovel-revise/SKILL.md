---
name: webnovel-revise
description: 根据 reviewer 的结构化反馈局部修订在编章节工作草稿。通过 Runtime 草稿登记、重审、ChapterCommit 与正式发布门禁。严禁直接覆盖正式正文；已 accepted 章节受状态机保护禁止常规覆写。Use when reviewer has produced structured JSON with blocking issues for an in-flight chapter.
allowed-tools: Read Write Edit Grep Bash Agent
---

# Local Chapter Revision (In-Flight Draft Re-ingestion & Protected Convergence)

## 目标

根据 reviewer 的结构化反馈，**针对在编工作草稿局部重写标出的段落**，并重新接入受治理的 Runtime、Reviewer、ChapterCommit 与 Publication 流程：
- 只改 contract 标出的段落，其他段落原样保留；
- **草稿隔离与发布保护**：严禁直接修改或覆盖正式 `正文/` 目录；
- **重新受控验收**：修订完成后刷新 `<chapter_changes>`、通过 `runtime ingest-draft` 重新登记草稿、重跑审查并落库指标；
- **唯一发布路径**：经 `runtime commit` 提交 accepted 后，唯一通过 `runtime publish-draft` 发布纯正文。

## 状态机边界与适用范围（核心契约）

### 1. 不可变提交权威守护（Immutable Commit Contract）
依据 `ChapterCommitService` 的状态机语义，已被 Durable Commit 接受（`commit_status == "accepted"`）的章节属于不可变 point-in-time snapshot，**禁止常规覆盖提交（overwrite is strictly forbidden）**。

因此，`webnovel-revise` **严格限定于在编草稿（In-Flight Working Draft）**：
- 适用：正在编写中、Step 3 审查发现 blocking issues、Step 4.5/4.7 闸门拦截、或 Step 5.5 commit 被拒收（`chapter-outcome == "rejected"`）的章节草稿。
- 禁界：**若本章已被正式接受（`status == "accepted"`），严禁使用常规 revise 流程覆盖！** 对已入账历史事实的修正属于 Phase 8/9 Canon Correction / Migration 范畴，常规修订入口严格 fail-closed。

### 2. 适用与不适用场景
- **适用**：
  - 在编草稿的 reviewer 审查输出 blocking issues
  - 局部段落修改（比整章重写节省 60-80% token）
  - 保持未受影响段落的原文，避免 AI 改稿漂移
- **不适用**：
  - 本章已被 commit accepted 并已正式发布（不可变，阻断）
  - reviewer 尚未运行（先跑 `/webnovel-review` 或 `/webnovel-write` Step 3）
  - 大面积返工（>50% 段落需改）—— 建议重新起草工作草稿

## 执行流程

### Step 0：状态机与前置检查

1. 环境与项目解析：
   ```bash
   export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-${PWD}}"
   export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is required}/scripts"
   export SKILL_ROOT="${CLAUDE_PLUGIN_ROOT}/skills/webnovel-revise"

   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" preflight
   export PROJECT_ROOT="$(python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
   if [ -z "${PROJECT_ROOT}" ] || [ ! -f "${PROJECT_ROOT}/.webnovel/state.json" ]; then
     echo "ERROR: 未找到有效书项目根目录（缺少 .webnovel/state.json）: ${PROJECT_ROOT}" >&2
     exit 1
   fi
   ```
2. 查询本章状态并提取在编草稿关联的 `package_fingerprint`：
   ```bash
   export STATUS_JSON="$(python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime status --chapter {chapter_num} --format json)"
   export PACKAGE_FINGERPRINT="$(echo "${STATUS_JSON}" | python3 -c 'import sys, json; print(json.load(sys.stdin).get("package_fingerprint") or "")')"
   ```
   **状态检查与硬阻断规则**：
   - 若 `commit_status == "accepted"`：本章事实已锁定入账，**立即阻断**。严禁覆写已接受章节或其正文文件；向用户明确说明已接受章节不可变，需走历史订正流程。
   - 若 `has_writer_package != true` 或 `[ -z "${PACKAGE_FINGERPRINT}" ]`：未找到有效的封口底包，**阻断**（说明尚未完成起草准备）。
   - 若 `is_writer_package_stale == true`：封口底包已与上游大纲或前情脱节，**阻断**。
   - 若 `draft_status != "ingested"` 且未找到 `${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md`：缺少在编工作草稿，提示用户先起草。

### Step 1：读取审查反馈与受治理上下文

1. 确认审查报告：从 `${PROJECT_ROOT}/.webnovel/tmp/review_results.json`（或 `.webnovel/review/ch{chapter_padded}.json`）读取 blocking issues。若不存在，提示用户先执行审查。
2. 构造共享受治理上下文：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime governed-context \
     --chapter {chapter_num} --format json > "${PROJECT_ROOT}/.webnovel/tmp/ch{chapter_padded}-revise-context.json"
   ```

### Step 2：局部重写工作草稿（Working Draft Local Revision）

针对工作草稿执行 dry-run 验证与真实重写：
```bash
# 1. dry-run 确认目标段落
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/revise_chapter.py \
    --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
    --contract "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
    --context-file "${PROJECT_ROOT}/.webnovel/tmp/ch{chapter_padded}-revise-context.json" \
    --dry-run

# 2. 真实重写并写回工作草稿
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/revise_chapter.py \
    --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
    --contract "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
    --context-file "${PROJECT_ROOT}/.webnovel/tmp/ch{chapter_padded}-revise-context.json" \
    --output "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md"
```

**绝对禁令**：**严禁直接修改或覆盖 `正文/第{chapter_padded}章*.md`**！所有修订输出严格保存在工作草稿。

### Step 3：刷新 ProposedChanges 与重新登记草稿（Re-Ingestion）

1. **刷新 CHANGES**：依据修订后的工作草稿全文重新生成末尾的 `<chapter_changes>...</chapter_changes>` 提案块。局部重写必须保持完整的 8 个顶级标准字段，确保协议块不被破坏。
2. **清理历史与上一轮草稿残留产物（防止脏数据与跨版本混用）**：
   ```bash
   rm -f "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
         "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json" \
         "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
         "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
         "${PROJECT_ROOT}/.webnovel/tmp/reconciliation_result.json"
   ```
3. **重新登记草稿（复用 Step 0 验证的有效 package_fingerprint，获取全新 Draft Identity）**：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime ingest-draft \
     --chapter {chapter_num} \
     --package-fingerprint "${PACKAGE_FINGERPRINT}" \
     --draft-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
     --format json
   ```
   **草稿身份封口契约**：调用返回全新的 `draft_id` 与 `draft_fingerprint`。旧草稿身份与其关联的审查、对账结果立即失效；后续审查、提取、对账和提交必须严格绑定此 `{new_draft_id}`。严格复用 Step 0 验证通过的底层 `PACKAGE_FINGERPRINT`，不重复封口，也不伪造指纹。

### Step 4：重新审查与门禁校验

1. 获取最新审查受治理上下文：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime reviewer-context \
     --chapter {chapter_num} \
     --format json > "${PROJECT_ROOT}/.webnovel/tmp/reviewer_context_{chapter_padded}.json"
   ```
2. 使用 `Agent` 工具调用 `webnovel-writer:reviewer`：
   ```
   Use the Agent tool to run `webnovel-writer:reviewer`
   ```
   传入参数：
   - `chapter`: `{chapter_num}`
   - `chapter_file`: `"${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md"`
   - `reviewer_context_file`: `"${PROJECT_ROOT}/.webnovel/tmp/reviewer_context_{chapter_padded}.json"`
   - `draft_id`: `"{new_draft_id}"`
   - `draft_fingerprint`: `"{new_draft_fingerprint}"`
3. 落盘并更新审查指标（严格遵守 CLI 参数契约：`--chapter` + `--review-results` + `--save-metrics`）：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" review-pipeline \
     --chapter {chapter_num} \
     --review-results "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
     --save-metrics
   ```
4. 校验 CHANGES 协议：
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/changes_gate.py \
     --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
     --db "${PROJECT_ROOT}/.webnovel/index.db" \
     --json
   ```
5. **草稿变更后的身份同步与 Reviewer 所有权规则（Post-Ingest Mutation & Reviewer Re-invocation）**：
   若 `changes_gate` 校验未通过并对 `<chapter_changes>` 进行了重写或修改，导致工作草稿发生任何内容变化：
   - **重新登记草稿**：必须重新调用 `runtime ingest-draft` 登记，获取更新后的 `{new_draft_id}` 与 `{new_draft_fingerprint}`；
   - **Reviewer 原始结果所有权**：严禁主流程手工篡改或就地修改 `review_results.json` 中的 `draft_id` 或指纹。必须复用既有 `reviewer_context_{chapter_padded}.json`（无需重建 Context Builder）重新调用 `webnovel-writer:reviewer`，传入新 `{new_draft_id}` 与 `{new_draft_fingerprint}`，由 Reviewer Agent 权威生成与新草稿绑定的全新审查结果，并重新运行 `review-pipeline --chapter {chapter_num} --review-results ... --save-metrics`；
   - **重新提取与对账**：Step 5 依据最新工作草稿重新拆分正文与 proposal，重新执行 Data Agent 提取与 `reconcile_changes.py`；
   - **最终提交**：`runtime commit` 必须且仅能传入最终的 `{new_draft_id}`；
   - **未变直通**：若草稿未变更，则沿用 Step 3 登记的草稿身份与既有审查产物，不得无意义重复调用。

### Step 5：提取、对账与事实提交

1. **拆分正文与 proposal**：
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prepare_data_agent_input.py" \
     --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
     --prose-output "${PROJECT_ROOT}/.webnovel/tmp/data_agent_prose.md" \
     --changes-output "${PROJECT_ROOT}/.webnovel/tmp/proposed_changes.json"
   ```
2. **调用 Data Agent 重新提取事实**：
   使用 Agent 工具调用 `webnovel-writer:data-agent`（只传入 `.webnovel/tmp/data_agent_prose.md`，严禁传入带有 CHANGES 的文件）。
   Data Agent 依据唯一 schema 规范产出 3 份 canonical commit 必需产物到 `${PROJECT_ROOT}/.webnovel/tmp/`：
   - `extraction_result.json`（实体/状态变更、事件、摘要与场景）
   - `fulfillment_result.json`（大纲目标履约结果：planned_nodes, covered_nodes, missed_nodes, extra_nodes）
   - `disambiguation_result.json`（实体消歧 pending 队列）
   严禁主流程跳过 Data Agent 或伪造 fulfillment 结果。
3. **执行语义对账（Reconciliation）**：
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reconcile_changes.py" \
     --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
     --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json" \
     --db "${PROJECT_ROOT}/.webnovel/index.db" \
     --output "${PROJECT_ROOT}/.webnovel/tmp/reconciliation_result.json"
   ```
4. **提交前产物完整性校验（Fail-Closed Gate）**：
   在调用 `runtime commit` 前，核验当前修订 draft 的 5 份必需产物完整存在且非空：
   ```bash
   for art in review_results.json extraction_result.json fulfillment_result.json disambiguation_result.json reconciliation_result.json; do
     if [ ! -s "${PROJECT_ROOT}/.webnovel/tmp/${art}" ]; then
       echo "ERROR: 缺少提交必需产物: ${art}，严禁执行 runtime commit！" >&2
       exit 1
     fi
   done
   ```
   若任一必需产物缺失，严禁调用 `runtime commit`。
5. **事实提交（Runtime Commit）**：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime commit \
     --chapter {chapter_num} \
     --draft-id {new_draft_id} \
     --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
     --fulfillment-result "${PROJECT_ROOT}/.webnovel/tmp/fulfillment_result.json" \
     --disambiguation-result "${PROJECT_ROOT}/.webnovel/tmp/disambiguation_result.json" \
     --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json" \
     --reconciliation-result "${PROJECT_ROOT}/.webnovel/tmp/reconciliation_result.json" \
     --format json
   ```

### Step 6：正文发布门禁（Publication Gate）

**仅当 Step 5 提交成功且 `chapter_outcome == "accepted"` 时**，调用正式发布：
```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime publish-draft \
  --chapter {chapter_num} \
  --draft-id {new_draft_id} \
  --format json
```
- 精确校验 draft SHA-256 与 accepted commit 一致；
- 剥离内部 `<chapter_changes>` 提案块，发布 100% 纯正文到 `正文/第{chapter_padded}章[-title].md`。
- 若提交未被 accepted，严禁向 `正文/` 写文件。
