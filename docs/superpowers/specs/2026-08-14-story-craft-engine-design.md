# Story Craft Engine — 故事工艺引擎 设计文档

| 字段 | 值 |
|---|---|
| 日期 | 2026-08-14 |
| 状态 | 草案（待用户审阅） |
| 范围 | webnovel-writer 插件的规划层（webnovel-plan） |
| 关联 | `/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer/` |

---

## 1. 目标与非目标

### 1.1 目标

为 webnovel-writer 的规划层补齐"故事工艺"维度，把规划从"格式正确"提升到"剧情可读且精妙"。具体：

1. **跌宕起伏** — 节奏可量化、可校验，自动检测平路和高潮
2. **精妙绝伦** — 反转/伏笔/巧合有结构、有回收、不突兀
3. **草蛇灰线** — 伏笔有埋有收、有追踪、有状态机
4. **理论可吸收** — 中外编剧理论、网文实践、古典叙事技法以 reference 形式工程化
5. **AI 主执行 + 人 review** — Plan 阶段 AI 自动生成机制，人在 Dashboard 一次性 review；Write 阶段自动检查；Review 阶段自动报警

### 1.2 非目标

- ❌ 不做 Web UI（继续用现有 dashboard）
- ❌ 不替代作者创作风格（工具是约束，不是替代）
- ❌ 不强制 100% 机制合规（设 BLOCKER / WARNING 两级）
- ❌ 不引入新模型（保持现有 Claude / Sonnet 链路）
- ❌ 不重写数据抽取（data-agent 流程不变）

---

## 2. 当前状态与缺口

### 2.1 当前已有的（form 层）

| 已有机制 | 出处 | 强弱 |
|---|---|---|
| 三线交织（Quest/Fire/Constellation） | `references/shared/strand-weave-pattern.md` | 强（硬规则） |
| 爽点密度（3 级） | `references/shared/cool-points-guide.md` | 中（建议级） |
| 章内节奏（3000 字黄金比例） | `skills/webnovel-plan/references/outlining/chapter-planning.md` | 中（启发级） |
| 卷级节拍表模板 | `templates/output/大纲-卷节拍表.md` | 弱（空白模板） |
| 伏笔表（buried/payoff） | `大纲/伏笔表.md` | 弱（无追踪状态） |
| CBN/CPNs/CEN 结构化节点 | plan SKILL.md Step 7 | 强（写入即校验） |
| 反 AI 扫描（slop） | `webnovel-deslop-check` | 强（量化引擎） |
| 5 维审查 | `webnovel-review` | 强（reviewer 子代理） |

### 2.2 当前缺位的（craft 层）

| 缺口 | 严重度 | 影响 |
|---|---|---|
| **角色弧无追踪** | 致命 | 主角"内在转变"完全靠作者自觉 |
| **主题无回响** | 致命 | 卷末无"主题论证"检查 |
| **Scene-Sequel 章内节拍缺失** | 高 | 章内"目标→冲突→挫折→结果"无机制 |
| **伏笔 5 字段追踪缺失** | 高 | 只能记内容，不能查状态/关联 |
| **定时锁缺失** | 高 | "3 章出村"等硬约束全靠作者自觉 |
| **15-beat 卷节拍缺失** | 高 | 卷末无 Midpoint/All Is Lost 硬约束 |
| **钩子类型无校验** | 中 | 章末钩子质量全凭 review |
| **节奏曲线无数据** | 中 | "追读率"是抽象概念，无具体章节追踪 |
| **跨卷伏笔回收追踪缺失** | 中 | 第二卷想回收第一卷伏笔困难 |
| **shuangwen-* reference 悬空** | 低 | write skill 引用了不存在的 reference |

---

## 3. 理论吸收（4 个 tier）

### 3.1 Tier 1 — 必吸收（核心机制级，8 项）

v1 实现 7 项直接机制 + 1 项过程映射；Dan Harmon Story Circle 入档但 v1 不实现（v2 增强）。

