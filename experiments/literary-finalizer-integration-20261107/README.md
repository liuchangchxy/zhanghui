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

## 结果速览

| 章 | 长度比 | 确定性护栏 | 语义门禁 | 最终 |
|---|---:|---|---|---|
| ch03 | 91.53% | 通过 | 拒绝（2 处） | Writer raw |
| ch05 | 90.66% | 通过 | 拒绝（6 处） | Writer raw |
| ch07 | 93.90% | 通过 | 拒绝（4 处） | Writer raw |

- 盲评（raw A vs 被拒候选 B，诊断性质）：36/36 全票 B，章级 OVERALL strict B 3/3。
- 人工内容检查：3 章候选均删除了受保护内容（潜台词动作、短情绪落点、因果连接、
  唯一线索/归属、首次性事实），门禁拒绝成立，不是误杀。
- 判定 **PARTIAL**，详见 `report/REPORT.md`。

## 复现

```bash
python3 scripts/run_e2e.py
python3 scripts/run_blind.py
python3 scripts/aggregate_blind.py
python3 scripts/content_check.py
```
