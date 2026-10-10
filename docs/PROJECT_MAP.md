# Project Map — 参考 vs 开发

> 最近更新：2026-10-11（Phase 5 Distribution Closure）

本仓库是 Zhanghui 唯一 authoritative source。**我们只维护 canonical plugin 主体本身**。

## 架构结构

### 唯一权威源：canonical repo
`/Users/chang/Desktop/Code/zhanghui/`

| 路径 | 性质 | 说明 |
|---|---|---|
| `.claude/plugins/zhanghui/` | **开发** | canonical plugin 源码（唯一权威源） |
| `bin/install-plugin.sh` | **分发** | 唯一标准安装/检查/更新入口 |
| `.claude-plugin/marketplace.json` | **分发** | 指向本地 canonical plugin 源码 |
| `docs/` | **开发** | 实施计划、复盘报告 |
| `README.md` | **开发** | fork 开发与安装指南 |

### 分发关系闭环

```text
canonical repo (.claude/plugins/zhanghui/)
→ bin/install-plugin.sh
→ Claude Code 直接加载 canonical plugin
```

历史上的旧分发层（`webnovel-chang-marketplace` 独立副本、cache symlink、`deploy-plugin.sh` 白名单同步）已彻底废弃。
修改 plugin 代码后，Claude Code 直接读取最新源码，无需再做任何中间副本同步。

## 参考区（不要改）

- `.claude/sources/webnovel-writer-upstream/`：upstream fork 源快照，要对比时看这里
- `.claude/references/`：历史参考文档
- `references/`：外部参考库快照（只读，遵循 AGENTS.md 规则）