# CHANGELOG

> 变更日志。新条目加在最上面。

## 2026-10-23 — 第一批 Literary Writing Skills

### 新增

- **`emotion-interiority`**：情绪从人物自己的感知、判断和选择里长出来，不由叙述者命名。
  明确**允许**内心独白与直接心理活动；禁止的是作者替人物下结论。核心链：
  触发 → 实际感知/反应 → 人物自己的判断 → 由此产生的选择。
- **`pov-distance`**：每一句都留在当前视角人物能感知、能知道的范围内；别人的内心只能从外部读；
  距离变化要有目的；人物不知道的事不能由叙述者宣布。
- **`sensory-description`**：细节由当前人物此刻真会注意到的东西决定，并参与判断、情绪或行动；
  不要求五感齐全，一个准确细节胜过一次打卡。

三个 Skill 均为 `writing-skills/<id>/SKILL.md`，走既有目录扫描发现，**未改 Router、注册表、
发现机制或校验规则**。

### 变更

- **`voice-style` 收窄**为纯文字声音：措辞、句段呼吸、套话、排比、比喻、不拔高。
  删除“只写身体和行为，不写情绪结论”（该条实际禁止了心理描写），情绪交 `emotion-interiority`，
  视角交 `pov-distance`，感官环境交 `sensory-description`。
- **`dialogue-subtext` 轻量整理**：删去“遮住名字也能分辨谁在说话”的声线职责，改为
  “各人回避与攻击方式不同”，并注明人物独特说话方式留给未来的 `character-voice`。

### 实验

- `study/experiments/2026-10-23-literary-skills-batch1-ab/`：两组受控单变量 A/B
  （第3章对峙章、第5章内省章），两臂共用同一 governed context 与同一 Creative Brief，
  唯一变量是 Skill 库（6 个 vs 9 个）。
- 结论：**`LITERARY_SKILLS_QUALITY_UNPROVEN`**。机制正常（发现、选择、翻译、校验全部通过，
  第5章两个新 Skill 均被选中），但正文文学表达没有出现方向一致的提升：
  两位盲评评委在每章上结论相反（第3章均分 B +0.45，第5章 A +0.25，两章合并仅 +0.10）；
  “规则太多/生硬执行”在第3章 B 臂偏高（+1.00），第5章互相抵消（+0.12），信号不稳定。
- 第5章最有信息量的不是分数而是失败模式之争：评委 1 认为 B 稿把方法执行成了
  编号小标题和完整推理链（“指导被过度字面执行”），评委 2 把同一段读成档案员的真实语域。
  分歧本身说明当前指导颗粒度还不足以稳定产出。
- 已知 blocker：无。第3章 B 臂只选中 `pov-distance`，两个新 Skill 未上场，该章无法归因；
  第5章两稿在“观测时次”这一 Canon 事实上互斥，属实验设计限制，非 Skill 缺陷。

## 2026-10-23 — Writing Skill Router

### 新增

- **`writing-skills/` 本地写作方法库**：目录即注册表。`writing-skills/<id>/SKILL.md` 用少量
  frontmatter（`id` / `name` / `purpose` / `applies_when` / `avoid_when` / `priority`）描述一种方法，
  正文存理论。新增/删除 Skill 不需要改任何 Python。
- **`writing_skill_registry.py`**：运行时扫描（插件内置 + 项目级 `.webnovel/writing-skills/`，
  同 id 项目覆盖内置）、选择校验（未知 id / 空指导 / 理论泄漏 / 5 个上限）、Writer 渲染。
- **`zhanghui:writing-skill-router` agent**：每章选择 2–5 个真正适用的技巧，并翻译成当前章节
  的具体写法；输出 `{selected_skills:[{id, reason, chapter_guidance}]}` 并通过
  `writing-skills validate` 自检。
- **CLI**：`writing-skills list` / `input` / `validate`；`runtime package` 与
  `runtime attach-creative-brief` 新增 `--skills-file` / `--skills-json`。
- **Writer 输出**：仅在 `writing_skills=True` 时追加“本章创作方法”编号列表，只含翻译后的指导，
  不含 id、reason、分数或理论名。选择指纹绑定进 `package_fingerprint`，`runtime status`
  暴露 `writing_skill_ids` 作为最小 provenance。
- **第一批 6 个 Skill**：`scene-sequel`、`reader-pull`、`information-gap`、`character-agency`、
  `dialogue-subtext`、`voice-style`，全部从仓库既有材料提炼，未引入外部理论。

### 实验

- `study/experiments/2026-10-23-writing-skill-router-ab/`：四类章节选择分化 + 热插拔验证 +
  第 3 章单变量 A/B。两名盲评评委均选 B → `WRITING_SKILL_ROUTER_SUPPORTED`。
  Prompt +1,573 bytes（+7.4%）；“规则太多”与“生硬执行技巧”两项 B 反而更低。

## 2026-10-17 — 6.5.0 正常用户验收返修

### 修复

- **发布版本号**：plugin.json / marketplace.json / README 同步到 `6.5.0`。PR #46/#47 合并后版本号仍停在 `6.4.0`，`claude plugin update zhanghui@zhanghui` 会直接返回 “already at the latest version”，老用户永远收不到修复。
- **`sync_plugin_version.py` 路径**：脚本原先假设 plugin 树就是仓库根，实际布局是 `<repo>/.claude/plugins/zhanghui` + `<repo>/.claude-plugin/marketplace.json`，导致发布辅助工具直接 `FileNotFoundError`。现已按现行布局解析，并新增回归测试。
- **修订计划定位**：`revise plan` 把 Reviewer 的 `第N行` 当成了“第 N 个非空段落”，标题和空行会让它落到另一段。现在行引用按**真实文件行号**解析；当行/段引用指向不同区间且 finding 的引用证据无法唯一裁决时，标记为 `line_paragraph_conflict`（不可自动应用），不再静默改错段落。
- **Agent 注册名**：Skills / 行为 fixture / `prose_quality_gate` 的 required action 仍写 `webnovel-writer:reviewer` 等旧插件命名；实际注册名是 `zhanghui:reviewer` / `zhanghui:context-agent` / `zhanghui:data-agent`。已统一，避免启用旧 `webnovel-writer` 插件时调用到错误的 agent。

### 回归测试

- `tests/unit/test_local_revision_and_judge.py`：`正文第N行（第N段）` 必须命中引用证据所在的行；无证据时拒绝猜测。
- `tests/unit/test_plugin_release_version_sync.py`：真实仓库布局下 `sync_plugin_version.py --check` 必须通过。
- `test_self_contained` / `test_distribution_integrity` 不再写死版本号，改为校验 plugin 与 marketplace 一致 + semver。

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