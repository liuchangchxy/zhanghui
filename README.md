# ai写小说工具开发

> 个人 fork 的 webnovel-writer 工具开发 workspace

## 这是什么

基于 [webnovel-writer](https://github.com/lingfengQAQ/webnovel-writer) 的个人 fork，加上 `_chang` 后缀做身份区分。**整个 fork 的目标：让 Claude Code 在任何书项目目录下直接加载这个 plugin，不要求书项目有 `.claude/` 配置。**

## 目录地图

详见 [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md)。

简版：
- `.claude/plugins/webnovel-writer_chang/` — 你开发的 plugin（self-contained）
- `docs/PROJECT_MAP.md` — 参考 vs 开发分层
- `docs/superpowers/specs/` — 设计文档
- `docs/superpowers/plans/` — 实施计划

## 加载机制

1. Claude Code 启动时读 `~/.claude/settings.json` 的 `enabledPlugins`
2. 找到 `webnovel-writer_chang@webnovel-chang-marketplace: true`
3. 加载 `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/` 里的 marketplace.json
4. 安装 plugin 到 `~/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang/`
5. 注入 `CLAUDE_PLUGIN_ROOT` 环境变量
6. plugin 自带的 hooks / skills / agents 全部可用

dev 模式下 cache 是 dev workspace 的 symlink，**修改立即生效**无需重启（但 hooks.json / plugin.json 改动建议重启一次）。

## 修改 plugin 代码

直接在 `.claude/plugins/webnovel-writer_chang/` 里改。完成后跑：
```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/ -v
```

## 同步到 marketplace（dev → marketplace）

```bash
bash .claude/plugins/webnovel-writer_chang/scripts/dev-only/sync_dev_to_marketplace.sh
```

（首次手动 cp 即可；后续可写 `scripts/sync_dev_to_marketplace.sh`）

## 写新章节

在任何书项目目录下：
```bash
cd /path/to/your-novel
claude
# 在 claude 里：
# /webnovel-init   # 首次初始化
# /webnovel-write  # 写章节
# /webnovel-doctor # 诊断
```

**书项目侧不需要任何 `.claude/` 配置。**

## 版本

当前 plugin version: 6.3.0（自我包含重构首发版）