| 来源 | 理论 | 网文/卷级映射 | v1 状态 |
|---|---|---|---|
| **Dan Harmon Story Circle** | 8 阶段圆 | 卷级 Story Circle | **v2 增强**（v1 只在 reference 留文档） |
| **Save the Cat Writes a Novel**（Jessica Brody 2018） | 15-beat 应用小说 | 卷级 15-beat 节拍表 | v1 实现 |
| **TV Writer's Room 流水线** | Pitch → Outline → Beat Sheet → Script | webnovel-plan Step 3-7 流程对应 | v1 实现（过程映射，不新增机制） |
| **Scene-Sequel**（Dwight Swain） | Scene 4 步 + Sequel 3 步 | 每章 Scene-Sequel 节拍 | v1 实现 |
| **起点编辑流水《爽文的节奏》** | "定时锁" | 章节级 + 卷级定时锁 | v1 实现 |
| **草蛇灰线伏脉千里** | 三层伏笔 + 5 字段追踪 | state.json foreshadow_chain | v1 实现 |
| **马良写作节奏曲线** | 1.8 章/情绪高峰，平路 ≤3 | state.json rhythm_curve | v1 实现 |
| **红楼梦 5 谶语载体** | 物/诗/戏/灯谜/环境 | foreshadow_chain.type 枚举 | v1 实现 |

### 3.2 Tier 2 — 强烈建议（结构补充，6 项）

| 来源 | 应用 |
|---|---|
| **Truby 22 steps** 的 7 大关键 | 卷节拍表必含：弱化/需求/欲望/对手/假盟友/计划/揭露 |
| **McKee 价值 ± 曲线** | 章末钩子的"价值反转"自动检查 |
| **Lost-style Mystery Box** | 深层伏笔 1-2 个 = 全书核心问号 |
| **Breaking Bad 跨季人物弧** | state.json character_arc |
| **国产剧双线结构**（《琅琊榜》《长安十二时辰》） | 跨卷/跨线 strand 平衡 |
| **6 种章末钩子**（马良 + 起点编辑） | state.json chapter_hook.type |

### 3.3 Tier 3 — 启发参考（不强制）

- Hero's Journey 12 阶段
- 七情节（Christopher Booker）
- Donald Maass 内心冲突
- 章回体"留白/不写之写"
- 麦基"故事价值论"

### 3.4 Tier 4 — 明确不吸收

- 三幕剧硬约束（媒介错配）
- 编剧节拍 15 个原版（过密）
- Lisa Cron Lie/Want/Need/Ghost（西方心理深度，非目标读者）

---

## 4. 四大核心机制

### 4.1 机制 1：15-Beat 卷节拍表（Save the Cat 卷级化）

**用途**：卷内节奏的硬骨架，强制 Midpoint、All Is Lost 关键节点。

**15 个 beat 在卷内位置**（卷长 50-80 章）：

| # | Beat | 占比 | 卷内章 | 内容 |
|---|---|---|---|---|
| 1 | Opening Image | 0-1% | 卷首章 | 卷前主角状态 |
| 2 | Theme Stated | 5% | ~3 章 | 配角说出卷主题 |
| 3 | Setup | 1-10% | ~5 章 | 人物/世界/目标展示 |
| 4 | Catalyst | 10% | ~5 章 | 卷内大事件触发 |
| 5 | Debate | 10-20% | ~10 章 | 主角是否回应 |
| 6 | Break Into Two | 20% | ~10 章 | 主角决定行动 |
| 7 | B Story | 22% | ~11 章 | 副线开启 |
| 8 | Fun and Games | 20-50% | ~25 章 | 卷主体 |
| 9 | **Midpoint** | 50% | ~25 章 | **卷中反转/假胜利/假失败** |
| 10 | Bad Guys Close In | 50-75% | ~37 章 | 压力升级 |
| 11 | **All Is Lost** | 75% | ~37 章 | **卷末最低点** |
| 12 | Dark Night of the Soul | 75-80% | ~40 章 | 主角独面 |
| 13 | Break Into Three | 80% | ~40 章 | 找到新方案 |
| 14 | Finale | 80-99% | ~49 章 | 卷末决战 |
| 15 | Final Image | 99-100% | 卷末章 | 对比 Opening Image |

**state.json 字段**：
```json
{
  "volume_beat": {
    "volume": 1,
    "beats": [
      {"name": "Opening Image", "chapter": 1, "filled": true, "notes": "..."},
      {"name": "Midpoint", "chapter": 25, "filled": false, "notes": null}
    ]
  }
}
```

**强制约束**：
- Midpoint 必须有 filled=true，否则 BLOCKER
- All Is Lost 必须有 filled=true，否则 BLOCKER
- Final Image 必须与下卷 Opening Image 呼应（自动检查）

