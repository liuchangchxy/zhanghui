# Cleanup Cycle: 39 Pre-existing Prompt-Integrity Failures

**Date:** 2026-08-16
**Status:** Proposed
**Goal:** Fix all 39 pre-existing `test_prompt_integrity.py` failures. Bring the plugin from L1 (feature-complete) to **L2 (production-ready)**.
**Builds on:** P0-Full + P1+P2 + 14 adversarial fixes + P3 + P3-fixes.

## Background

The plugin accumulated technical debt from earlier iterations:

1. **Stale references** — SKILL.md files mention deleted reference docs (`step-3-review-gate.md`, `step-5-debt-switch.md`, `polish-guide.md`, `style-adapter.md`).
2. **CLI surface drift** — Skills call `workflow` (deleted subcommand) instead of `review-pipeline`.
3. **Agent-tool naming drift** — Skills use the legacy `Task` tool / `Task 调用` instead of `Agent` + `webnovel-writer:<name>` registration strings.
4. **Missing author-friendly contracts** — The 3 main skills (init/write/review) lack the modern "作者友好最终报告契约" + "作者友好过程提示与恢复契约" sections.
5. **Write-specific contracts** — write SKILL.md lacks `chapter-commit`, `write-gate {prewrite,precommit,postcommit}`, `placeholder-scan`, `story-system --emit-runtime-contracts`, `projections retry`, `run-ledger write-resume`, `git diff` precommit check, 6-node process markers, SubagentRun summaries.
6. **Review pipeline metrics** — review SKILL.md doesn't use `review-pipeline --save-metrics`; user-facing final-state contract missing.
7. **State artifact ownership** — Write flow's data-agent ownership clauses missing; main flow's "不直写 state/index/summaries/memory/vectors/projection" missing.
8. **Plan reference_research** — `test_plan_reads_reference_research_when_pointer_set` + `test_plan_auto_discovers_reference_research` likely passing in source but failing in deployed copy (sync drift).

