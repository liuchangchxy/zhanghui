# webnovel-writer plugin 自包含化重构设计

**日期**：2026-08-15
**作者**：与 Claude Code 协作（superpowers:brainstorming）
**状态**：待用户审阅

---

## 0. 目标与边界

### 0.1 一句话目标
把 fork 出来的 webnovel-writer plugin 重构为**自包含、可在任何书项目目录直接加载**，不再要求每个书项目手动配置 `.claude/`、不再依赖 dev workspace 的项目级 skill/scripts。

### 0.2 触发问题
用户报告：cd 到 `/Users/chang/Desktop/根源牌序/` 后 `/webnovel-init`、`/webnovel-doctor`、`/webnovel-write` 等 skill 无法正常使用，SessionStart hook 也跑不出正确输出。同一时刻在 dev workspace `ai写小说工具开发/` 下却能跑——说明 plugin 跟 dev workspace 耦合过紧。

### 0.3 明确不做的
- 不重新发明 webnovel-writer（保留 plugin 主体，只重构路径与目录布局）
- 不发布到公共 marketplace（仅自用，fork 重命名为 `_chang` 后缀做身份区分）
- 不引入新功能（不解决"如何写好小说"，只解决"Claude Code 加载不动"）
- 不改写 plugin 业务逻辑（review pipeline、story craft、init 流程的语义保持不变）

### 0.4 约束
- 纯自用，许可证兼容不是问题
- dev workspace 是纯本地、无 remote 的 git 仓库
- macOS Darwin 25.5.0，`python3` 可用、`python` 别名不可用
- 现有 4e403ee 等 git 历史保留，重构是新 commit

---

## 1. 项目地图（重构前 vs 重构后）

### 1.1 重构前：参考与开发混杂

```
/Users/chang/Desktop/ai写小说工具开发/
├── .claude/
│   ├── settings.json                [开发] dev 配置（含 hooks 覆写、过宽 permissions）
│   ├── .webnovel-current-project    [开发] dev 指针
│   │
│   ├── plugins/webnovel-writer/     [开发] ★ plugin 主体（跟 marketplace cache 软链耦合）
│   ├── skills/                      [开发] 5 个项目级 skill（fast-write/revise/deslop/resume/chart-scan）
│   ├── scripts/                     [开发] 10 个项目级脚本（changes_gate.py/check-ai-patterns.js/context_slice.py/normalize-punctuation.js/rejection_contract.py/revise_chapter.py/snapshot_manager.py/style_fingerprint.py/text_humanizer.py/tracking_query.py）
│   │
│   ├── references/                  [参考]
│   ├── sources/webnovel-writer-upstream/ [参考] fork 源快照
│   └── worktrees/                   [不动]
├── docs/                            [开发]
├── README.md                        [开发]
└── .git/
```

**问题**：
- 5 个项目级 skill + 10 个项目级脚本**只在 dev workspace 下能用**——任何书项目 cd 进去调不到
- plugin SKILL.md 内部多处 `${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}/.claude/...}` 反模式 fallback（仅 webnovel-write/SKILL.md 命中），marketplace 装到非 dev workspace 时必然失败
- 8 个 plugin 自带 SKILL.md（init/plan/write/dashboard/review/query/learn/doctor）用 `${CLAUDE_PROJECT_DIR:-$PWD}` 设 WORKSPACE_ROOT——marketplace 安装下 CLAUDE_PROJECT_DIR 不会被注入，fallback 到 PWD 在大多数场景凑巧能跑但不正确
- `个人语料.md` / `写作宪法.md` 当前在代码里**未实现**（templates/ 没这俩文件，init_project.py 也没对应代码路径）——重构顺手实现
- dev `settings.json` 用 `${CLAUDE_PROJECT_DIR}` 拼出 plugin 路径的 hooks 跟 marketplace 自带的 `${CLAUDE_PLUGIN_ROOT}` hooks 双跑双失败（dev settings.json 本身用 python3，但 hooks 引用了 dev 本地 plugin 路径）
- plugin `hooks/hooks.json` 全用 `python -X utf8`——macOS 上没 `python` 别名，hooks 实际跑不起来

### 1.2 重构后：参考、dev 配置、plugin 三层清晰

