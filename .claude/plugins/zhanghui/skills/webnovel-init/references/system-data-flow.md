---
name: system-data-flow-redirect
purpose: 重定向到权威版本
---

<context>
此文件已迁移到统一位置，避免多版本不同步问题。
</context>

<instructions>

## 权威版本位置

`${CLAUDE_PLUGIN_ROOT}/skills/webnovel-query/references/system-data-flow.md`

## 加载方式

```bash
cat "${CLAUDE_PLUGIN_ROOT}/skills/webnovel-query/references/system-data-flow.md"

```

## 快速参考

### 目录结构
```
项目根目录/
├── 正文/           # 章节文件
├── 大纲/           # 卷纲/章纲
├── 设定集/         # 世界观/力量体系/角色卡
└── .webnovel/
    ├── state.json          # 兼容状态投影（Story System commit 才是章节事实权威）
    ├── workflow_state.json # 工作流断点
    ├── index.db            # SQLite 索引
    └── archive/            # 归档数据

```

### 当前结构核心变化
- **事实提交边界**: `chapter-commit` 将本章 Canon 持久化到 `.story-system/commits/chapter_NNN.commit.json`，再运行下游投影
- **Data Agent**: 生成临时提取产物，不直接写 Canon 或状态投影
- **无 XML 标签**: 纯正文写作，提取产物经校验后由提交入口处理
- **SQLite 存储**: entities/aliases/state_changes 迁移到 index.db
- **state.json 精简**: 兼容投影，主要包含 progress/protagonist_state/strand_tracker/disambiguation

</instructions>
