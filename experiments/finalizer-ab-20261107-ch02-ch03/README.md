# Literary Finalizer 全新章节验证：ch02 / ch03

- 日期：2026-11-07
- PRIMARY QUESTION：Literary Finalizer 是否能在两个新的真实章节上稳定提高整章总体文学质量？
- 代码基线：`main` @ `9f8f1c4818951c30769e1383a1e86a034bd10e4f`（PR #68 + PR #69）
- 书项目：`/Users/chang/Desktop/根源牌序`
- 样本：第 0002 章、第 0003 章（全新生产章节，未参加任何文学实验）
- 对照：ch01 = `ROUGHLY_TIED`（来自 `experiments/real-chapter-e2e-20261107`）

## 冻结协议

每章严格执行：

```
正常写前准备 → Writer raw → Finalizer candidate → 冻结 raw / candidate
→ 文学 A/B（匿名、两模型族、位置反转）
→ 人工阅读 raw / candidate / diff / 两份 Judge 理由并裁定
→ story-state 安全检查
→ 之后才继续 Reviewer / Step 4 / Data Agent / commit / publish
```

文学裁定发生在 Reviewer 修改正文之前。raw 与 candidate 在 A/B 前复制到本目录并记录 SHA-256；
后续 Reviewer / Step 4 的改动不得进入文学比较样本。

## A/B 协议

- 只评 6 维：`OVERALL_PREFERENCE`、`READING_APPEAL`、`LOW_AUTHOR_EXPLANATION`、
  `SENTENCE_NATURALNESS`、`SCENE_IMMERSION`、`SUBTEXT`。
- J1：Antigravity Gemini Flash（中性 project），甲=raw、乙=candidate。
- J2：本地 Anthropic-compatible proxy（会话模型组），甲=candidate、乙=raw（位置反转）。
- 不因评审分裂增加第三位评审或新维度。
- 最终裁定不数票；由主流程完整阅读三份材料后三选一。

## 目录

```
ch02/raw.md             Writer raw（冻结快照）
ch02/candidate.md       Finalizer candidate（冻结快照）
ch02/diff.txt           raw → candidate 统一 diff
ch02/blind/             两位 Judge 的 prompt / response / result / key
ch02/decision.md        人工裁定、决定性 diff、O2、story-state
ch03/...
REPORT.md               最终报告
```
