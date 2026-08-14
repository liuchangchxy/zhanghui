---
name: webnovel-style-profile
description: 章节文风指纹生成 + 跨章漂移检测。可在项目 ≥ 3 章时自动建立基线，每章写完后输出 drift advisory，用户主动调 --compare 做两章详细对比。仅做可计算的量化指标（句长/对话/标点/段长），不做 LLM 归纳。使用时机：跨章文风漂移检测、基线建立、风格对比。
allowed-tools: Read Grep Bash Write Edit
---

# Style Profile & Drift Detector

## 目标

- 用「确定性算法」量化章节文风：句长分布、标点密度、对话占比、说话标签密度、平均段长。
- 在项目 ≥ 3 章时建立基线指纹；每章写完后跑漂移检测，输出 advisory（非阻断）。
- 用户主动调 `--compare A B` 时输出两章详细对比。

**与已有管线的关系**：
- 与 `webnovel-deslop-check`（独立 anti-slop 扫描）正交：deslop 查 AI 痕迹与禁词，style-profile 查「与基线是否漂移」。
- 与 `webnovel-write` Step 4 润色对接：Step 4 可选调 `--drift` 拿 advisory。
- 与 `webnovel-review` 对接：新增 `--style-drift` flag。

## 触发场景

| 触发词 | 行为 |
|---|---|
| 「建立基线 / 生成 baseline」 | 跑 `--baseline` |
| 「检查漂移 / 风格漂移 / drift」 | 跑 `--drift` |
| 「对比第 X / Y 章」 | 跑 `--compare A B` |
| 「第 N 章文风指纹」 | 跑默认（无 flag） |
| Step 4 润色后 / Step 5 完成后 | 内部触发 `--drift`，advisory 写入 `.webnovel/style-profile/drift-ch{N}.md` |

## 三阶段工作流

### Stage 1：基线生成

**触发条件**：项目章节数 ≥ 3 时自动触发（首次 / 重新生成）。

**行为**：
1. 读取 `.webnovel/style-profile/ch*.json`（已落盘的指纹）按章号升序，取前 3 章
2. 对每个维度算 mean / min / max
3. 写 `.webnovel/style-profile/baseline.json`
4. 标 `confidence: high`（3 章）/ `med`（1-2 章）

**手动调用**：
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/style_fingerprint.py" \
  --project "${PROJECT_ROOT}" \
  --chapter 3 \
  --baseline

```

**自定义基线章**：
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/style_fingerprint.py" \
  --project "${PROJECT_ROOT}" \
  --chapter 3 \
  --baseline \
  --baseline-chapters 1 2 3

```

### Stage 2：每章写完后跑漂移

**触发条件**：Step 5 data-agent 完成后自动调（best-effort，失败不阻断）。

**行为**：
1. 计算当前章指纹
2. 写 `.webnovel/style-profile/ch{NNNN}.json`
3. 读 `baseline.json`，比对所有维度
4. 阈值见 `references/profile-protocol.md`
5. 输出 markdown advisory → `.webnovel/style-profile/drift-ch{NNNN}.md`

**手动调用**：
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/style_fingerprint.py" \
  --project "${PROJECT_ROOT}" \
  --chapter 7 \
  --drift

```

**advisory 样例**（仅在出现 warn / risk 时生成实质内容）：
```markdown
# 第 7 章 文风漂移报告

- 基线章：第 1, 2, 3 章（3 章）
- 置信度：high

## 漂移告警
- 🟠 **长句(>30) 占比**：基线 8.0 → 当前 24.0（绝对变化 +16.0pp，阈值 10）
- 🔴 **对话占比**：基线 35.0 → 当前 5.0（绝对变化 -30.0pp，阈值 15）

## 建议
- 漂移本身不等于错误；如剧情需要（战斗章、对话章）可保留。
- 若无明确剧情原因，建议在 Step 4 润色时回看一下。

```

### Stage 3：用户主动调 --compare

**触发**：用户说「对比第 X 和第 Y 章」或「比较 1 和 5 章」。

**行为**：
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/style_fingerprint.py" \
  --project "${PROJECT_ROOT}" \
  --chapter 1 \
  --compare 1 5

```

**输出**：markdown 表格，所有 8 维度两两对比 + 差异。

## 输出文件

```
项目根/
└── .webnovel/
    └── style-profile/
        ├── ch0001.json      # 第 1 章指纹
        ├── ch0002.json
        ├── ch0003.json
        ├── baseline.json    # 基线（mean/min/max + confidence）
        └── drift-ch0007.md  # 第 7 章漂移报告（advisory）

```

## 指纹 schema

详见 `references/profile-protocol.md`。

**8 个核心维度**：
1. `short_lt15_pct` — 短句(<15字) 占比
2. `mid_15to30_pct` — 中句(15-30字) 占比
3. `long_gt30_pct` — 长句(>30字) 占比
4. `avg_len` — 平均句长
5. `punct_density` — 标点密度
6. `dialogue_ratio` — 对话占比
7. `tags_density` — 说话标签密度（每千字）
8. `avg_para_len` — 平均段长

## confidence 分级

| 值 | 触发条件 | 下游处理 |
|---|---|---|
| `high` | ≥ 3 章基线 + 确定性算法 | drift 报告直接采纳 |
| `med` | 1-2 章基线 | drift 报告参考，advisory 语气 |
| `low` | 无基线 / 第一章 | 仅输出指纹，不输出 drift |

## 覆盖/硬约束优先级

**覆盖**（可被 drift 警告调整）：
- 句长分布默认值（>40 字 < 10%）
- 标点默认习惯
- 段落长度默认

**不可覆盖（永远赢）**：
- banned-words（Gate F）
- 章末禁升华
- 禁止万能/堆叠比喻
- 禁止章末预告
- 字数下限

drift 报告是 advisory，**不阻断写作**。

## 接入 webnovel-write（Step 4 polish 可选）

在 Step 4 润色后追加（best-effort）：
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/style_fingerprint.py" \
  --project "${PROJECT_ROOT}" \
  --chapter ${chapter_num} \
  --drift || true

```

输出 advisory 追加到变更摘要末尾。失败仅记 warning，不回滚 Step 4。

## 接入 webnovel-review

新增 `--style-drift` flag。开启时在审查报告中追加「文风漂移」一节。

## 失败处理

| 场景 | 降级 |
|---|---|
| 章节正文缺失 | 返回 error code 1 |
| `.webnovel/state.json` 不存在 | 返回 error code 2（不是有效书项目） |
| 无 baseline.json | 自动用已有指纹生成（仍失败则标 confidence: low） |
| 章节 < 3 章 | 跳过 Stage 1 基线生成，Stage 2 仍可输出指纹但不输出 drift |

## 引用

- 协议与阈值：`references/profile-protocol.md`
- 源算法：`oh-story-claudecode/skills/story-long-analyze/references/style-profile-generator.md:84-97`
