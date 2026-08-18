# ai写小说工具开发

为 webnovel-writer Claude Code 插件做的个人 skill 叠加层。解决三个具体痛点：
1. 长篇一致性崩坏
2. AI 味重
3. 流程繁琐

## 项目结构

```
ai写小说工具开发/
├── .claude/                  ← 核心实现（git tracked）
│   ├── scripts/
│   │   ├── changes_gate.py        CHANGES 协议 8 项校验 (R1-R8)
│   │   ├── text_humanizer.py      AI 词/弱化副词检测（from novel-creator-skill, MIT）
│   │   ├── check-ai-patterns.js   破折号/预告腔等实战漏网句式（from oh-story, MIT）
│   │   ├── normalize-punctuation.js  标点规范化
│   │   └── tests/                 40 个 pytest 测试
│   ├── references/
│   │   ├── changes-protocol.md    8 字段定义
│   │   ├── changes-examples.md    完整/极简/错误示例
│   │   └── deslop/                3 份 anti-slop 参考文档
│   └── skills/
│       ├── webnovel-write/skill.md    改造：注入 Step 4.5 + 4.6
│       ├── webnovel-fast-write/       新增：跳过 reviewer 的快车道
│       └── webnovel-deslop-check/     新增：写后独立扫描
├── docs/
│   └── superpowers/
│       ├── specs/2026-08-08-webnovel-writer-fork-design.md
│       └── plans/2026-08-08-webnovel-writer-fork-impl.md
├── ai-webnovel-repos/        本地参考（不在 git 里）
└── 小说写作/                 工作目录（不在 git 里）
```

## 安装（已经是项目级 skill，本仓库不能直接复用）

要把这个工具用到你自己的项目，需要：

1. 新建一个项目文件夹，比如 `~/novel-test-1/`
2. 在那个文件夹里建软链：
   ```bash
   ln -sfn ~/ai写小说工具开发/.claude ./.claude
   ```
3. 启动 `claude`（新会话）
4. 项目级 skill 会被自动加载，无需修改

测试环境未自带（请按上面第 1-2 步手动建一个）。

## 部署到 marketplace（每次 merge 到 main 后必跑）

Claude Code 从 `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/` 加载技能，不是从这个 source 目录。**改完代码必须跑 deploy 才能让 AI 看到新功能**：

```bash
bin/deploy-plugin.sh                # 真正同步
bin/deploy-plugin.sh --dry-run      # 看会同步哪些文件，不动 marketplace
bin/deploy-plugin.sh --skip-tests   # 不同步测试文件（默认会同步）
```

Source plugin 和 marketplace 是两份独立副本，**不是 symlink**。`sync_plugin_version.py` 只同步版本号字段，不同步文件；`bin/deploy-plugin.sh` 是新的 wrapper，负责文件同步 + 调用 version sync。

## 文档

- **设计文档**：`docs/superpowers/specs/2026-08-08-webnovel-writer-fork-design.md`
- **实施计划**：`docs/superpowers/plans/2026-08-08-webnovel-writer-fork-impl.md`

## 测试

```bash
cd .claude/scripts && python3 -m pytest tests/ -v
```

40 个测试覆盖 R1-R8 单元校验 + 10 个集成测试（5 正例 + 5 反例）。

## 排错流程

```bash
# 1. 先跑 doctor 做项目体检
/webnovel-doctor --deep

# 2. hook 误伤合法操作时的逃生口
WEBNOVEL_DISABLE_RUNTIME_GUARD_HOOK=1 /webnovel-write   # 临时绕过 guard_runtime_write hook

# 3. 查看 token 用量
ls .webnovel/observability/ 2>/dev/null
```

## 三个 skill 的功能

