# Safe Rerun Design — 2026-08-19

## GOAL（用户原话）

> 重跑一次都要问：到底是这个重写？还是改写部分？还是不改？

把这条行为契约系统化：让所有"重跑场景"在写入已存在文件前都必须弹出三态询问（重写 / 部分改写 / 不改）。

## 背景

2026-08-19 的"重跑/覆盖语义审计"（`study/extracts/2026-08-19-rerun-semantics-audit.md`）发现：

- 4 个 P0 脚本层强制覆盖（无任何提示）
- plan 的 8 个缺陷（2 个脚本可修）
- 3 处 SKILL.md 自称"覆盖时询问"但脚本不落地

完整证据见 audit 报告，本 spec 不重复。

## 决策记录（用户已逐项裁决）

| 维度 | 最终选择 | 备注 |
|------|---------|------|
| GOAL 用途 | 直接修代码 | — |
| 成功标准 | 4 个 P0 脚本遇覆盖就报错 | 用户后来扩展为"plan 8 个 + P0 4 个全修" |
| 兼容性 | 完全改写（breaking change） | **覆盖了** 苏格拉底式提问中"完全向后兼容"的选择 |
| plan 缺陷纳入 | 全部修复 | — |
| 实现方式 | A：逐缺口修补 | 不抽中间件、不做策略文件 |
| 三态机制 | 加 `--on-conflict=ask` 让人选三态 | ask 模式：调用 Claude Code `AskUserQuestion`；独立脚本降级 |
| 错误处理 | 确认（snapshot 备份 + 降级） | — |
| 测试策略 | 3 层：单测 + 集成 + SKILL.md 落地脚本 | — |

## 架构

```
┌────────────────────────────────────────────────────────────┐
│           webnovel-writer_chang (15 个 skill)               │
├────────────────────────────────────────────────────────────┤
│  SKILL.md (AI 提示)        写入函数 (scripts/*.py)        │
│  • 3 处"询问"声明 (撒谎)         • 4 个 P0 强制覆盖         │
│                                 • 2 个 plan 脚本可修         │
└────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────┐
│          新增：覆盖守卫层 (本 spec 的产出)                   │
├────────────────────────────────────────────────────────────┤
│  scripts/_shared/safe_overwrite.py                         │
│    - ConflictMode enum (overwrite/append/skip/ask)         │
│    - resolve_conflict()                                   │
│    - ask_via_claude_code() / fallback 降级                 │
│    - 接入 4 个 P0 + plan 2 处                                │
│                                                             │
│  scripts/check_plan_artifacts.py                           │
│    - 输入 --volume N / --chapter-range                     │
│    - 输出 {file, exists, last_modified}                    │
│    - 接入 3 个 SKILL.md (plan/init/review)                │
└────────────────────────────────────────────────────────────┘
```

## 组件清单（12 处改动）

### P0 类（脚本层强制覆盖 → 加守卫）

| # | 文件 | 函数 | 行 | 目标行为 |
|---|------|------|----|---------|
| 1 | `scripts/update_master_outline.py` | `_update_volume_table` | 121-162 | 默认 → `resolve_conflict` 报错；传 `--on-conflict` 才继续 |
| 2 | `scripts/chapter_commit.py` | `persist_commit` | 91-96 | 同上 |
| 3 | `scripts/snapshot_manager.py` | `cmd_freeze` | 121-137 | 同上；overwrite 才允许 `rmtree` |

### plan 类（脚本可修）

| # | 文件 | 行 | 改动 |
|---|------|----|------|
| 4 | `scripts/story_craft.py` | 237 | `VALID_HOOK_TYPES` 6 枚举 → 扩到 11 种（含"悬念钩"等别名）；用户已选的钩子全部可入库 |
| 5 | `scripts/story_craft.py` | 239-244 | `ALLOWED_CHAPTER_META_FIELDS` 11 字段 → 加 CBN/CPNs/CEN/must_cover/forbidden/strand/coolpoint/时间锚点/反派层级 |
| 6 | `scripts/data_modules/webnovel.py` | 467-523 | `check-volume` 加 `.md` 存在性检查；缺则 BLOCKER |

