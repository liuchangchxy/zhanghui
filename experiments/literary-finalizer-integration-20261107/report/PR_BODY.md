## 目标

把已经 held-out 验证的“文学减法编辑”（PR #66 / #67）接入正式 `webnovel-write` 流程，取代重复的文学后处理，并用 3 个真实章节做短 E2E 验收。

## 改动

- 新增 `scripts/data_modules/literary_finalizer.py`：冻结五原则 / 三护栏 / 保护清单、prompt 组装、确定性校验（≥90%、数字/日期/编号值集合、受保护术语）、复用既有语义门禁、失败回退 Writer raw。
- 新增 CLI：`prose literary-finalize-prompt`、`prose literary-finalize-validate`。
- `webnovel-write/SKILL.md`：
  - Step 2B 由“文风适配（rewrite-only）”改为“文学减法定稿”，成为**唯一**文学编辑环节；
  - Step 4 删除整章文学润色（`polish-guide.md`），保留 Reviewer 问题定向修复、事实纠错、`typesetting.md`；
  - 明确失败回退 Writer raw，不重复生成。
- `webnovel-fast-write/SKILL.md`：快车道跳过文学定稿。
- 新增 `tests/unit/test_literary_finalizer.py`（8 例）。
- 新增 `study/audits/2026-11-07-literary-finalizer-integration.md` 与短 E2E 实验证据。

未新增 Agent / Router / 数据库 / 状态系统 / 文学评分 / 语义分类框架。

## 短 E2E 结果（ch03 / ch05 / ch07）

| 章 | 类型 | 长度比 | 确定性护栏 | 语义门禁 | 最终 |
|---|---|---:|---|---|---|
| ch03 | 信息/推理密集 | 91.53% | 通过 | 拒绝（2 处） | Writer raw |
| ch05 | 对话/人物冲突 | 90.66% | 通过 | 拒绝（6 处） | Writer raw |
| ch07 | 章末钩子 | 93.90% | 通过 | 拒绝（4 处） | Writer raw |

- 数字/编号/日期值集合 3 章均未改变；每章只生成一次，无重试。
- 盲评（Writer raw vs 被拒候选，2 评审 × 正反两次 × 6 维）：**36/36 全票支持候选**，章级 OVERALL strict B 3/3。
- 人工逐句内容检查：3 章候选均删除了受保护内容（潜台词动作、短情绪落点、因果连接、唯一线索/归属、首次性事实），**门禁拒绝不是误杀**。

## 测试

```
tests/unit/test_literary_finalizer.py   8 passed
tests/unit（全量）                     386 passed, 1 pre-existing failed
```

失败用例为既有 `test_stage2_repair_regression.py::test_canonical_cli_invocations_are_identical_across_skills`（未跟踪的 `references/draft-review-lifecycle.md` 缺少 `--enforce-auto-budget`），与本改动无关。

## 判定

**PARTIAL**：机制已最小接入、安全回退正确、无重复文学后处理；但 3/3 真实章节因编辑模型删除受保护内容被门禁拒绝，**最终正文本轮未获得文学增益**。不满足本轮合并条件，建议保留 PR 作为结论与后续修复依据。

详细报告：`experiments/literary-finalizer-integration-20261107/report/REPORT.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