### 4.2 机制 2：Scene-Sequel 章内节拍（Dwight Swain）

**用途**：替代当前"3000 字黄金比例"的更精细章内结构。

```
Scene: Goal → Conflict → Setback → Resolution
       主角目标  阻碍    挫败/失败  暂时结果

Sequel: Reaction → Dilemma → Decision
        主角反应  困境    决定 (=下章目标)
```

**state.json 字段**（写入 `chapter_meta`）：
```json
{
  "chapter_beat": {
    "scene": {
      "goal": "本场主角目标",
      "conflict": "阻碍是什么",
      "setback": "挫败或失败",
      "resolution": "本场暂时结果"
    },
    "sequel": {
      "reaction": "主角反应",
      "dilemma": "主角面对的困境",
      "decision": "主角决定 = 下章目标"
    }
  },
  "hook_type": "悬念式|反转式|情绪炸弹式|信息投放式|留白式|反讽式"
}
```

**校验规则**：
- 任何 1 步缺失 → WARNING（避免过度约束新手章）
- Goal → Conflict 任一缺失 → BLOCKER
- Decision 必须与下章 Goal 形成因果 → BLOCKER

### 4.3 机制 3：草蛇灰线 5 字段追踪

**用途**：伏笔状态机化，自动查埋/收/漏。

**5 字段必填**：
```json
{
  "foreshadow_chain": [
    {
      "id": "FS-001",
      "type": "物谶|诗谶|戏谶|灯谜|环境|习惯|对话双关",
      "depth": "表层|中层|深层",
      "content": "伏笔内容描述",
      "buried_chapter": 5,
      "expected_payoff_chapter": 25,
      "payoff_method": "回收方式（如何响应当下情节）",
      "linked_entities": ["主角", "血玉蜘蛛", "虚天鼎"],
      "status": "active|paid_off|dormant|missed",
      "buried_quality": "强|中|弱（埋设质量评分）",
      "payoff_chapter": null,
      "payoff_quality": null
    }
  ]
}
```

**自动检查**（reviewer Step 3）：
- ✅ 每章 ≥1 表层伏笔埋/收（WARNING 阈值）
- ✅ 中层伏笔 ≥3 个/卷（HARD）
- ✅ 深层伏笔 1-2 个/全书（min=1, max=2；HARD）
- ⚠️ 任何 active 的伏笔 ≥10 章未推进 → WARNING
- 🚫 任何 expected_payoff_chapter 已过 + 未 paid_off → BLOCKER
- 🚫 任何 missed 的伏笔 → 标记 + 人 review

### 4.4 机制 4：定时锁 + 节奏曲线 + 钩子类型

#### 4.4.1 定时锁（Timed Locks）

**理论**：起点编辑流水《爽文的节奏》—— "到一定时间必发生特定事件"。

**典型定时锁**：
- 玄幻少年 3 章内"出村"
- 系统文第 1 章系统出现，第 2 章系统起作用 + 解决难题
- 女主 N 章内首次登场
- 反派首秀 M 章内必须完成
- 卷末高潮在最后 5 章

**state.json 字段**：
```json
{
  "timed_locks": [
    {
      "id": "TL-001",
      "description": "玄幻主角 3 章内出村",
      "trigger_chapter": null,
      "deadline_chapter": 3,
      "status": "active|fulfilled|missed",
      "fulfilled_chapter": null
    }
  ]
}
```

**校验规则**：deadline_chapter 已过 + status=active → BLOCKER

#### 4.4.2 节奏曲线（Rhythm Curve）

**理论**：马良写作（基于追读 top10% 数据）—— 1.8 章/情绪高峰，平路 ≤3 章。

**state.json 字段**：
```json
{
  "rhythm_curve": {
    "last_emotion_peak_chapter": 0,
    "chapters_since_peak": 0,
    "warning_threshold": 3,
    "block_threshold": 5,
    "history": [
      {"chapter": 1, "intensity": 3, "type": "small_cool_point"},
      {"chapter": 5, "intensity": 7, "type": "medium_cool_point"}
    ]
  }
}
```

**自动检查**：
- chapters_since_peak ≥ warning_threshold → WARNING（提醒加爽点）
- chapters_since_peak ≥ block_threshold → BLOCKER（必须加爽点或 override）

#### 4.4.3 钩子类型（Hook Type）

**6 种**（悬念/反转/情绪炸弹/信息投放/留白/反讽），写入 chapter_meta.hook_type。

