# webnovel-writer plugin 自包含化与跨平台分发设计

**日期**：2026-08-15（修订：原 spec 只覆盖自包含化；本修订加入跨平台分发 + Python 依赖自动安装）
**作者**：与 Claude Code 协作（superpowers:brainstorming）
**状态**：待用户审阅（修订中）

---

## 0. 目标与边界

### 0.1 一句话目标
把 fork 出来的 webnovel-writer plugin 重构为**自包含、可在任何书项目目录直接加载**，且具备**跨平台（macOS + Linux + Windows）自动安装 Python 依赖**的能力，通过 `webnovel-chang-marketplace` **公开分发**——用户装 marketplace 后零手动步骤可用；不再要求每个书项目手动配置 `.claude/`、不再依赖 dev workspace 的项目级 skill/scripts。

### 0.2 触发问题
用户报告：cd 到 `/Users/chang/Desktop/根源牌序/` 后 `/webnovel-init`、`/webnovel-doctor`、`/webnovel-write` 等 skill 无法正常使用，SessionStart hook 也跑不出正确输出。同一时刻在 dev workspace `zhanghui/` 下却能跑——说明 plugin 跟 dev workspace 耦合过紧。

### 0.3 明确不做的
- 不重新发明 webnovel-writer（保留 plugin 主体，只重构路径与目录布局）
- 不重写 Python 业务代码（chart-scan / dashboard / 根 scripts/ 保持当前实现，仅补依赖管理）
- 不砍任何 skill 功能（**含 fanqie**，虽然它是 BLOCKED_IMPLEMENTATION；用户明确"不能以牺牲功能为代价"）
- 不引入新功能（不解决"如何写好小说"，只解决"Claude Code 加载不动"和"依赖自动装"）
- 不改写 plugin 业务逻辑（review pipeline、story craft、init 流程的语义保持不变）
- 不做 GUI 弹窗（用 Claude Code 自身的 prompt 机制，跨平台一致）
- 不在 SessionStart 阻塞等装完（用户体验优先；后台并行安装）

### 0.4 约束
- **公开分发**：plugin 经 `webnovel-chang-marketplace` 公开，许可证 GPL-3.0（与上游一致）
- **跨平台**：macOS + Linux + Windows（不含 Windows ARM / Linux ARM；如未来需要再补）
- 平台差异：`macOS` 自带 python3（但版本不一） / `Linux` 通常有 python3 但版本可能 <3.11 / `Windows` 通常没有 python3；缺失时由 uv 自动下载
- Python 版本需求：>=3.11；缺失时由 uv 静默下载（用户无感）
- `_chang` 后缀保持（fork 身份区分，与上游 `webnovel-writer` 隔离）
- dev workspace 是纯本地、无 remote 的 git 仓库
- 现有 4e403ee 等 git 历史保留，重构是新 commit

---

## 1. 项目地图（重构前 vs 重构后）

### 1.1 重构前：参考与开发混杂

```
/Users/chang/Desktop/zhanghui/
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
/Users/chang/Desktop/zhanghui/           ← dev workspace（你唯一的项目）
├── .claude/
│   ├── settings.json                [开发] 只剩 enabledPlugins + 必要 permissions，无 hooks 覆写
│   ├── .webnovel-current-project    [开发] dev 指针（保留，README 说明仅 dev 用）
│   ├── plugins/zhanghui/  [开发] ★ plugin 源码（self-contained）
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
    ├── .claude-plugin/marketplace.json  声明 plugin: zhanghui
    └── zhanghui/           plugin 副本（dev 同步目标）

~/.claude/settings.json              [修改] 切换到 fork
    "marketplaces": { "webnovel-chang-marketplace": "<absolute path>" }
    "enabledPlugins": { "zhanghui@webnovel-chang-marketplace": true }

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
    ↓ 找到 enabledPlugins.zhanghui@webnovel-chang-marketplace: true
加载 marketplace webnovel-chang-marketplace
    ↓ 解析 .claude-plugin/marketplace.json
定位 plugin zhanghui
    ↓ 安装到 ~/.claude/plugins/cache/webnovel-chang-marketplace/zhanghui/
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
~/.claude/plugins/marketplaces/webnovel-chang-marketplace/zhanghui/   ← marketplace repo
    ↓ 首次安装时 cp 同步
~/.claude/plugins/cache/webnovel-chang-marketplace/zhanghui/         ← cache（Claude Code 实际加载）
    ↓ **必须建为 symlink** 指向
/Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui/      ← dev 源码
```

