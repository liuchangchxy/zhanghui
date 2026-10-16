# Zhanghui Benchmark — Stage 2 长程创作架构对比报告

三个 AI 长篇小说创作系统在**相同作者级创作条件下**，各自走**原生工作流**，
写同一部 30 章中文悬疑小说《潮汐档案》的受控对比。

| 系统 | 仓库 | 测试 SHA |
|---|---|---|
| A · Zhanghui | `liuchangchxy/zhanghui` | `665248a60c21f75b48cd783ebb2a646292bfb9b8` |
| B · Jarvis-Write | `ynnyh/jarvis-write` | `efc5e1030b33f4bb19fc9509a6f28dafefa59848` |
| C · AI_NovelGenerator | `YILING0013/AI_NovelGenerator` | `f9aefef90b1493c579d7f72547efb4a3d8a0da25` |

**同一 Writer 模型**：`deepseek-v4.1-flash`（经本地 cc-switch 代理 → OpenCode Go token plan）。
每次调用独立会话、禁用全部工具与 MCP、不落盘。新增付费 API：**否**。

---

## 一、核心结果

| 系统 | 完成章节 | 状态 |
|---|---|---|
| A Zhanghui | **1 / 30** | HALTED — 被自身 Canon 拦停 |
| B Jarvis-Write | **30 / 30** | 完成 |
| C AI_NovelGenerator | **30 / 30** | 完成 |

### 1. 长程事实一致性（30 条探针，仅在系统已写章节内判定）

| 系统 | PASS | FAIL | UNCLEAR | 未写该章 | 判定内通过率 |
|---|---|---|---|---|---|
| A | 1 | 0 | 0 | 29 | 100%（n=1） |
| B | 25 | 2 | 3 | 0 | **83.3%** |
| C | 27 | 2 | 1 | 0 | **90.0%** |

探针覆盖：物品归属链、人物身体状态连续性、世界规则不被破坏、
角色认知与客观事实分离、不可靠叙述、延迟伏笔回收、过去/现在时间线交叉。

**两者共同失败**：P15（第 17 章"韩策索要残页被拒 + 两人关系破裂"）——
两个系统都写出了"拒绝"，但都没有写成"关系破裂"，作者意图的后半段未被落实。

**分歧项**：
- P08（第 9 章钥匙开启机械切换盒）：B 失败（正文改用套筒扳手打开），C 通过
- P16（第 18 章离线终端归二人共同掌握）：B 通过，C 失败（仅乔宁持有）

### 2. 盲评（位置平衡，每个单元双序各评一次）

**B vs C —— 30 章共同范围，唯一具统计意义的比较**

| 维度 | Jarvis-Write | AI_NovelGenerator | 胜出 |
|---|---|---|---|
| 作者意图遵循 | 3.90 | **4.45** | AI_NovelGenerator |
| 正文质量 | 4.150 | 4.167 | 实质平手 |
| 读者偏好 | **4.067** | 3.883 | Jarvis-Write |

**A vs B / A vs C —— 各仅 1 章共同范围**：A 在作者意图遵循上胜出
（5.0 vs 4.0；4.0 vs 3.0），其余为平手或小幅领先。**n=1，不具统计意义。**

### 3. 位置偏差（重要方法学发现）

三对比较的位置偏差为 **+0.417 / +0.917 / +0.583**——
**评委系统性地偏向先展示的文稿**。双序平均是必要的；单序盲评会产生偏置结论。

### 4. 成本与吞吐

| 系统 | 每章 Writer 调用 | 每章 tokens | 总 tokens | 正文字数均值 |
|---|---|---|---|---|
| A | 4.0 | 97,912 | 145,912 | 2762 |
| B | **1.0** | **26,398** | 791,926 | 2643 |
| C | 4.97 | **174,430** | 5,232,885 | 2604 |

同样一部小说、同一个模型：**Jarvis 每章 1 次调用 / 2.6 万 tokens；
AI_NovelGenerator 每章约 5 次调用 / 17.4 万 tokens——单章成本差 6.6 倍。**

---

## 二、A 轨为何只跑出 1 章