**校验**：每章必须声明 hook_type，否则 BLOCKER。

---

## 5. 执行模型（分层）

```
┌──────────────────────────────────────────────┐
│ Stage 1: PLAN（AI 主执行 + 人 review 一次）    │
│                                              │
│   AI 自动生成：                                │
│   - 故事概念 → 总纲 (Pitch → Outline)         │
│   - 卷级 15-beat 节拍表                         │
│   - 草蛇灰线 5 字段追踪表                       │
│   - 定时锁列表                                 │
│   - 章级 Scene-Sequel 切片                      │
│                                              │
│   人 review（Dashboard 一次性确认）：            │
│   - 是否同意 beat 安排                          │
│   - 是否同意伏笔关联                            │
│   - 是否同意定时锁                              │
│   → 可 override，可补充                         │
│                                              │
├──────────────────────────────────────────────┤
│ Stage 2: WRITE（AI 主执行 + 自动检查）          │
│                                              │
│   每章 Step 2A 起草时自动注入：                 │
│   - 本章必须覆盖的 beat                          │
│   - 本章必须埋/收的伏笔                          │
│   - 本章 Scene-Sequel 目标                       │
│   - 本章定时锁（若在此章）                       │
│                                              │
│   每章 Step 4 完成后自动检查：                   │
│   - beat 是否到位                                │
│   - 伏笔是否埋/收                                │
│   - Scene-Sequel 是否完整                        │
│   - 钩子是否符合 6 种之一                        │
│                                              │
├──────────────────────────────────────────────┤
│ Stage 3: REVIEW（reviewer 自动 + 人确认）       │
│                                              │
│   reviewer 检查 7 维度：                        │
│   - 节拍合规性（15-beat）                        │
│   - 伏笔合规性（5 字段追踪）                      │
│   - Scene-Sequel 完整性                          │
│   - 钩子有效性                                  │
│   - 节奏曲线漂移                                 │
│   - (原) 设定一致性                              │
│   - (原) 时间线                                  │
│                                              │
│   人 review：                                   │
│   - 看 reviewer 报告                              │
│   - 在 Dashboard 上 override                       │
└──────────────────────────────────────────────┘
```

**关键设计点**：
- **AI 默认主执行**：按 15-beat + 5 字段强制生成，不是"建议"
- **人做节点性决策**：PLAN 完成后一次性 review，不逐章
- **机制违规即 BLOCKER**：reviewer 自动报警
- **Dashboard 优先于对话**：所有机制状态可视化

---

## 6. state.json Schema 变更

### 6.1 新增顶层字段

```json
{
  "story_craft": {
    "rhythm_curve": { ... },
    "foreshadow_chain": [ ... ],
    "timed_locks": [ ... ],
    "thematic_echoes": [
      {
        "id": "TE-001",
        "premise": "主题一句话陈述（如：真正的强大是记忆而非力量）",
        "echoes": [
          {"chapter": 5, "manifestation": "本章如何回响主题"}
        ]
      }
    ],
    "character_arc": {
      "name": "主角名",
      "starting_state": "卷首内在状态",
      "ending_state": "卷末内在状态",
      "transformation": "如何从 starting 变 ending",
      "key_moments": [{"chapter": 25, "event": "决定性事件"}]
    }
  }
}
```

### 6.2 chapter_meta 新增字段

```json
{
  "chapter_meta": {
    "0001": {
      "beat_position": "Opening Image",
      "scene_goal": "...",
      "scene_conflict": "...",
      "sequel_decision": "...",
      "hook_type": "悬念式",
      "foreshadow_buried": ["FS-001", "FS-005"],
      "foreshadow_paid_off": []
    }
  }
}
```

### 6.3 向后兼容

- 旧项目缺 story_craft 字段 → 自动初始化为空结构，不报错
- chapter_meta 缺 beat_position 等 → 写入时为 null，review 时 WARNING
- 不破坏现有 strand_tracker / review_checkpoints / plot_threads 等字段

---

## 7. 新增 Reference 文档清单

放在 `references/shared/`（单一事实源）：

