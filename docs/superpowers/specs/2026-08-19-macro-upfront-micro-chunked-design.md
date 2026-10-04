# Macro-Upfront + Micro-Chunked Planning Design

**日期**：2026-08-19
**状态**：Draft（待用户审）
**作者**：Claude（基于 24 个本地参考项目横向调研 + craft wisdom 网络搜索）

---

## 1. 背景与问题

**用户诉求**：先 plan 好所有大纲再开始写。

**当前架构痛点**（四个独立锁）：

1. **`spec/2026-08-18-multi-volume-init-design.md` §5.4 显式禁止生成 V+2+ 详细大纲/节拍/时间线/章纲**
   - 钉死在 `test_plan_flow_writes_minimal_next_volume_anchor` 测试断言里
2. **`scripts/story_craft.py:315` 的 `init_volume_beat` 单卷硬限**
   - schema 是 `volume_beat: dict[vol]`，无法跨卷扩展
3. **`scripts/update_master_outline.py:37` 的 `_require_current_volume_artifacts`**
   - plan 后续卷强制要求"当前卷已经写过"
4. **`/webnovel-plan` 没有 `--all-volumes` 入口**
   - 只能一卷一卷 plan，跨卷蓝图不存在

**结果**：AI 在用户面前只能答"不能一次性生成所有大纲"——这**不是 plugin 没能力**，是 spec §5.4 显式禁止。

## 2. 第一性原理结论

### 2.1 craft wisdom 共识（网络调研）

**Plotter / Pantser / Plantser 三元**：

> "You can be a pantser, someone who writes by the seat of your pants. You can be a plotter, someone who needs to have a detailed outline for each of the plot points in your novel. You can even be a plantser, somewhere in between the two (like most writers, including me)."
> ——The Write Practice, "How To Write a Novel"

> "Neither method is inherently right or wrong… there is only the way that works best for you."
> ——Jane Friedman, on plotting vs discovery writing

**共识**：没有"对的方法"；成功相关的是 *finishing*，不是方法。McKee 的"结构必须在写前 deep understand"不等于"锁死所有 beat"。

### 2.2 工程层不变量（24 个本地参考项目横向）

`/Users/chang/Desktop/zhanghui/references/04-ai-agent-systems/`（19 个 agent）+ `01-ai-webnovel-repos/upstream/02-skills/`（5 个 skill）+ `02-Openwrite/` 共 **24 个项目**：

| 不变量 | 数据 |
|---|---|
| 写作阶段 1 章 / LLM call | **24/24**——`commit_chapter` / `write_chapter` / `draft_chapter` / `generate_chapter` 全是单章 |
| 唯一的"批"是 blueprint 阶段 | Openwrite / AI_NovelGenerator 的 chunked 是给**大纲**的，不是给**正文**的 |
| 状态回写闭环（CHANGES / ledger / foreshadow / promise ledger） | **18/24** 有显式实现 |
| 中途检查点（每 3 章或每卷） | **15/24** |

**为什么 1 章/call 是硬约束**：
- 单章 3000-5000 字 × 模型 context window = 工程上必须切分
- 每章独立 context 注入保证伏笔追踪可追溯
- 失败回滚粒度 = 1 章（Openwrite canonical packet 模式）

### 2.3 宏观规划范围的真实分裂（三派）

| 派别 | 项目数 | 代表项目 | 共同特征 |
|---|---|---|---|
| **一次性 upfront** | 6 | AI_NovelGenerator、show-me-the-story、Openwrite、chinese-novelist-skill、Chinese-WebNovel-Skill、MaliangAINovalWriter | 单 prompt 产全 N 章蓝图；用户确认后逐章写 |
| **滚动 / 按需扩张** | 7 | ainovel-cli（初始 2 卷 + V1 详细）、storyforge、denova、awesome-novel-agent、oh-story-claudecode（开书 10 章 + 中途扩纲）、tianming（每卷 AIGenerate + 全卷 batch）| 一次铺少量骨架；后续 append/expand |
| **无固定规划 / 状态演化** | 7 | autonovel、OpenFic、WenShape、neuro-book、character-arc、vela、QMAI、NovelClaw | 不在"一次性 vs 滚动"维度上谈；走 stateful + 局部请求 |

