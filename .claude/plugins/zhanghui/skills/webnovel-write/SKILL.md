---
name: webnovel-write
description: Writes webnovel chapters (default 2000-2500 words). Use when the user asks to write a chapter or runs /webnovel-write. Runs context, drafting, review, polish, and data extraction.
allowed-tools: Read Write Edit Grep Bash Agent
---

# Chapter Writing (Structured Workflow)

## 目标

- 以稳定流程产出可发布章节：优先使用 `正文/第{NNNN}章-{title_safe}.md`，无标题时回退 `正文/第{NNNN}章.md`。
- 默认章节字数目标：2000-2500（用户或大纲明确覆盖时从其约定）。
- 保证审查、润色、数据回写完整闭环，避免"写完即丢上下文"。
- 输出直接可被后续章节消费的结构化数据：`review_metrics`、`summaries`、`chapter_meta`。

## 执行原则

1. 先校验输入完整性，再进入写作流程；缺关键输入时立即阻断。
2. 审查与数据回写是硬步骤，`--fast`/`--minimal` 只允许降级可选环节。
3. 参考资料严格按步骤按需加载，不一次性灌入全部文档。
4. Step 2B 与 Step 4 职责分离：2B 只做风格转译，4 只做问题修复与质控。
5. 任一步失败优先做最小回滚，不重跑全流程。

## 模式定义

- `/webnovel-write`：Step 1 → 2A → 2B → 3 → 4 → 5 → 6
- `/webnovel-write --fast`：Step 1 → 2A → 3 → 4 → 5 → 6（跳过 2B）
- `/webnovel-write --minimal`：Step 1 → 2A → 3（仅3个基础审查）→ 4 → 5 → 6

最小产物（所有模式）：
- `正文/第{NNNN}章-{title_safe}.md` 或 `正文/第{NNNN}章.md`
- `index.db.review_metrics` 新纪录（含 `overall_score`）
- `.webnovel/summaries/ch{NNNN}.md`
- `.webnovel/state.json` 的进度与 `chapter_meta` 更新

### 流程硬约束（禁止事项）

- **禁止并步**：不得将两个 Step 合并为一个动作执行（如同时做 2A 和 3）。
- **禁止跳步**：不得跳过未被模式定义标记为可跳过的 Step。
- **禁止临时改名**：不得将 Step 的输出产物改写为非标准文件名或格式。
- **禁止自创模式**：`--fast` / `--minimal` 只允许按上方定义裁剪步骤，不允许自创混合模式、"半步"或"简化版"。
- **禁止自审替代**：Step 3 审查必须由 Task 子代理执行，主流程不得内联伪造审查结论。
- **禁止源码探测**：脚本调用方式以本文档与 data-agent 文档中的命令示例为准，命令失败时查日志定位问题，不去翻源码学习调用方式。

## 引用加载等级（strict, lazy）

- L0：未进入对应步骤前，不加载任何参考文件。
- L1：每步仅加载该步"必读"文件。
- L2：仅在触发条件满足时加载"条件必读/可选"文件。

路径约定：
- `references/...` 相对当前 skill 目录。
- `../../references/...` 指向全局共享参考。

## References（逐文件引用清单）

### 根目录

- `../../references/shared/core-constraints.md`
  - 用途：Step 2A 写作约束（章纲是本章 Intent 目标 / 已发生事实以 Canon commit 为准 / 发明需识别）。
  - 触发：Step 2A 必读。
- `references/writing/typesetting.md`
  - 用途：Step 4 移动端阅读排版与发布前速查。
  - 触发：Step 4 必读。
- `../../references/reading-power-taxonomy.md`
  - 用途：Step 1（内置 Contract）钩子、爽点、微兑现 taxonomy。
  - 触发：Step 1 当需要追读力设计时加载。
- `../../references/genre-profiles.md`
  - 用途：Step 1（内置 Contract）按题材配置节奏阈值与钩子偏好。
  - 触发：Step 1 当 `state.project.genre` 已知时加载。
- `references/writing/genre-hook-payoff-library.md`
  - 用途：电竞/直播文/克苏鲁的钩子与微兑现快速库。
  - 触发：Step 1 题材命中 `esports/livestream/cosmic-horror` 时必读。

### writing（问题定向加读）

- `references/writing/combat-scenes.md`
  - 触发：战斗章或审查命中"战斗可读性/镜头混乱"。
- `references/writing/dialogue-writing.md`
  - 触发：审查命中 OOC、对话说明书化、对白辨识差。
- `references/writing/emotion-psychology.md`
  - 触发：情绪转折生硬、动机断层、共情弱。
- `references/writing/scene-description.md`
  - 触发：场景空泛、空间方位不清、切场突兀。
- `references/writing/desire-description.md`
  - 触发：主角目标弱、欲望驱动力不足。

## 工具策略（按需）

- `Read/Grep`：读取 `state.json`、大纲、章节正文与参考文件。
- `Bash`：运行 `extract_chapter_context.py`、`index_manager`、CLI 工具（webnovel.py）。
- `Task`：调用 `context-agent`、审查 subagent、`data-agent` 并行执行。

## 交互流程

### Step 0：预检与上下文最小加载

必须做：
- 解析真实书项目根（book project_root）：必须包含 `.webnovel/state.json`。
- 校验核心输入：`大纲/总纲.md`、`${CLAUDE_PLUGIN_ROOT}/scripts/extract_chapter_context.py` 存在。
- 规范化变量：
  - `WORKSPACE_ROOT`：Claude Code 打开的工作区根目录（可能是书项目的父目录，例如 `D:\wk\xiaoshuo`）
  - `PROJECT_ROOT`：真实书项目根目录（必须包含 `.webnovel/state.json`，例如 `D:\wk\xiaoshuo\凡人资本论`）
  - `SKILL_ROOT`：skill 所在目录（固定 `${CLAUDE_PLUGIN_ROOT}/skills/webnovel-write`）
  - `SCRIPTS_DIR`：脚本目录（固定 `${CLAUDE_PLUGIN_ROOT}/scripts`）
  - `chapter_num`：当前章号（整数）
  - `chapter_padded`：四位章号（如 `0007`）

环境设置（bash 命令执行前）：
```bash
export WORKSPACE_ROOT="${CLAUDE_PLUGIN_ROOT:-${PWD}}"
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT}/scripts"
export SKILL_ROOT="${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is required}/skills/webnovel-write"

python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" preflight
export PROJECT_ROOT="$(python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"

```

**硬门槛**：`preflight` 必须成功。它统一校验 `CLAUDE_PLUGIN_ROOT` 派生出的 `SKILL_ROOT` / `SCRIPTS_DIR`、`webnovel.py`、`extract_chapter_context.py` 和解析出的 `PROJECT_ROOT`。任一失败都立即阻断。