| 文件名 | 内容 | 大小 |
|---|---|---|
| `15-beat-save-the-cat.md` | 15 个 beat 定义 + 卷级映射 | 中 |
| `scene-sequel.md` | Dwain Swain Scene-Sequel 章内节拍 | 短 |
| `foreshadow-chain.md` | 草蛇灰线三层法 + 5 字段追踪 + 6 种载体 | **长（核心）** |
| `timed-lock.md` | 定时锁理论与训练题 | 中 |
| `rhythm-curve.md` | 节奏曲线规则 + 1.8 章阈值 | 短 |
| `chapter-hook-types.md` | 6 种章末钩子 | 中 |
| `character-arc.md` | 主角弧追踪（state.json 字段说明） | 中 |
| `thematic-echo.md` | 主题回响 + state.json 字段说明 | 短 |

放置在 `references/outlining/`（plan 专用）：

| 文件名 | 内容 |
|---|---|
| `volume-beat-sheet.md` | 卷节拍表填写模板（替代现有空白模板） |
| `foreshadow-tracking-template.md` | 5 字段追踪表模板 |

---

## 8. SKILL.md 变更（webnovel-plan）

### 8.1 Step 流程改造

| Step | 现状 | 变更 |
|---|---|---|
| Step 1 | 加载项目数据 | + 加载 genre → 决定 beat 强度 |
| Step 2 | 补齐设定基线 | + 加载 thematic_echoes 字段 |
| Step 3 | 选择目标卷 | + 卷级 Story Circle 阶段记录 |
| **Step 4.5 NEW** | — | **生成 15-beat 卷节拍表** |
| Step 5 | 生成卷时间线 | + 定时锁挂载到时间线 |
| Step 6 | 生成卷纲骨架 | + 草蛇灰线 5 字段追踪表初始化 |
| **Step 6.5 NEW** | — | **生成本卷主题 + thematic_echoes** |
| Step 7 | 批量生成章纲 | + 每章 Scene-Sequel 切片 + 钩子类型 |
| Step 8 | 写回新增设定 | + character_arc 写回 |
| **Step 8.5 NEW** | — | **伏笔链深度检查 + 节奏曲线预测** |
| Step 9 | 验证保存 | + 机制合规验证 |
| Step 10 | 刷新 Story System | + Story Circle 阶段 |

### 8.2 写入规约

- 每 Step 触发条件 → 显式列出加载哪些 reference
- BLOCKER 处理规则 → 暂停 + 人裁决
- WARNING 处理规则 → 自动继续 + Dashboard 显示

### 8.3 显式禁项

- 禁止在不读对应 reference 时输出 beat/伏笔内容
- 禁止用通用网文套路替代 15-beat（必须套 beat）
- 禁止 Scene-Sequel 字段为空

---

## 9. Reviewer 维度扩展

现有 5 维度 → 扩展为 7 维度：

| 维度 | 检查项 |
|---|---|
| 1. 设定一致性 | （现有） |
| 2. 时间线 | （现有） |
| **3. 节拍合规性** | beat 是否填充、Midpoint/All Is Lost 是否到位 |
| **4. 伏笔合规性** | 5 字段完整、active 状态、预期回收期 |
| 5. Scene-Sequel 完整性 | 7 步是否到位（Goal→Resolution + Reaction→Decision） |
| 6. 钩子有效性 | hook_type 是否声明 + 是否符合类型 |
| **7. 节奏曲线** | chapters_since_peak 是否超过阈值 |

Reviewer 子代理 prompt 需更新。

---

## 10. 现有项目迁移策略

### 10.1 现有项目情况

- 《根源牌序》：第 1 卷已完成骨架/节拍表/时间线/详细大纲 + 已写 0001/0002 两章
- 旧 state.json 字段保留，新字段为空初始化

### 10.2 迁移动作

1. **自动备份** `.webnovel/state.json.bak`
2. **增量添加** story_craft 顶层字段，初始化为空
3. **chapter_meta 增量** — 已写章节的 beat_position / hook_type 留 null，下一次 `/webnovel-write` 时自动补
4. **新卷规划** 时启用全部机制（旧卷不再回溯填充）

### 10.3 兼容性保证

- 新字段全 optional
- 旧 Step 流程保留（新增 Step 平铺插入，不替换）
- reviewer 旧维度保留，新维度作为增量
- 老 project_memory.json 不变

---

## 11. 测试策略

### 11.1 单元测试（pytest）