**关键自纠错**（来自调研）：之前把 ainovel-cli 归类为"纯 rolling"是错的。代码证据 `assets/prompts/architect-long.md` §"Layered Outline" "初始只包含 2 卷" + §"Story Compass"——**它必须 upfront 给出 2 卷骨架 + V1 第 1 弧详细**，否则 architect_long 启动不了。

### 2.4 真实模式

**没有任何项目是"纯 big-bang"或"纯 rolling"**。真实模式是：

```
宏观层（蓝图） = 按批次（upfront / 滚动 / 状态演化 三选一）
微观层（写作） = 1 章 / LLM call（硬约束）
状态层（CHANGES） = 每次 commit 写回（硬约束）
```

**这是 webnovel-writer plugin 应该对齐的架构**——不是"big-bang vs rolling 二选一"，是"宏观分批 + 微观 1 章"。

## 3. 目标

让 plugin 能交付"先 plan 好所有大纲再开始写"的需求，同时保留"随时调整下一卷"的灵活性：

1. **`/webnovel-plan` 支持 `--all-volumes` 选项**——一次铺 N 卷蓝图（每卷骨架 + 伏笔跨卷布局）
2. **每卷内部完整 plan**——15-beat + 章纲蓝图（每卷一次性产出，独立可执行）
3. **`/webnovel-write` 仍然是 1 章 / 调用**（不破硬约束）
4. **跨卷伏笔追踪**——承诺账本（Openwrite / neuro-book / QMAI 模式）
5. **中途检查点**——每 5-10 章回写 CHANGES + 状态校验（oh-story 模式）

## 4. 非目标

- ❌ 不强制用户承诺总卷数（保持 `expected_total_volumes: int | None`）
- ❌ 不改单章 1 调用约束
- ❌ 不预填 V3-V20 空行（避免误导）
- ❌ 不引入新外部依赖
- ❌ 不删除现有 `test_plan_flow_writes_minimal_next_volume_anchor`（改断言语义）

## 5. 数据模型

### 5.1 schema 迁移（`state.json`）

```yaml
project_info:
  # ... existing fields ...
  expected_total_volumes: 8        # 可空
  confirmed_through_volume: 1      # 现有字段，语义不变
  later_volumes_status: deferred   # deferred | unknown | planned
  cross_volume_foreshadowing: []   # 新增：跨卷伏笔账本

volumes:
  - index: 1
    title: 起势
    chapter_range: [1, 80]
    core_conflict: 主角必须在宗门考核中取得资格
    climax: 揭露长老作弊并夺得首席
    key_cool_points: [破境, 反杀]
    characters_to_appear: [林渊, 周长老]
    foreshadowing: [fs_001, fs_002]   # 引用跨卷伏笔账本
    status: confirmed
    source: human
    blueprint_path: 大纲/第1卷-详细大纲.md   # 新增：详细大纲文件路径
    beat_sheet_path: 大纲/第1卷-15节拍.md    # 新增：节拍表文件路径
    updated_at: 2026-08-19T10:30:00Z

story_craft:                        # 现有字段
  volume_beat:                      # 现有 schema：dict[vol, beat_sheet]
    "1": { ...15-beat 数据... }
  cross_volume_beat_map:            # 新增：跨卷节拍映射（卷→卷→beat）
    - from: 1
      to: 3
      beats: ["fs_001_payoff_in_arc2"]
  promise_ledger:                   # 新增：承诺账本（Openwrite 模式）
    - id: fs_001
      type: foreshadow
      depth: 3
      planted_chapter: 12
      planted_volume: 1
      expected_payoff_chapter: 145
      expected_payoff_volume: 3
      status: pending   # pending | advanced | paid_off | overdue
```