**调用 tracking_query.py**（R4b 伏笔紧急度预检，写前执行）：
- 当项目已写章节数 ≥ 3（即 `${PROJECT_ROOT}/正文/` 下已有 ≥ 3 个章节文件），且 `progress.current_chapter > 3` 时，执行：
  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracking_query.py \
      --project "${PROJECT_ROOT}" \
      --chapter ${chapter_num} \
      --md
  ```
- 输出（活跃伏笔 + 超期伏笔）追加到 Step 1 任务书的"活跃伏笔"section，作为规划参考；超期状态表示 plan deviation，不自动成为本章硬约束。
- 工具执行失败（exit code != 0）只记录警告，不阻断——best-effort。

**个人语料检测**（best-effort，不阻断；Phase E 重定位）：
- 检测 `${PROJECT_ROOT}/.webnovel/writer-profile/个人语料.md` 是否存在（Phase E 起基线目录迁到 `${CLAUDE_PLUGIN_ROOT}/templates/`，书项目副本目录改为 `.webnovel/writer-profile/`）。
- 存在 → 提取 ≤ 200 字摘要，作为非权威性（non-authoritative）Craft/Reference input 在 Step 1B 传给 Context Agent 做创作规划；不由 ContextManager / Governed Context 自动加载，严禁直接向 Writer 追加 prompt，不替代题材/大纲/设定硬约束。
- 不存在 → 跳过，不报错

**写作宪法检测**（best-effort，不阻断；Phase E 重定位）：
- 优先检测 `${PROJECT_ROOT}/.webnovel/writer-profile/写作宪法.md`（由 init 从 `${CLAUDE_PLUGIN_ROOT}/templates/写作宪法.md` 复制）。
- 存在 → 作为 Craft input 提供给 Step 1B Context Agent（作者风格底线约束）；不由 ContextManager 自动加载，严禁直接向 Writer / Step 2A 注入（严禁作为 L1 prompt 直接注入 Writer）。由 Context Agent 在 Creative Brief 中落实其作者风格底线，最终通过 sealed Native Writer Package 统一进入 Writer。
- 不存在 → 跳过，不报错（不再回退到 skill 内 templates/）。

**对标参考检测（reference_research）**：
- 在 Step 1B（Context Agent 认知创作规划）统一读取：
  - 调用 `python3 ${SCRIPTS_DIR}/data_modules/reference_research_injector.py build-step1-summary --project-root "${PROJECT_ROOT}"` 获取对标总览摘要；
  - 调用 `python3 ${SCRIPTS_DIR}/data_modules/reference_research_injector.py build-step2a-section --project-root "${PROJECT_ROOT}"` 获取详细约束（包含 `do_not_copy` 红线禁区、`canon_contamination_warnings` 设定污染警告、`borrowable_structures` 可借用结构、`satisfaction_point` 爽点落点）。
- 若返回空串 → 跳过（无 `reference_research/` 树，不报错）。
- 若非空 → 作为参考输入在 Step 1B 注入 Context Agent 任务书，由 Context Agent 在产出 Creative Brief 时消化这些约束；不由 Stage 1A / ContextManager 自动加载。

**占位符扫描（prewrite）**：
- 写前必须跑一次 placeholder-scan，确认大纲/设定/章纲无 `[待...]` / `暂名` / `{占位}` 残留：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" placeholder-scan --format text

```

输出：
- "已就绪输入"与"缺失输入"清单；缺失则阻断并提示先补齐。

### 可信断点查询（best-effort，不阻断）

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" run-ledger write-resume --chapter {chapter_num} || true

```

要求：
- 仅作断点记录，不阻断写作；执行失败仅记 warning。
- `run-ledger write-resume` 落库在 `${PROJECT_ROOT}/.webnovel/run_ledger/`，由 ledger 续跑逻辑直接消费。
- 重复执行时由 ledger 提示用户选"沿用当前正文 / 重新起草 / 只查看状态"三态。
- 沿用当前正文：保留已写正文，续跑 Step 1 之后。
- 重新起草：丢弃当前正文，强制 Step 2A 重新生成。
- 只查看状态：仅报告断点，不进入写作流程。

断点续跑合同（必须按 ledger 真实断点裁决，不得用主流程口头代替）：
- **可信断点**：以 `${PROJECT_ROOT}/.webnovel/run_ledger/` 下最近一次 `write-resume` 记录为准；不存在则按"无断点"处理，直接进入 Step 1。
- **正文被手动改过**：如果章节正文的 `mtime` 晚于 ledger 最新 accepted 时间戳，判定为"手改"，必须询问用户是否覆盖；未确认前不得重写正文。
- **章纲更新晚于正文**：章纲文件 mtime > 章节正文 mtime 时，必须询问用户采用"以新章纲为准重写"还是"沿用现有正文"，未确认前不进入 Step 2A。
- **本章已 accepted**：若 ledger 标记 `accepted=true`，默认只跑 Step 6 备份与最终报告；不要重跑 Step 1-5。

约束：无论选哪条路径，**不得覆盖作者手改**——除非用户在该次会话中显式说"覆盖"。

### Step 0.5: Pre-Write Gate Check（oh-story 模式）

每次写章前, 跑 `evaluate_pre_write_gates`：

```python
from data_modules.chunked_write import evaluate_pre_write_gates
from data_modules.volume_state import VolumeStateManager

state = json.loads(open(".webnovel/state.json").read())
mgr = VolumeStateManager(state)
overdue = mgr.list_overdue_foreshadows(
    current_chapter=<next_chapter>,
    current_volume=<current_volume>,
)
issues = evaluate_pre_write_gates(
    chapter=<next_chapter>,
    current_volume=<current_volume>,
    overdue_foreshadows=overdue,
)
if issues:
    print("\n".join(issues))  # 伏笔超期是规划偏差提示，不阻断正文写作
```

伏笔超期和临近回收期仅作为规划建议。作者可以继续写作，并在后续调整计划；只有明确绑定到用户要求的硬约束、Canon 矛盾、必要工作流材料缺失或持久化完整性失败，才由对应 authority 阻断。

该检查是 advisory；不需要通过环境变量跳过。

### Step 0.6：Snapshot Checkpoint（oh-story 模式）

每写 N 章（默认 3）触发一次 snapshot checkpoint；用于强制回写 CHANGES + 状态校验。

```python
from data_modules.chunked_write import should_take_snapshot

if should_take_snapshot(chapter=next_ch, snapshot_every=3):
    print(f"Snapshot checkpoint at chapter {next_ch}")
    # 强制写 CHANGES + 状态校验（由 Step 4.5 + Step 5.4/5.6 联合覆盖）
```

默认 `snapshot_every=3`（参考 oh-story 模式），可通过 `ChunkedWritePolicy.snapshot_every` 调整；`WEBNOVEL_DISABLE_CHUNKED_SNAPSHOT=1` 可跳过本 checkpoint。

### Step 1：写前准备与 Native Writer Package 封口（Governed Context → Context Agent → Sealed Package）

写前阶段统一采用收敛后的 Native Writer Workflow，杜绝主流程手工重新拼装 Canon/Intent/Craft 或另造第二套 Writer prompt：

#### 1A. Runtime 预检与受治理上下文加载（Runtime prepare & Governed Context）
进入 Step 1 先跑闸门预检并获取事实治理上下文（Governed Context）：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" write-gate --chapter {chapter_num} --stage prewrite
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime prepare --chapter {chapter_num} --format json
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime governed-context --chapter {chapter_num} --format json
```

