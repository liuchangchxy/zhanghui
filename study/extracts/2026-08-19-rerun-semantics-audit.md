---
name: 2026-08-19-rerun-semantics-audit
description: 第一次系统性审计 zhanghui 全部 15 个 skill 的"重跑/覆盖"语义。结论：plan 报的 8 个缺陷全部为真；但 init / volume_state / chapter_commit 已经在脚本层有显式守卫，定位不均。
metadata:
  type: project
---

# 2026-08-19 重跑/覆盖语义审计

## 背景

用户在使用 plan 时遇到 8 个疑似设计缺陷，提了两个第一性问题：
1. 列出的 8 个缺陷是否真实？
2. 其他 14 个 skill 是否同样缺失"重跑 = 覆盖 / 沿用 / 部分重写"的用户裁决机制？

## 审计方法

- 通读 `.claude/plugins/zhanghui/skills/*/SKILL.md`（15 份）
- 配套检查 `scripts/` 下所有 .py 中涉及 `overwrite` / `exists` / `merge` / `append_or_update` / `已存在` / `询问` 的关键函数
- 验证每个声称有"询问"机制的 SKILL.md 是否在脚本层落地

## 结论一：plan 的 8 个缺陷全部为真

| # | 缺陷 | 代码位置 | 状态 |
|---|------|---------|------|
| 1 | 不检测 .md 是否已存在 | plan/SKILL.md Step 4-7 无存在性检查；`init-volume-beat` 只检查 state.json | 真 |
| 2 | 不询问保留/重写 | SKILL.md 仅说"覆盖已有规划时询问"（line 431），但无任何脚本检测触发点 | 真 |
| 3 | Step 7 无脚本保障 | 整卷详细大纲是 AI 文本写入，无一致性脚本兜底 | 真 |
| 4 | `check-volume` 不验证 .md | `story_craft.py:check_volume_beat` 只读 state.json，exit code 仅反映 BLOCKER | 真 |
| 5 | .md 与 state.json 双向脱钩 | AI 写 .md、脚本写 state.json，无同步脚本 | 真 |
| 6 | Step 6/7 "生成" vs "校验" 语义模糊 | SKILL.md line 196/240 均用"生成"一字 | 真 |
| 7 | hook_type 校验过严 | `story_craft.py:237` 6 个枚举；`outline 写"悬念钩"` 必触发 ValueError | 真 |
| 8 | chapter_meta 白名单过窄 | `story_craft.py:239-244` 11 字段，不含 CBN/CPNs/CEN/must_cover/forbidden/strand/coolpoint/时间锚点/反派层级 | 真 |

## 结论二：重跑/覆盖语义分布极度不均

### A 类：脚本层有显式覆盖守卫（3 处）

| 位置 | 守卫语义 |
|------|---------|
| `init_project.py:423-444` | `volumes[]` 已含 confirmed → 拒绝重 init（除非 `force=True`） |
| `init_project.py:924-929` | reference_research 树已存在 → 拒绝（除非 `--reference-overwrite`） |
| `data_modules/volume_state.py:128-202` | `append_or_update` / `confirm_volume` / update field 均拒绝 AI 覆盖 confirmed/deferred |
| `scripts/project_memory.py:70-74` (`add_pattern`) | pattern_type + description 完全相同 → 跳过并返回 `status=skipped` |
| `data_modules/webnovel.py:524-606` (`init-forechains`) | per-volume 已存在伏笔按 depth 计数，缺多少补多少 |
| `data_modules/webnovel.py:607-663` (`init-locks`) | `_has(needle)` 检查 description 子串，已存在跳过 |

### B 类：SKILL.md 声称有"覆盖时询问"，但靠 AI 自觉（5 处）

| SKILL.md | 原文 | 实际落地 |
|---------|------|---------|
| webnovel-init:677 | "需要覆盖已有项目时才询问" | 无脚本检测，靠 AI 自觉 |
| webnovel-plan:431 | "覆盖已有规划时才询问" | 无脚本检测，靠 AI 自觉 |
| webnovel-write:174-180 | "正文被手改/章纲晚于正文/已 accepted → 询问" | 通过 `run-ledger` 落盘 + mtime 比较；这是**最好**的一个 |
| webnovel-write:790 | "需要覆盖 run-ledger 已记录的 step 时才询问" | 同上 |
| webnovel-review:326 | "review 报告被覆盖风险时才询问" | 无脚本检测，靠 AI 自觉 |

### C 类：脚本层**显式强制覆盖**（4 处，最差）