### 5.2 三层粒度约定（核心不变量）

| 层级 | 产出物 | 触发时机 | 批次大小 | 持久化 |
|---|---|---|---|---|
| **Layer 1: 跨卷骨架** | 总纲（`大纲-总纲.md`）、跨卷伏笔账本、节拍映射 | `/webnovel-plan --all-volumes` | 一次铺 N 卷 | 立即写盘 |
| **Layer 2: 卷内蓝图** | `第N卷-详细大纲.md`、`第N卷-15节拍.md`、`第N卷-时间线.md` | plan 流程 Step 4.5-6.5 | 每卷一次 | 写盘 |
| **Layer 3: 章节执行** | `第N章.md`、`第N章-CHANGES.md` | `/webnovel-write N` | **1 章 / 调用**（不破硬约束）| 写盘 + 状态回写 |

## 6. 四个核心组件（扩展上一版 spec）

### 6.1 保留现有 VolumeStateManager

**来源**：`scripts/data_modules/volume_state.py`（commit 580af18）

**新增 API**：
```python
def get_cross_volume_foreshadowing() -> List[ForeshadowEntry]
def upsert_promise_entry(entry: ForeshadowEntry) -> None
def get_promise_ledger_for_volume(index: int) -> List[ForeshadowEntry]
def advance_foreshadow(id: str, at_chapter: int) -> None
def payoff_foreshadow(id: str, at_chapter: int) -> None
def list_overdue_foreshadows(current_chapter: int) -> List[ForeshadowEntry]  # BLOCKER 触发
```

### 6.2 改 `webnovel-plan` SKILL.md —— 加 `--all-volumes` 入口

**当前**（line 336）：
> "执行最小总纲写回（只更新 `大纲/总纲.md` 的 V+1 卷名 / 核心冲突 / 卷末高潮与伏笔表，**不生成下一卷详细大纲 / 节拍表 / 时间线 / 章纲**）"

**新版本（保持 `--all-volumes` 可选）**：
```markdown
Step 9: 卷级蓝图生成（--all-volumes 模式）

  IF --all-volumes:
    1. 读 state.json 的 volumes[]（包含 expected_total_volumes 与 confirmed 卷）
    2. 对每个 confirmed 卷（不限于 V+1）：
       - 产 第N卷-详细大纲.md (15-beat + 章纲蓝图)
       - 产 第N卷-15节拍.md (Save the Cat beat sheet)
       - 产 第N卷-时间线.md (卷内时间线)
    3. 写跨卷伏笔账本 + 节拍映射（cross_volume_beat_map）
    4. 校验 index continuity + cross_volume_beat_map 无环路
  ELSE (单卷模式，默认):
    沿用现有逻辑：只更新 V+1 锚点
```

**关键兼容**：默认行为（无 `--all-volumes`）完全不变；现有测试继续通过。

### 6.3 改 `update_master_outline.py:37` 前置门

**当前**：`_require_current_volume_artifacts()` 强制当前卷已写。

**新版本**：
```python
def _require_current_volume_artifacts(volume_index: int, all_volumes_mode: bool = False):
    """在 --all-volumes 模式下，不需要当前卷已写过。"""
    if all_volumes_mode:
        return  # plan 阶段不需要前置 artifacts
    # 默认模式：保留现有逻辑
    ...
```

### 6.4 新增章节级 chunked 续写钩子（micro 层）

**来源参考**：denova 的 chapter-group plan + oh-story 的"中途快照每 3 章"。

```python
# scripts/data_modules/chunked_write.py
@dataclass
class ChunkedWritePolicy:
    chunk_size: int = 5       # 默认 5 章一批（denova 默认 ~3-8）
    snapshot_every: int = 3   # 每 3 章检查点（oh-story 模式）
    fore_check_threshold: int = 50  # 距离伏笔回收 N 章时 BLOCKER 警告

def should_take_snapshot(chapter: int) -> bool:
    return chapter % 3 == 0

def evaluate_pre_write_gates(chapter: int) -> List[Blocker]:
    """oh-story + tianming 六道门禁模式：写前检查跨卷伏笔是否 overdue。"""
    ...
```

