# 文学编辑器 Held-out 外部验证 — 2026-11-07

独立实验。参考 PR #66（`experiments/jarvis-literary-gain-20261107/`）。

唯一目标：

> 冻结 PR #66 的五条文学编辑原则，只在没有参与规则提炼的章节上测试，
> 判断“更抓人、少解释”的机制是否能泛化，同时不损坏内容。

本目录不属于生产主链。没有修改 Writer / Reviewer / Commit / Canon / Data Agent /
reconciliation / Step 2B / Step 4；没有新增 Agent；没有重跑完整 E2E。

## 设计

- 测试集（生成前冻结，固定 6 章）：ch01、ch02、ch06、ch07、ch09、ch10。
- 五条原则逐字复用 PR #66；只新增三个来自上一轮真实失败的护栏：
  推进信息保护、必要推理连接保护、90% 长度硬约束。
- 编辑器模型 / temperature / max_tokens 与 PR #66 相同：
  `group/mac-deepseek4.1-gpt[1m]`，0.4，16000。
- 每章只生成一次 B；仅空输出/截断可技术性重试，不改 Prompt。
- 长度低于原文正文 90%：`EDITOR_REJECT_LENGTH`，不补字、不重跑、不做 A-vs-A 盲评。
- 两位不同模型族评委；每章每位两遍，第二遍强制位置反转；两遍同臂才计胜。

## 产物

- `SAMPLE_SELECTION.md`：测试集与成功标准（生成前）
- `ANALYSIS_PLAN.md`：判定的操作化定义（盲评前）
- `FREEZE.json`：样本、Prompt、全部输入的 SHA-256
- `prompts/editor_zh_heldout.md`：冻结的编辑器 Prompt
- `inputs/`：A 输入、outline、硬限制清单、下一章开头、provenance
- `outputs/`：B、运行记录、长度状态、diff、确定性检查
- `blind/`：盲评提示词、原始输出、逐维证据、聚合
- `analysis/`：人工内容检查
- `report/`：最终报告

## 复现

```bash
cd experiments/jarvis-literary-heldout-20261107
python3 scripts/build_inputs.py
python3 scripts/freeze.py
python3 scripts/run_editor.py 1 2 6 7 9 10
python3 scripts/check_preservation.py
python3 scripts/style_metrics.py
python3 scripts/run_blind.py
python3 scripts/aggregate_blind.py
python3 scripts/judge_table.py
python3 scripts/make_manifest.py
```
