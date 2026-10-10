# 章回 Zhanghui

> 让 AI 写完整本长篇网文 —— 一套跑在 [Claude Code](https://claude.com/claude-code) 里的长篇创作系统

章回不解决「生成一段好看的文字」，它解决的是：**写到第 800 章，设定还没崩、文风还没飘、伏笔还没丢。**

## 为什么叫「章回」

章回体是中文长篇连载小说的原生形态——一回落一章，回回相扣。这个工具的每一个设计都建立在「长篇连载」这个前提上：一致性数据链、跨章文风指纹、伏笔追踪、断点续写。脱离长篇，这些全无意义。名字直接指向它要解决的问题域。

## 三个痛点，三种做法

| 痛点 | 章回的做法 |
|---|---|
| **长篇一致性崩坏** | 正文稳定后刷新 Writer 的 CHANGES 声明；Data Agent 独立观察最终正文；reconciliation 对账后，仅获批的观察事实进入 `CHAPTER_COMMIT`，再更新可查的派生视图 |
| **AI 味重** | 双引擎 anti-slop 扫描（`text_humanizer.py` 查 AI 词与弱化副词 + `check-ai-patterns.js` 查破折号、预告腔等实战漏网句式），外加跨章文风指纹漂移检测 |
| **流程繁琐** | 14 个斜杠命令覆盖「调研 → 初始化 → 规划 → 写作 → 审查 → 局部重写 → 诊断」全链路；信任方向时可用 `/fast-write` 快车道跳过 reviewer，省 60–80% token |

## 装了什么

### 14 个命令

| 命令 | 用途 |
|---|---|
| `/webnovel-init` | 分阶段交互收集创作信息，生成项目骨架与约束文件 |
| `/webnovel-chart-scan` | 扫起点/番茄/纵横/七猫/刺猬猫榜单，调研题材、找对标书 |
| `/webnovel-deconstruct` | 拆解参考书，提取可迁移的创作模式 |
| `/webnovel-plan` | 基于总纲生成卷纲、时间线、章纲，增量写回设定集 |
| `/webnovel-write` | 写章节（默认 2000–2500 字），完整流程 |
| `/webnovel-fast-write` | 快车道写章，跳过 reviewer 与 polish |
| `/webnovel-review` | 多维度审查：设定一致性、时间线、叙事连贯、角色、逻辑、节拍、草蛇灰线、禁抄合规 |
| `/webnovel-revise` | 按 reviewer 的结构化反馈**局部**重写，只改标出的段落 |
| `/webnovel-deslop-check` | 对已有章节独立跑 anti-slop 扫描 |
| `/webnovel-query` | 查设定、角色、力量体系、势力、伏笔，支持紧急度与金手指状态 |
| `/webnovel-resume` | 从 ledger 断点恢复，提示「沿用 / 重写 / 查看」 |
| `/webnovel-learn` | 从当前会话提取成功写作模式，写入 `project_memory.json` |
| `/webnovel-doctor` | 只读体检：目录、文件、JSON、SQLite、RAG 配置、依赖 |
| `/webnovel-dashboard` | 启动只读管理面板，查看项目状态、实体图谱与章节内容 |

另有第 15 个 skill `/webnovel-style-profile`（无独立命令，写作流程内自动触发）：生成章节文风指纹并检测跨章漂移，仅做可计算的量化指标（句长 / 对话 / 标点 / 段长）。

### 4 个 agent

`context-agent`（写前 research，产出写作任务书）· `data-agent`（从正文抽取事实，生成 commit artifacts）· `deconstruction-agent`（从参考书抽模式）· `reviewer`（统一审查，输出结构化问题清单）

### 重跑守卫

`update_master_outline` / `chapter_commit` / `snapshot_manager` 默认「目标已存在就报错」，调用者必须显式传 `--on-conflict=overwrite|append|skip|ask`。杜绝脚本静默覆盖已有产物。实现见 `scripts/_shared/safe_overwrite.py`。

## 安装与启用

### 方式 A：从 GitHub 安装

```bash
claude plugin marketplace add liuchangchxy/zhanghui
claude plugin install zhanghui@zhanghui
```

装完在任意书项目目录下直接可用，**书项目侧不需要 `.claude/` 配置**。

### 方式 B：本地源码安装与更新（唯一 Authoritative 路径）

本仓库根目录是**唯一权威源码开发库**，插件本体位于 `.claude/plugins/zhanghui/`。
运行安装脚本即可直接将本地仓库注册并连接到 Claude Code，直接读取完整最新的 Skill 与 Runtime：

```bash
bin/install-plugin.sh
```

- 该命令会自动配置 Claude Code 直接从本地仓库加载 `zhanghui@zhanghui`。
- 修改代码后直接生效（无需手动执行 whitelist 复制）。
- 检查当前安装源：
  ```bash
  bin/install-plugin.sh --check
  ```

First run 时插件会在后台自动安装 Python 依赖到 `~/.cache/webnovel-writer-chang/venvs/`；`chart-scan` 的番茄 adapter 需要 chromium，会弹一次 y/N。PyPI 不可达时自动切清华/阿里镜像。清理：`rm -rf ~/.cache/webnovel-writer-chang/`。

## 使用

在任意书项目目录下启动即可，**书项目侧不需要任何 `.claude/` 配置**：

```bash
cd /path/to/your-novel
claude
```

```
/webnovel-init      # 首次初始化
/webnovel-plan      # 生成卷纲章纲
/webnovel-write     # 写章节
/webnovel-review    # 审查
/webnovel-doctor    # 诊断
```

## 开发与验证

本地修改代码后，直接由 `bin/install-plugin.sh` 保证一致加载，无需任何手工 whitelist 文件复制。

临时调试单次会话也可直接使用：
```bash
claude --plugin-dir .claude/plugins/zhanghui
```

### 测试

```bash
cd .claude/plugins/zhanghui/scripts && python3 -m pytest tests/ -v
```

## 已知待办

- `tests/test_run_behavior_evals.py` 当前 3 项失败（`skill_init_contract` / `skill_review_contract` / `write_blocks_before_commit`）——SKILL.md 内容与评测契约漂移，待修
- plugin 名 `zhanghui` 含下划线，非 kebab-case——Claude Code 可用，但上架 Claude.ai 目录要求 kebab-case

## 许可与来源

**GPL-3.0**（见 [`LICENSE`](LICENSE)）。本项目是 [lingfengQAQ/webnovel-writer](https://github.com/lingfengQAQ/webnovel-writer) 的个人 fork，
已吸收的第三方成果与完整署名见 [`NOTICE.md`](NOTICE.md)。

`references/`（本地调研用的第三方项目只读快照，2.1 GB）**不随仓库分发**。