**关键**：cache 必须建为 `ln -sfn` 指向 dev workspace 的 plugin/，而不是把 marketplace 拷贝过来。任何对 dev workspace 的修改都立即被 Claude Code 感知（无需 rehash）。如果 cache 是普通目录而非 symlink，dev 修改不会生效，会出现「测试通过但实际加载的仍是旧版」的诡异问题。

**发布流程**：改完 dev workspace 代码后，跑 `scripts/sync_dev_to_marketplace.sh` 把代码同步到 marketplace 仓库（cache 通过 symlink 自动跟上），再 `sync_plugin_version.py --version X.Y.Z` 同步 version 字段。marketplace.json 字段按 https://docs.claude.com/en/docs/claude-code/marketplace 规范填写完整（`name` / `owner` / `plugins[].source` / `plugins[].description`），让 Claude Code 的 marketplace browser 能发现此 marketplace。

### 2.4 CLAUDE_PROJECT_DIR 的合法保留（不属反模式）

`scripts/project_locator.py`（约 6 处）与 `hooks/session_start.py:33` 仍读 `CLAUDE_PROJECT_DIR`——**这是有意保留**，因为 Claude Code 注入 CLAUDE_PROJECT_DIR 作为 workspace 提示，plugin 用它来 hint 项目根解析。

**禁止清理这两处**。`test_no_claude_project_dir_in_skills` 测试断言范围**仅限** `skills/**/*.md` 与 `agents/**/*.md`，不覆盖 scripts/ 与 hooks/。

---

## 3. 改名影响范围

| 位置 | 现状 | 重构后 |
|---|---|---|
| plugin 目录 | `plugins/webnovel-writer/` | `plugins/zhanghui/` |
| `plugin.json` 的 `name` | `"webnovel-writer"` | `"zhanghui"` |
| `plugin.json` 的 `version` | `"6.2.1"` | `"6.3.0"` |
| `enabledPlugins` key | `webnovel-writer@webnovel-writer-marketplace` | `zhanghui@webnovel-chang-marketplace` |
| marketplace 仓库 | `webnovel-writer-marketplace/` | `webnovel-chang-marketplace/` |
| `marketplace.json` `plugins[0].name` | `webnovel-writer` | `zhanghui` |
| `marketplace.json` `plugins[0].version` | 跟随 upstream | `6.3.0` |
| `sync_plugin_version.py` 检查路径 | 旧名 | 新名 |
| README / docs 字样 | 混用 | 统一为 `_chang` 后缀 |

`_chang` 后缀表明这是你的 fork，与 upstream `webnovel-writer` 完全隔离。

---

## 4. 改动清单

### 4.1 plugin 内部自包含化（最核心）

- **5 个项目级 skill 搬入 plugin**（每个 skill 自带 scripts 子目录；跨 skill 共享的脚本放 `plugins/zhanghui/scripts/_shared/`，避免重复）：
  - `webnovel-fast-write` ← `.claude/skills/webnovel-fast-write/` + 依赖 `changes_gate.py` / `context_slice.py` / `snapshot_manager.py` / `text_humanizer.py`
  - `webnovel-revise` ← `.claude/skills/webnovel-revise/` + 依赖 `revise_chapter.py` / `rejection_contract.py` / `normalize-punctuation.js`
  - `webnovel-deslop-check` ← `.claude/skills/webnovel-deslop-check/` + 依赖 `check-ai-patterns.js` / `text_humanizer.py`（共享）
  - `webnovel-resume` ← `.claude/skills/webnovel-resume/`
  - `webnovel-chart-scan` ← `.claude/skills/webnovel-chart-scan/`

- **被 plugin 自带 skill（webnovel-write / webnovel-style-profile）调用的脚本直接搬入 plugin 主 scripts/ 目录**：
  - `style_fingerprint.py` → `plugins/zhanghui/scripts/style_fingerprint.py`（被 webnovel-write 调）
  - `tracking_query.py` → `plugins/zhanghui/scripts/tracking_query.py`（被 webnovel-write 调）