第 1 章**已提交并被接受**。第 2 章组装写作包时，Zhanghui 自身的 Canon 发现冲突：

```
canonical fact conflict at chapter 1: ('lin_yue', 'investigation.status')
```

根因：同一语义位置产生两种不同表示——

- **Writer 的 `<chapter_changes>` 提案**：自由文本 `new_state`，未指定字段
- **Data Agent 的 `state_deltas`**：字段级 delta，且 `old` 值是它自行推断的

两者投影到同一 `(lin_yue, investigation.status)` 后取值不一致。

`prepare` 对已提交 Canon 是确定性的，因此未重试。这是该架构下的**稳定失败模式**：
早前一轮（run-001）曾以 `('林越','左手机能')` 的形式独立出现过同一类冲突。

**执行器未做任何修补**：未修改冻结场景、未修改 Zhanghui 生产代码、未直接写数据库。

---

## 三、原生工作流真实性

- **B Jarvis-Write**：`_prepare_chapter_context → Composer._draft_prompt →
  apply_chapter_tail（故事圣经事实抽取 + 伏笔调度 + 滚动摘要 + 章末交接契约）→ update_style_memo`。
  30 章后故事圣经终态：**212 条事实 / 103 个实体 / 91 条伏笔**。
- **C AI_NovelGenerator**：作者计划以产品**原生可编辑文件**（`Novel_architecture.txt` /
  `Novel_directory.txt` / `character_state.txt`）提供 → `Chapter_blueprint_generate` 续写分支
  （0 次 LLM 调用）→ `build_chapter_prompt` → 正文 → `finalize_chapter`
  （更新 `global_summary.txt`、`character_state.txt`、**创建 Chroma 向量库**）→ `check_consistency`。
- **A Zhanghui**：`ChapterRuntime.prepare → runtime governed-context → attach_creative_brief →
  to_writer_prompt → ingest_draft → runtime reviewer-context → prepare_data_agent_input.py →
  reconcile_changes → commit → publish_accepted_draft`。

**明确记录**：C 轨跳过了 `Novel_architecture_generate`。该步会无条件覆写架构文件，
且其 `core_seed_prompt` 提示词模板**没有 `{user_guidance}` 占位符**，因此无法接收作者输入——
系统只能从"书名+类型+篇幅"自创故事。这是产品能力限制，不是绕过。
本报告**不声称执行了该原生步骤**。

---

## 四、必须随结论一并阅读的限制

1. **A 轨只有 1 章**，与 B/C 的任何对比都是 n=1，不具统计意义。
2. **Writer 不是 Claude**，是 `deepseek-v4.1-flash`。本报告不对 Claude 行为作任何断言。
3. **评委与 Writer 是同一模型**，存在自我偏好风险；位置平衡只缓解顺序偏差，不能消除它。
4. **单一场景、单一随机种子**，不外推到多场景统计结论。
5. A 轨本轮的上下文来源经过公平性修复（改用原生 governed-context 与原生 prose-only artifact），
   因此其本次冲突**不能直接等同于**早前那次的同类冲突。
6. 早前阶段（Stage 1）的 AI_NovelGenerator 同样存在共同故事规划偏离，
   旧的对比结论**不能**解释为"同一故事任务下的架构优势"。

---

## 五、方法学说明

- 三系统收到**逐字节相同**的作者级创作要求（962 字符前缀），含：故事前提、
  世界硬规则、人物及初始状态、物品及初始归属、全书主线、本章目标与关键变化、
  连续性规则、目标字数。各系统内部如何检索与组织上下文，仍由各自原生架构决定。
- **评估探针的正确答案从未进入任何 Writer 上下文**——277 个已发出 prompt 全部通过污染审计。
- 评估器：盲评（评委不知道文稿来自哪个系统）+ 位置平衡（每单元双序各评一次）+
  每个输入记录 SHA256 + 长文分窗口评估 + 事实证据引用 + 确定性聚合。
- 评委侧共 425 次调用，**传输完整性全部通过，零截断**。
- 全部运行证据（逐章回执、调用记录、输入输出 SHA256、tokens、失败现场）留存于
  `runs/pilot-tide-archive-001/stage2-run-003/`。
