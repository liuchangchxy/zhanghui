---
name: constants
purpose: 全局常数单一源。所有阈值/比例/字数要求必须在这里查阅，不得散落各文件
---

> **来源说明**：
> - tianming-skill `constants/global-constants.md`（CC BY-NC-SA 4.0）—— 表格 + 修改约定结构
> - novel-writing-toolkit `.claude/commands/novel.md`（MIT）—— 6 维度质量评分阈值
> - webnovel-writer 现状 —— 2000-2500 字/章默认 + 爽点/伏笔规则
>
> **使用规则**：本文件是单一真源。任何 skill 或 reference 中的阈值必须引用本文件，不得复制修改。
> 修改本文件需经用户授权（见末尾"修改约定"）。

# 全局常数单一源

## 字数戒律

### 长篇连载（默认）

| 常数 ID | 值 | 说明 |
|---------|---|------|
| `[CONST:word.long_chapter.min]` | **2000 净字** | 长篇章节字数下限 |
| `[CONST:word.long_chapter.max]` | **2500 净字** | 长篇章节字数上限 |
| `[CONST:word.long_chapter.default]` | **2200 净字** | 长篇章节字数默认值 |

> **用途**：`webnovel-write` 默认 2000-2500 字/章。

### 短篇（番茄短故事）

| 常数 ID | 值 | 说明 |
|---------|---|------|
| `[CONST:word.short.min]` | **8000 净字** | 短篇字数下限 |
| `[CONST:word.short.max]` | **18000 净字** | 短篇字数上限 |

> **用途**：`/webnovel-plan` 短篇模式（待 C4 落地）。

## 爽点密度

| 常数 ID | 值 | 说明 |
|---------|---|------|
| `[CONST:cool.basic_per_chapter]` | **≥1** | 每章最低小爽点数 |
| `[CONST:cool.key_chapter_interval]` | **5-8 章** | 关键章节（含中爽点）间隔 |
| `[CONST:cool.peak_per_volume]` | **≥1** | 每卷高潮章节数（含大爽点） |
| `[CONST:cool.same_type_warning]` | **3 章** | 连续同类型爽点预警阈值 |

> **来源**：webnovel-writer `references/shared/cool-points-guide.md`（已存在）

## 伏笔管理

### 三层伏笔

| 层级 | 常数 ID | 覆盖范围 | 紧急度权重 |
|------|---------|----------|------------|
| 核心 | `[CONST:foreshadow.core.range]` | 50-300 章 | 3.0x |
| 支线 | `[CONST:foreshadow.branch.range]` | 30-100 章 | 2.0x |
| 装饰 | `[CONST:foreshadow.deco.range]` | 10-30 章 | 1.0x |

### 紧急度阈值

| 常数 ID | 值 | 说明 |
|---------|---|------|
| `[CONST:foreshadow.dormant_threshold]` | **50 章** | 沉睡伏笔预警阈值 |
| `[CONST:foreshadow.urgency_critical]` | **>20 章超时（核心）** | 红色警告 |
| `[CONST:foreshadow.urgency_warning]` | **>80% 目标进度（支线）** | 黄色警告 |

> **来源**：webnovel-writer `foreshadowing.md` 紧急度公式 + tianming 沉睡阈值

## 平台差异化

### 七猫女频

| 常数 ID | 值 | 说明 |
|---------|---|------|
| `[CONST:platform.qimao_female.chapter_words]` | **2000 字/章** | 七猫女频章节字数 |
| `[CONST:platform.qimao_female.open_rule]` | **开篇直接冲突，不铺垫** | 开篇规则 |
| `[CONST:platform.qimao_female.dialogue_share]` | **18-30%** | 对白占比 |

### 七猫男频

| 常数 ID | 值 | 说明 |
|---------|---|------|
| `[CONST:platform.qimao_male.chapter_words]` | **2000 字/章** | 七猫男频章节字数 |
| `[CONST:platform.qimao_male.open_rule]` | **第 1 章出金手指** | 开篇规则 |

### 番茄短故事

| 常数 ID | 值 | 说明 |
|---------|---|------|
| `[CONST:platform.fanqao_short.total_words]` | **8000-15000 字** | 全文总字数 |
| `[CONST:platform.fanqao_short.hook_rule]` | **前 300 字必须出钩子** | 开篇规则 |

### 番茄男频连载

| 常数 ID | 值 | 说明 |
|---------|---|------|
| `[CONST:platform.fanqao_male.chapter_words]` | **2000 字/章** | 章节字数 |
| `[CONST:platform.fanqao_male.first_coolpoint]` | **前 5 章第一个爽点** | 节奏要求 |

### 起点男频

| 常数 ID | 值 | 说明 |
|---------|---|------|
| `[CONST:platform.qidian_male.chapter_words]` | **2000-3000 字/章** | 章节字数 |
| `[CONST:platform.qidian_male.open_rule]` | **前 100 字确定主角** | 开篇规则 |
| `[CONST:platform.qidian_male.golden_finger_limit]` | **必须明确限制 + 代价** | 金手指规则 |

> **来源**：novel-writing-toolkit `novel.md` 平台适配章节

## 质量自检阈值（6 维度评分）

| 维度 | 权重 | 目标值 |
|------|------|--------|
| 对白占比 | 15% | 18-30%（长篇）/ 40-55%（短篇）|
| 句长波动 | 20% | >0.55 |
| 设定密度 | 15% | <10% |
| 解释密度 | 15% | <5% |
| 现场密度 | 20% | >30% |
| 重复开头% | 15% | <15% |

### 综合分阈值

| 分值 | 状态 |
|------|------|
| **>95** | 可投稿 |
| **85-95** | 需修改 |
| **<85** | 重写 |

> **来源**：novel-writing-toolkit `novel.md` 行 287-295

## 7 铁律阈值（来自 writing-edicts.md）

| 常数 ID | 值 | 说明 |
|---------|---|------|
| `[CONST:edict.short_sentence_density]` | **每 500 字 ≥1 句 ≤5 字** | 短句密度 |
| `[CONST:edict.long_sentence_density]` | **每 500 字 ≥1 句 ≥25 字** | 长句密度 |
| `[CONST:edict.dialogue_share_long]` | **18-30%** | 长篇对白占比 |
| `[CONST:edict.dialogue_share_short]` | **40-55%** | 短篇对白占比 |

> **来源**：novel-writing-toolkit 7 铁律

## 修改约定

### 何时可以修改本文件

- 用户基于自己的写作风格和小说体量，决定调整字数下限/上限时
- 用户对叙事节奏有特殊偏好，需要重新校准比例时
- 用户在多次实战后发现某项常数与其创作目标不匹配时

### 修改时必须做的事

1. 修改完成后，必须跑 `/webnovel-doctor` 重新校验项目是否仍能通过新约束
2. 重大修改（如字数下限、爽点密度）需要测试 3-5 章实战验证
3. 修改需在本文件底部"修改日志"追加记录

### 严禁修改的常数

| 常数 | 不建议修改原因 |
|------|--------------|
| `[CONST:cool.basic_per_chapter]` | 改 ≥0 会导致无爽点章节合法化 |
| `[CONST:foreshadow.urgency_critical]` | 改阈值会破坏伏笔系统的预警机制 |

## 修改日志

| 日期 | 修改内容 | 修改人 | 理由 |
|------|---------|--------|------|
| 2026-08-08 | 初始版本 | Claude（基于融合计划）| 收敛散落阈值 |