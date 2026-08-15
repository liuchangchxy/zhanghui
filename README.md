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

dev 模式下 cache 是 dev workspace 的 **symlink**，**修改立即生效**无需重启（但 hooks.json / plugin.json 改动建议重启一次）。

## ⚠️ 第一次开发：跑 setup_dev_env.sh

**这步不能跳过，跳过的话改了代码 Claude Code 看不到，plugin 直接挂。**

```bash
bash .claude/plugins/webnovel-writer_chang/scripts/dev-only/setup_dev_env.sh
```

这个脚本会：
1. 验证 plugin source 完整
2. 把 dev workspace 同步到 marketplace
3. **把 cache 建为指向 dev workspace 的 symlink**（spec §2.3 强制）
4. 验证 symlink 工作
5. 跑 smoke test

**幂等**：可重复跑。如果 cache 已经是 symlink 不会有任何改动。

SessionStart 已经加了自检——如果你忘了建 symlink 跑 setup_dev_env.sh，session_start 会在 stderr 警告你。

## 日常开发流程

```
1. 在 .claude/plugins/webnovel-writer_chang/ 里改代码
2. 保存
3. 重启 Claude Code（如果只改了 hooks.json / plugin.json，普通 .py 改动有时免重启）
4. 验证
```

**不要做**：
- ❌ 手动 cp / 复制文件到 cache
- ❌ 手动 cd 到 cache 改东西
- ❌ 跳过 setup_dev_env.sh

**如果 cache 变回普通目录**（比如手动 sync 出错）：再跑一次 setup_dev_env.sh 它会修正。

## 首次安装依赖

第一次跑 `claude` 时，plugin 会自动在后台装 Python 依赖（不需要你手动操作）：
- 装在 `~/.cache/webnovel-writer-chang/venvs/<module>/`
- SessionStart 后台 fork 子进程，不阻塞你的会话
- 装好后会写 `.install-stamp`，下次不再装

`webnovel-chart-scan` 的 fanqie adapter 需要 chromium（~150MB），会弹一次 y/N 让你选。

**离线场景**：默认从 PyPI 装；如果 PyPI 不可达会自动切国内镜像（清华/阿里）。要彻底离线请用 `WEBNOVEL_CACHE_DIR` 指向预装好的 venv。

**清理**：`rm -rf ~/.cache/webnovel-writer-chang/` 即可重装。

## 测试

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/ -v
```

## 同步到 marketplace（dev → marketplace）

```bash
bash .claude/plugins/webnovel-writer_chang/scripts/dev-only/sync_dev_to_marketplace.sh
```

跑这个脚本：rsync plugin + 验证 uv 4 个平台二进制 sha256。

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

## 常见问题

### SessionStart 警告 "plugin cache is not a symlink"

session_start.py 在 cache 不是 symlink 时会警告到 stderr。**修复**：跑 setup_dev_env.sh。

### 改了代码但 Claude Code 看不到

1. 确认 cache 是 symlink：`ls -la ~/.claude/plugins/cache/webnovel-chang-marketplace/`
2. 如果不是 symlink：跑 setup_dev_env.sh
3. 如果是 symlink 但内容不对：检查 `readlink` 指向的路径

### Python 依赖没装 / 装错了

```bash
rm -rf ~/.cache/webnovel-writer-chang/
# 下次 SessionStart 会自动重装
```

## 版本

当前 plugin version: 6.3.0（自我包含重构首发版）