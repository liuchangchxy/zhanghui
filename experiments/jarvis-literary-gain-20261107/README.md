# Jarvis 文学增益迁移实验 — 2026-11-07

独立实验原型。目标只有一个：

> 验证能否让 Zhanghui 在保住现有文学优势（句段自然度、场景沉浸、章首自然度）的前提下，
> 提高阅读吸引力、减少作者解释。

本目录不属于生产主链。没有修改 Writer / Reviewer / Commit / Canon / Step 2B / Step 4；
没有新增 Agent；没有重跑完整 E2E；没有改评分系统。

## 设计

- A = Zhanghui 当前 final（2026-10-29 benchmark 的 `e2e/zhanghui/chNN/published.md`，去掉封包指纹）
- B = 同一个 A 经过一次最小文学编辑后的版本
- Jarvis final 只用于分析，不进入编辑器输入，也不进入 A/B 盲评

样本在生成前冻结（`SAMPLE_SELECTION.md` + `FREEZE.json`）：ch03、ch04、ch05、ch08。
选择规则与原因见 `SAMPLE_SELECTION.md`。

## 最小编辑原则

来自 10 章 final-vs-final 的实际正文对比，最多五条，见 `analysis/ANALYSIS.md` 与
`prompts/editor_zh.md`：

1. 删叙述者对动作/对白的意义总结。
2. 对白说清的信息不再由叙述者翻译。
3. 同一信息只留一处，删“总结—再总结”。
4. 章末收在已有动作/画面/新消息上。
5. 用已有的时间/身体/危险限制组织节拍；不新增事实。

## 盲评

- 六维：`OVERALL_PREFERENCE`、`READING_APPEAL`、`LOW_AUTHOR_EXPLANATION`、
  `SENTENCE_NATURALNESS`、`SCENE_IMMERSION`、`SUBTEXT`
- 两位不同模型族评委：J1 `codex/gpt-6.1-terra`；J2 Antigravity Gemini 3.8 Flash
- 每章每位评委两遍，第二遍强制位置反转；两遍同臂才计胜，否则 SPLIT
- 盲评提示词、原始输出、逐维证据与聚合结果都在 `blind/`

## 复现

```bash
cd experiments/jarvis-literary-gain-20261107
python3 scripts/prep_inputs.py      # 冻结 A 输入与本章意图
python3 scripts/freeze.py           # 预注册哈希
python3 scripts/run_editor.py 3 4 5 8
python3 scripts/check_preservation.py
python3 scripts/run_blind.py
python3 scripts/aggregate_blind.py
```

编辑器模型：本地 Anthropic 兼容代理 `group/mac-deepseek4.1-gpt[1m]`，
temperature 0.4，max_tokens 16000。每次调用的 metadata 在 `outputs/chNN_run/`。
