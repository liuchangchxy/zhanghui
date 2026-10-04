# Webnovel Foundation Hardening — Design Spec

**日期**: 2026-08-18
**作者**: Claude + 用户
**目标**: 在 zhanghui fork 上吸收 7 个跨卷一致性补丁，把地基从 �⭐⭐ 提到 ⭐⭐⭐⭐
**状态**: Approved (用户决定跳过逐节审批，会在生产中测试)

---

## 0. 决策摘要（已确认）

| 决策 | 选择 |
|---|---|
| 范围 | 全部 7 个补丁打包 |
| 顺序 | 依赖序：DAG → anchor → event_matrix → pacing → state_revision → reader_contract → derived_views |
| 执行强度 | 全部硬门禁（BLOCKER 级别） |
| 验证手段 | Fixture + Python 测试 |
| 架构 | C 方案：分层（core + patches + runner + skill 集成） |

---

## 1. 架构

### 1.1 模块树

```
scripts/consistency/                          ← 新建
├── __init__.py                               ← 暴露 ConsistencyRunner
├── core/
│   ├── __init__.py
│   ├── patch_base.py                         ← Patch ABC, Blocker, Context
│   ├── state_schema.py                       ← state.json 字段定义 + 迁移
│   └── runner.py                             ← 统一调度
├── patches/
│   ├── __init__.py
│   ├── p1_foreshadow_dag.py                  ← 伏笔 DAG
│   ├── p2_volume_anchor.py                   ← 大纲 anchor + 配额
│   ├── p3_event_matrix.py                    ← 事件矩阵防模式化
│   ├── p4_pacing_tracker.py                  ← 节奏 3 档追踪
│   ├── p5_state_revision.py                  ← expected_state_revision 防 stale
│   ├── p6_reader_contract.py                 ← 读者契约 5 维度
│   └── p7_derived_views.py                   ← 派生视图
└── cli.py                                    ← webnovel.py consistency <cmd>

tests/
├── unit/consistency/                         ← 单测
│   ├── test_p1_foreshadow_dag.py
│   ├── test_p2_volume_anchor.py
│   └── ...
├── integration/                              ← 集成测试
│   └── test_runner_e2e.py
└── fixtures/cross_volume/                    ← 合成项目
    ├── project_clean/                        ← 干净 baseline
    ├── project_dag_violation/                ← DAG 故意违规
    ├── project_anchor_overrun/               ← 配额超限
    ├── project_event_pattern_break/          ← 5 章同事件类型
    ├── project_pacing_drift/                 ← 节奏漂移
    ├── project_state_revision_stale/         ← state_revision 不匹配
    ├── project_reader_contract_breach/       ← 挖坑不填
    └── project_derived_view_mismatch/        ← 派生视图不一致
```

### 1.2 核心抽象

**Patch 接口**（`core/patch_base.py`）:
```python
class Patch(ABC):
    name: str                          # "foreshadow_dag"
    description: str
    depends_on: tuple[str, ...]        # 依赖的其他 patch
    
    @abstractmethod
    def check(self, ctx: CheckContext) -> list[Blocker]: ...
    
    @abstractmethod
    def apply(self, ctx: ApplyContext) -> None: ...
```

**数据类**:
```python
@dataclass
class CheckContext:
    project_root: Path
    chapter_num: int
    state: dict                        # state.json 解析后
    chapter_outline: dict | None       # 章纲或正文（写后阶段）
    previous_chapters: list[dict]      # 前 N 章摘要
    chapter_text: str | None           # 已写正文（仅 write/review 阶段有）

@dataclass
class ApplyContext:
    project_root: Path
    chapter_num: int
    state: dict

@dataclass
class Blocker:
    patch: str
    chapter: int
    message: str                       # 作者可读
    fix_hint: str                      # 怎么修
    # severity 永远 "blocker"（按用户决定）
```

