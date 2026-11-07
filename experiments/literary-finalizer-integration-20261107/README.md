# 文学减法编辑正式集成 — 短 E2E 证据

- 日期：2026-11-07
- 分支：`feat/literary-finalizer-integration`
- 目的：验证已经通过 held-out 的“文学减法编辑”接入正式 `webnovel-write` 流程后，
  在 2–3 个真实 Writer 章节上继续产生文学收益，同时不破坏事实、推进信息与原有文学承载。
- 不是新一轮 prompt 研究，也不是同类型 A/B。五条原则与三条护栏沿用
  `experiments/jarvis-literary-heldout-20261107`（PR #67）冻结版本。

## 章节

| 章 | 样本类型 | 来源 |
|---|---|---|
| 第 3 章 | 信息/推理密集（数字 19、7、67，时间线） | 2026-10-29 Zhanghui E2E `raw.prose.md` |
| 第 5 章 | 常规对话/人物冲突（梅叔、乔宁） | 同上 |
| 第 7 章 | 明确章末钩子（“明天拿到钥匙的时候……”） | 同上 |

只做一次生成。截断/空输出才允许机械重试，不做“再试一次更好”的重复生成。
门槛未过则回退 Writer 原稿，不换 prompt、不追加第二轮文学润色。

## 流程

1. `prose literary-finalize-prompt`：从既有 governed-context 取 outline / 约束 / VoiceTarget，
   从下一章章纲取开头，生成唯一 prompt；同时输出剥离 CHANGES 与封包指纹的纯正文 source。
2. 宿主模型执行一次定稿，产出 `step2b_candidate`。
3. `prose judge-request` → 宿主 Judge（本实验用 `codex/gpt-6.1-terra`，与编辑模型不同族）
   → `prose judge-bind`。
4. `prose literary-finalize-validate`：≥90% 长度、数字/日期/编号值集合、受保护术语，
   再复用现有 semantic gate（`STYLE_ONLY_SAFE` 才放行）。
5. 盲评：Writer raw vs finalizer final，两位评审（codex / Gemini 3.8 Flash），
   每章正反两次，六维。
6. 单独内容检查：推进信息、推理连接、章末钩子、潜台词动作、感官承载、术语、数字日期、
   知情状态、事件结果。

## 目录

```
inputs/       三章 Writer raw 快照
outputs/      每章 prompt / source / candidate / final / gate
judge/        语义裁决 request / response / verdict
blind/        盲评 prompt、匿名映射、原始判断
results/      运行记录
analysis/     自动内容筛查 + 手检
report/       结论
scripts/      可复现脚本
```

## 结果速览（v2：acceptance 边界修正后）

| 章 | 长度比 | Judge changes | 最终 |
|---|---:|---|---|
| ch03 | 91.53% | 14 条全部 DISCOURSE | 采用候选 |
| ch05 | 90.66% | 6 条全部 DISCOURSE | 采用候选 |
| ch07 | 93.88% | 3 DISCOURSE + 1 STORY_STATE + 1 硬保护 | 回退 Writer raw |

- 逐条重新分类：`analysis/RECLASSIFICATION.md`。
- 内容复检：采用的两章无真实 story-state loss；ch07 必要因果被正确拒绝。
- 盲评（raw A vs 候选 B）：36/36 全票 B；ch03/ch05 的增益现在进入最终正文。
- 判定 **PASS**，详见 `report/REPORT.md`。

### v1（修正前，保留对照）

三章全部因 Judge 把“删显式解释”判为语义变化而整体回滚；候选盲评 36/36 优于 raw，
说明增益存在但被 acceptance 层挡住。v1 记录见 `results/run_records.json` 与 `analysis/DIFFS.md`。

## 复现

```bash
python3 scripts/run_e2e.py            # v1：生成候选 + 旧 acceptance
python3 scripts/run_blind.py
python3 scripts/aggregate_blind.py
python3 scripts/content_check.py
python3 scripts/revalidate_gate.py    # v2：复用候选，只重跑 Judge + acceptance
python3 scripts/content_check.py v2
```
