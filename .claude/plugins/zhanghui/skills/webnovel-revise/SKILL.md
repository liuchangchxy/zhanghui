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

> **共享命令契约**：本文件内联的 `runtime ingest-draft` / `runtime reviewer-context` /
> `review-pipeline` / `revise verify` / `runtime commit` / `runtime publish-draft` 命令，
> 其**唯一权威副本**是 `../../references/draft-review-lifecycle.md`（含"何时必须重审"的判据表）。
> 改动任何一条命令时，先改该文件再同步本文件；`tests/unit/test_stage2_repair_regression.py`
> 会在三个生命周期 Skill 的副本不一致时失败。

## 状态机边界与适用范围（核心契约）

### 1. 不可变提交权威守护（Immutable Commit Contract）
依据 `ChapterCommitService` 的状态机语义，已被 Durable Commit 接受（`commit_status == "accepted"`）的章节属于不可变 point-in-time snapshot，**禁止常规覆盖提交（overwrite is strictly forbidden）**。

因此，`webnovel-revise` **严格限定于在编草稿（In-Flight Working Draft）**：
- 适用：正在编写中、Step 3 审查发现 blocking issues、Step 4.5/4.7 闸门拦截、或 Step 5.5 commit 被拒收（`chapter-outcome == "rejected"`）的章节草稿。
- 禁界：**若本章已被正式接受（`status == "accepted"`），严禁使用常规 revise 流程覆盖！** 对已入账历史事实的修正属于 Phase 8/9 Canon Correction / Migration 范畴，常规修订入口严格 fail-closed。

### 2. 适用与不适用场景
- **适用**：
  - 在编草稿的 reviewer 审查输出 findings（含非阻断建议；默认全部纳入计划）
  - 局部段落修改
  - 保持未受影响段落的原文，避免 AI 改稿漂移
- **不适用**：
  - 本章已被 commit accepted 并已正式发布（不可变，阻断）
  - reviewer 尚未运行（先跑 `/webnovel-review` 或 `/webnovel-write` Step 3）
  - 大面积返工（>50% 段落需改）—— 建议重新起草工作草稿

> **省的是什么**：定点修订省下的是**正文重新生成**（以及由此带来的改稿漂移风险）——
> 只改必要句段，其余原文一字不动。
> **不省的是什么**：只要正文发生任何变化，就**必须**重新登记新 Draft 并对新草稿完整重跑 Reviewer；
> 正文变了却复用旧审查是被拒绝的（`revise plan` 拒绝旧审查、`runtime commit` 以
> `REVIEW_DRAFT_MISMATCH` 拒收）。因此本流程**不减少审查轮次**，只减少每轮的正文生成成本。
> 唯一真正省掉一次审查的情况是「正文没有变化」（`changed=false`）——那种情况下也确实没有什么可审。

## 执行流程

> **绝对禁令**：**严禁直接修改或覆盖 `正文/第{chapter_padded}章*.md`**！所有修订输出严格保存在
> 工作草稿与 `.webnovel/tmp/` 下。正式正文只能由 `runtime publish-draft` 发布。

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

### Step 2：定向修订（Host-Model Local Revision）

**定位不依赖 `## §N` 标题。** 真实章节正文没有这种结构，审查意见给的是「第79段」「第45段 / 第83段」
或原文引用。修订分四步，全部走正式 CLI：

1. **生成定向修订计划**（把 reviewer JSON 转成可执行的最小改动清单）：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" revise plan \
     --chapter {chapter_num} \
     --draft-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
     --review-result "${PROJECT_ROOT}/.webnovel/tmp/review_results.json" \
     --draft-id "{draft_id}" --draft-fingerprint "{draft_fingerprint}" \
     --output "${PROJECT_ROOT}/.webnovel/tmp/revision_plan_{chapter_padded}.json" --format text
   ```
   计划逐条给出 `locator`（`paragraph` / `line` / `quote` / `section` / `chapter`）、命中的字符区间、
   `before_text`、`fix_hint` 与 `kind`。默认包含非阻断（advisory）问题；`--blocking-only` 可只看阻断项。
   - `resolvable=false` / `ambiguity=ambiguous_quote` 的条目**不会被自动替换**：同一句话在正文里
     出现多次时，脚本拒绝猜位置，需要在 `--edits` 里补上更长的原文引用或改用段落号。
   - `locator=chapter`（整章范围）不属于可编辑区间 —— 它表示「这需要重新起草的决策」，不是「可以就地重写整章」。

2. **读取受治理上下文**（供改写时对照 Canon / 意图 / 禁区）：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime governed-context \
     --chapter {chapter_num} --format json > "${PROJECT_ROOT}/.webnovel/tmp/ch{chapter_padded}-revise-context.json"
   ```