| 位置 | 行为 |
|------|------|
| `scripts/update_master_outline.py:121-162` (`_update_volume_table`) | V+1 行若已存在 → 直接覆写 volume_name/core_conflict/climax，无任何提示 |
| `scripts/chapter_commit.py:91-96` (`persist_commit`) | `chapter_{NNN}.commit.json` 已存在 → 直接覆写 |
| `scripts/snapshot_manager.py:121-137` (`cmd_freeze`) | snapshot dir 已存在 → `shutil.rmtree` 清空后重建 |
| `data_modules/webnovel.py:443-454` (`init-volume-beat`) | 同卷 id 已存在 → return state 不报错（看似安全，但跳过了脚本层"再次跑会怎样"的语义） |
| `data_modules/webnovel.py:664-687` (`set-chapter-meta`) | `existing.update(...)` 字段级 merge，但 hook_type 6 枚举过严 |

### D 类：只读 skill，本身不写文件

`webnovel-query`, `webnovel-doctor`, `webnovel-dashboard`, `webnovel-deslop-check` — 无重跑覆盖问题（但 `deslop-check` 报告会覆盖 `审查报告/deslop-*.md`，未审计）。

## 结论三：模式不止 plan，缺陷是系统性的

| skill | 是否需要"覆盖前询问"？ | 现状 |
|-------|---------------------|------|
| webnovel-init | 是 | **有**守卫（confirmed-volume + reference-tree） |
| webnovel-plan | 是 | **无**脚本守卫，SKILL.md 自称询问但落空 |
| webnovel-write | 是 | **有**run-ledger + mtime 部分守卫 |
| webnovel-fast-write | 是 | 同 write（继承 run-ledger） |
| webnovel-review | 是 | **无**脚本守卫 |
| webnovel-revise | 是 | **有**（写到 .revised.md 等用户确认后才覆盖原文件） |
| webnovel-deslop-check | 是（产出覆盖报告） | 未深审 |
| webnovel-style-profile | 是（baseline 覆盖） | 未深审 |
| webnovel-learn | 是 | **有**（add_pattern 按 description 去重） |
| webnovel-resume | 是（专门处理中断） | **有**（沿用/重写/查看三态） |
| webnovel-query | 否 | 只读 |
| webnovel-doctor | 否 | 只读 |
| webnovel-dashboard | 否 | 只读 |
| webnovel-chart-scan | 部分 | 写 chart-scan/ 目录（每次新建子目录） |
| webnovel-deconstruct | 是 | **有**守卫（reference tree 已存在 → 默认覆盖但备份 _schema.json） |

## 缺口的统一语义

用户问"覆盖 / 部分覆盖 / 沿用"的三态，当前**没有一个 skill 在脚本层实现了完整三态**。最接近完整三态的是：

1. `webnovel-resume`（沿用 / 重新起草 / 只查看状态）— 通过 run-ledger 实现
2. `webnovel-revise`（写到 `.revised.md` 等用户确认）— 但只是"写副本等批准"
3. `webnovel-init` 的 `append_or_update` 语义 — 通过 state 锁实现

## 修复优先级建议

| 优先级 | 缺口 | 修复成本 |
|--------|------|---------|
| P0 | `update_master_outline.py:_update_volume_table` V+1 行静默覆写 | 低：加 `if existing and not --force: BLOCKER` |
| P0 | `chapter_commit.py:persist_commit` 静默覆写 accepted commit | 低：检查 ledger accepted 标志 |
| P0 | `snapshot_manager.py:cmd_freeze` `rmtree` 清空快照 | 中：备份 .bak-{ts} 或拒绝 |
| P1 | plan 8 个缺陷整套（建议先扩 ALLOWED_CHAPTER_META_FIELDS + 把 check-volume 加 .md 存在性检查） | 中 |
| P2 | SKILL.md 自称"询问"但脚本不落地的 5 处 | 中：要么删 SKILL.md 声明，要么写脚本 |
| P3 | 统一设计：所有写文件 skill 提供 `--force / --append / --skip-existing` 三态 | 高：跨 14 个 skill 改动 |

## 相关

- 用户原始 8 个缺陷列表来自 `~/.claude/projects/-Users-chang-Desktop-ai-------/memory/MEMORY.md`（待归档）
- 历史教训（CLAUDE.md §4）：重跑覆盖问题属于"应当询问但 AI 跳过了"的反模式
- [[review-style-feedback.md]] 提到的"确认型而非对抗型 review"是同源问题