- **共享脚本归位**：`text_humanizer.py` 同时被 fast-write 和 deslop-check 调用，统一放 `plugins/zhanghui/scripts/_shared/text_humanizer.py`，两个 skill 的 SKILL.md 用 `${CLAUDE_PLUGIN_ROOT}/scripts/_shared/text_humanizer.py` 引用

- **路径变量统一**：
  - `python` → `python3`（hooks.json + 所有 SKILL.md + 所有 agent md）
  - `${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}/.claude/...}` → 严格 `${CLAUDE_PLUGIN_ROOT:?}`
  - `${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}}/.claude/plugins/webnovel-writer/scripts` → `${CLAUDE_PLUGIN_ROOT}/scripts`（webnovel-write SKILL.md line 136 反模式）

- **`webnovel-init` 个人语料改路径**（顺手实现）：
  - **新功能**：`templates/个人语料.md` 与 `templates/写作宪法.md` 默认模板（首次创建），含空 schema + 示例
  - init 流程：把 templates/ 两份 copy 到 `<book>/.webnovel/writer-profile/`，用户编辑这里
  - `webnovel-write/SKILL.md:158` 等读取路径同步改为 `${PROJECT_ROOT}/.webnovel/writer-profile/个人语料.md`
  - 模板放 `plugins/zhanghui/templates/`（plugin root，非 skills/webnovel-init/）

### 4.2 dev workspace 瘦身

- `.claude/settings.json`：
  - 删除整个 `hooks` 块（marketplace 自带 hooks.json）
  - **重写** `permissions.allow`（不是只删过宽项，因为 Phase D 后 `.claude/scripts/` 与 `.claude/plugins/webnovel-writer/` 都不存在了）：
    - 删：`.claude/scripts/{changes_gate,tracking_query,style_fingerprint}.py` / `.claude/scripts/{check-ai-patterns,normalize-punctuation}.js` / `.claude/plugins/webnovel-writer/scripts/webnovel.py` / `.claude/plugins/webnovel-writer/scripts/data_modules/*` / `.claude/plugins/webnovel-writer/skills/webnovel-style-profile/*`
    - 加：`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/_shared/text_humanizer.py*)`、`Bash(node ${CLAUDE_PLUGIN_ROOT}/scripts/check-ai-patterns.js*)`、`Bash(node ${CLAUDE_PLUGIN_ROOT}/scripts/normalize-punctuation.js*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/style_fingerprint.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracking_query.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/changes_gate.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/context_slice.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/snapshot_manager.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/revise_chapter.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/rejection_contract.py*)`、`Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract_chapter_context.py*)`
    - 注：`${CLAUDE_PLUGIN_ROOT}` 在 settings.json 的 Bash allow 里被原样作为 glob 字符串处理（不展开），所以允许规则能匹配到任何 cache 路径下的对应脚本
  - `enabledPlugins.webnovel-writer` 裸名 → `zhanghui@webnovel-chang-marketplace`

- `.claude/skills/` → 删空（已搬入 plugin）

- `.claude/scripts/` → 删空（已搬入 plugin）

- `.claude/.webnovel-current-project` → 保留，README 说明仅 dev 用

- `.claude/references/` / `.claude/sources/` → 不动，gitignore 强化或 README 标注「参考、不在重构范围」

### 4.3 独立 marketplace 建立

- 创建目录 `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/`
- 写 `.claude-plugin/marketplace.json`，声明 plugin `zhanghui`
- 把 dev workspace 的 `plugins/zhanghui/` 同步到 `marketplaces/webnovel-chang-marketplace/zhanghui/`（首次手动 cp；后续可写 sync 脚本）
- 修改 `~/.claude/settings.json`：
  - 加 `marketplaces` 字段指向新 marketplace 路径
  - `enabledPlugins.zhanghui@webnovel-chang-marketplace: true`
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

- 保留 `plugins/zhanghui/scripts/tests/` 全部 pytest
- 新增 `plugins/zhanghui/scripts/tests/test_self_contained.py`：
  - 断言所有 SKILL.md 不含 `${CLAUDE_PROJECT_DIR}`
  - 断言所有 SKILL.md 用 `python3` 而非 `python`
  - 断言所有 `${CLAUDE_PLUGIN_ROOT}` 引用都解析到真实存在的路径
  - 断言 plugin 自带全部被引用脚本（无外部依赖）

