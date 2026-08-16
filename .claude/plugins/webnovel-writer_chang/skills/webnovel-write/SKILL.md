---
name: webnovel-write
description: Writes webnovel chapters (default 2000-2500 words). Use when the user asks to write a chapter or runs /webnovel-write. Runs context, drafting, review, polish, and data extraction.
allowed-tools: Read Write Edit Grep Bash
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
  - 用途：Step 2A 写作硬约束（大纲即法律 / 设定即物理 / 发明需识别）。
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
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-${PWD}}"
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
- 输出（活跃伏笔 + 超期伏笔）追加到 Step 1 任务书的"活跃伏笔"section，作为本章写作的"必承接"约束。
- 工具执行失败（exit code != 0）只记录警告，不阻断——best-effort。

**个人语料检测**（best-effort，不阻断；Phase E 重定位）：
- 检测 `${PROJECT_ROOT}/.webnovel/writer-profile/个人语料.md` 是否存在（Phase E 起基线目录迁到 `${CLAUDE_PLUGIN_ROOT}/templates/`，书项目副本目录改为 `.webnovel/writer-profile/`）。
- 存在 → 在 Step 1 任务书与 Step 2A 写作执行包中追加一段"个人表达指纹约束"（≤ 200 字摘要），作为可选 L1 prompt 注入；不替代题材/大纲/设定硬约束
- 不存在 → 跳过，不报错

**写作宪法加载**（best-effort，不阻断；Phase E 重定位）：
- 优先检测 `${PROJECT_ROOT}/.webnovel/writer-profile/写作宪法.md`（由 init 从 `${CLAUDE_PLUGIN_ROOT}/templates/写作宪法.md` 复制）。
- 存在 → 作为 L1 prompt 注入的一部分（作者风格底线，硬约束）。
- 不存在 → 跳过，不报错（不再回退到 skill 内 templates/）。

**对标参考检测（reference_research）**：
- 调用 `python3 ${SCRIPTS_DIR}/data_modules/reference_research_injector.py build-step1-summary --project-root "${PROJECT_ROOT}"`，得到 ≤ 800 chars (~1200 CJK tokens) 摘要字符串
- 若返回空串 → 跳过（无 `reference_research/` 树，不报错）
- 若非空 → 摘要拼接到 context-agent 任务书的"对标参考"段

输出：
- "已就绪输入"与"缺失输入"清单；缺失则阻断并提示先补齐。

### Step 0.5：写入断点（best-effort，不阻断）

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" run-ledger write-resume --chapter {chapter_num} || true

```

要求：
- 仅作断点记录，不阻断写作；执行失败仅记 warning。
- `run-ledger write-resume` 落库在 `${PROJECT_ROOT}/.webnovel/run_ledger/`，由 ledger 续跑逻辑直接消费。
- 重复执行时由 ledger 提示用户选"沿用/重写/查看"三态。

### Step 1：Context Agent（内置 Context Contract，生成直写执行包）

使用 Agent 调用 `context-agent`，参数：
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
- 输出必须同时包含：
  - 7 板块任务书（目标/冲突/承接/角色/场景约束/伏笔/追读力）；
  - Context Contract 全字段（目标/阻力/代价/本章变化/未闭合问题/开头类型/情绪节奏/信息密度/过渡章判定/追读力设计）；
  - Step 2A 可直接消费的"写作执行包"（章节节拍、不可变事实清单、禁止事项、终检清单）。
- 合同与任务书出现冲突时，以"大纲与设定约束更严格者"为准。

输出：
- 单一"创作执行包"（任务书 + Context Contract + 直写提示词），供 Step 2A 直接消费，不再拆分独立 Step 1.5。

### Step 2A：正文起草

执行前必须加载：

调用 `python3 ${SCRIPTS_DIR}/data_modules/reference_research_injector.py build-step2a-section --project-root "${PROJECT_ROOT}"`，
若非空 → 把"对标书红黑名单"段（必读，含 do_not_copy / canon_contamination_warnings / borrowable_structures / satisfaction_point）追加到章节起草提示词的"约束"段，作为 L1 注入。
主流程**不口头重写或简化**该段；原样作为约束素材传下去。
若返回空串 → 跳过此注入。

```bash
cat "${SKILL_ROOT}/../../references/shared/core-constraints.md"