- `write-gate --stage prewrite` 校验大纲存在、章纲可用、占位符扫描通过、伏笔数据可读。任一 fail 立即阻断。
- `runtime prepare` 统一校验环境、大纲存在、章纲可用、Story System 合同与 prewrite 闸门状态。若有阻断项（blockers），立即停止并报告。
- `runtime governed-context` 由 `ContextManager.build_context()` 统一组装当前章的事实权威（Governed Canon、Current Intent、Master Setting/Craft 约束、Writer Context），杜绝向后剧透或虚假前情。

#### 1B. Context Agent 认知创作规划（Context Agent Creative Brief）

输入装配：
- **受治理上下文**：Stage 1A 的 `runtime governed-context`（Governed Canon、Current Intent、Master Setting/Craft 约束、Writer Context）。
- **非权威参考输入（Optional Craft / Reference Inputs）**（由主流程收集并作为参考/工艺输入传入 Context Agent，不由 ContextManager 自动加载）：
  1. **写作宪法**（若存在 `${PROJECT_ROOT}/.webnovel/writer-profile/写作宪法.md`）：作为作者风格底线与工艺约束（Craft input）提供给 Context Agent，严禁直接 L1 注入 Writer；由 Context Agent 在 Creative Brief 中落实其作者风格底线；
  2. **个人语料**（若存在 `${PROJECT_ROOT}/.webnovel/writer-profile/个人语料.md`）：提取 ≤ 200 字摘要，作为个人表达指纹参考注入；
  3. **对标研究（reference_research）**：
     调用 injector 工具读取对标输入：
     ```bash
     python3 ${SCRIPTS_DIR}/data_modules/reference_research_injector.py build-step1-summary --project-root "${PROJECT_ROOT}"
     python3 ${SCRIPTS_DIR}/data_modules/reference_research_injector.py build-step2a-section --project-root "${PROJECT_ROOT}"
     ```
     在注入 Context Agent 任务书时明确保留关键字段：
     - `do_not_copy`（红线禁区）
     - `canon_contamination_warnings`（设定污染警告）
     - `borrowable_structures`（可借用结构）
     - `satisfaction_point`（爽点落点）
     由 Context Agent 在产出 Creative Brief 时深度消化并落实为本章创作禁区与结构借鉴。

使用 Agent 调用 `webnovel-writer:context-agent`，参数：
- `chapter`
- `project_root`
- `storage_path=.webnovel/`
- `state_file=.webnovel/state.json`

按以下字面调用方式触发：
```
Use the Agent tool to run `webnovel-writer:context-agent`
```

硬要求：
- 若 `state` 或大纲不可用，立即阻断并返回缺失项。
- 写章链路隔离约束：本步使用 `webnovel-writer:context-agent`（写作任务书），与下游 `webnovel-writer:reviewer` / `webnovel-writer:data-agent` 通过 Agent 工具显式分隔；不得用主流程口头代替 subagent 输出。
- **保留 Context Agent 文学认知能力**：Context Agent 消费上述受治理上下文及参考输入，专注文学层面的创作决策：
  - 人物核心动机与心理走向；
  - 本章核心冲突、阻力与代价；
  - 章节节拍（Beats）与情节推进（CBN/CPNs/CEN）；
  - 情绪节奏与追读力设计；
  - 针对性写法与镜头指导。
- **产物**：返回真实五段写作任务书（Creative Brief）：
  1. 开篇委托（书名、章号、标题、一句话目标）
  2. 这章的故事（本章目标/阻力、情节节点、必须覆盖/禁区、跨章约束）
  3. 人物小动作（动机外化、微反应、心理处境）
  4. 本章阻力与代价（逆境设计、情绪底色、写法指导）
  5. 收在哪里（章末钩子、微兑现、定格画面）
- **硬边界**：Context Agent 专注于认知决策并输出写作任务书，不负责拼装底层系统/模型 Prompt，也不绕过 Native Writer Package 直接驱动起草。

#### 1C. Runtime 封口与唯一 Canonical Writer Prompt 生成（Seal Native Writer Package）
将 Context Agent 输出的真实写作任务书回传给 Runtime 进行签名封口，生成唯一 Canonical Writer Prompt：

```bash
# 将 Context Agent 输出的五段任务书作为参数传给 runtime attach-creative-brief
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime attach-creative-brief \
  --chapter {chapter_num} \
  --brief "{context_agent_creative_brief}" \
  --format prompt
```
（亦可将 brief 写入临时文件后使用 `--brief-file "${PROJECT_ROOT}/.webnovel/tmp/creative_brief_{chapter_padded}.txt"`）

- **封口保证**：Runtime 计算 `creative_brief_fingerprint` 与 `package_fingerprint`，将任务书与受治理事实永久绑定为 `is_writer_ready=True` 的 Sealed Native Writer Package。
- **唯一输入渲染**：命令附带 `--format prompt` 将直接调用 `WriterPackage.to_writer_prompt()` 输出完整的 Canonical Writer Prompt。未提供 Brief 时该命令严格 fail-closed。

输出：
- 唯一已封口的 Canonical Writer Prompt（包含 Story Identity、Current Intent、Governed Canon、Creative Brief、Constraints & Craft、Writer Context 六层治理内容及交付协议），直接作为 Step 2A 正文起草的输入。

### 一致性检查（写前）

写前必须通过一致性检查：

```bash
# PYTHONPATH 必须指向工具根（${CLAUDE_PLUGIN_ROOT}），使 cwd=PROJECT_ROOT 时仍能 import scripts.consistency
# 默认返回结构化评估；退出码 0 表示评估完成，1 表示执行/基础设施错误，2 表示输入无效。
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -c "
from scripts.consistency.cli import main
import sys
sys.exit(main(['check', '--project-root', '${PROJECT_ROOT}', '--chapter', '${chapter_num}']))
"
```

读取 JSON 的 `policy_action`：`ALLOW_WITH_ADVISORY` 记录建议后继续；`RECOVER` 先调用投影恢复 owner 修复派生视图并重跑；`REQUIRE_HUMAN` 暂停当前写作步骤并请用户裁决；`REJECT` 可停止当前写作步骤并报告硬问题。`REJECT` 不是章节拒绝，最终章节接受/拒绝只由 `ChapterCommitService` 决定。退出码 1/2 表示本次没有完整策略结论，修复执行或输入问题后重试，不得当作故事问题。

在使用旧评估结果作人工裁决、恢复或流程转换前，重新运行检查并比较 `source_input_fingerprint`；若改变，将旧结果保留为过期上下文，只按新结果行动。本阶段不保证跨进程持久化这些响应尝试。

### Step 2A：正文起草（Writer 消费 Canonical Writer Input）

#### 唯一输入契约（Zero Redundant Assembly）
- **唯一输入来源**：Writer 严格且仅消费 Step 1C 封口生成的 Canonical Writer Prompt（`WriterPackage.to_writer_prompt()` 输出）。
- **禁止事项**：
  - **严禁重新拼装**：Skill 主流程严禁自己重新拼一份 Canon、Intent 或 Craft 模板；
  - **严禁双重模板**：严禁在 Skill 内再造第二套与 External Host 差异化的 Writer prompt 模板；
  - **严禁绕过封口**：严禁绕过 Native Writer Package 直接把 Context Agent 未封口输出喂给 Writer。未获得带有 `package_fingerprint` 的封口包前不得启动起草；
  - **严禁死调用与私自追加（Zero Dead Injection）**：禁止在 Step 2A 进行任何 dead call / dead injection（严禁调用任何外部 injector 或提示词注入脚本；严禁向 Writer 重新追加任何零散 prompt 段）。个人语料与对标研究已在 Step 1B 经 Context Agent 消化进 Creative Brief 并密封于 Native Writer Package。

