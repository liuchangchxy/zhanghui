# Multi-Volume Init Design

**日期**：2026-08-18
**状态**：Draft（待用户审）
**作者**：Claude (brainstorming + 4 个参考项目调研)

---

## 1. 背景与问题

**用户诉求**：在 init 阶段建立"全本卷骨架"以避免"写崩一卷 = 重做 N 卷"的风险。

**当前架构痛点**（三重锁）：
1. `webnovel-init` Step 1 只收 `target_chapters`，**不收总卷数**
2. `templates/output/大纲-总纲.md` 的卷划分表**只有 V1 一行**（`_inject_volume_rows` 行为）
3. `webnovel-plan` Step 9 硬规则"**不生成下一卷详细大纲/节拍/时间线/章纲**"，配 `test_plan_flow_writes_minimal_next_volume_anchor` 钉死

**参考项目调研结论**：
- 9 个参考项目里**没有任何一个**完整实现了"init 阶段逐卷询问 + 允许中途跳过"的 UX
- 主流三种形态：① AI 起草 + 用户编辑（StoryForge）② 先填总规模 + 系统拆卷（天命）③ **滚动规划（ainovel-cli）**
- 最值得借鉴：**ainovel-cli 状态模型**（后续卷可暂不存在）+ **StoryForge 交互外壳**（候选态、逐卷编辑）+ **天命字段 schema**（每卷字段化最完整）

---

## 2. 目标

让作者在 init 阶段能：
1. **交互式**填 V_1..V_k 的卷骨架（卷名 / 章节范围 / 核心冲突 / 卷末高潮）
2. **可选**让 AI 根据一句话创意起草候选卷（候选态，需用户接受）
3. **随时叫停**——没填的卷不进入项目状态，不伪造空白 V2-VN
4. 让 plan skill 能读取已填的 V+1 信息做更准的锚点回写

## 3. 非目标

- ❌ 不改 `webnovel-write`（依赖 plan 产物不变）
- ❌ 不强制用户承诺总卷数
- ❌ 不预填 V3-V20 空行（避免误导用户以为"必须填")
- ❌ 不删除现有 plan 测试 `test_plan_flow_writes_minimal_next_volume_anchor`（改断言语义）
- ❌ 不引入新外部依赖

---

## 4. 数据模型

### 4.1 新增字段（写入 `.webnovel/state.json`）

```yaml
project_info:
  # ... existing fields ...
  expected_total_volumes: 8        # 用户填的"预计几卷"，可空
  confirmed_through_volume: 1      # 当前 confirmed 的最大卷号
  later_volumes_status: deferred   # 见下表

# later_volumes_status 取值语义：
# - "deferred":  用户在 init 中**明确**选了"暂不确定"，后续 V_{k+1}+ 不进 volumes[]
# - "unknown":   用户还没回答是否继续（仅在 init 流程中间态存在，init 完成后必转为 deferred 或 volumes[] 中有更多项）
# - "planned":   AI 起草过 V_{k+1}+ 但用户未确认（仅 draft 状态，**不持久化**，仅运行时存在）

volumes:
  - index: 1
    title: 起势
    chapter_range: [1, 80]
    core_conflict: 主角必须在宗门考核中取得资格
    climax: 揭露长老作弊并夺得首席
    key_cool_points: [破境, 反杀]
    characters_to_appear: [林渊, 周长老]
    foreshadowing: []
    status: confirmed   # confirmed | draft | deferred
    source: human        # human | ai
    updated_at: 2026-08-18T10:30:00Z
```

### 4.2 状态机

```
                    用户接受 AI 候选
        ┌──────────────────────────────────┐
        ▼                                  │
   ┌─────────┐                        ┌─────────┐
   │ (空)    │   用户填写或 AI 起草    │  draft  │
   └─────────┘ ──────────────────────► └─────────┘
                                          │
                                          │ 用户确认
                                          ▼
                                    ┌──────────┐
                                    │confirmed │
                                    └──────────┘
                                          │
                                          │ 用户撤回
                                          ▼
                                    ┌──────────┐
                                    │ deferred │
                                    └──────────┘
```

