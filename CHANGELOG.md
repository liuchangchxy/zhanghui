# CHANGELOG

> 变更日志。新条目加在最上面。

## 2026-08-19 — safe-rerun 重构

### 新增

- `scripts/_shared/safe_overwrite.py`：覆盖守卫层，统一处理"重跑=三态询问"语义。提供 `ConflictMode` 枚举、`resolve_conflict()` 函数、`--on-conflict` CLI flag 解析。
- `scripts/check_plan_artifacts.py`：SKILL.md 落地的 CLI 工具，用于 plan 阶段检查所有 `.md` artifact 是否生成。
- 3 个 P0 脚本接入 `--on-conflict=overwrite|append|skip|ask` flag：
  - `update_master_outline.py` — 总纲写回
  - `chapter_commit.py` — 章节 commit
  - `snapshot_manager.py` — 快照冻结

### 破坏性变更（breaking change）

- 默认行为从"静默覆盖"改为"存在则报错"。
- 调用者必须显式传 `--on-conflict=<mode>`；不传时若目标已存在则抛 `FileExistsError`。
- 影响：`master-outline-sync` / `chapter-commit` / `update-state` / `snapshot_manager cmd_freeze`。
- 同时 `data_modules/memory_contract_adapter.py`（batch replay 路径）现在显式 `on_conflict="overwrite"` —— **不需要外部调用方关心，但实现内部已自包含**。
- `chapter_commit.py` 不再 double-write commit（移除冗余的 `persist_commit` 调用，仅由 `apply_projections` 内部统一写一次），避免 projection_status 中间态。

### 修复

- plan SKILL.md "覆盖时询问"声明首次落到脚本（`check_plan_artifacts` CLI 验证产物存在性）。
- `check_volume_md` 加 `.md` artifact 存在性检查（之前只看 JSON）。
- `hook_type` 枚举从 6 扩到 11（含别名"悬念钩"、"xwhook"等），与 SKILL.md 文档对齐。
- `chapter_meta` 字段白名单从 11 扩到 20（补 outline 字段）。
- 3 个 SKILL.md（plan/init/review）通过重跑守卫段落地：plan/init/review SKILL.md 在"重跑"场景下要求 SKILL 自己处理"已存在"产物，**脚本默认不再静默覆盖**。
- 2 个 SKILL.md 调用者显式传 `--on-conflict=overwrite`（plan/write）——这两个场景语义是"重跑就是覆盖"，显式声明后人类读者一眼能看明白。
- `dashboard/app.py` 经审计确认为只读（无写入路径需要升级），审计结果归档。
- 对抗性审查关键修复：
  - `snapshot_manager.discover_files` 拒绝 symlink（防止 `设定集 → /etc` 把外部文件读进 snapshot 引致数据外泄/磁盘爆满）。
  - `chapter_commit.py` 移除冗余的 `service.persist_commit` 调用 —— 仅由 `apply_projections` 内部统一写一次 commit，避免 projection_status 中间态。
  - `data_modules/memory_contract_adapter.py` 显式传 `on_conflict="overwrite"`（保持 batch replay 行为）。

### 测试

- 新增 30 个测试，覆盖 safe_overwrite 全部 ConflictMode 分支 + 3 个 P0 脚本的 conflict 路径 + 扩展字段白名单 + check_plan_artifacts 落地。
- 实际回归：修复 `update_master_outline.py` subprocess import fallback 后，655 个测试通过、4 个失败（3 个为本次修复的 regress 测试现已恢复 + 1 个 pre-existing `test_run_behavior_evals_fast_suite_passes_for_current_package`，与本次改动无关）。
- 已知 pre-existing failure：`test_run_behavior_evals_fast_suite_passes_for_current_package`（不相关 contract drift，与本次改动无关）。

### 引用

- 设计 spec：[`docs/superpowers/specs/2026-08-19-safe-rerun-design.md`](docs/superpowers/specs/2026-08-19-safe-rerun-design.md)
- 实施 plan：[`docs/superpowers/plans/2026-08-19-safe-rerun-design.md`](docs/superpowers/plans/2026-08-19-safe-rerun-design.md)