硬要求：
- **工作草稿隔离（Working Draft Isolation）**：起草只输出纯正文到工作草稿文件 `${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md`。
- **发布门禁后置（Publication Gate）**：**严禁在正式提交 accepted 前直接创建或覆盖正式 `正文/第{chapter_padded}章[-title].md` 文件**！正式正文文件的发布严格后置于 `runtime commit` accepted 之后。
- **登记草稿（Runtime Draft Ingestion）**：生成工作草稿后，必须立即调用 `runtime ingest-draft` 登记草稿并捕获 `draft_id` 与 `draft_fingerprint`：
  ```bash
  python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime ingest-draft \
    --package-fingerprint {package_fingerprint} \
    --draft-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
    --format json
  ```
  记录返回的 `draft_id` 与 `draft_fingerprint`。后续审查、润色重审、提炼、对账与最终提交均严格绑定此 `draft_id`。
- 默认按 2000-2500 字执行；若大纲为关键战斗章/高潮章/卷末章或用户明确指定，则按大纲/用户优先。
- 禁止占位符正文（如 `[TODO]`、`[待补充]`）。
- 保留承接关系：若上章有明确钩子，本章必须回应（可部分兑现）。

中文思维写作约束（硬规则）：
- **禁止"先英后中"**：不得先用英文工程化骨架（如 ABCDE 分段、Summary/Conclusion 框架）组织内容，再翻译成中文。
- **中文叙事单元优先**：以"动作、反应、代价、情绪、场景、关系位移"为基本叙事单元，不使用英文结构标签驱动正文生成。
- **禁止英文结论话术**：正文、审查说明、润色说明、变更摘要、最终报告中不得出现 Overall / PASS / FAIL / Summary / Conclusion 等英文结论标题。
- **英文仅限机器标识**：CLI flag（`--fast`）、checker id（`consistency-checker`）、DB 字段名（`anti_ai_force_check`）、JSON 键名等不可改的接口名保持英文，其余一律使用简体中文。

输出：
- 章节工作草稿 `${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md` 与对应的 `draft_id`（可进入 Step 2B 或 Step 3）。

### Step 2A 末尾追加：CHANGES 协议声明

Step 2A 生成工作草稿后，**必须在工作草稿末尾追加一个 `<chapter_changes>...</chapter_changes>` 块**，
包含本章对设定集/人物/物品/伏笔的所有结构化变更。

CHANGES 是 Writer 对变化的提案，不是已发生事实或 Canon。Step 2A 的块只是草稿；任何后续正文改写/润色完成后，必须按最终工作草稿正文重生成整个 CHANGES 块。不得把旧块直接沿用到最终正文。

字段定义见 `.claude/references/changes-protocol.md`。
示例见 `.claude/references/changes-examples.md`。

8 个顶级字段必须全部显式存在（即使无变化也要写 `[]` 或 `null`）。

### Step 2B：文风适配与候选门禁（Voice Candidate & Fact-Safe Validation；`--fast` / `--minimal` 跳过）

执行前加载：
```bash
cat "${SKILL_ROOT}/references/style-adapter.md"
```

职责与候选生成：
- 负责语调、句式呼吸感、人物台词差异化、叙事距离，锚定本作品 Positive Voice Target。
- 允许丰富局部文学质感、增加合理的场景环境细节，不破坏剧情事实、事件顺序、角色行为结果与已有设定。
- 严禁机械切碎句子、严禁套用固定三段式动作模板；保护不同角色的口吻差异。
- 生成文风候选稿并保存至临时路径：`${PROJECT_ROOT}/.webnovel/tmp/step2b_candidate_{chapter_padded}.md`。**严禁绕过门禁直接覆盖工作草稿或章节文件**。

门禁校验（必须执行）：
运行事实安全比对与质量门禁：
```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" prose validate \
  --before-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
  --after-file "${PROJECT_ROOT}/.webnovel/tmp/step2b_candidate_{chapter_padded}.md" \
  --chapter {chapter_num}
```

判定逻辑：
- `status == ACCEPTED`：文风调整通过，将候选正文覆盖回工作草稿 `${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md`。因为正文发生变更，重新生成 `<chapter_changes>` 块并重新调用 `runtime ingest-draft` 登记，获取更新后的 `draft_id` 与 `draft_fingerprint`。
- `status == UNCERTAIN` 且提示需要 Semantic Judge：若改动超出确定性检查覆盖（涉及知情状态/事件结果/因果/线索等），调用 Semantic Judge 并传入 `--judge-result '<json>'`（或 `--judge-file`）重验；若未配置或执行失败，严格遵循 fail-closed 保持 `ROLLEDBACK`。
- `status == ROLLEDBACK`：检测到事实漂移、新增未授权履历/设定或质量退化，**自动保留 Step 2A Draft 原稿**，记录回退审计信息。

输出：
- 文风适配后工作草稿（通过则覆盖，未通过则保持 Step 2A 原工作草稿）及当前有效 `draft_id`。

### Step 3：审查（auto 路由，必须由 Agent 子代理执行）

调用约束：
- 必须用 `Agent` 工具按注册名 `webnovel-writer:reviewer` 调用审查 subagent：
  ```
  Use the Agent tool to run `webnovel-writer:reviewer`
  ```
- 审查对象为当前工作草稿 `${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md`，审查结果严格绑定当前的 `draft_id` 与 `draft_fingerprint`。
- 禁止主流程伪造审查结论。
- 可并行发起审查，统一汇总 `issues/severity/overall_score`。
- 默认使用 `auto` 路由：根据"本章执行合同 + 正文信号 + 大纲标签"动态选择审查器。

核心审查器（始终执行）：
- `consistency-checker`
- `continuity-checker`
- `ooc-checker`

条件审查器（`auto` 命中时执行）：
- `reader-pull-checker`
- `high-point-checker`
- `pacing-checker`

模式说明：
- 标准/`--fast`：核心 3 个 + auto 命中的条件审查器
- `--minimal`：只跑核心 3 个（忽略条件审查器）

审查指标落库（必做）：
```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" index save-review-metrics --data "@${PROJECT_ROOT}/.webnovel/tmp/review_metrics.json"

```

落库走 `review-pipeline --save-metrics`（与 webnovel-review 共用同一落库命令）：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" review-pipeline --save-metrics \
  --results "${PROJECT_ROOT}/.webnovel/tmp/review_results.json"

```

review_metrics 字段约束（当前工作流约定只传以下字段）：
```json
{
  "start_chapter": 100,
  "end_chapter": 100,
  "overall_score": 85.0,
  "dimension_scores": {"爽点密度": 8.5, "设定一致性": 8.0, "节奏控制": 7.8, "人物塑造": 8.2, "连贯性": 9.0, "追读力": 8.7},
  "severity_counts": {"critical": 0, "high": 1, "medium": 2, "low": 0},
  "critical_issues": ["问题描述"],
  "report_file": "审查报告/第100-100章审查报告.md",
  "notes": "单个字符串；selected_checkers / timeline_gate / anti_ai_force_check 等扩展信息压成单行文本写入此字段"
}

