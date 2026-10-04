# webnovel-writer 个人 fork 设计文档

**日期**：2026-08-08
**作者**：与 Claude Code 协作
**状态**：待用户审阅

---

## 0. 目标与边界

### 0.1 一句话目标
为"自己写书用、要好用"做一套基于现有 Claude Code 插件 webnovel-writer 的个人扩展，**最小侵入解决三个具体痛点**：
1. 长篇一致性崩坏
2. AI 味重
3. 流程繁琐

### 0.2 明确不做的
- 不重新发明 webnovel-writer
- 不做 Web UI、不做产品化
- 不解决"如何写出好小说"（只解决"AI 写长篇时的具体技术崩坏"）
- 不为想象中的"其他用户"设计

### 0.3 约束
- 纯自用，许可证隔离不是问题
- 工作目录非 git 仓库（不强制 commit）

---

## 1. 总体形态

**核心决策：不做 fork，做项目级 skill 叠加。**

证据：
- 项目级 `.claude/skills/webnovel-write/skill.md`（小写 s）已存在并覆盖 plugin 版，验证了"同名 skill 覆盖"机制
- plugin 还在活跃更新（5.5.4 → 6.2.1 架构级变化），fork 维护成本极高
- 项目级 skill 完全可控、不破坏 plugin 的 schema 校验、不触发 GPL 传染

### 1.1 目录结构

```
/Users/chang/Desktop/webnovel-tool-lab/.claude/    ← 历史快照（2026-08-08 起点）。当前路径：/Users/chang/Desktop/zhanghui/
├── skills/                              ← 项目级 skill 层（核心新增/覆盖）
│   ├── webnovel-write/skill.md           ← 主流程（已存在，需改造）
│   ├── webnovel-review/skill.md          ← 审查（已存在，按需改造）
│   ├── webnovel-plan/skill.md            ← 规划（已存在，按需改造）
│   ├── webnovel-fast-write/SKILL.md      ← 新增：快车道 skill
│   ├── webnovel-deslop-check/SKILL.md    ← 新增：独立 anti-slop 扫描
│   └── webnovel-revise-chapter/SKILL.md  ← 新增（视 Phase 3 验收决定）
├── agents/                              ← 同名覆盖（如需改造 reviewer）
├── references/                          ← 项目级参考文档
│   ├── changes-protocol.md               ← 新增：CHANGES 字段定义
│   ├── changes-examples.md               ← 新增：CHANGES 示例
│   └── deslop/
│       ├── banned-words.md               ← 复制自 oh-story
│       ├── anti-ai-writing.md            ← 复制自 oh-story
│       └── humanizer-guide.md            ← 复制自 novel-creator-skill
├── scripts/                             ← 项目级 Python/JS 脚本
│   ├── text_humanizer.py                 ← 复制自 novel-creator-skill
│   ├── check-ai-patterns.js              ← 复制自 oh-story
│   ├── normalize-punctuation.js          ← 复制自 oh-story
│   └── changes_gate.py                   ← 新增：CHANGES 校验门禁
└── settings.json                        ← 项目级 Claude 配置
```

---

## 2. 数据流

### 2.1 正常流程（`/webnovel-fast-write`）

```
Step 0 预检
  └→ webnovel.py preflight + placeholder-scan
Step 1 context-agent（plugin 原生 subagent）
  └→ 产出 5 段写作任务书
Step 2 主流程起草
  └→ LLM 生成正文 + <chapter_changes>...</chapter_changes> 块
Step 4.5 changes_gate.py（本项目新增）
  ├─ 协议完整性
  ├─ 实体引用合法性（查 index.db）
  ├─ 物品/伏笔状态推进
  ├─ 关系/信任度变化超 ±30
  └─ 未登记实体上限
  └→ 失败：退回 Step 2 重写声明块（最多 2 次）
Step 4.6 text_humanizer.py + check-ai-patterns.js（本项目新增）
  └→ 失败：退回 Step 4 重写正文（最多 2 次）
Step 5 data-agent（plugin 原生 subagent）
  └→ 产出 extraction_result.json + fulfillment_result.json + disambiguation_result.json
Step 5.2 chapter-commit（plugin 原生）
  └→ schema 校验 + 5 路 projection + git tag
```

