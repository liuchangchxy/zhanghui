# ai 写小说工具开发

为 webnovel-writer Claude Code 插件做的个人 skill 叠加层。解决三个具体痛点：
1. 长篇一致性崩坏
2. AI 味重
3. 流程繁琐

## 项目结构

```
~/Desktop/ai写小说工具开发/                ← 工具本体（git root）
├── .claude/
│   ├── plugins/
│   │   └── webnovel-writer/  ← vendored v6.2.1 upstream（git tracked）
│   ├── skills/               ← 本地独有 4 个（plugin 没有的）
│   ├── scripts/              ← CLI 工具
│   ├── references/           ← 协议/规则文档
│   ├── settings.json
│   └── hooks/                ← 由 plugin 提供
├── docs/                     ← 审查记录 + KNOWN_ISSUES + 历史快照
├── README.md
└── .git/

~/Desktop/根源牌序/                      ← 小说项目（独立 git root）
├── 大纲 设定集 正文 审查报告
├── .webnovel/
└── .claude → ~/Desktop/ai写小说工具开发/.claude  (软链)

~/References/ai-webnovel-repos/          ← 参考仓库（物理隔离，只读）
```

## 边界规则

1. **工具运行时只读** `.claude/`（本体）和**显式传入的 cwd**（项目）
2. **不读** `~/References/` 任何东西
3. **不递归扫描** `~/Desktop/` 找小说项目——必须靠 `cwd` 或 `.webnovel-current-project` 指针
4. **`webnovel-writer` plugin 已在 git 里**——`.gitignore` 不再排除；`git clone` 直接可用

## 安装

工具仓默认 `git clone` 即用。在另一个小说项目里复用：

```bash
cd /path/to/your-novel-project
ln -sfn ~/Desktop/ai写小说工具开发/.claude ./.claude
claude    # 启动后 plugin + 本地独有 skill 自动加载
```

或者从 `~/Desktop/根源牌序/` 直接启动（已配软链）。

## 三个本地 skill 的功能

| Skill | 跳过什么 | 保留什么 |
|---|---|---|
| `/webnovel-fast-write` | Step 2B 风格转译 + Step 3 reviewer + Step 4 polish | Step 4.5 CHANGES + 4.6 anti-slop |
| `/webnovel-deslop-check` | 写流程 | 仅扫描任意已有章节 |
| `/webnovel-resume` | 无 | workflow 断点恢复（用 `run-ledger` 子命令）|

## CHANGES 协议

每章末尾追加 `<chapter_changes>...</chapter_changes>` 块，8 个顶级字段声明本章对设定集/人物/物品/伏笔的所有变更。详见 `changes-protocol.md`。

## 测试

```bash
cd .claude/scripts && python3 -m pytest tests/ -q
cd .claude/plugins/webnovel-writer/scripts && python3 -m pytest tests/ -q
```

## 排错流程

```bash
# 1. 先跑 doctor 做项目体检
/webnovel-doctor --deep

# 2. hook 误伤合法操作时的逃生口
WEBNOVEL_DISABLE_RUNTIME_GUARD_HOOK=1 /webnovel-write

# 3. 查看 token 用量
ls .webnovel/observability/ 2>/dev/null
```