3. **主流程（当前模型）改写对应句段**，把替换写成 edits 文件：
   `${PROJECT_ROOT}/.webnovel/tmp/revision_edits_{chapter_padded}.json`
   ```json
   [{"target_id": "<计划里的 issue_id>", "new_text": "<该区间改写后的原文>"}]
   ```
   一次只改计划命中的区间；不做整章重写。

4. **应用并校验**：
   ```bash
   # 应用（草稿若在计划生成后被改过，会以 drift 报错拒绝，绝不盲改）
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" revise apply \
     --draft-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
     --plan "${PROJECT_ROOT}/.webnovel/tmp/revision_plan_{chapter_padded}.json" \
     --edits "${PROJECT_ROOT}/.webnovel/tmp/revision_edits_{chapter_padded}.json" \
     --output "${PROJECT_ROOT}/.webnovel/tmp/step4_candidate_{chapter_padded}.md"

   # 边界校验：只允许计划区间发生变化
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" revise verify \
     --before-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
     --after-file "${PROJECT_ROOT}/.webnovel/tmp/step4_candidate_{chapter_padded}.md" \
     --plan "${PROJECT_ROOT}/.webnovel/tmp/revision_plan_{chapter_padded}.json" \
     --output "${PROJECT_ROOT}/.webnovel/runtime/chapter_{chapter_padded}/verify_minimal_edit.json"
   ```

   `--output` **必传**：该报告是下一轮 `review-pipeline` 判定"上一轮问题是否真的闭环"的
   closure 证据。不落盘时，即使问题确实修好了，收敛统计也只能记为 `uncertain`（因为
   校验器找不到证据文件）。   - `out_of_scope_changes` 非空 → 改动越界，回退重做，不得带着越界改动进入重审。
   - `untouched_targets` 列出本轮没有真正改到的条目，需要回到第 3 步补做。
   - `changed=false`（正文没变）→ **不登记新草稿、不重跑审查、不重新初始化全书或整卷规划**，
     沿用当前 `draft_id` 与既有审查结论。
   - 退出码 `4` = 版本/来源不匹配（计划不属于当前草稿，或审查未绑定当前草稿）→ 重新 `revise plan`。

5. **事实安全校验**（按改动性质分流）：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" prose validate \
     --before-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
     --after-file "${PROJECT_ROOT}/.webnovel/tmp/step4_candidate_{chapter_padded}.md" \
     --chapter {chapter_num} \
     --revision-plan "${PROJECT_ROOT}/.webnovel/tmp/revision_plan_{chapter_padded}.json"
   ```
   - `semantic_outcome=STYLE_ONLY_SAFE` → 纯文风修改，接受。
   - `status=PENDING_REREVIEW` + `semantic_outcome=FACT_FIX_DECLARED` → **待提交草稿内的事实纠错**的正常结果：
     不要求判成 `STYLE_ONLY_SAFE`，也不回滚；但必须完成 Step 3 的新 Draft 登记与新 Reviewer 审查。
   - `status=ROLLEDBACK` → 越界改写或事实篡改；回退重做。确定性层抓到的事实漂移一律硬阻断。
   - 若确属纯文风且需要裁决背书，按 `webnovel-write` 的「Semantic Judge 宿主裁决」接线
     （`prose judge-request` → 宿主模型裁决 → `prose judge-bind --request-file` → `prose validate --judge-file`）；
     Judge 未接通或失败则保持 `ROLLEDBACK`（fail-closed），**严禁伪造裁决**。

   > 事实边界的区分（不要混淆）：
   > - 纯文风修饰 / 非事实性措辞优化 → 可走 Semantic Judge 的 `STYLE_ONLY_SAFE` 判断；
   > - 待提交草稿内部的事实纠错 → 走本步骤的受治理草稿修订 + 重新审查；
   > - 已 accepted 章节的历史订正 → 只能走 Canon Correction，普通 revise 必须 fail-closed。
   > **不得把事实修改伪装成 STYLE_ONLY_SAFE。**

> **兼容路径（非默认）**：`scripts/revise_chapter.py` 仍然保留，用 `## §N` 分段 + 独立 Anthropic SDK
> 重写段落，需要额外的 `ANTHROPIC_API_KEY`。它只适用于正文确实采用 `## §N` 结构的老项目；
> 正常流程请使用上面的宿主模型路径，不需要额外 API Key。