### SKILL.md 类（落地脚本）

| # | 文件 | 改动 |
|---|------|------|
| 7 | `skills/webnovel-plan/SKILL.md` Step 1 | 加 `webnovel.py check-plan-artifacts --volume N` 调用步骤 |
| 8 | `skills/webnovel-init/SKILL.md` Step 0 | 同上 |
| 9 | `skills/webnovel-review/SKILL.md` Step 4 | 加 `if Path.exists(): AskUserQuestion` 显式步骤 |

### 调用者同步升级（breaking change 一部分）

| # | 文件 | 行 | 改动 |
|---|------|----|------|
| 10 | `skills/webnovel-plan/SKILL.md` Step 4-7 | 所有 `master-outline-sync` / `update-state` 调用 | 加 `--on-conflict=overwrite`（明确意图：plan 默认是覆盖） |
| 11 | `skills/webnovel-write/SKILL.md` Step 5.5 | `chapter-commit` 调用 | 加 `--on-conflict=overwrite` |
| 12 | `dashboard/app.py` | 写入类调用 | 加 `--on-conflict` 透传 |

## 三态机制 API

### CLI flag

```bash
# 默认（缺省）：存在 → 报错退出
python scripts/update_master_outline.py --project-root ... --volume 1
# ERROR: 大纲/总纲.md V2 row 已存在。请传 --on-conflict=overwrite|append|skip|ask

# 显式覆盖
... --on-conflict=overwrite

# 显式追加（merge 到现有）
... --on-conflict=append

# 显式跳过
... --on-conflict=skip

# 显式询问（仅 Claude Code Skill 上下文有效）
... --on-conflict=ask
```

### Python helper（统一接口）

```python
# scripts/_shared/safe_overwrite.py
from enum import Enum

class ConflictMode(str, Enum):
    OVERWRITE = "overwrite"
    APPEND = "append"
    SKIP = "skip"
    ASK = "ask"

def resolve_conflict(
    path: Path,
    mode: str | None,
    *,
    append_op: Callable[[Path], None] | None = None,
) -> None:
    """如果 path 已存在且 mode=None → raise FileExistsError。
    否则按 mode 执行。

    mode=ASK 时调用 Claude Code AskUserQuestion；独立脚本降级。
    """
```

### Append 语义（每个写入点单独定义）

| 写入类型 | append 语义 |
|---------|-----------|
| 总纲 V+1 行 | 不支持 append → 报错 |
| `chapter_NNN.commit.json` | 不支持 append → 报错 |
| snapshot dir | append = 不 `rmtree`；新文件复制到现有 dir；manifest.json 增量更新 `chapter_files` 列表 |
| `chapter_meta[N]` | append = 不覆盖现有字段，merge 新字段 |
| hook_type / chapter_meta 白名单 | append = 追加允许值，不是覆盖文件 |

## 错误处理

| 场景 | 行为 |
|------|------|
| `--on-conflict=ask` 且 Claude Code 不可用（脚本独立跑） | 降级：报错 + 提示用户传 overwrite/append/skip |
| 用户在 `ask` 模式下选 skip | 写 `.webnovel/logs/conflict_skip-{ts}.json`，记录被跳过的内容 |
| 用户在 `ask` 模式下选 append，但 append_op 不支持该操作 | 报错 `此操作不支持 append 语义`，让用户重选 overwrite 或 skip |
| `--on-conflict=overwrite` 但写入中途失败 | 用 `backup_manager.py` 的 snapshot 机制，先备份再写；失败则从 snapshot 恢复 |

### 降级路径检测

```python
def _in_claude_code_context() -> bool:
    """检测是否在 Claude Code Skill 上下文（CLAUDE_PLUGIN_ROOT 环境变量）"""
    return os.environ.get("CLAUDE_PLUGIN_ROOT") is not None
```

