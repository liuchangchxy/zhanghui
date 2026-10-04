# AGENTS.md — 项目级规则

本文件在每次 Codex 会话启动时自动加载。规则优先级：用户指令 > 本文件 > 默认行为。

## 1. 参考工具的存放（最重要）

> **永远不要把 reference 工具下载/clone 到 `/Users/chang/` 下的任何目录。**

❌ 禁止位置：
- `/Users/chang/References/`
- `/Users/chang/Downloads/`
- `/Users/chang/Desktop/`（除本项目根）
- `~/.Codex/plugins/marketplaces/`（marketplace 是 Codex 装插件用的，不是放参考的地方）

✅ 唯一允许的位置：`/Users/chang/Desktop/zhanghui/references/`

新下载/clone 参考工具的标准流程：
1. 下到 `references/0X-name/` 下，X 是递增编号
2. 更新 `references/INDEX.md`
3. 如有吸收项，在 `study/extracts/` 写提取文档
4. **不要 chmod +w references/**（已锁 0555，写入会失败）

## 2. 项目自包含原则

整个开发背景（包括所有参考、决策日志、吸收项）必须在 `/Users/chang/Desktop/zhanghui/`
这一个目录里完整可读。**不能依赖项目外的文件**（除了系统工具和用户偏好）。

## 3. references/ 与项目代码的分界

- `references/` — ⛔ **只读快照**，来源原始代码，**永远不改**
- `.claude/plugins/zhanghui/` — ✅ Zhanghui 当前 canonical source path；自有插件代码在这里维护。
- `.Codex/plugins/zhanghui/` — ⛔ 过期路径，**不要创建第二份实现**。本仓库不把插件源码复制或双写到此路径。
- `.claude/plugins/zhanghui/6.4.0/` — 已跟踪的版本化插件快照；架构源代码改动应落在上方 canonical source tree，不为同一功能维护平行实现。
- `study/` — ✅ 提取层和决策日志，记录"我们从参考学到了什么"

引用参考时必须有 cite：
```python
# from: study/extracts/2026-08-XX-foo-from-bar.md
def some_function():
    ...
```

## 4. 不重犯的错误

历史教训（2026-08-18 整理）：
- 之前参考散落 3 处，导致不知道下载了什么
- 参考目录里混入了我们自己的代码（style_fingerprint.py + webnovel-style-profile/）
- 同一份 webnovel-writer upstream 复制了 3 次

**新会话如果发现 references/ 外的位置有疑似 reference 工具，立即报告并清理。**