### Step 3：刷新 ProposedChanges 与重新登记草稿（Re-Ingestion）

0. **确认采用修订稿**：`revise verify` 通过（`boundary_ok=true`）且 `semantic_outcome` 允许后，
   把 `${PROJECT_ROOT}/.webnovel/tmp/step4_candidate_{chapter_padded}.md` 覆盖回工作草稿
   `${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md`。
   若 `changed=false`，跳过本步全部动作，直接沿用现有草稿身份。

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
2. 使用 `Agent` 工具调用 `zhanghui:reviewer`：
   ```
   Use the Agent tool to run `zhanghui:reviewer`
   ```
   传入参数：
   - `chapter`: `{chapter_num}`
   - `chapter_file`: `"${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md"`
   - `reviewer_context_file`: `"${PROJECT_ROOT}/.webnovel/tmp/reviewer_context_{chapter_padded}.json"`
   - `draft_id`: `"{new_draft_id}"`
   - `draft_fingerprint`: `"{new_draft_fingerprint}"`
   - `review_subject_fingerprint`: `"{new_review_subject_fingerprint}"`
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
   若 `changes_gate` 校验未通过并对 `<chapter_changes>` 进行了重写或修改，导致工作草稿发生变化，
   先按**审查对象指纹**判断该变化是否触及正文：
   - **重新登记草稿**：必须重新调用 `runtime ingest-draft` 登记，获取更新后的 `{new_draft_id}` /
     `{new_draft_fingerprint}` / `{new_review_subject_fingerprint}`（`runtime commit` 从登记草稿读取提案）；
   - **`review_subject_fingerprint` 未变化**（只改了提案块）→ **不重审**。既有审查依然有效，只需重新运行
     `review-pipeline --chapter {chapter_num} --review-results ... --save-metrics` 把它登记到新草稿身份上。
     重新调用 Reviewer 属于无意义重复（实测三章共 836 s 的纯冗余成本）；
   - **`review_subject_fingerprint` 已变化** → 旧审查失效。**严禁主流程手工篡改或就地修改
     `review_results.json` 中的草稿身份字段**；必须复用既有 `reviewer_context_{chapter_padded}.json`
     （无需重建 Context Builder）重新调用 `zhanghui:reviewer`，传入新草稿身份，由 Reviewer Agent 权威
     生成与新草稿绑定的全新审查结果，并重新运行 `review-pipeline --save-metrics`；
   - **重新提取与对账**：Step 5 依据最新工作草稿重新拆分正文与 proposal，重新执行 Data Agent 提取与
     `reconcile_changes.py`；提案块变更是对账层的输入变化，**不因"正文没变"而豁免**；
   - **最终提交**：`runtime commit` 必须且仅能传入最终的 `{new_draft_id}`；
   - **未变直通**：若草稿完全未变更，则沿用 Step 3 登记的草稿身份与既有审查产物，不得无意义重复调用。

### Step 5：提取、对账与事实提交

1. **拆分正文与 proposal**：
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prepare_data_agent_input.py" \
     --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
     --prose-output "${PROJECT_ROOT}/.webnovel/tmp/data_agent_prose.md" \
     --changes-output "${PROJECT_ROOT}/.webnovel/tmp/proposed_changes.json"
   ```
2. **调用 Data Agent 重新提取事实**：
   使用 Agent 工具调用 `zhanghui:data-agent`（传入 `.webnovel/tmp/data_agent_prose.md` 与 `scripts_dir="${SCRIPTS_DIR}"`，严禁传入带有 CHANGES 的文件）。
   `scripts_dir` 必须显式传入：subagent 的 Bash 不继承本会话的 `export SCRIPTS_DIR`。
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
5. **write-gate precommit 闸门**（产物齐备后、提交之前；退出码 `0` 才可提交）：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" write-gate --chapter {chapter_num} --stage precommit
   ```
   非 `0` 时按 `errors[].repair` 回到对应上游步骤补齐，严禁为通过闸门伪造 Data Agent 产物。
6. **事实提交（Runtime Commit）**：
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