```
- `notes` 在当前执行契约中必须是单个字符串，不得传入对象或数组。
- 当前工作流不额外传入其它顶层字段；脚本侧未在此处做新增硬校验。

硬要求：
- `--minimal` 也必须产出 `overall_score`。
- 未落库 `review_metrics` 不得进入 Step 5。

### Step 4：定向安全润色与回滚门禁（Targeted Fact-Safe Editing）

执行前必须加载：
```bash
cat "${SKILL_ROOT}/references/polish-guide.md"
cat "${SKILL_ROOT}/references/writing/typesetting.md"
```

执行原则（先诊断再修改，定向小修优先）：
1. **先诊断**：运行 `python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" prose diagnose --file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md"`，列出真实病灶，不得无病呻吟或整篇机械改写。
2. **定向生成候选**：针对审查意见与诊断项生成润色候选稿（Targeted Edit Candidate），保存至 `${PROJECT_ROOT}/.webnovel/tmp/step4_candidate_{chapter_padded}.md`。严禁为了修补逻辑漏洞或增加合理性而私自发明履历、设定、翻转所有权或颠倒意图。
3. **事实与退化校验**：运行：
```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" prose validate \
  --before-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
  --after-file "${PROJECT_ROOT}/.webnovel/tmp/step4_candidate_{chapter_padded}.md" \
  --chapter {chapter_num}