**不变量**：
- `volumes[i].index` 必须连续无空洞（`confirmed_through_volume` 是其中最大值）
- `status=confirmed` 的卷字段不可被 AI 起草覆盖（除非用户主动重抽）
- `status=draft` 不能持久化到 `state.json`——只在内存中流转，候选确认后才升级为 `confirmed`
- `deferred` 卷的字段可全部为空

---

## 5. 四个核心组件

### 5.1 Volume Collector（采集器）

**职责**：在 init 阶段做 V_1 → V_k 的逐卷交互循环

**交互形式**（每次循环）：
```
[V_k 采集]
  卷名：
  预计章节范围（如 "1-80" 或 "约 60 章"）：
  核心冲突（一句话）：
  卷末高潮 / 状态变化：
  [可选] 关键爽点（最多 3 个）：
  [可选] 主要登场角色：
  [可选] 关键伏笔：
  
  接下来：
    A) 继续填 V_{k+1}
    B) 让 AI 起草 V_{k+1}
    C) 暂不确定，结束卷骨架采集
    D) 批量粘贴剩余卷（一次贴多行表格）
```

**边界**：只采集、只转换用户意图；不写文件；不调 AI

### 5.2 AI Volume Drafter（起草器）

**职责**：根据一句话创意 + 已确认卷上下文，起草下一卷的字段

**输入**：
- 一句话创意
- 已确认的 V_1..V_{k-1}（作为上下文，避免与已有冲突冲突）
- 题材 + 力量体系（从 `state.json` 读）

**输出**：`CandidateVolume`，结构与 `VolumeRecord` 相同但带 `status=draft, source=ai`

**边界**：纯生成；不持久化；不修改既有 confirmed 卷

**关键约束**：
- 必须复用现有参考项目设计——具体参考 `references/01-ai-webnovel-repos/.../novel-creator-skill/SKILL.md` 第 70-82 行（伏笔禁揭露规则）
- 不得从已确认卷推断新伏笔（避免"未来剧情泄露"denova `system.go:200` 的反模式）

### 5.3 Volume State Manager（状态管理）

**职责**：唯一事实真源——`volumes[]` 数组 + `planning_horizon` 元数据

**API**：
```python
list_volumes() -> List[VolumeRecord]
get_volume(index: int) -> VolumeRecord | None
append_draft(candidate: CandidateVolume) -> None  # 内存态，不写盘
confirm_volume(index: int) -> None                # draft → confirmed，写盘
revise_volume(index: int, fields: dict) -> None   # 用户手改字段，写盘
set_deferred(index: int) -> None                  # confirmed → deferred
load_planning_horizon() -> PlanningHorizon
```

**不变量验证**（每次状态变更后跑）：
- `volumes[i].index` 连续无空洞
- `status` 转换符合状态机
- AI 起草不能覆盖已 confirmed 字段

### 5.4 Plan Skill 集成层

**职责**：plan 流程读取新状态，写回 V+1 锚点

**改动点**：`webnovel-plan` SKILL.md 的 Step 9 一段

**改动前（line 336）**：
> "执行最小总纲写回（只更新 `大纲/总纲.md` 的 V+1 卷名 / 核心冲突 / 卷末高潮与伏笔表，**不生成下一卷详细大纲 / 节拍表 / 时间线 / 章纲**）"

**改动后**：
> "执行最小总纲写回：
> 1. 从 `state.json` 读 `volumes[]`；若 V+1 已 `confirmed`，用其字段回写总纲的 V+1 行
> 2. 若 V+1 `deferred` 或不存在，回写 V+1 行为空（保留 placeholder）
> 3. **不生成** V+2+ 详细大纲/节拍/时间线/章纲（与现行硬约束一致）"

**测试改动**：`test_plan_flow_writes_minimal_next_volume_anchor` 改断言：
- 旧断言："plan V1 后第2卷-详细大纲.md 不存在"
- 新断言："plan V1 后，若 V2 status=confirmed 则第2卷-详细大纲.md **不存在**（仍不预生成）；若 V2 status=deferred 则**只**总纲的 V2 行被填充，**不**生成第2卷-详细大纲.md"

---