```
/Users/chang/Desktop/ai写小说工具开发/           ← dev workspace（你唯一的项目）
├── .claude/
│   ├── settings.json                [开发] 只剩 enabledPlugins + 必要 permissions，无 hooks 覆写
│   ├── .webnovel-current-project    [开发] dev 指针（保留，README 说明仅 dev 用）
│   ├── plugins/webnovel-writer_chang/  [开发] ★ plugin 源码（self-contained）
│   ├── references/                  [参考] 不动
│   ├── sources/webnovel-writer-upstream/ [参考] 不动
│   └── worktrees/                   [不动]
├── docs/
│   ├── superpowers/specs/<本设计文档>.md
│   ├── superpowers/plans/<由 writing-plans 产生>.md
│   ├── PROJECT_MAP.md               [开发] 新增：解释「参考 vs 开发」分层
│   ├── KNOWN_ISSUES.md              [开发] 删除 M-H8 / MED-5 / MED-52 反模式条目
│   └── ...（其它实施计划保留）
├── README.md                        [开发] 重写为 fork 开发指南
└── .git/

~/.claude/plugins/marketplaces/
└── webnovel-chang-marketplace/      [新增] 你专属的 marketplace
    ├── .claude-plugin/marketplace.json  声明 plugin: webnovel-writer_chang
    └── webnovel-writer_chang/           plugin 副本（dev 同步目标）

~/.claude/settings.json              [修改] 切换到 fork
    "marketplaces": { "webnovel-chang-marketplace": "<absolute path>" }
    "enabledPlugins": { "webnovel-writer_chang@webnovel-chang-marketplace": true }

<书项目>/（如 /Users/chang/Desktop/根源牌序/）   ← 零配置
    .webnovel/
    ├── state.json
    ├── backups/
    ├── summaries/
    ├── writer-profile/              ← 新位置：个人语料、写作宪法
    └── ...（其它 init 生成的文件）
    （不需要 .claude/！）
```

---

## 2. 目标架构

### 2.1 加载链

```
Claude Code 启动
    ↓
读取 ~/.claude/settings.json
    ↓ 找到 enabledPlugins.webnovel-writer_chang@webnovel-chang-marketplace: true
加载 marketplace webnovel-chang-marketplace
    ↓ 解析 .claude-plugin/marketplace.json
定位 plugin webnovel-writer_chang
    ↓ 安装到 ~/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang/
注入 CLAUDE_PLUGIN_ROOT 环境变量
    ↓ 指向 cache 路径（dev 模式可 symlink 到 dev workspace 加速）
加载 plugin 内容：
    ├── .claude-plugin/plugin.json     ← 注册 agents
    ├── hooks/hooks.json               ← 自动跑 SessionStart + PreToolUse guard
    ├── skills/  (10 个 SKILL.md)      ← 用户用 /webnovel-init 等命令时触发
    └── agents/  (4 个 agent md)       ← Skill 调用 subagent 时派发
    ↓
用户 cd 到任何书项目
    ↓
/webnovel-doctor → CLAUDE_PLUGIN_ROOT/scripts/webnovel.py 跑诊断
/webnovel-init   → 把 templates/ 内容 copy 到 <book>/.webnovel/writer-profile/
/webnovel-write  → 调 plugin 自带的 scripts（含原项目级 scripts/）
```

### 2.2 关键不变量

- **所有路径都从 `${CLAUDE_PLUGIN_ROOT}` 出发**，不再出现 `${CLAUDE_PROJECT_DIR}/.claude/...`
- **所有 python 调用都用 `python3 -X utf8`**，不再依赖 `python` 别名
- **plugin 自带全部运行时依赖**（webnovel.py、changes_gate.py、check-ai-patterns.js、text_humanizer.py 等），不依赖书项目或 dev workspace 里有 `.claude/scripts/`
- **个人用户数据落在书项目里**（`<book>/.webnovel/writer-profile/`），不落在 plugin 安装目录里（升级不丢）
- **书项目零 `.claude/` 配置**——所有 plugin 配置走 user 级 marketplace

### 2.3 dev workflow 与用户 workflow 合一（cache 走 symlink 是**强制**的，不是可选）

dev 模式下 plugin 三跳链路：
```
~/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/   ← marketplace repo
    ↓ 首次安装时 cp 同步
~/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang/         ← cache（Claude Code 实际加载）
    ↓ **必须建为 symlink** 指向
/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/      ← dev 源码
```

**关键**：cache 必须建为 `ln -sfn` 指向 dev workspace 的 plugin/，而不是把 marketplace 拷贝过来。任何对 dev workspace 的修改都立即被 Claude Code 感知（无需 rehash）。如果 cache 是普通目录而非 symlink，dev 修改不会生效，会出现「测试通过但实际加载的仍是旧版」的诡异问题。