**Runner**（`core/runner.py`）:
```python
class ConsistencyRunner:
    def __init__(self, project_root: Path, patches: list[Patch] | None = None):
        self.project_root = project_root
        self.patches = patches or self._default_patches()
    
    def _default_patches(self) -> list[Patch]:
        return [
            P1ForeshadowDAG(),
            P2VolumeAnchor(),
            P3EventMatrix(),
            P4PacingTracker(),
            P5StateRevision(),
            P6ReaderContract(),
            P7DerivedViews(),
        ]
    
    def run_all(self, chapter: int, *, chapter_outline=None, 
                chapter_text=None, prev_chapters=None) -> list[Blocker]:
        all_blockers = []
        for patch in self.patches:
            ctx = CheckContext(
                project_root=self.project_root,
                chapter_num=chapter,
                state=self._load_state(),
                chapter_outline=chapter_outline,
                previous_chapters=prev_chapters or self._load_summaries(chapter),
                chapter_text=chapter_text,
            )
            all_blockers.extend(patch.check(ctx))
        return all_blockers
    
    def apply_all(self, chapter: int) -> None:
        """plan 阶段 + write 后 commit 时调用，把 patch 状态写回 state.json"""
        ctx = ApplyContext(
            project_root=self.project_root,
            chapter_num=chapter,
            state=self._load_state(),
        )
        for patch in self.patches:
            patch.apply(ctx)
        self._save_state(ctx.state)
```

### 1.3 Skill 集成点（薄调用）

| Skill | 调用点 | 代码 |
|---|---|---|
| `webnovel-plan` Step 7 | 拆章完成后 | `runner.run_all(chapter=N, chapter_outline=outline)` → blocker 则用户改 |
| `webnovel-write` Step 2A | 写前 | `runner.run_all(chapter=N, chapter_outline=outline)` → blocker 则打回 |
| `webnovel-write` Step 5 | 写后 commit | `runner.apply_all(chapter=N)` 写回 state |
| `webnovel-review` | 现有 reviewer | 追加一致性维度报告 |

---

## 2. 数据模型：state.json 扩展

按依赖序定义。每加一个补丁，state.json 增加对应字段。**所有新字段都可选**（缺字段 = patch 报 "未初始化" blocker，要求先 init）。

### 2.1 补丁 1：伏笔 DAG（state 字段）

```json
{
  "story_craft": {
    "foreshadow_chain": {
      "version": 1,
      "dag": [
        {
          "id": "fs_001",
          "content": "主角获得神秘戒指",
          "level": "中层",
          "planted_chapter": 3,
          "paid_off_chapter": null,
          "status": "active",
          "depends_on": [],
          "introduced_by": "webnovel-plan/第1卷"
        }
      ],
      "validated_at": null,
      "validation_history": []
    }
  }
}
```

**Patch 行为**:
- `check`: 验证 DAG（无环 + 有向 + 可达 + 超期检测）
- `apply`: 把 init 阶段声明的伏笔写入 dag 数组

**算法**（移植自 Openwrite）:
```python
def validate_dag(dag: list[Foreshadow]) -> list[Blocker]:
    blockers = []
    
    # 1. 无环检测（DFS）
    if has_cycle(dag):
        blockers.append(Blocker(
            patch="foreshadow_dag",
            message="伏笔 DAG 存在循环引用",
            fix_hint="检查伏笔的 depends_on 是否形成回环"
        ))
    
    # 2. 有向：每个 active 伏笔的 planted_chapter < paid_off_chapter（如果已填）
    for fs in dag:
        if fs["status"] == "active" and fs["paid_off_chapter"] is not None:
            if fs["planted_chapter"] >= fs["paid_off_chapter"]:
                blockers.append(Blocker(...))
    
    # 3. 可达：每个 active 伏笔在 DAG 中有到 paid_off_chapter 的路径
    # 4. 超期：active 状态且当前 chapter > paid_off_chapter + 容忍窗口（如 50 章）
    
    return blockers
```

### 2.2 补丁 2：Volume anchor + 配额

```json
{
  "story_craft": {
    "volume_anchors": {
      "version": 1,
      "anchors": [
        {
          "volume": 1,
          "volume_name": "萧家崛起",
          "core_conflict": "萧炎 vs 三年之约",
          "volume_end_climax": "萧炎 vs 纳兰嫣然决斗",
          "must_not_reveal": ["药老真实身份"],
          "must_achieve": ["主角恢复修炼", "加入迦南学院"],
          "foreshadows_to_plant": ["fs_001"],
          "total_chapters": 30,
          "current_chapter": 0
        }
      ]
    }
  }
}
```

**Patch 行为**:
- `check`: 当前章是否在配额内、是否违反 must_not_reveal、是否推进了 must_achieve
- `apply`: 每卷完成时更新 current_chapter