```

硬要求：
- 只输出纯正文到章节正文文件；若详细大纲已有章节名，优先使用 `正文/第{chapter_padded}章-{title_safe}.md`，否则回退为 `正文/第{chapter_padded}章.md`。
- 默认按 2000-2500 字执行；若大纲为关键战斗章/高潮章/卷末章或用户明确指定，则按大纲/用户优先。
- 禁止占位符正文（如 `[TODO]`、`[待补充]`）。
- 保留承接关系：若上章有明确钩子，本章必须回应（可部分兑现）。

中文思维写作约束（硬规则）：
- **禁止"先英后中"**：不得先用英文工程化骨架（如 ABCDE 分段、Summary/Conclusion 框架）组织内容，再翻译成中文。
- **中文叙事单元优先**：以"动作、反应、代价、情绪、场景、关系位移"为基本叙事单元，不使用英文结构标签驱动正文生成。
- **禁止英文结论话术**：正文、审查说明、润色说明、变更摘要、最终报告中不得出现 Overall / PASS / FAIL / Summary / Conclusion 等英文结论标题。
- **英文仅限机器标识**：CLI flag（`--fast`）、checker id（`consistency-checker`）、DB 字段名（`anti_ai_force_check`）、JSON 键名等不可改的接口名保持英文，其余一律使用简体中文。

输出：
- 章节草稿（可进入 Step 2B 或 Step 3）。

### Step 2A 末尾追加：CHANGES 协议声明

Step 2A 生成章节正文后，**必须在正文末尾追加一个 `<chapter_changes>...</chapter_changes>` 块**，
包含本章对设定集/人物/物品/伏笔的所有结构化变更。

字段定义见 `.claude/references/changes-protocol.md`。
示例见 `.claude/references/changes-examples.md`。

8 个顶级字段必须全部显式存在（即使无变化也要写 `[]` 或 `null`）。

### Step 2B：风格适配（`--fast` / `--minimal` 跳过）

执行前加载：（本 Step 已被 `--fast`/`--minimal` 跳过；删版内联风格契约，由 `Step 2A 写作执行包` 直接消费）

硬要求：
- 只做表达层转译，不改剧情事实、事件顺序、角色行为结果、设定规则。
- 对"模板腔、说明腔、机械腔"做定向改写，为 Step 4 留出问题修复空间。

输出：
- 风格化正文（覆盖原章节文件）。

### Step 3：审查（auto 路由，必须由 Agent 子代理执行）

调用约束：
- 必须用 `Agent` 工具按注册名 `webnovel-writer:reviewer` 调用审查 subagent：
  ```
  Use the Agent tool to run `webnovel-writer:reviewer`
  ```
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

### Step 4：润色（问题修复优先）

执行前必须加载：
```bash
cat "${SKILL_ROOT}/references/writing/typesetting.md"

```

执行顺序：
1. 修复 `critical`（必须）
2. 修复 `high`（不能修复则记录 deviation）
3. 处理 `medium/low`（按收益择优）
4. 执行 Anti-AI 与 No-Poison 全文终检（必须输出 `anti_ai_force_check: pass/fail`）

输出：
- 润色后正文（覆盖章节文件）
- 变更摘要（至少含：修复项、保留项、deviation、`anti_ai_force_check`）

### Step 4.5：CHANGES 协议门禁

执行命令：

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/changes_gate.py \
    --chapter-file 正文/第{NNNN}章-{title_safe}.md \
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
    detect --chapter-file 正文/第{NNNN}章-{title_safe}.md

node ${CLAUDE_PLUGIN_ROOT}/scripts/check-ai-patterns.js \
    --check --fail-on=blocking \
    正文/第{NNNN}章-{title_safe}.md

```

