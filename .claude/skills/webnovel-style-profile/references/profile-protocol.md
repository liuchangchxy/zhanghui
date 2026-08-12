# Style Profile Protocol

> 输出 schema、阈值与 confidence 规则。所有数值由 `style_fingerprint.py` 确定性计算，不做 LLM 归纳。

## Fingerprint schema（`{项目}/.webnovel/style-profile/ch{NNNN}.json`）

```json
{
  "chapter": 1,
  "chapter_file": "正文/第0001章-归乡人的觉醒.md",
  "char_count": 3200,
  "sentence_count": 87,
  "short_lt15_pct": 42,
  "mid_15to30_pct": 45,
  "long_gt30_pct": 13,
  "avg_len": 18,
  "punct_density": 12,
  "dialogue_ratio": 35,
  "tags_density": 8,
  "paragraph_count": 24,
  "avg_para_len": 130,
  "generated_at": "2026-08-11T10:00:00Z"
}

```

| 字段 | 含义 | 单位 |
|---|---|---|
| `chapter` | 章号 | 整数 |
| `chapter_file` | 章节文件相对路径 | 字符串 |
| `char_count` | 非空白字符总数 | 字符 |
| `sentence_count` | 切分后的句子数 | 句 |
| `short_lt15_pct` | 短句(<15字) 占比 | 百分点 |
| `mid_15to30_pct` | 中句(15-30字) 占比 | 百分点 |
| `long_gt30_pct` | 长句(>30字) 占比 | 百分点 |
| `avg_len` | 平均句长 | 字符 |
| `punct_density` | 标点密度（标点数 / 非空白字符） | 百分点 |
| `dialogue_ratio` | 引号内字数 / 非空白字符 | 百分点 |
| `tags_density` | 说话动词次数 / 千字 | 整数 |
| `paragraph_count` | 段数 | 整数 |
| `avg_para_len` | 平均段长（非空白字符） | 字符 |
| `generated_at` | 指纹生成 UTC 时间 | ISO 8601 |

## Baseline schema（`{项目}/.webnovel/style-profile/baseline.json`）

```json
{
  "ok": true,
  "baseline_chapters": [1, 2, 3],
  "char_count_mean": 3050,
  "metrics": {
    "short_lt15_pct": {"mean": 42.0, "min": 40.0, "max": 44.0},
    "mid_15to30_pct": {"mean": 45.0, "min": 43.0, "max": 47.0},
    "long_gt30_pct":  {"mean": 13.0, "min": 12.0, "max": 14.0},
    "avg_len":        {"mean": 18.0, "min": 17.0, "max": 19.0},
    "punct_density":  {"mean": 12.0, "min": 11.0, "max": 13.0},
    "dialogue_ratio": {"mean": 35.0, "min": 33.0, "max": 37.0},
    "tags_density":   {"mean":  8.0, "min":  7.0, "max":  9.0},
    "avg_para_len":   {"mean": 130.0,"min": 120.0,"max": 140.0}
  },
  "thresholds": {
    "short_lt15_pct": 15,
    "mid_15to30_pct": 15,
    "long_gt30_pct": 10,
    "avg_len": 5,
    "punct_density": 5,
    "dialogue_ratio": 15,
    "tags_density": 50,
    "avg_para_len": 30
  },
  "confidence": "high",
  "generated_at": "2026-08-11T10:00:00Z"
}

```

## 漂移阈值

漂移判定逻辑（来自 `style_fingerprint.py:detect_drift`）：

```
delta = current - baseline.mean
severity = "risk"  if |delta| >= 2 * threshold
        = "warn"  if |delta| >= threshold
        = "ok"    otherwise

```

| 维度 | threshold (warn) | risk (2x) | 单位 |
|---|---:|---:|---|
| `short_lt15_pct` | 15 | 30 | 百分点 |
| `mid_15to30_pct` | 15 | 30 | 百分点 |
| `long_gt30_pct` | 10 | 20 | 百分点 |
| `avg_len` | 5 | 10 | 字符 |
| `punct_density` | 5 | 10 | 百分点 |
| `dialogue_ratio` | 15 | 30 | 百分点 |
| `tags_density` | 50 | 100 | 相对 % |
| `avg_para_len` | 30 | 60 | 字符 |

注意：`tags_density` 是相对值（baseline 8 → 12 等于 +50%），其它是绝对百分点。

## confidence 字段

| 值 | 触发条件 |
|---|---|
| `high` | ≥ 3 章基线 + 确定性算法 |
| `med` | 1-2 章基线 |
| `low` | 无基线 / 第一章 |

## 覆盖与硬约束优先级

- **可被覆盖**（drift 建议可调整）：
  - 句长分布默认值
  - 标点默认习惯
  - 段落长度默认
- **不可被覆盖**（永远是硬约束）：
  - banned-words（参考 `references/shared/banned-words.md`）
  - 章末禁升华
  - 禁止万能/堆叠比喻
  - 禁止章末预告
  - 字数下限

drift 报告是 **advisory**，不阻断写作，不直接修改正文。

## 算法引用

句长/标点统计 1-liner 来自 `oh-story-claudecode/skills/story-long-analyze/references/style-profile-generator.md:84-97`：

```python
sents = [s for s in re.split(r'[。！？]+', text) if s.strip()]
total = max(len(sents), 1)
short = sum(1 for s in sents if len(s) < 15)
mid   = sum(1 for s in sents if 15 <= len(s) <= 30)
lng   = sum(1 for s in sents if len(s) > 30)
chars = max(sum(1 for c in text if not c.isspace()), 1)
puncts = sum(1 for c in text if c in '，。！？；：、…—""\'\'')
avg = sum(len(s) for s in sents) // total

```

本 skill 在此基础上扩展：
- 对话占比（全/半角引号字数）
- 说话标签密度（动词统计）
- 段落统计
- 漂移检测（基线 + threshold）
- CLI 与 JSON 落盘