### 4.6 跨平台 Python 依赖自动安装

**为什么需要**：plugin 内有 Python 依赖：

| 子模块 | 依赖（pyproject / requirements） |
|---|---|
| `webnovel-chart-scan` skill | `httpx + bs4 + pydantic + lxml` core + `playwright + chromium` 可选（150-300MB） |
| `dashboard/` web server | `fastapi + uvicorn + httpx + watchdog`（独立 `requirements.txt`，跟 chart-scan 完全分家） |
| 根 `scripts/*.py` | `pydantic`（**隐式依赖**，未在 pyproject/requirements 声明，需顺手修） |
| `hooks/*.py` | stdlib only ✅ |

公开 marketplace 分发要求用户**不感知**任何装依赖的动作。

#### 4.6.1 实现方案：uv bootstrapper + SessionStart 后台安装

**核心思想**：bundled `uv` 单文件二进制（~15MB，跨平台）作为 Python bootstrapper。SessionStart hook 检测每个 Python skill 的 venv 状态，后台 fork 子进程跑 `uv venv` + `uv pip install`，**不阻塞当前会话**。

**为什么选 uv**：
- 静态二进制单文件，bundled 进 plugin 简单
- 自带 Python 下载（缺 Python 的机器也能跑）
- 用 Rust 写的，比 pip 快 10-100×
- 跨平台行为一致（mac/linux/win 都是同一套 API）

#### 4.6.2 vendor/uv/ 布局

```
plugins/zhanghui/vendor/uv/
├── uv-darwin-arm64           ← macOS Apple Silicon
├── uv-darwin-x86_64          ← macOS Intel
├── uv-linux-x86_64           ← Linux x86_64
└── uv-windows-x86_64.exe     ← Windows x86_64
```

由 `scripts/sync_dev_to_marketplace.sh` 在 release 时从 https://github.com/astral-sh/uv/releases 下载 + sha256 校验，commit 进 git（不用 git LFS；uv 0.4.18 每个 binary 25-40MB，4 个合计 ~120MB；后续版本如变重再评估 LFS）。

#### 4.6.3 用户态缓存布局

```
~/.cache/webnovel-writer-chang/        ← 主路径（mac/linux/win 都解析到这）
├── venvs/
│   ├── webnovel-chart-scan/
│   │   ├── .install-stamp              ← 内容 = sha256(pyproject.toml + 任何 requirements.txt)（去重核心；任一文件可选）
│   │   └── .chromium-prompted          ← "yes" / "no" / 不存在（用户是否接受过 chromium 弹窗）
│   └── dashboard/
└── logs/
    ├── install-<skill>-<ts>.log
    └── session-start-<ts>.log
```

Windows 上 `%LOCALAPPDATA%` 解析为同一个 `~/.cache/` 路径（`os.path.expanduser` 在 Windows 也用 `%USERPROFILE%`）。

**.install-stamp 是核心去重机制**：每次 SessionStart hook 比对当前 `pyproject.toml` 和 `requirements.txt`（任一可选）的合并 sha256 与 stamp 内容，不匹配就重建 venv。plugin 升级时依赖清单内容变了 → 自动重装依赖，无需手动 bump 版本号。

#### 4.6.4 SessionStart 触发流（不阻塞会话）

```
SessionStart (session_start.py 扩展)
    │
    ├─ 扫描 ${CLAUDE_PLUGIN_ROOT}/skills/*/pyproject.toml
    │     + dashboard/ 目录
    │     → 枚举 Python 子模块列表 [webnovel-chart-scan, dashboard, ...]
    │
    ├─ 对每个 Python 子模块：
    │     ├─ venv 不存在 ────────────────→ 加入 install_queue（小依赖）
    │     ├─ .install-stamp 不匹配 ─────→ 加入 install_queue
    │     └─ venv 完好 + stamp 匹配 ───→ 跳过
    │
    ├─ 后台 fork 子进程跑 install_python_deps.py
    │     （**不阻塞当前会话**，用户在 hook 跑完后立刻能继续写代码）
    │
    └─ install_python_deps.py：
          1. 按当前平台选 vendor/uv/* 二进制
          2. uv venv ~/.cache/.../venvs/<module>
          3. uv pip install -e <module_dir>[本 module 的 extras]
          4. 写 .install-stamp = sha256(pyproject.toml + requirements.txt)
          5. 写 logs/install-<module>-<ts>.log
          6. 后台进程退出，下次 SessionStart 已就绪
```