### 2.2 完整流程（`/webnovel-write`）

正常流程 + Step 3（reviewer 5 维审查）+ Step 4（polish 全流程）

### 2.3 失败恢复矩阵

| 失败点 | 行为 | 影响范围 |
|---|---|---|
| Step 0 预检失败 | 整个流程不启动 | 无副作用 |
| Step 1 context-agent 失败 | 重试 subagent，最多 3 次 | 仅 task 任务，无副作用 |
| Step 2 起草失败 | 重试主流程 LLM 调用，最多 3 次 | 无副作用 |
| Step 4.5 CHANGES 校验失败 | 退回 Step 2 重写 `<chapter_changes>` 块（仅替换声明，不改正文）| 正文保留 |
| Step 4.6 anti-slop blocking | 退回 Step 4 重写正文 | 声明块保留 |
| Step 5 data-agent schema 失败 | 退回 Step 2 全章重写 | 全文 + 声明 |
| Step 5.2 chapter-commit 失败 | 走 `/webnovel-resume` | 全部已落盘数据 |
| LLM token 超限 | plugin 内部 5 级降级 | 由 plugin 处理 |

---

## 3. CHANGES 协议设计

### 3.1 字段定义（snake_case 简化版）

借鉴天命 12 顶级字段，砍到 8 个核心字段以减低 LLM 输出成本：

```json
{
  "character_state_changes": [],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
```

### 3.2 字段细则

每字段定义、必填项、枚举值、示例见 `references/changes-protocol.md`。

### 3.3 容器形式

**优先格式**：`<chapter_changes>...</chapter_changes>`
**容错**：依次尝试 `---CHANGES---`、`# CHANGES`、末尾 JSON 兜底
**JSON 容错**：借鉴天命 9 类字符修复（中文标点→半角、单引号→双引号、缺尾引号自动闭合等）

### 3.4 8 项校验规则

| ID | 规则名 | 检查内容 | 实现方式 | 数据源 |
|---|---|---|---|---|
| R1 | 协议完整性 | 8 个顶级字段必须显式存在 | 字段名集合包含检查 | 解析后 JSON |
| R2 | 枚举值合法 | action/importance/status 取值在枚举内 | 字符串等于检查 | 解析后 JSON |
| R3 | 实体引用合法 | character_id/location_id/faction_id 必须在账本 | SQL 查询 | `index.db` entities 表 |
| R4 | 伏笔推进 | 标记 setup/payoff 的伏笔 ID 必须存在 | SQL 查询 | `index.db` foreshadowing 表 |
| R5 | 信任度变化 | relationship 变化的 ±delta ≤ 30 | 数值比较 | `index.db` relationships 表 |
| R6 | 未登记实体 | 正文中提到但未在 CHANGES 申报的名字 ≤ 5 | 正则 + 账本差集 | `index.db` entities + 正文 |
| R7 | 物品状态机 | item_transfers 前后 status 合法转移 | 状态机 | 解析后 JSON |
| R8 | 时间线连贯 | time_progression 不与上一章冲突 | SQL 查询 | `index.db` timeline 表 |

R3、R4、R5、R6、R8 必须有 `index.db` 数据——这是 webnovel-writer 已经维护好的。

---

## 4. Anti-Slop 扫描器集成

### 4.1 双引擎架构

| 引擎 | 来源 | 优势 | 接入点 |
|---|---|---|---|
| `text_humanizer.py` | novel-creator-skill（MIT）| 词表 + 密度 + 中文原生 | Step 4.6 |
| `check-ai-patterns.js` | oh-story-claudecode（MIT）| 实战漏网句式（not-is-comparison、trailer-ending 等）| Step 4.6 |
| `normalize-punctuation.js` | oh-story-claudecode（MIT）| 标点规范化 | Step 4.6 末尾 |

### 4.2 判定分级

- **blocking**（必须修）：高频 AI 词密度超阈值、章末预告腔、对话标签公式化密度 >30%
- **advisory**（记日志）：段落长度均质、转折词过载

### 4.3 白名单