**注意**：chunk_size 只影响"一次 commit 几章"的人体工学，**不是 1 章/调用的硬约束被打破**——每章仍独立 LLM call，只是 UI 把 N 章打包提交。

## 7. 文件改动清单

| 文件 | 改动类型 | 关键变更 |
|---|---|---|
| `.claude/plugins/zhanghui/scripts/story_craft.py` | 改 | `init_volume_beat()` 支持跨卷参数；新加 `init_cross_volume_beat_map()` |
| `.claude/plugins/zhanghui/scripts/update_master_outline.py` | 改 | `_require_current_volume_artifacts` 加 `all_volumes_mode` 参数；新增跨卷伏笔账本写入 |
| `.claude/plugins/zhanghui/scripts/init_project.py` | 改 | 加 `--all-volumes` CLI 入口；新增 `cross_volume_foreshadowing` / `promise_ledger` 字段 |
| `.claude/plugins/zhanghui/scripts/data_modules/chunked_write.py` | **新增** | `ChunkedWritePolicy` + `evaluate_pre_write_gates` |
| `.claude/plugins/zhanghui/scripts/data_modules/volume_state.py` | 改 | 加跨卷伏笔 / 承诺账本 API（§6.1） |
| `.claude/plugins/zhanghui/skills/webnovel-plan/SKILL.md` | 改 | Step 9 按 §6.2 加 `--all-volumes` 段落 |
| `.claude/plugins/zhanghui/skills/webnovel-write/SKILL.md` | 改 | 注入 chunked 续写钩子（Step 0：pre-write gate check） |
| `.claude/plugins/zhanghui/templates/output/大纲-总纲.md` | 改 | 加跨卷伏笔账本 + 节拍映射表头 |
| `.claude/plugins/zhanghui/scripts/tests/integration/test_plan_all_volumes.py` | **新增** | 测 N 卷蓝图一次性产出 + index continuity |
| `.claude/plugins/zhanghui/scripts/tests/integration/test_promise_ledger.py` | **新增** | 测伏笔账本 + overdue BLOCKER |
| `.claude/plugins/zhanghui/scripts/tests/integration/test_plan_flow_writes_minimal_next_volume_anchor.py` | 改断言 | 默认模式行为不变；新增 `--all-volumes` 模式分支 |

## 8. 测试策略

**TDD 顺序**：
1. 先写 `test_plan_all_volumes` 红：plan --all-volumes 一次性铺 V1-V8 蓝图
2. 写 `test_promise_ledger` 红：伏笔账本 + overdue BLOCKER
3. 写 `test_chunked_write_policy` 红：每 3 章快照 + pre-write gate
4. 实现 + 跑绿
5. 改 plan skill 的测试断言（默认模式保持 + `--all-volumes` 模式新分支）
6. 端到端：用 `study/extracts/` 里的 fixture 跑 init → plan --all-volumes → write

**关键不变量测试**：
- `volumes[i].index` 连续无空洞
- `cross_volume_beat_map` 无环路
- 伏笔 planted_volume < expected_payoff_volume
- overdue 伏笔触发 BLOCKER
- 默认（无 `--all-volumes`）行为与现行完全一致

## 9. 风险与未决问题

| 风险 | 缓解 |
|---|---|
| `--all-volumes` 一次性 LLM 调用 token 超限 | Chunked blueprint（AI_NovelGenerator 模式）：按 `chunk_size` 切片，分多次 LLM call 写 N 卷蓝图 |
| 用户中途调整 V3 卷纲 → 跨卷伏笔账本失效 | `revise_volume` 时联动 `cascade_foreshadow_impact()`（影响面分析） |
| chunked_write hook 误伤合法操作 | 提供 `WEBNOVEL_DISABLE_CHUNKED_GATE=1` 逃生口（参照现有 runtime guard hook 模式） |
| 默认模式行为意外变化 | 全部现有测试 + 默认路径回归测试必须通过 |