**chromium 弹窗单独处理**（仅 webnovel-chart-scan）：
- 检测 `.chromium-prompted` 是否存在
- 不存在 → 通过 Claude prompt 问 "fanqie 需要 150MB chromium，装吗？(y/N)"
  - y → 写 `.chromium-prompted=yes` + 后台 `uv run playwright install chromium`
  - N → 写 `.chromium-prompted=no` + chart-scan 把 fanqie 永久 skip
- 存在 → 跳过弹窗，不再打扰

#### 4.6.5 错误处理

| 失败场景 | 行为 |
|---|---|
| 网络断 / PyPI 不可达 | 自动 fallback 到 PyPI 国内镜像（清华/阿里/中科大，CN IP 检测）；失败 3 次后写 log + 下次 SessionStart 重试 |
| `~/.cache/` 写不了（权限） | fallback 链：`~/Library/Caches/` (mac) → `%LOCALAPPDATA%` (win) → `$XDG_CACHE_HOME` (linux) → 项目根 `.webnovel/venv/` → 最后兜底报错让用户 export `WEBNOVEL_CACHE_DIR` |
| uv 二进制跟平台不匹配 | 报错 "找不到匹配的 uv，请检查 vendor/uv/"，不静默 |
| chromium 下载被中断 | 不影响 chart-scan 主流程；fanqie 走现有 BLOCKED_IMPLEMENTATION 报错路径（KNOWN_LIMITATIONS.md:14-16） |
| 后台 install 进程被杀 | 下次 SessionStart 重新检测 + 重试（stamp 不会写除非装成功） |
| 已有 venv 损坏 | 检测 `venv/bin/python --version`；失败则删了重建 |
| dashboard port 被占 | dashboard 启动前探测 8000 端口；被占则给清晰错误 + 提示改 `WEBVIEW_PORT` |

#### 4.6.6 测试策略

| 层 | 内容 |
|---|---|
| 单元 | `install_python_deps.py` 纯函数：stamp 计算、平台二进制选择、venv 路径解析、pyproject 解析（mock 实际 uv 调用） |
| 集成 | 干净 Docker 镜像（`python:3.11-slim` + 无 Python 的 `ubuntu:latest`）跑 SessionStart hook，断言 venv 创建 + stamp 正确 + 不阻塞 |
| 跨平台 CI | GitHub Actions matrix：macos-14 (arm64) / ubuntu-22.04 / windows-2022，每个跑 `pytest tests/install/ -v` |
| 冒烟 | 装好后真跑 `chart-scan --platform=qidian --top=3`，断言 `chart-scan/books.json` 至少含 3 个 BookItem |
| 升级触发重装 | 手动改 pyproject.toml bump lxml 版本 + 重启 SessionStart → venv 被重建 + stamp 更新 |
| **不测** | chromium 下载（CI 太大 + 慢 + 国内网络不稳） |

#### 4.6.7 新增/修改的文件

