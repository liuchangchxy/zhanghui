---
name: webnovel-review
description: Reviews chapter quality with checker agents and generates reports. Use when the user asks for a chapter review or runs /webnovel-review.
allowed-tools: Read Grep Write Edit Bash AskUserQuestion
---

# Quality Review Skill

## Project Root Guard（必须先确认）

- Claude Code 的"工作区根目录"不一定等于"书项目根目录"。常见结构：工作区为 `D:\wk\xiaoshuo`，书项目为 `D:\wk\xiaoshuo\凡人资本论`。
- 必须先解析真实书项目根（必须包含 `.webnovel/state.json`），后续所有读写路径都以该目录为准。

环境设置（bash 命令执行前）：
```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-${PWD}}"

if [ -z "${CLAUDE_PLUGIN_ROOT}" ] || [ ! -d "${CLAUDE_PLUGIN_ROOT}/skills/webnovel-review" ]; then
  echo "ERROR: 未设置 CLAUDE_PLUGIN_ROOT 或缺少目录: ${CLAUDE_PLUGIN_ROOT}/skills/webnovel-review" >&2
  exit 1
fi
export SKILL_ROOT="${CLAUDE_PLUGIN_ROOT}/skills/webnovel-review"

if [ -z "${CLAUDE_PLUGIN_ROOT}" ] || [ ! -d "${CLAUDE_PLUGIN_ROOT}/scripts" ]; then
  echo "ERROR: 未设置 CLAUDE_PLUGIN_ROOT 或缺少目录: ${CLAUDE_PLUGIN_ROOT}/scripts" >&2
  exit 1
fi
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT}/scripts"

export PROJECT_ROOT="$(python "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"

```

## 0.5 工作流断点（best-effort，不得阻断主流程）

> 目标：让 ledger 续跑逻辑能基于真实断点恢复。即使 ledger 调用出错，也**只记录警告**，审查继续。

推荐（bash）：
```bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" run-ledger write-resume --chapter {end} || true

```

> 步骤状态由 `run-ledger record-write-step` 在每个 Step 末尾持久化；不再使用 `workflow start-step` / `complete-step`。

## Review depth

- **Core (default)**: consistency / continuity / ooc / reader-pull
- **Full (关键章/用户要求)**: core + high-point + pacing

## Step 1: 加载参考（按需）

## References（按步骤导航）

- Step 1（必读，硬约束）：[core-constraints.md](../../references/shared/core-constraints.md)
- Step 1（可选，Full 或节奏/爽点相关问题）：[cool-points-guide.md](../../references/shared/cool-points-guide.md)
- Step 1（可选，Full 或节奏/爽点相关问题）：[strand-weave-pattern.md](../../references/shared/strand-weave-pattern.md)
- Step 1（可选，仅在返工建议需要时）：[common-mistakes.md](references/common-mistakes.md)
- Step 1（可选，仅在返工建议需要时）：[pacing-control.md](references/pacing-control.md)

## Reference Loading Levels (strict, lazy)

- L0: 先确定审查深度（Core / Full），再加载参考。
- L1: 只加载 References 区的"必读"条目。
- L2: 仅在问题定位需要时加载 References 区的"可选"条目。

**必读**:
```bash
cat "${SKILL_ROOT}/../../references/shared/core-constraints.md"

```

**建议（Full 或需要时）**:
```bash
cat "${SKILL_ROOT}/../../references/shared/cool-points-guide.md"
cat "${SKILL_ROOT}/../../references/shared/strand-weave-pattern.md"

```

**可选**:
```bash
cat "${SKILL_ROOT}/references/common-mistakes.md"
cat "${SKILL_ROOT}/references/pacing-control.md"

```

## Step 2: 加载项目状态（若存在）

```bash
cat "$PROJECT_ROOT/.webnovel/state.json"

```

### 一致性维度

Review 阶段额外输出"一致性"维度：

```bash
python3 -m scripts.consistency.cli check --project-root "$PROJECT_ROOT" --chapter {chapter_num}
```

把所有 BLOCKER 列在 review 报告里（patch + message + fix_hint）。

## Step 3: 调用统一 reviewer（unified pipeline）

**调用约束**:
- 必须通过 Agent 工具调用 `webnovel-writer:reviewer`，由 reviewer 自身统揽 6 个维度（爽点/设定/节奏/人物/连贯/追读）。禁止主流程直接内联审查结论：
  ```
  Use the Agent tool to run `webnovel-writer:reviewer`
  ```