ASK 模式下：
- `_in_claude_code_context()` 返回 True → 通过 stdout 输出结构化 JSON `{ask: true, options: [...]}`，由 Claude Code 主流程捕获并调用 `AskUserQuestion`（不在 Python 层直接调 tool）
- 返回 False → 报错"ASK 模式仅在 Claude Code 内可用"

## 测试策略

### 1. 单元测试（safe_overwrite.py）

| 用例 | 期望 |
|------|------|
| `path.exists() == False`, `mode=None` | 正常通过 |
| `path.exists() == True`, `mode=None` | 抛 `FileExistsError` |
| `path.exists() == True`, `mode='skip'` | 不修改，返回 log |
| `path.exists() == True`, `mode='overwrite'` | 允许后续覆盖 |
| `path.exists() == True`, `mode='append'` + append_op | 执行 append_op |
| `path.exists() == True`, `mode='append'` 但 append_op=None | 抛 ValueError |
| `mode='ask'` + Claude Code 上下文 | 调用 AskUserQuestion |
| `mode='ask'` + 独立脚本 | 报错降级路径 |

### 2. 集成测试（每个 P0 脚本）

| 脚本 | 测试场景 |
|------|---------|
| `update_master_outline` | V+1 行已存在 → 不传 flag 报错；传 overwrite 覆盖；传 skip 不修改 |
| `chapter_commit` | 已 accepted commit 再跑 → 不传 flag 报错；传 overwrite 重新提交 |
| `snapshot_manager cmd_freeze` | dir 已存在 → 不传 flag 报错；传 overwrite 清空重建 |

### 3. SKILL.md 落地脚本测试

`check_plan_artifacts`：
- 无 .md 时返回空列表
- 有 .md 时返回所有存在的文件 + 时间戳
- 与 `update-state --volume-planned` 联动验证

## 范围外（out of scope）

- 不抽通用 `safe_*` 中间件给未来新 skill 用（A 方案明确否决）
- 不写 `.webnovel/.policy.yaml` 策略文件（方案 C 明确否决）
- 不修存量 `scripts/tests/` 之外的旧测试
- 不改 `webnovel-writer_chang` 之外的项目

## 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Breaking change 触发用户已有工作流报错 | 中 | 中 | 在 CHANGELOG 标注；提供迁移指南 |
| `--on-conflict=ask` 在独立脚本中不可用导致卡住 | 低 | 高 | 降级路径明确报错；用户可选 overwrite/skip |
| snapshot 备份机制本身有 bug | 低 | 高 | 复用 `backup_manager.py` 已测试代码 |
| plan 8 个缺陷修了一半剩一半 | 中 | 中 | 测试用例覆盖每个字段名 |

## 验收标准

- ✅ 4 个 P0 脚本遇覆盖就报错，且报错信息含 `--on-conflict=overwrite|append|skip|ask`
- ✅ plan 8 个缺陷全修复（hook_type 11 枚举 + chapter_meta 20+ 字段 + check-volume 验 .md）
- ✅ 3 个 SKILL.md 通过 `check_plan_artifacts` 脚本落地
- ✅ 调用者（plan / write / dashboard）同步传 `--on-conflict=overwrite`
- ✅ 单元测试 8 用例全过 + 集成测试 3 脚本全过 + SKILL.md 落地测试 3 用例全过
- ✅ 现有 test suite 不被打破（`pytest scripts/tests/` 全过）

## 时间预算

- safe_overwrite.py + 单测：~2 小时
- P0 4 脚本接入：~3 小时
- plan 2 脚本修复：~2 小时
- SKILL.md 3 处落地：~1.5 小时
- 调用者 3 处升级：~1 小时
- 集成测试 + 验收：~2 小时

合计：**~12 小时**，1.5 个工作日。

## 相关文档

- 审计原文：`study/extracts/2026-08-19-rerun-semantics-audit.md`
- 已有 init overwrite 守卫参考：`scripts/init_project.py:423-444`（confirmed volumes 拒绝重 init）
- run-ledger 三态机制参考：`skills/webnovel-write/SKILL.md:174-180`

## 下一步

走 brainstorming skill → writing-plans skill，写实现 plan。