| 文件 | 操作 |
|---|---|
| `plugins/zhanghui/vendor/uv/*` | 新增（裸二进制 commit，不用 LFS） |
| `plugins/zhanghui/hooks/session_start.py` | 改：扩展检测 Python skill 依赖 + fork 后台进程 |
| `plugins/zhanghui/hooks/install_python_deps.py` | 新增：实际跑 uv 的脚本（纯函数 + 子进程封装） |
| `plugins/zhanghui/hooks/hooks.json` | 改：SessionStart timeout **默认** 30s（覆盖原 5s）；实现里保证「检测 + fork」步骤 < 2s 完成，超时只是兜底，**不会真用到** |
| `plugins/zhanghui/skills/webnovel-chart-scan/pyproject.toml` | 已有，确保 extras 标注清晰（fanqie / dev） |
| `plugins/zhanghui/dashboard/pyproject.toml` | **新增**（替代裸 `requirements.txt`，让 install 流程统一） |
| `plugins/zhanghui/scripts/` 隐式 `pydantic` 依赖 | 顺手补：加 `pyproject.toml` 或 `requirements.txt` 显式声明 |
| `plugins/zhanghui/scripts/tests/test_install_*.py` | 新增：install 流程的单元 + 集成测试 |
| `plugins/zhanghui/scripts/sync_dev_to_marketplace.sh` | 改：release 时同步 uv 二进制 |
| `README.md` | 改：加"首次使用会后台装依赖"说明 + 离线场景说明 + 镜像配置说明 |

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
| 单元测试 | `pytest plugins/zhanghui/scripts/tests/` | 全绿 |
| 自包含断言 | `pytest plugins/zhanghui/scripts/tests/test_self_contained.py` | 反模式扫描全 0 命中 |
| dev 加载测试 | `cd dev && claude → /webnovel-doctor` | 报 OK，hook 输出完整 |
| **根治测试** | `cd /Users/chang/Desktop/根源牌序 && claude → SessionStart 输出完整 → /webnovel-doctor` | 报 OK，**book 项目下零 `.claude/` 配置** |
| 写章节测试 | 在根源牌序 下跑 `/webnovel-init` 重做 → `/webnovel-write` 写一章 | 个人语料落在 `<book>/.webnovel/writer-profile/`；数据链完整 |
| **跨平台 install (CI)** | GitHub Actions matrix 跑 clean container（`ubuntu:22.04` 无 python3 / `python:3.11-slim` / `windows:2022`） | 三平台 venv 都建好 + stamp 正确 + SessionStart 不阻塞 |
| **升级触发重装** | 手动改 `pyproject.toml` bump lxml 版本 → 重启 SessionStart | venv 被重建 + stamp 更新（断言 `mtime` 与 `install-stamp` 内容都更新） |
| **chromium 弹窗** | 干净 venv + 跑 chart-scan | 弹窗出现一次 + y 后 chromium 安装 + `.chromium-prompted=yes` 写入 |
| **离线降级** | `pip` 指向不存在的镜像 + SessionStart | 失败 3 次后写 log，chart-scan 仍可跑（--platform=qidian 跳过 fanqie） |

---

## 7. 风险与兜底

| 风险 | 兜底 |
|---|---|
| cache symlink 失效（cache 6.2.1 → dev 副本的 hack） | 拆掉 symlink，重跑 `claude plugin install zhanghui@webnovel-chang-marketplace` |
| 现有 根源牌序 项目半初始化 state.json 残留（`project_info` 填了但 `init_completed` 缺失） | init skill 启动时检测 `progress.init_completed` 缺失则警告 + 给出 `--force` 选项 |
| dev 副本与 marketplace 副本 drift | README 写明「dev 时改 dev workspace 的 plugin/，发布时改 marketplace 仓库的 plugin/」双源约定；提供 `scripts/sync_dev_to_marketplace.sh` 一键 cp 同步 |
| `python3` 在某些 Linux 发行版指向 Python 2 | hooks 用 `python3 -X utf8` 字面量，依赖显式 python3；如未来要兼容 Linux，加一个 venv 探测脚本 |
| marketplace cache 与 marketplace repo 的 plugin version 不一致 | `sync_plugin_version.py --check` 在 CI 跑；marketplace.json 的 version 字段与 plugin.json 同步 |
| user-level settings.json 切换 enabledPlugins 后旧 plugin 残留 | 旧 `webnovel-writer@webnovel-writer-marketplace` 改为 `false` 而非删除，保留回滚路径 |
| **uv 二进制过时 / 有 CVE** | release 流程固定每月一次 bump uv；CVE 出现时 hotfix release；commit message 必须包含 uv 版本号 |
| **首次 SessionStart 后台 install 失败但用户没注意** | install 失败时 stderr 写到 `~/.cache/.../logs/`，下次 SessionStart 顶部 hook 输出明确说"上次的依赖安装失败，详见 logs/" |
| **PyPI 国内镜像同步滞后**（某新版本 lxml 已发布但清华镜像没跟上） | install_python_deps.py 同时尝试 PyPI 官方源 + 国内镜像，取先成功的；不强制走镜像 |
| **Windows 长路径问题**（`~/.cache/webnovel-writer-chang/...` 路径 > 260 字符） | Python 3.11+ 默认启用长路径支持；hooks 启动时检测 `sys.getwindowsversion()` 并显式 `import` 触发 enable_long_paths |
| **dashboard 跟 chart-scan 各自 venv 隔离**（避免依赖冲突） | 设计上两个独立 venv，不共享 site-packages；这意味着 dashboard 重装不影响 chart-scan，反之亦然 |
| **playwright 装 chromium 后磁盘占用 ~500MB** | README 写明磁盘预算；给 `WEBNOVEL_SKIP_CHROMIUM=1` env var 让 CI / 不想装的用户跳过 |