| Skill | 跳过什么 | 保留什么 |
|---|---|---|
| `/webnovel-write` | 无（完整流程） | 全部 |
| `/webnovel-fast-write` | Step 2B 风格转译 + Step 3 reviewer + Step 4 polish | Step 4.5 CHANGES + 4.6 anti-slop |
| `/webnovel-deslop-check` | 写流程 | 仅扫描任意已有章节 |
| `/webnovel-resume` | 无 | workflow 断点恢复（用 `run-ledger` 子命令）|
| `/webnovel-style-profile` | 无 | 文风指纹 + 漂移检测（≥ 3 章时建基线）|
- **Multi-volume init** (`webnovel-init` Step 1.6 + Step 5.5) — collect V1-VN skeleton with optional AI drafting; status state machine per spec `docs/superpowers/specs/2026-08-18-multi-volume-init-design.md`

## `--all-volumes` 模式（macro upfront + micro chunked）

`init_project.py` 新增 `--all-volumes` CLI 选项：

````markdown
```bash
python3 scripts/init_project.py <project_dir> <title> \
    --genre <genre> --target-chapters <N> --target-words <W> \
    --all-volumes
```
````

**效果**：一次性铺 N 卷蓝图（每卷产 `详细大纲.md` / `15节拍.md` / `时间线.md` 三件套）。

**默认行为不变**（无 `--all-volumes`）：只更新 V+1 锚点，与旧版本兼容。

详见 `docs/superpowers/specs/2026-08-19-macro-upfront-micro-chunked-design.md`。

## CHANGES 协议

每章末尾追加 `<chapter_changes>...</chapter_changes>` 块，8 个顶级字段声明本章对设定集/人物/物品/伏笔的所有变更。详见 `changes-protocol.md`。

## v2.0 — Story Craft Engine (2026-08-14)

Added 4 core narrative mechanisms to upgrade plan from form-level to craft-level:

- **15-Beat Save the Cat** (volume level) — forces Midpoint + All Is Lost (BLOCKER)
- **Scene-Sequel** (chapter level) — Goal/Conflict/Setback/Resolution/Reaction/Dilemma/Decision
- **草蛇灰线 5-field tracking** — foreshadow state machine with BLOCKER on overdue
- **Timed Lock + Rhythm Curve + Hook Type** — chapter-level discipline

### State.json Schema
New `story_craft` top-level field (optional, backward-compatible). Contains:
- `rhythm_curve` — chapter-level emotion peak tracking with warning/block thresholds
- `foreshadow_chain` — 5-field tracking (id/type/depth/buried_chapter/expected_payoff_chapter)
- `timed_locks` — chapter-level deadlines (e.g., "主角 3 章内出村")
- `thematic_echoes` — premise + per-chapter echo list
- `character_arc` — protagonist name + starting_state + ending_state + transformation
- `volume_beat` — 15-beat sheet with filled status per beat

### New CLI Commands
```
webnovel.py story-craft init-volume-beat --volume N --total-chapters M
webnovel.py story-craft fill-beat --volume N --beat-name "Midpoint" --chapter 25 --notes "..."
webnovel.py story-craft check-volume --volume N
webnovel.py story-craft init-forechains --volume N
webnovel.py story-craft init-locks --volume N
```

### webnovel-plan Changes
- New Step 4.5 (15-beat volume sheet)
- New Step 6.5 (foreshadow chain + timed locks)
- Step 7 extended with Scene-Sequel + beat fields
- New Step 8.5 (craft consistency check)

### Reviewer Extension
5 → 7 dimensions. Added: 节拍合规性 / 草蛇灰线合规性.

### Dashboard
4 new panels: `/craft/beat/{vol}` / `/craft/foreshadow` / `/craft/timed-locks` / `/craft/rhythm`

### Migration
Run `python3 scripts/migrate_story_craft.py <path/to/state.json>` to add the field to existing projects. Idempotent. Creates `.bak` before modifying.

### Tests
- 141+ tests passing
- TDD coverage for all 17 public functions in story_craft.py
- Integration tests for review_pipeline + plan flow

### New References
8 markdown files under `references/shared/`:
- 15-beat-save-the-cat.md
- scene-sequel.md
- foreshadow-chain.md
- timed-lock.md
- rhythm-curve.md
- chapter-hook-types.md
- character-arc.md
- thematic-echo.md