**发布流程**（当前仅自用，未来如要发版）：改完 dev workspace 代码后，跑 `scripts/sync_dev_to_marketplace.sh` 把代码同步到 marketplace 仓库（cache 通过 symlink 自动跟上），再 `sync_plugin_version.py --version X.Y.Z` 同步 version 字段。

### 2.4 CLAUDE_PROJECT_DIR 的合法保留（不属反模式）

`scripts/project_locator.py`（约 6 处）与 `hooks/session_start.py:33` 仍读 `CLAUDE_PROJECT_DIR`——**这是有意保留**，因为 Claude Code 注入 CLAUDE_PROJECT_DIR 作为 workspace 提示，plugin 用它来 hint 项目根解析。

**禁止清理这两处**。`test_no_claude_project_dir_in_skills` 测试断言范围**仅限** `skills/**/*.md` 与 `agents/**/*.md`，不覆盖 scripts/ 与 hooks/。

---

## 3. 改名影响范围

| 位置 | 现状 | 重构后 |
|---|---|---|
| plugin 目录 | `plugins/webnovel-writer/` | `plugins/webnovel-writer_chang/` |
| `plugin.json` 的 `name` | `"webnovel-writer"` | `"webnovel-writer_chang"` |
| `plugin.json` 的 `version` | `"6.2.1"` | `"6.3.0"` |
| `enabledPlugins` key | `webnovel-writer@webnovel-writer-marketplace` | `webnovel-writer_chang@webnovel-chang-marketplace` |
| marketplace 仓库 | `webnovel-writer-marketplace/` | `webnovel-chang-marketplace/` |
| `marketplace.json` `plugins[0].name` | `webnovel-writer` | `webnovel-writer_chang` |
| `marketplace.json` `plugins[0].version` | 跟随 upstream | `6.3.0` |
| `sync_plugin_version.py` 检查路径 | 旧名 | 新名 |
| README / docs 字样 | 混用 | 统一为 `_chang` 后缀 |

`_chang` 后缀表明这是你的 fork，与 upstream `webnovel-writer` 完全隔离。

---

## 4. 改动清单

### 4.1 plugin 内部自包含化（最核心）

- **5 个项目级 skill 搬入 plugin**（每个 skill 自带 scripts 子目录；跨 skill 共享的脚本放 `plugins/webnovel-writer_chang/scripts/_shared/`，避免重复）：
  - `webnovel-fast-write` ← `.claude/skills/webnovel-fast-write/` + 依赖 `changes_gate.py` / `context_slice.py` / `snapshot_manager.py` / `text_humanizer.py`
  - `webnovel-revise` ← `.claude/skills/webnovel-revise/` + 依赖 `revise_chapter.py` / `rejection_contract.py` / `normalize-punctuation.js`
  - `webnovel-deslop-check` ← `.claude/skills/webnovel-deslop-check/` + 依赖 `check-ai-patterns.js` / `text_humanizer.py`（共享）
  - `webnovel-resume` ← `.claude/skills/webnovel-resume/`
  - `webnovel-chart-scan` ← `.claude/skills/webnovel-chart-scan/`

- **被 plugin 自带 skill（webnovel-write / webnovel-style-profile）调用的脚本直接搬入 plugin 主 scripts/ 目录**：
  - `style_fingerprint.py` → `plugins/webnovel-writer_chang/scripts/style_fingerprint.py`（被 webnovel-write 调）
  - `tracking_query.py` → `plugins/webnovel-writer_chang/scripts/tracking_query.py`（被 webnovel-write 调）

- **共享脚本归位**：`text_humanizer.py` 同时被 fast-write 和 deslop-check 调用，统一放 `plugins/webnovel-writer_chang/scripts/_shared/text_humanizer.py`，两个 skill 的 SKILL.md 用 `${CLAUDE_PLUGIN_ROOT}/scripts/_shared/text_humanizer.py` 引用

- **路径变量统一**：
  - `python` → `python3`（hooks.json + 所有 SKILL.md + 所有 agent md）
  - `${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}/.claude/...}` → 严格 `${CLAUDE_PLUGIN_ROOT:?}`
  - `${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}}/.claude/plugins/webnovel-writer/scripts` → `${CLAUDE_PLUGIN_ROOT}/scripts`（webnovel-write SKILL.md line 136 反模式）