- `tests/test_foreshadow_chain.py` — 5 字段验证、状态机迁移
- `tests/test_15_beat.py` — beat 完整性、Midpoint/All Is Lost 必填
- `tests/test_scene_sequel.py` — 7 步字段验证
- `tests/test_timed_locks.py` — deadline 检查
- `tests/test_rhythm_curve.py` — chapters_since_peak 计算
- `tests/test_migration.py` — 旧 state.json → 新 state.json 平滑升级

### 11.2 集成测试

- `tests/integration/test_plan_with_craft.py` — 模拟 plan 完整流程，验证 state.json 终态
- `tests/integration/test_review_with_craft.py` — 模拟 reviewer 报警 BLOCKER
- `tests/integration/test_dashboard.py` — Dashboard 正确显示新字段

### 11.3 端到端测试

- 创建一个测试项目（genre=玄幻），跑 webnovel-init → webnovel-plan → webnovel-write 三阶段
- 验证：plan 生成节拍表正确；write 每章写入 Scene-Sequel；reviewer 检查 BLOCKER

---

## 12. 风险与未知

| 风险 | 影响 | 缓解 |
|---|---|---|
| 15-beat 套到 50 章卷可能节奏过快 | 强制 Midpoint 在第 25 章可能太早 | 允许 genre-specific override（修仙可拉长到 30 章） |
| Scene-Sequel 强制 7 步可能过度约束 | 新手章可能瘫痪 | 部分字段允许 null + WARNING 容忍 |
| 草蛇灰线追踪污染"已写章节" | 老章节无 5 字段，reviewer 全 BLOCKER | 旧章节新字段全 null，下一次 `/webnovel-write` 时增量补 |
| 节奏曲线 1.8 章阈值可能过密 | 卷末密度需求可能冲突 | 阈值做成可配置（state.json 默认值） |
| AI 不会写"反讽式"钩子 | 钩子类型单一化 | reference 给出正反例 + 训练题 |
| 中文术语翻译漂移 | "Midpoint" 等词读者可能陌生 | reference 中英对照 + 卷节拍表用中文别名 |
| 用户可能中断流程 | 半成 plan 状态混乱 | `/webnovel-resume` 适配新流程 |

---

## 13. 分阶段上线（4-6 周）

### Phase 1：reference 文档 + state.json schema（第 1 周）

- 写 8 个 reference 文档（references/shared/）
- 写 state.json schema 变更
- 写 migration 脚本（state.json → 新字段）
- 单元测试：5 个 test_*.py

### Phase 2：webnovel-plan SKILL.md 改造（第 2-3 周）

- 重写 Step 流程（新增 Step 4.5 / 6.5 / 8.5）
- 集成 reference 加载
- 集成模板（volume-beat-sheet.md / foreshadow-tracking-template.md）
- 集成测试

### Phase 3：reviewer 扩展（第 3-4 周）

- reviewer 子代理 prompt 更新（5 → 7 维度）
- reviewer-pipeline 脚本扩展
- 集成测试

### Phase 4：dashboard + 上线（第 4-6 周）

- dashboard 视图扩展（新增节拍/伏笔/钩子/曲线 4 个面板）
- 端到端测试
- 现有《根源牌序》项目迁移试运行
- 文档发布

---

## 14. 验收标准

| 项 | 标准 |
|---|---|
| reference 文档完整 | 8 个文件全部存在 + 单一事实源 |
| state.json schema 变更 | migration 脚本可跑 |
| plan 主流程 | 新增 3 个 Step + Step 7 增强 |
| reviewer 维度 | 从 5 → 7 |
| 单元测试 | ≥30 个 test 通过 |
| 集成测试 | ≥5 个 scenario 通过 |
| 端到端 | 《根源牌序》第 1 卷规划在迁移后能产出节拍表 + 5 字段表 |
| Dashboard | 新增 4 个可视化面板 |

---

## 15. 开放问题（待用户裁决）

1. **Deep mode 下 plan 默认开哪些机制？** 是否在 init 阶段加开关？
2. **节奏曲线 1.8 章阈值是否做成 genre-specific？** 还是全局默认？
3. **草蛇灰线 5 字段是必填还是建议填？** 必填 = 强制约束；建议 = 仅 warning
4. **Scene-Sequel 7 步必填还是允许压缩？** 必填 = 严谨但慢；允许压缩 = 灵活但松
5. **dashboard 是否需要新页面？** 还是叠在现有 dashboard 上？

---

**接下来**：本 spec 待用户审阅 → 通过后调用 writing-plans skill 生成实施计划。