---

## 8. 不在范围（明确推迟）

- 把 upstream 同步策略自动化（merge upstream → fork 的流程留给后续 PR）
- ~~把 marketplace 发布到 GitHub releases~~ → **修订为 IN SCOPE**：本 spec 修订后将 marketplace 公开分发；具体的 GitHub release 流程（如打 tag、release notes 模板）放到第一个 release 时再做，本 spec 只要求 `marketplace.json` 字段填写完整
- webnovel-style-profile skill 的跨章漂移检测算法优化
- dashboard 前端的视觉重构
- agent 调度策略优化
- 引入新能力（如多书并行写、跨书知识图谱）
- Windows ARM / Linux ARM 平台（仅覆盖 mac+linux x86_64 + win x86_64；未来按需扩展）
- 跨平台 wheel 构建（依赖 uv 自动管；如 uv 出现兼容问题再单独处理）

---

## 9. 决策记录

| 决策点 | 选项 | 选定 | 理由 |
|---|---|---|---|
| 重构范围 | 彻底重做 / 最小修 / 只修 init | **彻底重做** | 用户选择 |
| 代码事实源 | marketplace repo / dev workspace / monorepo | **dev workspace** | 用户明确「就这一个项目」 |
| ~~开箱即用对象~~ → **分发受众（修订）** | 自用 / 公开 marketplace | **公开 marketplace（webnovel-chang-marketplace）** | 2026-08-15 修订：用户要求"换台电脑装也能用"，升级为公开分发 |
| 个人语料位置 | 书项目 / 用户 home / 保留 | **书项目 `.webnovel/writer-profile/`** | 用户选择 |
| dev skill 去留 | 全迁 plugin / 保留 dev / 部分迁 | **全部迁入 plugin** | 用户选择 |
| plugin 后缀 | 不改 / 加 `_chang` / 加 `_fork` | **`_chang`** | 用户选择 |
| 架构变体 | 复用上游 marketplace / 独立 marketplace / file:// 直装 | **独立 marketplace** | 用户选择 |
| 个人语料功能 | 顺手实现 / 删除 / 延后 | **顺手实现** | 用户选择；审查员发现代码里未实现，顺手补 |
| cache 同步策略 | symlink / cp / 双向 rsync | **symlink（强制）+ 同步脚本（可选）** | 审查员指出 cp 模式会导致 dev 修改不生效 |
| **平台覆盖（新增）** | 仅 macOS / mac+Linux / mac+Linux+Windows | **mac+Linux+Windows** | 用户 2026-08-15 选定 |
| **Python 依赖管理方案（新增）** | 手动装 / 全 vendor / SessionStart hook 自动装 / bundle Python | **uv bootstrapper + SessionStart 后台装** | 用户要求"用户体感无感"；uv 是当前最简方案 |
| **fanqie 命运（新增）** | 删 / 保留+默认 skip / 保留+显式弹窗 | **保留 + 显式弹窗** | 用户明确"不能以牺牲功能为代价" |
| **install 阻塞策略（新增）** | 阻塞会话 / 后台并行 / 进度条 | **后台并行** | 用户 2026-08-15 选定 |
| **venv 落点 fallback（新增）** | 仅 `~/.cache` / 多级 fallback | **多级 fallback（~/.cache → OS 标准 → 项目根 .webnovel/venv/）** | 实现细节；多级保安全 |
| **CI 测 chromium（新增）** | 测 / 不测 | **不测** | 实现细节（CI 太大 + 国内网络不稳） |
| **chromium 弹窗机制（新增）** | CLI 直接 y/N / Claude prompt | **Claude prompt** | 跨平台一致 + 复用了 Claude Code 自身 prompt 机制 |