**关键算法**:
```python
def check_anchor_quota(anchor, chapter_num) -> list[Blocker]:
    blockers = []
    
    # 配额检查：当前章是否在 [start, end] 范围
    if not (start <= chapter_num <= end):
        return []  # 不在本卷范围内，由其他逻辑处理
    
    # 进度比例 vs 配额
    progress = (chapter_num - start + 1) / total
    expected_progress = ...  # 根据节拍表算
    
    if abs(progress - expected_progress) > 0.15:  # 偏离 15% 报警
        blockers.append(Blocker(
            message=f"本卷进度偏离预期 {progress:.0%} vs 期望 {expected_progress:.0%}",
            fix_hint="加快/放缓节奏，或调整剩余章纲"
        ))
    
    # must_not_reveal 扫描
    if chapter_text_violates_must_not_reveal(anchor, chapter_text):
        blockers.append(Blocker(..., severity="blocker"))
    
    return blockers
```

### 2.3 补丁 3：Event Matrix

```json
{
  "story_craft": {
    "event_matrix_state": {
      "version": 1,
      "types": {
        "conflict_thrill":     {"cooldown": 2, "last_used_chapter": 5},
        "bond_deepening":      {"cooldown": 4, "last_used_chapter": 3},
        "faction_building":    {"cooldown": 4, "last_used_chapter": 7},
        "world_painting":      {"cooldown": 3, "last_used_chapter": 6},
        "tension_escalation":  {"cooldown": 2, "last_used_chapter": 4}
      },
      "history": [
        {"chapter": 1, "types": ["conflict_thrill"], "primary": "conflict_thrill"},
        {"chapter": 2, "types": ["tension_escalation", "world_painting"], "primary": "tension_escalation"}
      ],
      "gentle_window": 5,        # 每 5 章至少 1 个 soft type
      "max_consecutive_fast": 2 # 连续 fast 上限
    }
  }
}
```

**Patch 行为**:
- `check`: 当前章声明的事件类型是否违反冷却/连续/gentle 配额
- `apply`: 把当前章的事件类型记录到 history

### 2.4 补丁 4：Pacing 3 档

```json
{
  "story_craft": {
    "pacing_history": {
      "version": 1,
      "history": [
        {"chapter": 1, "tier": "fast", "event_types": ["conflict_thrill"]},
        {"chapter": 2, "tier": "medium", "event_types": ["tension_escalation"]},
        {"chapter": 3, "tier": "slow", "event_types": ["bond_deepening", "world_painting"]}
      ],
      "rules": {
        "max_consecutive_fast": 1,
        "slow_per_4_chapters_min": 1
      }
    }
  }
}
```

**Patch 行为**:
- `check`: 当前章 tier 是否违反连续快档上限、慢档配额
- `apply`: 当前章 tier 入 history

### 2.5 补丁 5：State Revision

```json
{
  "state": {
    "_revision": 17,
    "_last_modified_by": "webnovel-write/ch15",
    "_last_modified_at": "2026-08-18T..."
  }
}
```

**Patch 行为**:
- `check`: 写入时的 revision 与当前 state 的 revision 是否匹配（防止 stale 事务）
- `apply`: +1 revision，更新 modified_by/at

### 2.6 补丁 6：Reader Contract

```json
{
  "story_craft": {
    "reader_contract": {
      "version": 1,
      "expectation_debt": [
        {"id": "exp_001", "created_chapter": 5, "category": "主角能力", "satisfied_chapter": null}
      ],
      "causal_credits": {
        "protagonist_actions_used_without_setup": []
      },
      "endgame_reserves": ["最终决战伏笔", "终局揭示"],
      "swap_debts": []
    }
  }
}
```

**Patch 行为**:
- `check`: 当前章是否新增期待债、是否偿还旧债、是否使用未铺垫的能力、是否消耗终局底牌
- `apply`: 更新 expectation_debt、causal_credits

### 2.7 补丁 7：Derived Views

不存新字段，**从已有字段派生**。例如:
- `summary.md` 派生自 state 的伏笔/角色当前状态
- `foreshadow_table.md` 派生自 `foreshadow_chain.dag`
- `pacing_chart.md` 派生自 `pacing_history.history`

**Patch 行为**:
- `check`: 派生文件是否存在 + 是否与源 state 一致（如 hash 对比）
- `apply`: 重新生成派生文件

---

## 3. CLI 表面