- **`webnovel-init` 个人语料改路径**（顺手实现）：
  - **新功能**：`templates/个人语料.md` 与 `templates/写作宪法.md` 默认模板（首次创建），含空 schema + 示例
  - init 流程：把 templates/ 两份 copy 到 `<book>/.webnovel/writer-profile/`，用户编辑这里
  - `webnovel-write/SKILL.md:158` 等读取路径同步改为 `${PROJECT_ROOT}/.webnovel/writer-profile/个人语料.md`
  - 模板放 `plugins/webnovel-writer_chang/templates/`（plugin root，非 skills/webnovel-init/）

### 4.2 dev workspace 瘦身

- `.claude/settings.json`：
  - 删除整个 `hooks` 块（marketplace 自带 hooks.json）
  - **重写** `permissions.allow`（不是只删过宽项，因为 Phase D 后 `.claude/scripts/` 与 `.claude/plugins/webnovel-writer/` 都不存在了）：
    - 删：`.claude/scripts/{changes_gate,tracking_query,style_fingerprint}.py` / `.claude/scripts/{check-ai-patterns,normalize-punctuation}.js` / `.claude/plugins/webnovel-writer/scripts/webnovel.py` / `.claude/plugins/webnovel-writer/scripts/data_modules/*` / `.claude/plugins/webnovel-writer/skills/webnovel-style-profile/*`
    - 加：`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/_shared/text_humanizer.py*)`、`Bash(node ${CLAUDE_PLUGIN_ROOT}/scripts/check-ai-patterns.js*)`、`Bash(node ${CLAUDE_PLUGIN_ROOT}/scripts/normalize-punctuation.js*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/style_fingerprint.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracking_query.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/changes_gate.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/context_slice.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/snapshot_manager.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/revise_chapter.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/rejection_contract.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract_chapter_context.py*)`
    - 注：`${CLAUDE_PLUGIN_ROOT}` 在 settings.json 的 Bash allow 里被原样作为 glob 字符串处理（不展开），所以允许规则能匹配到任何 cache 路径下的对应脚本
  - `enabledPlugins.webnovel-writer` 裸名 → `webnovel-writer_chang@webnovel-chang-marketplace`

- `.claude/skills/` → 删空（已搬入 plugin）

- `.claude/scripts/` → 删空（已搬入 plugin）

- `.claude/.webnovel-current-project` → 保留，README 说明仅 dev 用

- `.claude/references/` / `.claude/sources/` → 不动，gitignore 强化或 README 标注「参考、不在重构范围」

### 4.3 独立 marketplace 建立

- 创建目录 `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/`
- 写 `.claude-plugin/marketplace.json`，声明 plugin `webnovel-writer_chang`
- 把 dev workspace 的 `plugins/webnovel-writer_chang/` 同步到 `marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/`（首次手动 cp；后续可写 sync 脚本）
- 修改 `~/.claude/settings.json`：
  - 加 `marketplaces` 字段指向新 marketplace 路径
  - `enabledPlugins.webnovel-writer_chang@webnovel-chang-marketplace: true`
  - 可选：保留 `webnovel-writer@webnovel-writer-marketplace: false`（切到 false 而不是删除，留可回滚路径）

### 4.4 文档

- 新增 `docs/PROJECT_MAP.md`：解释「参考 vs 开发」分层，画出重构后目录地图
- `README.md`：重写为 fork 开发指南
  - 删除软链安装教程
  - 增加：marketplace 安装、切换到 fork、dev 加速（symlink）说明
  - 增加：版本同步流程（dev → marketplace → cache）
- `docs/KNOWN_ISSUES.md`：
  - 删除 M-H8（CLAUDE_PLUGIN_ROOT 在项目级 symlink 安装时未设）——已根治
  - 删除 MED-5（Step 4.5/4.6 用 CLAUDE_PROJECT_DIR 拼接）——已根治
  - **保留 MED-52**：原意是 `.webnovel-current-project` 是项目级状态泄漏，与本次重构的路径问题无关，重构后保留此文件并标注「仅 dev workspace 内部用」

### 4.5 测试与验证脚本

- 保留 `plugins/webnovel-writer_chang/scripts/tests/` 全部 pytest
- 新增 `plugins/webnovel-writer_chang/scripts/tests/test_self_contained.py`：
  - 断言所有 SKILL.md 不含 `${CLAUDE_PROJECT_DIR}`
  - 断言所有 SKILL.md 用 `python3` 而非 `python`
  - 断言所有 `${CLAUDE_PLUGIN_ROOT}` 引用都解析到真实存在的路径
  - 断言 plugin 自带全部被引用脚本（无外部依赖）

---

## 5. 不动的东西