**未决问题**（实施计划时确认）：
- `--all-volumes` 一次铺全部卷 vs 一次铺 K 卷（如 K=4）的 UX
- chunk_size 是否暴露为可配置参数（denova 默认 3-8 章）

## 10. 与上一版 spec 的关系

**`2026-08-18-multi-volume-init-design.md` §5.4 写"不生成 V+2+ 详细大纲"**——这是本 spec **显式反对**的设计决策。本 spec 不是替换上一版 spec，是**扩展**：保留交互式 init + candidate 卷机制，新增 `--all-volumes` 选项让用户自主选择宏观模式。

**用户面接口**：
- `webnovel-init` 不变（仍交互式填 V1..Vk）
- `webnovel-plan` 加 `--all-volumes`（**可选**，默认 = 现状）
- `webnovel-write` 不变（1 章/调用）

**两个 spec 共存**：
- 上一版：解决"init 时怎么收集多卷"（采集 UX 层）
- 本版：解决"plan 时怎么铺 N 卷蓝图"（规划模式层）

## 11. 引用来源

### 内部（references/）
- `references/04-ai-agent-systems/ainovel-cli/assets/prompts/architect-long.md`（§"Layered Outline" "初始只包含 2 卷"）
- `references/04-ai-agent-systems/AI_NovelGenerator/prompt_definitions.py:267-358`（chapter_blueprint_prompt + chunked 续写）
- `references/04-ai-agent-systems/storyforge/src/lib/outline/generation-request.ts:4-7`（{kind:'volumes'/'chapters'/'single-volume'/'single-chapter'}）
- `references/04-ai-agent-systems/denova/internal/book/workspace_context.go:16`（workspaceContextChapterGroupLimit=2）
- `references/04-ai-agent-systems/Long-Novel-GPT/core/outline_writer.py:50-89`（单 chunk 一次性 chapter_titles + chapter_contents）
- `references/04-ai-agent-systems/tianming-novel-ai-writer/Modules/Generate/Elements/VolumeDesign/VolumeDesignViewModel/VolumeDesignViewModel.AIGenerate.cs:173-195`（BuildBatchGenerationPromptAsync）
- `references/04-ai-agent-systems/Openwrite/tools/architect.py:142-214`（generate_outline 一次性 N 章）
- `references/04-ai-agent-systems/Openwrite/tools/chapter_pipeline.py`（canonical packet 失败回滚）
- `references/01-ai-webnovel-repos/upstream/02-skills/oh-story-claudecode/skills/story-long-write/SKILL.md:180`（中途快照每 3 章 + tracking_commit check）
- `references/01-ai-webnovel-repos/upstream/02-skills/chinese-novelist-skill/SKILL.md:43+49-51+57`（phase2-planning 全章规划 + 每章创作前必读对应规划）

### 内部（项目内）
- `docs/superpowers/specs/2026-08-18-multi-volume-init-design.md`（上一版 spec，本 spec 显式扩展）
- `.claude/plugins/zhanghui/scripts/data_modules/volume_state.py`（VolumeStateManager 实现）

### 外部（craft wisdom）
- The Write Practice, "How To Write a Novel" — plantser 是大多数作家状态
- Jane Friedman — 共识：没有"对的方法"，成功相关的是 finishing
- Robert McKee, *Story* — "structural flaws multiply, not diminish, at scale"（结构必要但 ≠ 锁死）
- Blake Snyder, *Save the Cat* — 15-beat 卷级骨架（被 18/24 项目采用）
- Stephen King, *On Writing* — Pantser 学派（约束"AI 必须有人介入"）