- reviewer 输出结构化 JSON，由主流程保存到 `.webnovel/tmp/review_results.json`。
- 维度覆盖：
  - **Core (default)**：爽点密度 / 设定一致性 / 节奏控制 / 人物塑造 / 连贯性 / 追读力
  - **Full (关键章 / 用户要求)**：Core + do_not_copy_violation 维度 + 对标书禁抄合规性
- 落库走 `review-pipeline --save-metrics`（详见 `../../agents/reviewer.md` 的 SubagentRun 契约）。

**do_not_copy 检查（reviewer 任务之前执行）**：

1. 定位本章正文文件 `CHAPTER_FILE`：优先 `正文/第{NNNN}章-{title_safe}.md`，无标题时回退 `正文/第{NNNN}章.md`。
2. 调用 `reference_research_injector.build_do_not_copy_check_data()`，用本章正文全文扫描 `do_not_copy` 条目：

   ```bash
   mkdir -p "${PROJECT_ROOT}/.webnovel/tmp"
   python3 -X utf8 -c '
   import sys, json, pathlib
   sys.path.insert(0, sys.argv[1])
   from data_modules.reference_research_injector import build_do_not_copy_check_data
   text = pathlib.Path(sys.argv[3]).read_text(encoding="utf-8")
   v = build_do_not_copy_check_data(pathlib.Path(sys.argv[2]), text)
   print(json.dumps({"violations": v}, ensure_ascii=False, indent=2))
   ' "${SCRIPTS_DIR}" "${PROJECT_ROOT}" "${PROJECT_ROOT}/${CHAPTER_FILE}" \
     > "${PROJECT_ROOT}/.webnovel/tmp/do_not_copy_check.json"
   ```

3. 输出写入 `.webnovel/tmp/do_not_copy_check.json`，每个 violation 含 item / source_book / chapter_line / matched_text / severity / category：

   ```json
   {"violations": [{"item": "韩立人设", "source_book": "凡人修仙传", "chapter_line": 12, "matched_text": "韩立微微一笑道……", "severity": "critical", "category": "do_not_copy_violation"}]}
   ```

4. 无 `reference_research/` 树或无命中 → 上述命令自然产出 `{"violations": []}`，不报错、不阻断。
5. reviewer 任务读取此 artifact 并把每个 violation 加入 `issues` 数组（见 `reviewer` 的"对标书禁抄合规性"维度）。

## Step 4: 生成审查报告

保存到：`审查报告/第{start}-{end}章审查报告.md`

**报告结构（精简版）**:
```markdown
# 第 {start}-{end} 章质量审查报告

## 综合评分
- 爽点密度 / 设定一致性 / 节奏控制 / 人物塑造 / 连贯性 / 追读力
- 总评与等级

## 修改优先级
- 🔴 高优先级（必须修改）
- 🟠 中优先级（建议修改）
- 🟡 低优先级（可选优化）

## 改进建议
- 可执行的修复建议

```

**审查指标 JSON（用于趋势统计）**:
```json
{
  "start_chapter": {start},
  "end_chapter": {end},
  "overall_score": 48,
  "dimension_scores": {
    "爽点密度": 8,
    "设定一致性": 7,
    "节奏控制": 7,
    "人物塑造": 8,
    "连贯性": 9,
    "追读力": 9
  },
  "severity_counts": {"critical": 1, "high": 2, "medium": 3, "low": 1},
  "critical_issues": ["设定自相矛盾"],
  "report_file": "审查报告/第{start}-{end}章审查报告.md",
  "notes": ""
}

```

注意：此处只生成审查指标 JSON；落库见 Step 5。

## Step 5: 通过 review-pipeline 落库（必做）

reviewer 输出的 `.webnovel/tmp/review_results.json` 必须经 `review-pipeline --save-metrics` 落库到 `index.db.review_metrics`：

```bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" review-pipeline --save-metrics \
  --results "${PROJECT_ROOT}/.webnovel/tmp/review_results.json"

```

metrics 摘要同步输出到 `.webnovel/tmp/review_metrics.json`，供 `webnovel-write` 的 Step 4 与最终报告消费。

## Step 6: 写回审查记录到 state.json（必做）

将审查报告记录写回 `state.json.review_checkpoints`，用于后续追踪与回溯（依赖 `update_state.py --add-review`）：
```bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" update-state -- --add-review "{start}-{end}" "审查报告/第{start}-{end}章审查报告.md"

```

## Step 7: 处理关键问题

如发现 critical 问题（`severity_counts.critical > 0` 或 `critical_issues` 非空），**必须使用 AskUserQuestion** 询问用户：
- A) 立即修复（推荐）
- B) 仅保存报告，稍后处理