The current 39 failures cause real production risks:
- Skills lie to the LLM about what CLI subcommands exist (LLM calls `webnovel.py chapter-commit`, gets `unrecognized argument` → silent failure)
- Skills omit modern contracts (no SubagentRun summaries → user can't recover from interrupted runs)
- Skills use deprecated `Task` tool (works but defeats the `webnovel-writer:&lt;name&gt;` discovery mechanism)
- 6-node process markers missing (write SKILL has unbounded `cat`/verbose chains → user gets lost)

## Goal

After this lands:
- `python3 -m pytest data_modules/tests/test_prompt_integrity.py` shows 0 failures (down from 39)
- Skills match reality (no SKILL.md promises that the CLI can't deliver)
- New CLI subcommands exist where Skills need them
- All 3 main skills have author-friendly contracts

## Non-Goals

- No functional feature changes (writing flow behavior unchanged)
- No new agents
- No skill consolidation
- No `webnovel.py` interface redesign (additive only)
- No `state.json` schema migration
- No deprecation of legacy tooling (Skills updated; old tooling may continue to exist)

## File modifications (estimated scope)

| File | Action | Approx. lines |
|---|---|---|
| `skills/webnovel-init/SKILL.md` | Modify (add contracts) | +60 |
| `skills/webnovel-write/SKILL.md` | Modify (heavy rewrite) | +200/-50 |
| `skills/webnovel-review/SKILL.md` | Modify (heavy rewrite) | +150/-30 |
| `skills/webnovel-plan/SKILL.md` | Verify sync | ±0 |
| `agents/context-agent.md` | Verify wording | ±0 |
| `agents/reviewer.md` | Verify wording | ±0 |
| `agents/deconstruction-agent.md` | Verify wording | ±0 |
| `scripts/webnovel.py` | Modify (re-export) | +10 |
| `scripts/data_modules/webnovel.py` | Modify (add subcommands) | +200 |
| `scripts/data_modules/write_gate.py` | **Create** | ~80 |
| `scripts/data_modules/chapter_commit.py` | **Create** | ~100 |
| `scripts/data_modules/review_pipeline.py` | Modify (add --save-metrics) | +50 |
| `scripts/data_modules/story_system.py` | Modify (add --emit-runtime-contracts) | +30 |
| `scripts/data_modules/projections.py` | Modify (add retry subcommand) | +40 |
| `scripts/data_modules/run_ledger.py` | Modify (add write-resume) | +30 |
| `scripts/data_modules/tests/test_write_gate.py` | **Create** | ~60 |
| `scripts/data_modules/tests/test_chapter_commit.py` | **Create** | ~50 |
| `scripts/data_modules/tests/test_review_pipeline.py` | **Modify** | +30 |
| `scripts/data_modules/tests/test_story_system_runtime.py` | **Create** | ~40 |
| `scripts/data_modules/tests/test_prompt_integrity.py` | (no change — tests are the contract) | 0 |

Total: ~700-800 lines added/modified across ~14 files.

## Test categories & fixes (39 failures)

### A. Stale references (8 failures)

| Test | Fix |
|---|---|
| `test_all_references_exist[SKILL.md6/8/14]` | Remove mention of `references/step-3-review-gate.md`, `references/step-5-debt-switch.md`, `references/polish-guide.md`, `references/style-adapter.md` etc. |
| `test_no_stale_references[SKILL.md5/10/11/14]` | Remove mentions of `step-3-review-gate.md`, `workflow_manager.py`, `webnovel-resume`, etc. |

### B. CLI surface drift (3 failures)

| Test | Fix |
|---|---|
| `test_cli_commands_valid[SKILL.md11]` | Replace `webnovel.py workflow ...` with `webnovel.py review-pipeline ...` |
| `test_cli_commands_valid[SKILL.md14]` | Same |
| `test_webnovel_review_skill_uses_unified_reviewer_pipeline` | Update review SKILL.md to reference `reviewer` agent + `.webnovel/tmp/review_results.json` + `review-pipeline` (not legacy 6 checkers) |

### C. Agent-tool naming (2 failures)

| Test | Fix |
|---|---|
| `test_active_skills_use_agent_tool_name_not_legacy_task` | Change `allowed-tools` from `... Task ...` to `... Agent ...`. Change "Task 调用" → "Agent 调用" |
| `test_webnovel_write_skill_uses_explicit_agent_invocation_templates` | Add explicit `webnovel-writer:context-agent` / `webnovel-writer:reviewer` / `webnovel-writer:data-agent` strings; remove `subagent_type:` blocks; add "不得用主流程口头代替 subagent 输出" clause |

### D. Author-friendly final report contract (3 failures)

Add to init/write/review SKILL.md each:
```
## 作者友好最终报告契约

最终状态：已完成 / 部分完成 / 需要你处理 / 未完成

### 一、做了什么
### 二、当前状态  
### 三、需要你处理的问题（按优先级）

- 已自动处理（无需操作）
- 建议确认（你判断）
- 必须处理（阻塞下一步）

附：可复制命令 / `/webnovel-doctor` / 不写 token 统计
```

### E. Author-friendly progress + recovery contract (3 failures)

Add to init/write/review each:
```
## 作者友好过程提示与恢复契约

- 过程提示：少打扰确认策略
- 卡住时必须说明卡点 + 已完成内容
- 恢复建议：`.webnovel/logs/run_last.log` / run-log / user-report
```

### F. Write-specific contracts (12 failures)

| Test | Required |
|---|---|
| `test_write_skill_final_report_covers_commit_projection_and_backup` | Final report covers: 正文文件路径, 审查报告路径, `.webnovel/tmp/{review_results,fulfillment_result,disambiguation_result,extraction_result}.json`, `.story-system/commits/chapter_{NNN}.commit.json`, state/index/summary/memory/vector 更新状态, 备份状态, 是否可以继续写下一章, "chapter-commit rejected", 最终状态不得写"已完成", "--fast"/"--minimal", "projection retry" |
| `test_main_skills_record_subagent_run_summaries_for_agent_calls` | "SubagentRun" + 6 fields (`status`/`problems`/`auto_handled`/`needs_user_action`/`duration_ms`/`outputs`) + each required agent name |
| `test_write_skill_progress_nodes_are_author_friendly_and_limited` | "写章过程节点（最多 6 个）" + ≤ 6 nodes (regex `^\d+\.\s+(.+)$`) with author-friendly labels (e.g. "检查项目环境","整理写作依据","起草正文","写作检查","保存本章故事事实","提交备份"); forbidden tokens (`write-gate`,`chapter-commit`,`projection_status`,`artifact`,`schema`) must not appear in nodes |
| `test_write_skill_resume_contract_uses_runtime_ledger_and_confirmation_boundaries` | `run-ledger write-resume` + 可信断点 + 正文被手动改过 + 章纲更新晚于正文 + 本章已 accepted + 沿用当前正文 / 重新起草 / 只查看状态 + 不得覆盖作者手改 |
| `test_webnovel_write_skill_uses_chapter_commit_as_step5_mainline` | `chapter-commit` + `CHAPTER_COMMIT`; must NOT contain `state process-chapter` |
| `test_webnovel_write_skill_uses_project_root_backup_not_bare_git_add` | `webnovel.py --project-root "${PROJECT_ROOT}" backup`; must NOT contain `git add .` |
| `test_write_skill_routes_step2_through_writing_brief` | 写作任务书 + context-agent + NOT "Step 0.5" + NOT `cat "${SKILL_ROOT}/../../references/shared/core-constraints.md"` + NOT `cat "${SKILL_ROOT}/references/anti-ai-guide.md"` |
| `test_context_agent_and_write_skill_form_isolated_write_chain` | 写作任务书 in both; NOT "Context Contract" in context-agent.md; NOT "Step 2 直写提示词" in context-agent.md |
| `test_write_review_skills_state_artifact_ownership` | Both must say 主流程 + `.webnovel/tmp/review_results.json`; write must say 唯一写入者, "主流程只检查文件存在与 schema", "不直接写 state/index/summaries/memory/vectors/projection" |
| `test_write_skill_postcommit_verifies_five_projections_and_retry_only` | `state/index/summary/memory/vector` and `projections retry --chapter {chapter_num}` |
| `test_write_skill_has_readonly_git_diff_change_surface_check` | `diff --name-status` and `diff --check` |
| `test_write_skill_gate_stages_ordered_prewrite_precommit_postcommit` | `write-gate --chapter {chapter_num} --stage prewrite`, `--stage precommit`, `--stage postcommit` in that order |
| `test_placeholder_scan_runs_in_both_plan_and_write_skills` | Both must call `placeholder-scan` CLI subcommand |

### G. Story-system runtime contracts (3 failures)

| Test | Required |
|---|---|
| `test_story_system_runtime_contract_commands_exist` | write SKILL.md must contain `story-system` and `--emit-runtime-contracts` |
| `test_story_system_chapter_refresh_uses_real_goal_not_placeholder_query` | write SKILL.md must have `story-system "${CHAPTER_GOAL}"`; must NOT have `story-system "{章纲目标}"` / `story-system "第N章章纲目标"`; must mention both placeholders in禁止说明 |
| `test_story_system_chapter_refresh_persists_runtime_contracts` | The `story-system "${CHAPTER_GOAL}"` call must contain `--persist`, `--emit-runtime-contracts`, `--chapter` |

### H. Review pipeline metrics (2 failures)

| Test | Required |
|---|---|
| `test_review_pipeline_persists_metrics_in_review_chain[webnovel-write]` | write must call `review-pipeline` CLI + `--save-metrics` |
| `test_review_pipeline_persists_metrics_in_review_chain[webnovel-review]` | review must call `review-pipeline` + `--save-metrics` |
| `test_review_skill_final_report_covers_metrics_and_blocking_decision` | review must cover: 审查报告文件, `.webnovel/tmp/{review_results,review_metrics}.json`, review_metrics, 阻断问题数量, 用户裁决状态, "如果无阻断，明确可以继续写作", "有 blocking 问题且用户未选择处理策略", "最终状态为"需要你处理"" |

### I. State artifact ownership (1 failure)

`test_write_review_skills_state_artifact_ownership` — covered in F table.

### J. Plan reference_research (2 failures, likely sync drift)

| Test | Fix |
|---|---|
| `test_plan_reads_reference_research_when_pointer_set` | Plan SKILL.md at line 100 already contains the required strings (per P3-fixes). Sync drift — copy `skills/webnovel-plan/SKILL.md` to marketplace. |
| `test_plan_auto_discovers_reference_research` | Same — sync fix |

## New CLI subcommands to add

| Subcommand | File | Function |
|---|---|---|
| `webnovel.py write-gate --chapter N --stage {prewrite,precommit,postcommit}` | `scripts/data_modules/write_gate.py` | Gate checks per chapter stage. prewrite: chapter outline exists. precommit: artifacts present + deslop pass. postcommit: 5 projections OK + run-ledger committed. |
| `webnovel.py chapter-commit --chapter N` | `scripts/data_modules/chapter_commit.py` | Atomic commit of chapter artifact + state/index/summary/memory/vector updates. Replaces `state process-chapter`. |
| `webnovel.py review-pipeline --save-metrics --chapter N` | `scripts/data_modules/review_pipeline.py` | Run reviewer + persist metrics + update review history. |
| `webnovel.py story-system refresh "${CHAPTER_GOAL}" --chapter N --persist --emit-runtime-contracts` | `scripts/data_modules/story_system.py` | Refresh story contracts from chapter goal. |
| `webnovel.py projections retry --chapter N` | `scripts/data_modules/projections.py` | Retry state/index/summary/memory/vector projections after failure. |
| `webnovel.py run-ledger write-resume --chapter N` | `scripts/data_modules/run_ledger.py` | Resume a write flow at the last safe step. |

## Acceptance Criteria

- [ ] `test_prompt_integrity.py` shows 0 failures (down from 39)
- [ ] All 6 new CLI subcommands exist + work
- [ ] 3 main skills (init/write/review) have author-friendly final report + progress/recovery contracts
- [ ] write SKILL.md has 6-node process markers (author-friendly labels, no forbidden tokens)
- [ ] write SKILL.md has `chapter-commit`, `write-gate`, `placeholder-scan`, `projections retry`, `run-ledger write-resume`, `story-system`, `git diff` invocations
- [ ] review SKILL.md has `review-pipeline --save-metrics`, blocking decision contract
- [ ] All P0-Full + P1+P2 + 14 fixes + P3 + P3-fixes tests still pass (172 → 172+)
- [ ] Both copies in sync
- [ ] Final adversarial review pass: no new Critical bugs introduced

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Adding CLI subcommands without real backing tests = more silent failures | Each new subcommand gets ≥ 3 unit tests before being referenced from SKILL.md |
| `webnovel.py` dispatch becomes unwieldy (already 20+ subcommands) | New subcommands use subparser pattern; clean docstring; help text matches SKILL.md invocation |
| `chapter-commit` replacing `state process-chapter` may break legacy code paths | `state process-chapter` kept as deprecated alias; both paths tested |
| Skill rewrites accidentally remove functional sections | Run smoke test (write 1 chapter) after each skill change |
| Long-running implementation (2-3 weeks) | Split into ~6 sub-cycles (one per file cluster), each with its own adversarial review |

## Implementation sub-cycles (suggested)

The 39 failures cluster into 6 natural sub-cycles. Each is independent and can ship separately:

| # | Sub-cycle | Failures | Files touched | Est. time |
|---|---|---|---|---|
| 1 | Stale references + CLI surface drift | 11 | webnovel-init/write/review SKILL.md | 1 day |
| 2 | Agent-tool naming | 2 | 3 skills frontmatter + body | 1 day |
| 3 | Author-friendly final report contract | 3 | 3 skills new sections | 2 days |
| 4 | Author-friendly progress + recovery contract | 3 | 3 skills new sections | 2 days |
| 5 | SubagentRun summaries + state artifact ownership | 2 | 3 skills + agents | 1 day |
| 6 | Write-specific contracts (F + G + H + I) | ~18 | write SKILL.md heavy rewrite + 6 new CLI subcommands + tests | 1-2 weeks |

Each sub-cycle has its own spec/plan/execute/review.

## Out of Scope

- Functional feature changes
- Performance optimization
- Documentation beyond SKILL.md (README updates, etc.)
- Migration of pre-existing projects to new contracts
- Compatibility shims for legacy CLI commands
- English / multi-language reference_research (separate spec)