**判定逻辑**：
- blocking 命中：退回 Step 4 重写正文（**保留 CHANGES 块**）。最多 2 次。
- advisory 命中：写入 `.story-system/anti_patterns.json`，继续流程。

可选关闭：在命令前加 `--skip-deslop`。

**anti-slop 双引擎仲裁规则**（解决同一处文本被两边各报一次的 conflict resolution）：

两个扫描器对同一章可能给出重叠但不一致的判定（例如"仿佛"在 `text_humanizer.py` 报"AI 高频词"frequency-based，在 `check-ai-patterns.js` 报"套词密度 tic"density-based）。仲裁规则如下：

1. **frequency-based finding 优先于 density-based finding**。`text_humanizer.py` 给的是绝对命中次数 + 每千字密度，证据链更精确；`check-ai-patterns.js` 的密度 tic 只是阈值告警（min_hits + per_kilo 双门槛），可能把零散的合规用法一并扫进去。冲突时以 `text_humanizer.py` 的命中次数 + 原文上下文为准决定是否改稿。
2. **任一工具报 critical / blocking → 触发整章重写**。critical 是硬级别（必须修），blocking 同 critical（必须退回 Step 4）。advisory 是软级别（提示，不阻断）。
3. **warning 级别（advisory）→ 标 advisory 不阻断**。advisory 项写入 `.story-system/anti_patterns.json`，不退回 Step 4，但作者应在下一轮迭代中处理。
4. **advisory 命中数 ≤ 2 → 放行**，> 2 但同类别聚集 → 主动改稿。同一 chapter 内同类 advisory 聚集（如同时报 "long-paragraph"、"cliche-density-tic"、"metaphor-density-tic"）说明文风系统性问题，不只是局部。
5. **工具彼此各管一段**：density-only finding（`check-ai-patterns.js` 独有，如 long-paragraph / period-stutter / micro-action-tic / action-list-tic / quote-emphasis-tic）和 frequency-only finding（`text_humanizer.py` 独有，如意义膨胀 / 论文式段落结构 / 排比三连）互不覆盖，重叠时按规则 1 仲裁。
6. **人工最终裁决**：两个工具都是启发式，按 1-5 处理后作者应扫一眼原文 sanity check，再决定是改稿还是放过。不允许"两工具都没报就一定安全"——双盲区是已知 gap。

执行建议：先把 `text_humanizer.py` 的 `severity=high` 和 `check-ai-patterns.js` 的 `--fail-on=blocking` 输出做并集，再按规则 1 仲裁重叠，最后按规则 2/3 决定是否退回 Step 4。

**重要前提**：
1. **两个工具都假定输入是 UTF-8 文本**。对 binary / GBK / UTF-16 / 截断 UTF-8 输入，
   `text_humanizer.py detect` 会把字节当字符处理并输出 `ok: true`（已知限制，
   工具是外部的，未在 fork 中修复）。若章节文件 > 50KB，应先确认编码。
2. **anti-slop 是启发式，不是合同**。两个工具的判定可能不一致（humanizer 对
   long-paragraph 不报警，check-ai-patterns 对 binary 会报警）。blocking 项
   都需要人工 review 一次，再决定是改稿还是放过。

### Step 5：Data Agent（状态与索引回写）

使用 Agent 调用 `data-agent`，参数：
- `chapter`
- `chapter_file` 必须传入实际章节文件路径；若详细大纲已有章节名，优先传 `正文/第{chapter_padded}章-{title_safe}.md`，否则传 `正文/第{chapter_padded}章.md`
- `review_score=Step 3 overall_score`
- `project_root`
- `storage_path=.webnovel/`
- `state_file=.webnovel/state.json`