- `.claude/sources/webnovel-writer-upstream/`（fork 源快照，留着对比）
- `.claude/references/`（参考资料）
- `docs/` 下所有现有实施计划（保留作为重构实施记录）
- 现有 git 历史 4e403ee 及之前所有 commit（保留，重构是新 commit）
- plugin 业务逻辑（review pipeline、story craft、init 流程、reviewer agent 等的语义）
- 上游 `~/.claude/plugins/marketplaces/webnovel-writer-marketplace/`（Claude Code 自动管理的上游 marketplace，本机不该手动改；如不再使用可在 user settings 把 enabledPlugins 设 false）

---

## 6. 验证方法

| 测试 | 步骤 | 通过条件 |
|---|---|---|
| 单元测试 | `pytest plugins/webnovel-writer_chang/scripts/tests/` | 全绿 |
| 自包含断言 | `pytest plugins/webnovel-writer_chang/scripts/tests/test_self_contained.py` | 反模式扫描全 0 命中 |
| dev 加载测试 | `cd dev && claude → /webnovel-doctor` | 报 OK，hook 输出完整 |
| **根治测试** | `cd /Users/chang/Desktop/根源牌序 && claude → SessionStart 输出完整 → /webnovel-doctor` | 报 OK，**book 项目下零 `.claude/` 配置** |
| 写章节测试 | 在根源牌序 下跑 `/webnovel-init` 重做 → `/webnovel-write` 写一章 | 个人语料落在 `<book>/.webnovel/writer-profile/`；数据链完整 |

---

## 7. 风险与兜底

| 风险 | 兜底 |
|---|---|
| cache symlink 失效（cache 6.2.1 → dev 副本的 hack） | 拆掉 symlink，重跑 `claude plugin install webnovel-writer_chang@webnovel-chang-marketplace` |
| 现有 根源牌序 项目半初始化 state.json 残留（`project_info` 填了但 `init_completed` 缺失） | init skill 启动时检测 `progress.init_completed` 缺失则警告 + 给出 `--force` 选项 |
| dev 副本与 marketplace 副本 drift | README 写明「dev 时改 dev workspace 的 plugin/，发布时改 marketplace 仓库的 plugin/」双源约定；提供 `scripts/sync_dev_to_marketplace.sh` 一键 cp 同步 |
| `python3` 在某些 Linux 发行版指向 Python 2 | hooks 用 `python3 -X utf8` 字面量，依赖显式 python3；如未来要兼容 Linux，加一个 venv 探测脚本 |
| marketplace cache 与 marketplace repo 的 plugin version 不一致 | `sync_plugin_version.py --check` 在 CI 跑；marketplace.json 的 version 字段与 plugin.json 同步 |
| user-level settings.json 切换 enabledPlugins 后旧 plugin 残留 | 旧 `webnovel-writer@webnovel-writer-marketplace` 改为 `false` 而非删除，保留回滚路径 |

---

## 8. 不在范围（明确推迟）

- 把 upstream 同步策略自动化（merge upstream → fork 的流程留给后续 PR）
- 把 marketplace 发布到 GitHub releases（仅自用，不发布）
- webnovel-style-profile skill 的跨章漂移检测算法优化
- dashboard 前端的视觉重构
- agent 调度策略优化
- 引入新能力（如多书并行写、跨书知识图谱）

---

## 9. 决策记录

| 决策点 | 选项 | 选定 | 理由 |
|---|---|---|---|
| 重构范围 | 彻底重做 / 最小修 / 只修 init | **彻底重做** | 用户选择 |
| 代码事实源 | marketplace repo / dev workspace / monorepo | **dev workspace** | 用户明确「就这一个项目」 |
| 开箱即用对象 | 自用 / 发布 / 都做 | **只为自己用** | 用户选择 |
| 个人语料位置 | 书项目 / 用户 home / 保留 | **书项目 `.webnovel/writer-profile/`** | 用户选择 |
| dev skill 去留 | 全迁 plugin / 保留 dev / 部分迁 | **全部迁入 plugin** | 用户选择 |
| plugin 后缀 | 不改 / 加 `_chang` / 加 `_fork` | **`_chang`** | 用户选择 |
| 架构变体 | 复用上游 marketplace / 独立 marketplace / file:// 直装 | **独立 marketplace** | 用户选择 |
| 个人语料功能 | 顺手实现 / 删除 / 延后 | **顺手实现** | 用户选择；审查员发现代码里未实现，顺手补 |
| cache 同步策略 | symlink / cp / 双向 rsync | **symlink（强制）+ 同步脚本（可选）** | 审查员指出 cp 模式会导致 dev 修改不生效 |
