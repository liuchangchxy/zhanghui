# Writing Layered Plans Skill

## Overview

`writing-layered-plans` 是一个父子 skill，被 `interactive-planning` 自动调用，用于生成详细的 TDD 实施计划。

## 功能特性

- ✅ **Explore Phase**: 启动最多 3 个 Explore agents 并行理解代码
- ✅ **Design Phase**: Plan agent 设计实施方案
- ✅ **分层任务粒度**: Phase (1-2小时) + Step (2-5分钟)
- ✅ **强制 TDD**: RED→GREEN→REFACTOR 循环
- ✅ **Frontmatter 集成**: 使用 new-plan.ps1 或手动生成
- ✅ **完整代码**: 每个任务包含完整代码示例

## 使用方式

### 自动调用（推荐）

当使用 `interactive-planning` skill 时，它会：
1. 澄清需求
2. 确定三层架构
3. **自动调用** `writing-layered-plans` 生成详细任务

### 独立调用

当需求已明确时，直接使用：

```
我需要为 XXX 添加 YYY 功能。
需求已明确：...
请生成详细的实施计划。
```

## 技能关系

```
interactive-planning (父)
    ├── 需求澄清
    ├── 架构决策
    └── writing-layered-plans (子) ← 你在这里
            ├── Explore Phase
            ├── Design Phase
            └── 详细 TDD 任务
```

## 与 writing-plans 的区别

| 维度 | writing-plans | writing-layered-plans |
|------|--------------|---------------------|
| 上下文假设 | 零上下文 | 有 MEMORY.md + 文档树 |
| 文档结构 | 单层 | 三层 (Master/Phase/Step) |
| Frontmatter | 无 | 完整 YAML 元数据 |
| Explore | ❌ | ✅ 3 agents |
| 自动化 | 手动 | new-plan.ps1 集成 |

## 示例输出

技能会生成包含以下内容的计划：

```markdown
## Phase 1: 核心开发 (15 分钟)

### Step 1.1: 创建函数 ⏱️ 3 分钟
**Files:** `path/to/file.m`

**Step 1: Write failing test (RED)**
[完整测试代码]

**Step 2: Run → verify FAIL**
Run: `pytest test.py`
Expected: FAIL

**Step 3: Implement (GREEN)**
[完整实现代码]

**Step 4: Run → verify PASS**
Run: `pytest test.py`
Expected: PASS

**Step 5: Commit**
```bash
git add file.py
git commit -m "feat: add function"
```
```

## 相关文件

- **Skill**: `.claude/skills/writing-layered-plans/SKILL.md`
- **父技能**: `.claude/skills/interactive-planning/SKILL.md`
- **脚本**: `.claude/scripts/new-plan.ps1`
- **文档系统**: `atomic-foraging-cat.md`

## 技术细节

### CSO 优化
- 字数: 453 words (<500 ✅)
- 触发关键词: clear requirements, detailed plan, TDD, multi-file
- 描述以 "Use when" 开头

### 核心原则
1. **Explore First**: 先理解代码，再设计方案
2. **Layer Granularity**: Phase 粗，Step 细
3. **Mandatory TDD**: 每个任务必须有 RED→GREEN→REFACTOR
4. **Full Code**: 不写"添加XXX"，提供完整代码
