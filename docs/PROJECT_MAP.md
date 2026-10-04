# Project Map — 参考 vs 开发

> 最近更新：2026-08-15（plugin self-contained 重构后）

这个 fork 是基于 upstream `lingfengQAQ/webnovel-writer` 的个人工作区。**我们只开发 plugin 主体本身**，其它都是参考。

## 三层结构

### 层 1：dev workspace（你唯一的项目）
`/Users/chang/Desktop/zhanghui/`

| 路径 | 性质 | 说明 |
|---|---|---|
| `.claude/plugins/webnovel-writer_chang/` | **开发** | plugin 源码（self-contained） |
| `.claude/settings.json` | **开发** | dev 配置（瘦身后只剩 enabledPlugins + 必要权限） |
| `.claude/.webnovel-current-project` | **开发** | dev 指针，仅 dev workspace 内部用 |
| `.claude/references/` | 参考 | 文档参考 |
| `.claude/sources/webnovel-writer-upstream/` | 参考 | upstream fork 源快照 |
| `.claude/worktrees/` | — | git worktree 目录 |
| `docs/` | **开发** | 实施计划、复盘报告 |
| `README.md` | **开发** | fork 开发指南 |

### 层 2：marketplace（plugin 发布仓库）
`~/.claude/plugins/marketplaces/webnovel-chang-marketplace/`

| 路径 | 性质 | 说明 |
|---|---|---|
| `.claude-plugin/marketplace.json` | **开发** | marketplace manifest |
| `webnovel-writer_chang/` | **开发** | plugin 副本（与 dev workspace 同步） |

### 层 3：cache（Claude Code 实际加载位置）
`~/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang/`

dev 模式下 symlink 到 dev workspace 的 `plugins/webnovel-writer_chang/`，修改立即生效。

## 修改规则

- **改 plugin 代码**：在 `.claude/plugins/webnovel-writer_chang/` 里改，cache 通过 symlink 自动 reload
- **改 plugin metadata**：plugin.json / hooks.json 在 plugin 目录里改
- **改 marketplace manifest**：直接改 `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/.claude-plugin/marketplace.json`
- **同步 dev → marketplace**：跑 `scripts/dev-only/sync_dev_to_marketplace.sh`

## 参考区（不要改）

- `.claude/sources/webnovel-writer-upstream/`：upstream fork 源快照，要对比时看这里
- `.claude/references/`：历史参考文档