`references/deslop/whitelist.md`：玄幻/科幻/同人不该误报的题材术语
由 webnovel-init 在生成题材标签时自动追加

---

## 5. 快车道与瘦身审查

### 5.1 `webnovel-fast-write` skill

跳过 Step 3（reviewer）+ Step 4 polish 全流程
保留 Step 0/1/2/4.5/4.6/5/6
**节省**：1 次 subagent 调用（reviewer 是 5 维串行，耗时最久）

### 5.2 `webnovel-deslop-check` skill

独立触发双扫描器，对任意章节（已写好的）做扫描
输出 Markdown 报告：blocking 项位置 + 原文引用 + 修改建议

### 5.3 `webnovel-review` 可选改造（初版跳过）

让 reviewer 只跑 continuity + setting + character 三个维度
跳过 logic + pacing（reviewer 判断这两维度质量不高，且 polish 阶段已部分覆盖）
此改造**推迟到 Phase 4+**，Phase 1-3 不动 reviewer。

---

## 6. 开发路线图

### Phase 1：anti-slop 资产落地（1-2 天）

- 复制 text_humanizer.py / check-ai-patterns.js / normalize-punctuation.js
- 复制 banned-words.md / anti-ai-writing.md / humanizer-guide.md
- 烟测：用 webnovel-writer 测试章节跑扫描
- **验收**：扫描器能在 webnovel-writer 测试章节上跑出非空报告且无脚本报错

### Phase 2：CHANGES 协议 + 门禁脚本（1 周）

- 写 changes_gate.py（约 400 行）
- 在 webnovel-write/skill.md Step 2 注入协议说明
- 在 Step 4.5 注入门禁调用
- **验收**：用 evals/files/test-project 跑 5 正例 + 5 反例

### Phase 3：快车道 + 独立扫描 skill（2-3 天）

- 写 webnovel-fast-write/SKILL.md
- 写 webnovel-deslop-check/SKILL.md
- **验收**：跑完整 /webnovel-fast-write，对比与 /webnovel-write 输出

### 退出条件
- 跑完 Phase 3 后你应该有 5-10 章测试稿
- 如果此时仍觉得 webnovel-writer 比 overlay 更顺 → 归档
- 如果某些痛点未解决 → 进 Phase 4

---

## 7. 风险与备选方案

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| LLM 不遵守 CHANGES 协议 | 高 | 门禁永远失败 | 协议解析宽松容错；前 5 章人 review 解析结果 |
| 误报题材术语 | 中 | blocking 过多 | whitelist.md 按题材标签自动加载 |
| plugin 升级破坏项目级 skill | 中 | skill 失效 | skill 只引用 plugin 资源名，不依赖内部 API |
| data-agent schema 变更 | 低 | 数据不一致 | CHANGES 与 extraction_result 两套独立 schema，事后对账 |
| token 成本上升 | 中 | 单章 +10-15% | snake_case + 8 字段（vs 天命 12） |
| 痛点 3 未解决 | 中 | 快车道仍繁琐 | Phase 3 后给出 webnovel-revise-chapter skill |
| 许可证争议 | 低 | 不能公开 | 当前纯自用不触发；想公开时改干净室实现 |

---

## 8. 不做的清单（YAGNI）

- ❌ Web UI / Dashboard
- ❌ 题材自适应阈值系统
- ❌ 神经 AIGC 检测器后端
- ❌ CHANGES 自动重试 N 次后的"手动介入"模式
- ❌ 结构级 LLM judge（autonovel 12 条）
- ❌ 跨卷事实归档 / 向量索引

---

## 9. 验收标准

完成后整套工具应满足：

1. `/webnovel-write` 跑完整流程时，每章都过 CHANGES 校验 + anti-slop 扫描 + reviewer
2. `/webnovel-fast-write` 跑完整流程时，跳过 reviewer 但仍过 CHANGES + anti-slop
3. `/webnovel-deslop-check` 能对任何已写章节出 Markdown 报告
4. plugin 升级到 6.3.x 时，本项目级 skill 不需要修改
5. 跑 5-10 章后，作者本人能说出"至少 X 个痛点被解决"

---

**待用户审阅。审阅通过后转入 writing-plans 阶段。**