```bash
# 跑所有 7 个补丁
python webnovel.py consistency check --project-root /path --chapter 15

# 只跑某个补丁
python webnovel.py consistency check --patch foreshadow_dag --chapter 15

# init 阶段：初始化所有 state 字段（plan 时用）
python webnovel.py consistency init --volume 1

# 列出当前所有 blocker
python webnovel.py consistency list --chapter 15

# 强制绕过（仅紧急用）
python webnovel.py consistency override --chapter 15 --reason "用户已确认"
```

---

## 4. 测试策略

每个补丁 = 1 个 fixture + 1 个单测 + 1 个集成测试。

### Fixture 项目结构

```
tests/fixtures/cross_volume/project_X/
├── 大纲/
│   └── 总纲.md
├── 设定集/
├── 正文/                       ← 合成章节（不必真写，可用模板生成）
│   ├── 第0001章-*.md
│   ├── 第0002章-*.md
│   └── ...
├── .webnovel/
│   ├── state.json             ← 含所有 patch 字段
│   └── summaries/
└── README.md                  ← 说明这个 fixture 故意触发哪个 patch
```

### 测试用例结构

```python
# tests/unit/consistency/test_p1_foreshadow_dag.py
def test_dag_validation_clean():
    """干净 fixture 应通过"""
    runner = ConsistencyRunner(PROJECT_CLEAN)
    blockers = runner.run_all(chapter=5)
    p1_blockers = [b for b in blockers if b.patch == "foreshadow_dag"]
    assert p1_blockers == []

def test_dag_validation_cycle():
    """DAG 含环应报 BLOCKER"""
    runner = ConsistencyRunner(PROJECT_DAG_VIOLATION)
    blockers = runner.run_all(chapter=10)
    assert any("循环" in b.message for b in blockers if b.patch == "foreshadow_dag")
```

---

## 5. 迁移策略（针对《根源牌序》等已有项目）

**新字段全部可选**。已有 state.json 没有 patch 字段时，patch 报 "未初始化" blocker，提示用户：
```
BLOCKER [foreshadow_dag] 第 5 章
  问题: state.json 缺少 foreshadow_chain 字段
  修复: 运行 `webnovel.py consistency init --volume <current_volume>`
```

`init` 命令做向后兼容：缺失字段用默认值填充。

---

## 6. 风险与回滚

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 7 个补丁同时上 → 用户立刻卡在 BLOCKER | 高 | 中 | init 一次填默认；提供 override 命令 |
| fixture 不能复现真实问题 | 中 | 中 | fixture 故意覆盖典型违规场景 |
| state.json 字段膨胀 | 低 | 低 | 每个字段独立 namespace（story_craft.*） |
| 与现有 changes_gate.py 冲突 | 中 | 高 | 先调研 changes_gate.py，确认职责边界 |

**回滚方案**: 每个 patch 是独立模块，单独禁用只需 `__init__.py` 里注释掉即可。state.json 字段保留无害。

---

## 7. 实施顺序（按依赖序）

1. **P1 Foreshadow DAG** — 无依赖，先做
2. **P2 Volume Anchor** — 无依赖，独立
3. **P3 Event Matrix** — 依赖 P1（用 foreshadow 索引）
4. **P4 Pacing Tracker** — 无依赖，独立
5. **P5 State Revision** — 无依赖，独立
6. **P6 Reader Contract** — 依赖 P1（伏笔）+ P4（节奏）
7. **P7 Derived Views** — 依赖 P5（state revision）

每个补丁走同一循环：写 patch 模块 → 写 fixture → 写测试 → 集成到 skill。

---

## 8. 引用源

每个 patch 的 `module docstring` 必须包含：
```
# Patch: {name}
# Source: {Openwrite | novel-creator | oh-story-claudecode | 原創}
# Path in references: references/{path}
# Original algorithm: ...
```

---

## 9. 完成定义（DoD）

- [ ] 7 个 patch 模块全部实现并通过单测
- [ ] Runner 集成测试通过（runner_e2e）
- [ ] CLI 4 个子命令可用
- [ ] webnovel-plan / webnovel-write / webnovel-review 集成点已加
- [ ] 至少 1 个真实项目（用 fixture）跑通全链路
- [ ] 不破坏现有 changes_gate.py / reviewer.py
- [ ] 文档：每个 patch 的 docstring + 一个 README