```
   - 检查语义事实差异（`diff-semantic`）：禁止新增未授权履历/故意行为转变/所有权翻转/规则极性颠倒。
   - 检查质量退化（字数缩水率 > 20%、电报式断句率飙升）。
4. **决策判定与失效重审规则（Targeted Polish Invalidation Rule）**：
   - 若 `status == ROLLEDBACK` 或正文未发生改变：自动保持润色前工作草稿（即 Step 3 审查版本），沿用原 `draft_id` 与原审查结论，记录回退原因与审计记录。
   - 若 `status == UNCERTAIN` 且提示需要 Semantic Judge：若候选修改超出确定性覆盖范围，调用 Semantic Judge 并传入 `--judge-result '<json>'`（或 `--judge-file`）重验；若 Judge 未配置或失败，严格遵循 fail-closed 保持回滚。
   - 若 `status == ACCEPTED` 且正文发生改变：
     1. 将候选正文覆盖回工作草稿 `${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md`；
     2. 依据新正文刷新工作草稿末尾的 `<chapter_changes>` 块；
     3. 重新调用 `runtime ingest-draft`：
        ```bash
        python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime ingest-draft \
          --package-fingerprint {package_fingerprint} \
          --draft-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
          --format json
        ```
        获取全新的 `draft_id` 与 `draft_fingerprint`；
     4. **旧草稿的审查结果彻底失效**：严禁沿用旧 `draft_id` 对应的 review_results；
     5. 重新调用 `webnovel-writer:reviewer` 对新草稿进行完整审查，产出与新 `draft_id` 绑定的全新 `review_results.json`，并调用 `review-pipeline --save-metrics` 刷新 metrics；
     6. 只有完成新草稿审查并绑定新 `draft_id` 后，方可进入 Step 4.5。

输出：
- 最终工作草稿（通过则为润色正文，回退则为原工作草稿）
- 当前有效的最新 `draft_id` 与对应的审查结果
- 编辑与校验审计记录（包含 diagnosis, edit_plan, diff_result, decision）

### Step 4.5：刷新 ProposedChanges 并校验协议

Step 4 润色及所有 rewrite 完成后，依据此时的最终正文重新生成完整 `<chapter_changes>` 块，然后运行本节 changes_gate。它只校验 ProposedChanges 的 schema、协议和原有账本完整性；它不裁决事实，不与 Data Agent extraction 做语义对账。

执行命令：

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/changes_gate.py \
    --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
    --db .webnovel/index.db \
    --json

```

**判定逻辑**：
- `passed=true`：进入 Step 5（data-agent）。
- `passed=false`：读取 `failures` 列表，把每条规则的报错反馈给主流程 LLM，要求**只重写 `<chapter_changes>` 块**（不改正文）。最多 2 次。
- 2 次仍未通过：记录到 `.webnovel/tmp/changes_gate_failures.jsonl`，人工介入后由 ledger 续跑接管。

**调 changes_gate.py R4b**（advisory 子规则，不阻塞）：
- `changes_gate.py` 默认 `--json` 已启用 `R4b`（伏笔超期 advisory），阈值 20 章。
- 输出 `severity=advisory` 的 failures **不阻塞门禁**（`passed` 仍为 `true`），但需记录到 `.webnovel/tmp/r4b_advisories.jsonl`，作为下一章的"必须考虑回收"信号。
- R4b advisory 仅提示，不要求本章立即修复——避免和创作节奏冲突。

### Step 4.6：anti-slop 扫描

并行执行两个扫描器：

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/text_humanizer.py \
    detect --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md"

node ${CLAUDE_PLUGIN_ROOT}/scripts/check-ai-patterns.js \
    --check --json --fail-on=blocking \
    "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" || true

```

**判定逻辑**：
- 这两个 scanner 的 `blocking` / `high` 是 detector 的分类，不是架构 gate authority；scanner finding 一律作为 Craft/style advisory 展示。
- 作者可选择安全、局部、非语义的 cleanup；不得强制退回 Step 4、整章重写或要求先清零 finding。
- 未处理的 Craft/style scanner finding 不阻止 Step 5。只有 exact stable explicit user-bound style prohibition 可经现有 shared hard-constraint policy 产生硬 action。
- `check-ai-patterns.js` 对 detector-level `blocking` 可能返回非零；`|| true` 保留输出并避免把该分类误作 workflow veto。输入/执行错误仍需先排查。

可选关闭：在命令前加 `--skip-deslop`。

**anti-slop 双引擎仲裁规则**（解决同一处文本被两边各报一次的 conflict resolution）：

两个扫描器对同一章可能给出重叠但不一致的判定（例如"仿佛"在 `text_humanizer.py` 报"AI 高频词"frequency-based，在 `check-ai-patterns.js` 报"套词密度 tic"density-based）。仲裁规则如下：

1. **frequency-based finding 优先于 density-based finding**。`text_humanizer.py` 给的是绝对命中次数 + 每千字密度，证据链更精确；`check-ai-patterns.js` 的密度 tic 只是阈值告警（min_hits + per_kilo 双门槛），可能把零散的合规用法一并扫进去。冲突时以 `text_humanizer.py` 的命中次数 + 原文上下文为准决定是否改稿。
2. **所有 scanner 命中默认都是 advisory**，包括 detector 标为 `critical` / `blocking` 的结果；不据此触发整章重写。
3. 作者可忽略、记录，或选择做最小局部 cleanup；聚集命中可以作为作者考虑的信号，不构成必须改稿的阈值。
5. **工具彼此各管一段**：density-only finding（`check-ai-patterns.js` 独有，如 long-paragraph / period-stutter / micro-action-tic / action-list-tic / quote-emphasis-tic）和 frequency-only finding（`text_humanizer.py` 独有，如意义膨胀 / 论文式段落结构 / 排比三连）互不覆盖，重叠时按规则 1 仲裁。
6. **人工最终裁决**：两个工具都是启发式，按 1-5 处理后作者应扫一眼原文 sanity check，再决定是改稿还是放过。不允许"两工具都没报就一定安全"——双盲区是已知 gap。

执行建议：合并两种 scanner 的位置、证据与建议，按规则 1 去重；将结果作为 advisory 呈现，由作者决定是否局部处理。只有 shared hard-constraint policy 验证通过的明确用户禁令可以阻断。

**重要前提**：
1. **两个工具都假定输入是 UTF-8 文本**。对 binary / GBK / UTF-16 / 截断 UTF-8 输入，
   `text_humanizer.py detect` 会把字节当字符处理并输出 `ok: true`（已知限制，
   工具是外部的，未在 fork 中修复）。若章节文件 > 50KB，应先确认编码。
2. **anti-slop 是启发式，不是合同**。两个工具的判定可能不一致（humanizer 对
   long-paragraph 不报警，check-ai-patterns 对 binary 会报警）。blocking 项
   都需要人工 review 一次，再决定是改稿还是放过。

### Step 4.6.5：提交前只读 git diff 变更面校验

提交前（Step 5 之前）必须执行只读 git diff 变更面校验，**不得直接调用 git add（裸 add 命令）**：

```bash
git -c color.ui=never diff --name-status HEAD
git -c color.ui=never diff --check HEAD

```

要求：
- `diff --name-status`：列出本次变更文件清单，校验预期文件（章节正文 + data artifacts + summary）都已包含；缺失则阻断。
- `diff --check`：检测空白错误（trailing whitespace / indent-with-tab / no-newline-at-eof）与冲突标记（<<<<<<< / ======= / >>>>>>>）；命中冲突标记直接阻断，未通过空白检查记 warning。
- 此步只读 git，不做任何 `add` / `commit`；提交动作由 Step 6 的 `webnovel.py ... backup` 唯一完成。

### Step 4.7：write-gate precommit 检查

提交前再跑一道闸门（Step 5 之前必跑）：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" write-gate --chapter {chapter_num} --stage precommit

```

闸门会检查项目/章节是否具备提交条件，并验证必需 review、fulfillment、disambiguation、extraction artifacts 的存在与 schema。此命令不会把 anti-slop detector 的 exit code 当成硬 gate；Craft/style finding 也不能单独阻止 Step 5。必需产物损坏或缺失、尚未解决的人类决策、以及 shared policy / ChapterCommitService 验证出的真实 Canon、用户约束或 integrity 问题仍按各自既有规则处理。

### 一致性 apply（写后）

写后 commit 时触发一致性 apply（更新 state + 派生视图）：

```bash
# PYTHONPATH 必须指向工具根（${CLAUDE_PLUGIN_ROOT}），使 cwd=PROJECT_ROOT 时仍能 import scripts.consistency
# apply 输出逐 patch outcomes；退出码 0 表示全部适用操作成功，1 表示部分失败，2 表示输入无效。
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -c "
from scripts.consistency.cli import main
import sys
sys.exit(main(['apply', '--project-root', '${PROJECT_ROOT}', '--chapter', '${chapter_num}']))
"
```

检查每个 patch 的 outcome；出现 `failed` 时按结果中的错误类型修复并重试。apply 的失败属于执行/投影维护问题，应按错误类型修复，不改变一致性 finding 的 policy action，也不代替 `ChapterCommitService` 的章节提交判断。

### Step 5：Data Agent + reconciliation + runtime commit / chapter-commit 提交（事实回写主链）

使用 Agent 调用 `webnovel-writer:data-agent`，参数：
- `chapter`
- 先运行 `prepare_data_agent_input.py`，把实际最终章节工作草稿拆成 prose-only 文件与独立 ProposedChanges JSON；Data Agent 的 `chapter_file` 必须指向 prose-only 文件，绝不传原始章节工作草稿。
- 工作草稿 `${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md` 对应的提取产物与 proposal JSON 必须一致。
- `review_score=Step 3 overall_score`
- `project_root`
- `storage_path=.webnovel/`
- `state_file=.webnovel/state.json`

按以下字面调用方式触发：
```
Use the Agent tool to run `webnovel-writer:data-agent`
```

生成隔离输入并调用 Data Agent：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prepare_data_agent_input.py" \
  --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
  --prose-output "${PROJECT_ROOT}/.webnovel/tmp/data_agent_prose.md" \
  --changes-output "${PROJECT_ROOT}/.webnovel/tmp/proposed_changes.json"
```

Data Agent 只收到 `.webnovel/tmp/data_agent_prose.md` 路径。正文改动后必须重新拆分并重新提取；Proposal 单独保存在 `.webnovel/tmp/proposed_changes.json`，不会混入观察输入。Data Agent 只生成临时提取产物，不直接写入事实或状态投影。完成提取后执行 reconciliation：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reconcile_changes.py" \
  --chapter-file "${PROJECT_ROOT}/.webnovel/tmp/chapter_{chapter_padded}_working.md" \
  --extraction-result "${PROJECT_ROOT}/.webnovel/tmp/extraction_result.json" \
  --db "${PROJECT_ROOT}/.webnovel/index.db" \
  --output "${PROJECT_ROOT}/.webnovel/tmp/reconciliation_result.json"
```

`status=conflict` 阻断 commit；任何 CHANGES/extraction schema 错误或 changes_gate 未通过时不得生成 reconciliation。`proposed_not_observed` 不进入 Canon，默认作为 advisory；`unproposed_observed` 保留为正文观察并可进入 accepted payload。提交必须同时接收 `.webnovel/tmp/reconciliation_result.json` 并绑定当前 `draft_id`；哈希不匹配、结果缺失或未通过均 fail-fast。

提取产物与 reconciliation 结果由 `runtime commit` / `chapter-commit` 校验、提交，并驱动后续投影。Data Agent 默认子步骤：
- A. 加载上下文
- B. AI 实体提取
- C. 实体消歧
- D. 生成实体与状态变化提取产物
- E. 生成章节摘要提取产物
- F. 生成场景切片提取产物

`chapter-commit` 的 projection writers 从 durable commit 刷新状态、索引、摘要、记忆和向量查询数据。风格样本提取是单独的 Craft 操作，不属于 Canon 提交或其成功条件；债务利息默认跳过。

Step 5 失败隔离规则：
- 若 A-F 产物生成失败：仅重跑 Step 5，不回滚已通过的 Step 1-4。
- 若 chapter-commit 已成功但任一 projection 失败：只从 durable commit 执行 `runtime retry-projection --chapter {chapter_num}`（或 `projections retry --chapter {chapter_num}`），不重跑提取或整个写作链。
- 风格样本等 Craft 操作失败不改变 Canon commit 状态。

执行后检查（最小白名单）：
- `.webnovel/state.json`
- `.webnovel/index.db`
- `.webnovel/summaries/ch{chapter_padded}.md`
- `.webnovel/observability/data_agent_timing.jsonl`（观测日志）

性能要求：
- 读取 timing 日志最近一条；
- 当 `TOTAL > 30000ms` 时，输出最慢 2-3 个环节与原因说明。

观测日志说明：
- `call_trace.jsonl`：外层流程调用链（agent 启动、排队、环境探测等系统开销）。
- `data_agent_timing.jsonl`：Data Agent 内部各子步骤耗时。
- 当外层总耗时远大于内层 timing 之和时，默认先归因为 agent 启动与环境探测开销，不误判为正文或数据处理慢。

#### Step 5.4：story-system 章级运行时合同刷新（commit 之前执行）

`runtime commit` / `chapter-commit` 提交前必须用真实 `CHAPTER_GOAL` 刷新 `.story-system/` 运行时合同；query 实参必须是 `${CHAPTER_GOAL}` 变量，**禁止**把 `{章纲目标}` / `第N章章纲目标` 这类占位文本作为 story-system 命令的 positional 实参：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" story-system "${CHAPTER_GOAL}" \
  --genre "${GENRE}" --chapter {chapter_num} --persist --emit-runtime-contracts --format both

```

约束：
- `--persist` + `--emit-runtime-contracts` + `--chapter` 三项开关必须同时存在；缺一即视为章级合同未刷新。
- 占位 query 禁止文本：`{章纲目标}` / `第N章章纲目标` 仅作"禁用示例"出现，不得作为命令实参。
- 失败兜底：retry 一次；仍失败则停止本次提交调用并报告提交失败，之后由 `ChapterCommitService` 按其既有契约处理。

#### Step 5.5：runtime commit 事实提交与 publish-draft 正文发布（本章主链真源）

`chapter-commit` / `CHAPTER_COMMIT` 是本章写作事实的唯一 Canon 提交权威，**取代旧的 state 流程（process-chapter / 同步落库链路）**。收敛架构下，主流程分为两个独立而精确契合的阶段：首先执行事实提交（Canon Acceptance），提交 accepted 后显式发布正文草稿（Publication Gate）。

##### 5.5A. 事实提交（Runtime Commit）

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

> 协议说明：`runtime commit` 底层委托 `ChapterCommitService` 执行唯一的 canonical commit，在 `.story-system/commits/chapter_{NNN}.commit.json` 落库，并刷新 `.story-system/` 下 contracts。命令行亦保留等价直接入口 `chapter-commit`。

Story System canonical mode 下，禁止用 `StateManager.process_chapter_result`、`IndexManager.process_chapter_data`、`SQLStateManager.process_chapter_entities` 或 `update_state` 的章节事实参数旁路写入；审查 checkpoint 等 workflow metadata 与规划配置仍可由各自入口维护。章节 commit 必须按递增章号执行；旧章 projection retry 若会倒退 state 会失败，历史全量 rebuild 属于 migration 流程。

`chapter-commit` 拒收（`chapter-commit rejected`）时：
- 最终状态不得写“已完成”。
- 严禁调用 `publish-draft`，严禁向 `正文/` 目录写正文！
- 立即进入最终报告"必须处理"段，输出 reject 原因 + 重提命令。
- 不重跑 Step 1-4，只重跑 Step 5.5 提交。

##### 5.5B. 正文发布门禁（Publication Gate）

检查 5.5A 返回的 `chapter_outcome`。仅当 `chapter_outcome == "accepted"` 时，显式执行 `runtime publish-draft`：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime publish-draft \
  --chapter {chapter_num} \
  --draft-id {draft_id} \
  --format json
```

**发布安全保证（Exact Accepted Draft 绑定）**：
- **Exact SHA 校验**：`publish_accepted_draft` 强制校验待发布草稿的 SHA-256 与 durable commit 中的 `provenance.reconciliation_chapter_sha256` 完全一致；任何未被该 commit 接受的草稿（例如 commit 后新生成的 draft B）均被严格拒绝（`ACCEPTED_DRAFT_MISMATCH`），杜绝非 accepted 草稿冒充发布到正式 `正文/`。
- **显式草稿 ID**：必须显式传入 `--draft-id {draft_id}`，严禁猜测或退回 active draft。
- **发布失败隔离**：若 publication 失败，明确报告“Canon 已 accepted，但正式正文尚未发布”并提示重试发布命令；绝不重跑起草（Writer）、审查（Reviewer）或数据提炼（Data Agent）。

#### Step 5.6：postcommit projection 五项验证与重试

`chapter-commit` 先持久化 canonical commit，再运行 projection。投影状态写入 `.webnovel/projection_log.jsonl`，不写入 canonical commit。缺失或失败的投影可由 durable commit 重建。验证 5 项 projection：`state/index/summary/memory/vector`。失败唯一兜底是 `runtime retry-projection --chapter {chapter_num}` 或 `projections retry --chapter {chapter_num}`（从已提交事实重建投影，不得重跑提取或整个写作链）：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" runtime retry-projection --chapter {chapter_num}
# 或字面调用：
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" projections retry --chapter {chapter_num}

```

projection retry 失败仍不算"已完成"，进入最终报告"必须处理"段。

#### Step 5.7：write-gate postcommit 最终闸门

Step 5.6 通过后跑最后一道闸门：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" write-gate --chapter {chapter_num} --stage postcommit

```

闸门校验：chapter-commit + projection 五项 + placeholder-scan 全通过；任一 fail 进入最终报告"必须处理"段。

债务利息：
- 默认关闭，仅在用户明确要求或开启追踪时执行。

### Step 6：项目根备份（可失败但需说明）

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" backup

```

> 等价 shell（解释版）：`webnovel.py --project-root "${PROJECT_ROOT}" backup` 由脚本统一处理 git add / commit / tag；本流程不直接调用裸 git add。

规则：
- 提交时机：write-gate postcommit、projection 五项验证、清理全部完成后最后执行。
- 提交信息默认中文，格式：`第{chapter_num}章: {title}`（由 backup 子命令拼装）。
- 若 backup 失败，必须给出失败原因与未提交文件范围。
- **禁止裸 `git add`（无 diff 校验的批量 add）**：变更面必须先经 Step 4.6.5 的 `diff --name-status` / `diff --check` 校验。

> 术语：`chapter-commit` / `CHAPTER_COMMIT`（同义；CLI 用 `chapter-commit`，数据流文档中用 `CHAPTER_COMMIT`）是本章写作事实的提交入口，是 `.story-system/commits/chapter_{NNN}.commit.json` 的唯一生产者。

## 写章过程节点（最多 6 个）

主流程必须把"写一章"压缩成下列 6 个作者可理解的阶段，每步用作者语言提示，不再混入工程术语：

1. 检查项目环境
2. 整理写作依据
3. 起草正文
4. 写作检查
5. 保存本章故事事实
6. 提交备份

执行时按顺序推进；每个阶段给作者两行进度提示 + 落 `run-log` 日志，不直接输出原始 JSON。

## 充分性闸门（必须通过）

未满足以下条件前，不得结束流程：

1. 章节正文文件存在且非空：`正文/第{chapter_padded}章-{title_safe}.md` 或 `正文/第{chapter_padded}章.md`
2. Step 3 已产出 `overall_score` 且 `review_metrics` 成功落库
3. Step 4 已处理全部 `critical`，`high` 未修项有 deviation 记录
4. Step 4 的 `anti_ai_force_check=pass`（基于全文检查；fail 时不得进入 Step 5）
5. Step 5.6 已确认本次 accepted commit 对应的 state/index/summary/memory/vector 投影全部成功，或 `projections retry` 已成功；仍缺失或过期的投影必须保持为可见失败。
6. 若开启性能观测，已读取最新 timing 记录并输出结论

## 验证与交付

执行检查：

```bash
test -f "${PROJECT_ROOT}/.webnovel/state.json"
test -f "${PROJECT_ROOT}/正文/第${chapter_padded}章.md"
test -f "${PROJECT_ROOT}/.webnovel/summaries/ch${chapter_padded}.md"
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" index get-recent-review-metrics --limit 1
tail -n 1 "${PROJECT_ROOT}/.webnovel/observability/data_agent_timing.jsonl" || true

```

成功标准：
- 章节文件、摘要文件、状态文件齐全且内容可读。
- 审查分数可追溯，`overall_score` 与 Step 5 输入一致。
- 润色后未破坏大纲与设定约束。

### 状态产物所有权（chapter-commit 与 projection writers）

主流程对 reviewer JSON 的落盘语义：reviewer 通过 Agent tool 返回结构化 JSON，主流程落盘到 `.webnovel/tmp/review_results.json`（review-pipeline 后续接续）。主流程不直接重写该文件。

其余状态产物（state/index/summaries/memory/vectors）的所有权约束：

- Data Agent 只生成临时提取产物，不写这些持久化产物。
- `chapter-commit` 先写 `.story-system/commits/chapter_{NNN}.commit.json`，随后 projection writers 从该提交写入投影。
- 主流程只检查文件存在与 schema，不直接写 state/index/summaries/memory/vectors。
- 写入路径约定：
  - `state.json`、`index.db`、章节事件 JSON、summaries、memory、vectors → projection writers 写入；投影可由 durable chapter commit 重试重建
  - projection 执行状态 → `.webnovel/projection_log.jsonl`
- 临时提取产物所有权凭证：`.webnovel/tmp/subagent_runs/write-data-agent.jsonl`

## 失败处理（最小回滚）

触发条件：
- 章节文件缺失或空文件；
- 审查结果未落库；
- Data Agent 关键产物缺失；
- 润色引入设定冲突。

恢复流程：
1. 仅重跑失败步骤，不回滚已通过步骤。
2. 常见最小修复：
   - 审查缺失：只重跑 Step 3 并落库；
   - 润色失真：恢复 Step 2A 输出并重做 Step 4；
   - 摘要/状态缺失：只重跑 Step 5；
3. 重新执行"验证与交付"全部检查，通过后结束。

## 作者友好最终报告契约

最终回复必须面向作者，不输出原始 JSON、traceback 或长命令日志。使用固定三段式，并以一句总状态开头：

```text
总状态：已完成 / 部分完成 / 需要你处理 / 未完成。

一、产生的文件与完成情况
- ...

二、过程中遇到的问题与异常耗时
- 已自动处理：...
- 建议确认：...
- 必须处理：...

三、下一步建议
- ...

```

必须汇报：
- `正文文件路径`（`正文/第{NNN}章-章名.md`、`正文/第{NNN}章-{slug}.md`）是否落盘。
- `审查报告路径`（`审查报告/第{NNN}章审查报告.md` 或对应 range 报告）。
- `.webnovel/tmp/{context, draft, polish, review_results, fulfillment_result, disambiguation_result, extraction_result}.json` 是否齐全：
  - `.webnovel/tmp/review_results.json`
  - `.webnovel/tmp/fulfillment_result.json`
  - `.webnovel/tmp/disambiguation_result.json`
  - `.webnovel/tmp/extraction_result.json`
- `.story-system/commits/chapter_{NNN}.commit.json` 是否落盘（若被拒 `chapter-commit rejected` 则不算"已完成"）。
- `state / index / summary / memory / vector 更新状态`（5 项 projection 是否全部成功；任一失败必须报告）。
- `备份状态`、`是否可以继续写下一章`。
- 模式（默认 / `--fast` / `--minimal`）是否按约定跳过 2B / 减少审查器。

异常分类：
- 已自动处理：自动重跑失败 batch、自动重做 anti-slop 扫描、自动重投影合同、自动重写 data artifacts、`projections retry` 自动跑通。
- 建议确认：人物小传细节、微世界观表述、节拍微调、伏笔登记需要作者看一眼。
- 必须处理：`chapter-commit rejected`、projection retry 仍失败、写作前置条件未完成、关键产物缺失。

下一步建议必须使用任务化语言 + 可复制命令，例如：

```text
- 继续写下一章：
  /webnovel-write {NNN+1}

- 如需快车道（跳过 reviewer/polish）：
  /webnovel-fast-write {NNN+1}

- 如需最少链路（仅 draft + commit）：
  /webnovel-write {NNN+1} --minimal

- 投影失败时：
  webnovel.py --project-root "${PROJECT_ROOT}" projections retry --chapter {NNN}

```

最终状态不得写“已完成”，除非所有产物落盘 + tests 跑通；任一产物缺失、projection 失败、`chapter-commit rejected` 都只能写"部分完成 / 需要你处理"。

最终状态不得写“已完成”（再次强约束；已在前一句声明，此处复述确保测试断言命中）。

不写 token 统计；如需排查故障，只给日志路径或建议运行 `/webnovel-doctor`。

## SubagentRun 可汇总信号

主流程对每个 subagent 调用必须记录一次 `SubagentRun` JSON（按调用顺序逐行写入）：

```json
{"name": "context-agent", "status": "completed | partial | failed | skipped", "problems": [], "auto_handled": [], "needs_user_action": false, "duration_ms": 0, "outputs": []}
{"name": "reviewer", "status": "completed | partial | failed | skipped", "problems": [], "auto_handled": [], "needs_user_action": false, "duration_ms": 0, "outputs": []}
{"name": "data-agent", "status": "completed | partial | failed | skipped", "problems": [], "auto_handled": [], "needs_user_action": false, "duration_ms": 0, "outputs": []}
```

写入路径：`.webnovel/tmp/subagent_runs/write-{chapter}.jsonl`（每行一个 SubagentRun）。

主流程"汇总 Step N 已确认的 subagent 输出"并把它整合到下一步输入。

## 作者友好过程提示与恢复契约

写章开始前先说明本次会经历：解项目根 -> 准备写作依据 -> 起草正文 -> 写作检查 -> 保存本章事实 -> 提交备份。过程提示用作者语言，不直接输出原始 JSON、traceback 或长命令日志；技术详情写入 `.webnovel/logs/run_last.log`：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" run-log \
  --event write-progress \
  --payload-json "{\"stage\": \"write\", \"chapter\": {N}}" \
  --format text

```

过程提示每次不超过两行，只说当前动作和影响，例如"正在写检查：会按设定/伏笔/节奏逐维度过一遍本章正文"。少打扰确认策略：默认继续推进；只有正文被手动改过、章纲更新晚于正文、本章已 accepted、需要覆盖 run-ledger 已记录的 step 时才询问。

需要用户裁决时使用有限选项，并说明影响；例如沿用当前正文 / 重新起草 / 只查看状态。卡住时必须说明卡点、已完成内容和恢复建议，例如"起草与审查已保留，提交备份失败；重新运行 `/webnovel-write {N}` 会只重做提交与归档"。

不可恢复故障才在最终报告提示 `.webnovel/logs/run_last.log`；平时只保留日志，不打扰作者。收尾必须调用作者报告 helper：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" user-report \
  --stage write \
  --chapter {N} \
  --format text

```