若用户选择 A：
- 输出"返工清单"（逐条 critical 问题 → 定位 → 最小修复动作 → 注意事项）
- 如用户明确授权可直接修改正文文件，则用 `Edit` 对对应章节文件做最小修复，并建议重新运行一次 `/webnovel-review` 验证

若用户选择 B：
- 不做正文修改，仅保留审查报告与指标记录，结束本次审查

## Step 8: 收尾（落 ledger）

```bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" run-ledger record-write-step \
  --chapter {end} --step review --status done || true
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" run-log \
  --event review-complete \
  --payload-json "{\"start\":{start},\"end\":{end}}" || true

```

## 状态产物所有权（reviewer → 主流程单一写入者）

- 唯一写入者（reviewer 链路）：主流程从 reviewer 的 Agent 返回结构化 JSON 落盘到 `.webnovel/tmp/review_results.json`（含 `review_metrics` 落到 `.webnovel/tmp/review_metrics.json`）。
- reviewer 本身不直接写文件；主流程不直接重写 review 结果，只在 review-pipeline 中落库与重放。
- write 链路下其余状态产物（state/index/summaries/memory/vectors/projection）的唯一写入者是 `data-agent`，主流程只检查文件存在与 schema，不直接写。
- 产物所有权凭证：`.webnovel/tmp/subagent_runs/{skill}-reviewer.jsonl` / `write-data-agent.jsonl`。

## SubagentRun 可汇总信号

主流程对每个 subagent 调用必须记录一次 `SubagentRun` JSON：

```json
{
  "name": "reviewer",
  "status": "completed | partial | failed | skipped",
  "problems": [],
  "auto_handled": [],
  "needs_user_action": false,
  "duration_ms": 0,
  "outputs": []
}
```

写入路径：`.webnovel/tmp/subagent_runs/review-{chapter}.jsonl`（每行一个 SubagentRun）。

主流程"汇总 Step N 已确认的 subagent 输出"并把它整合到下一步输入。

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
- 审查报告文件路径（`审查报告/第{start}-{end}章审查报告.md`）是否落盘。
- `.webnovel/tmp/review_results.json` 是否齐全。
- `.webnovel/tmp/review_metrics.json` 是否生成，并写明 `review_metrics` 关键维度得分。
- `severity_counts.critical / major / minor` 与阻断问题数量（`critical_issues` 数）。
- `state.json.review_checkpoints` 是否写回、`update-state --add-review` 是否成功。
- 用户裁决状态（修复 / 仅保留报告）。
- 如果无阻断，明确可以继续写作。

异常分类：
- 已自动处理：自动重跑失败 sub-agent、自动重生成 metrics、自动补 checkpoint 记录。
- 建议确认：人物小传细节、微世界观表述、节拍微调、伏笔登记需要作者看一眼。
- 必须处理：有 blocking 问题且用户未选择处理策略（最终状态为“需要你处理”）、`BLOCKER` 未裁决、关键产物缺失。

下一步建议必须使用任务化语言 + 可复制命令，例如：

```text
- 如需返工修复：
  /webnovel-revise {start}-{end}

- 继续写作：
  /webnovel-write {end+1}

```

不写 token 统计；如需排查故障，只给日志路径或建议运行 `/webnovel-doctor`。

## 作者友好过程提示与恢复契约

审查开始前先说明本次会经历：解项目根 -> 收集章节 -> 调度 reviewer -> 生成 metrics -> 落审查报告 -> 写回 state。过程提示用作者语言，不直接输出原始 JSON、traceback 或长命令日志；技术详情写入 `.webnovel/logs/run_last.log`：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" run-log \
  --event review-progress \
  --payload-json "{\"stage\": \"review\", \"range\": \"{start}-{end}\"}" \
  --format text

```

过程提示每次不超过两行，只说当前动作和影响，例如"正在过 reviewer：会按设定/时间线/节奏/角色/逻辑五维度逐章扫一遍"。少打扰确认策略：默认继续推进；只有审查范围不明、有 blocking 问题且需要返工取舍、review 报告被覆盖风险时才询问。

需要用户裁决时使用有限选项，并说明影响；例如修复 / 仅保留报告 / 暂停审查。卡住时必须说明卡点、已完成内容和恢复建议，例如"前两章 reviewer 已完成，第三章 metrics 生成失败；重新运行 `/webnovel-review {start}-{end}` 会只重做失败批次"。

不可恢复故障才在最终报告提示 `.webnovel/logs/run_last.log`；平时只保留日志，不打扰作者。收尾必须调用作者报告 helper：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" user-report \
  --stage review \
  --range "{start}-{end}" \
  --format text

```