按以下字面调用方式触发：
```
Use the Agent tool to run `webnovel-writer:data-agent`
```

Data Agent 默认子步骤（全部执行）：
- A. 加载上下文
- B. AI 实体提取
- C. 实体消歧
- D. 写入 state/index
- E. 写入章节摘要
- F. AI 场景切片
- G. RAG 向量索引（`rag index-chapter --scenes ...`）
- H. 风格样本评估（`style extract --scenes ...`，仅 `review_score >= 80` 时）
- I. 债务利息（默认跳过）

`--scenes` 来源优先级（G/H 步骤共用）：
1. 优先从 `index.db` 的 scenes 记录获取（Step F 写入的结果）
2. 其次按 `start_line` / `end_line` 从正文切片构造
3. 最后允许单场景退化（整章作为一个 scene）

Step 5 失败隔离规则：
- 若 G/H 失败原因是 `--scenes` 缺失、scene 为空、scene JSON 格式错误：只补跑 G/H 子步骤，不回滚或重跑 Step 1-4。
- 若 A-E 失败（state/index/summary 写入失败）：仅重跑 Step 5，不回滚已通过的 Step 1-4。
- 禁止因 RAG/style 子步骤失败而重跑整个写作链。

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

债务利息：
- 默认关闭，仅在用户明确要求或开启追踪时执行。

### Step 6：Git 备份（可失败但需说明）

```bash
git add .
git -c i18n.commitEncoding=UTF-8 commit -m "第{chapter_num}章: {title}"

```

规则：
- 提交时机：验证、回写、清理全部完成后最后执行。
- 提交信息默认中文，格式：`第{chapter_num}章: {title}`。
- 若 commit 失败，必须给出失败原因与未提交文件范围。

## 充分性闸门（必须通过）

未满足以下条件前，不得结束流程：

1. 章节正文文件存在且非空：`正文/第{chapter_padded}章-{title_safe}.md` 或 `正文/第{chapter_padded}章.md`
2. Step 3 已产出 `overall_score` 且 `review_metrics` 成功落库
3. Step 4 已处理全部 `critical`，`high` 未修项有 deviation 记录
4. Step 4 的 `anti_ai_force_check=pass`（基于全文检查；fail 时不得进入 Step 5）
5. Step 5 已回写 `state.json`、`index.db`、`summaries/ch{chapter_padded}.md`
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
- `正文/第{NNN}章-章名.md`、`正文/第{NNN}章-{slug}.md` 是否落盘。
- 审查报告路径（`审查报告/第{NNN}章审查报告.md` 或对应 range 报告）。
- `state.json` / index / summary / memory / vector 更新状态。
- `.webnovel/tmp/{context, draft, polish, review_results, fulfillment_result, disambiguation_result, extraction_result}.json` 是否齐全。
- `.story-system/commits/chapter_{NNN}.commit.json` 是否落盘（若被拒 `chapter-commit rejected` 则不算"已完成"）。
- 备份状态、是否可以继续写下一章。

异常分类：
- 已自动处理：自动重跑失败 batch、自动重做 anti-slop 扫描、自动重投影合同、自动重写 data artifacts。
- 建议确认：人物小传细节、微世界观表述、节拍微调、伏笔登记需要作者看一眼。
- 必须处理：`chapter-commit rejected`、projection retry 仍失败、`BLOCKER` 未裁决、关键产物缺失。

下一步建议必须使用任务化语言 + 可复制命令，例如：

```text
- 继续写下一章：
  /webnovel-write {NNN+1}

- 如需快车道（跳过 reviewer/polish）：
  /webnovel-fast-write {NNN+1}

- 如需最少链路（仅 draft + commit）：
  /webnovel-write {NNN+1} --minimal

```

最终状态不得写"已完成"，除非所有产物落盘 + tests 跑通。

不写 token 统计；如需排查故障，只给日志路径或建议运行 `/webnovel-doctor`。

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