## 6. 文件改动清单

| 文件 | 改动类型 | 关键变更 |
|---|---|---|
| `.claude/plugins/zhanghui/scripts/init_project.py` | 改 | `_build_master_outline` 路径**默认启用**（取代 `_inject_volume_rows`）；加 `expected_total_volumes` / `confirmed_through_volume` / `later_volumes_status` 字段写入 |
| `.claude/plugins/zhanghui/scripts/data_modules/volume_state.py` | **新增** | VolumeStateManager + CandidateVolume dataclass + 状态机校验 |
| `.claude/plugins/zhanghui/templates/output/大纲-总纲.md` | 改 | 卷划分表改为可扩展；加"卷字段说明"段 |
| `.claude/plugins/zhanghui/skills/webnovel-init/SKILL.md` | 改 | 加 Step 1.6（卷骨架采集循环）+ Step 5.5（AI 起草候选态） |
| `.claude/plugins/zhanghui/skills/webnovel-init/references/multi-volume-ux.md` | **新增** | 压缩 ainovel-cli / StoryForge / 天命 的设计原则 |
| `.claude/plugins/zhanghui/skills/webnovel-plan/SKILL.md` | 改 | Step 9 段落按本设计 §5.4 改写 |
| `.claude/plugins/zhanghui/scripts/tests/integration/test_init_volumes.py` | **新增** | 测采集循环、状态机、deferred 不持久化 |
| `.claude/plugins/zhanghui/scripts/tests/integration/test_plan_flow_writes_minimal_next_volume_anchor.py` | 改断言 | 按 §5.4 改 |

---

## 7. 测试策略

**TDD 顺序**（按 superpowers:test-driven-development）：
1. 先写 `volume_state.py` 的 dataclass + 状态机测试（红）
2. 实现 + 跑绿
3. 写 `init_project.py` 多卷生成测试（红）
4. 实现 + 跑绿
5. 改 plan skill 的测试断言（按 §5.4）
6. 端到端：用 `study/extracts/` 里现成的 fixture 跑一遍 init → plan → state.json check

**关键不变量测试**：
- 不填任何卷 → `volumes=[]`, `confirmed_through_volume=0`
- 只填 V1 → `volumes=[V1]`, `confirmed_through_volume=1`
- 填 V1+V2 → `volumes=[V1,V2]`, `confirmed_through_volume=2`
- AI draft **不能** 自动升级为 confirmed
- plan 后 V+1 锚点回写语义正确

---

## 8. 风险与未决问题

| 风险 | 缓解 |
|---|---|
| AI 起草的卷与已确认卷伏笔冲突 | Drafter 必读已确认卷字段；冲突阻断让用户裁决 |
| 用户中途放弃 init → 部分卷留下 | State Manager 持久化前确认；deferred 不写盘 |
| 现有 plan 测试改断言破坏行为 | 新断言比旧断言更严格（仍禁止 V+2+ 详细生成） |
| init SKILL.md 步骤变长用户疲劳 | 每卷字段支持"快速模式"（只填核心冲突 + 卷末高潮 2 项） |

**未决问题**（写实施计划时确认）：
- Drafter 调什么 LLM？沿用主 LLM 还是专门用 cheaper model？
- Drafter 是否允许在 init 阶段被多次调用（每卷都起草）？

---

## 9. 引用来源

- 内部：
  - `references/03-webnovel-writer-upstream/from-sources/upstream/docs/archive/superpowers/specs/2026-04-30-system-quality-fixes.md`（line 564 原文 "保留下一卷正式规划时的创作空间"）
  - `references/04-ai-agent-systems/ainovel-cli/`（状态模型）
  - `references/04-ai-agent-systems/storyforge/`（交互外壳）
  - `references/04-ai-agent-systems/tianming-novel-ai-writer/`（每卷字段 schema）
- 外部（craft wisdom）：
  - Robert McKee, *Story* — "structural flaws multiply, not diminish, at scale"
  - Blake Snyder, *Save the Cat* — 15-beat 卷级骨架
  - Stephen King, *On Writing* — Pantser 学派（反对面，用于约束本设计的"AI 必须有人介入"决策）