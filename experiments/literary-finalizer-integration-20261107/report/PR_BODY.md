## 目标

把已 held-out 验证的“文学减法编辑”接入正式 `webnovel-write`，并通过修正 acceptance 边界，
让“删掉显式解释但不改变故事状态”的候选真正进入最终正文。

## 改动

- 新增 `scripts/data_modules/literary_finalizer.py`：五原则 / 三护栏 / 保护清单、prompt 组装、
  确定性护栏（≥90%、数字/日期/编号值集合、受保护术语）、复用既有语义 Judge、失败回退无缝。
- 新增 CLI：`prose literary-finalize-prompt`、`prose literary-finalize-validate`。
- **Acceptance 边界修正**：
  - `judge-request --state-impact`（仅 Step 2B）要求 Judge 给每条 change 标
    `STORY_STATE | DISCOURSE | UNKNOWN`；
  - Finalizer 只阻断 `STORY_STATE` / 未标注 / `UNKNOWN` / 绑定或 Judge 失败；
  - 明确 `DISCOURSE` 的话语层压缩放行；`ownership` / `world_rule` 保留硬拒绝；
  - 其他流程的 Judge 请求与行为不变（默认 `UNKNOWN`，仍 fail-closed）。
- `literary-finalize-prompt --context-output` 输出 Judge 参考用 Canon/Intent。
- Step 2B 成为唯一文学环节；Step 4 删除整章文学润色，保留定向修复 / 事实纠错 / 排版。
- `webnovel-fast-write` 跳过文学定稿。
- 测试：`tests/unit/test_literary_finalizer.py` 16 例。

未新增 Agent / Router / 数据库 / 状态系统 / 文学评分 / 语义分类框架。

## 短 E2E（复用 PR #68 已生成候选，未重新生成正文）

| 章 | 长度比 | Judge changes | 最终 |
|---|---:|---|---|
| ch03 | 91.53% | 14 条全部 DISCOURSE | **采用候选** |
| ch05 | 90.66% | 6 条全部 DISCOURSE | **采用候选** |
| ch07 | 93.88% | 3 DISCOURSE + 1 STORY_STATE + 1 硬保护 | 回退 Writer raw |

- ch07 拒绝项：“一登记就等于当众揭了梅叔的盖子”（必要因果，无法从保留正文恢复）；
  “唯一能带出档案屋的实物……”（`ownership` 硬保护）。
- 逐条分类：`experiments/literary-finalizer-integration-20261107/analysis/RECLASSIFICATION.md`
- 内容复检：ch03 / ch05 无真实 story-state loss；ch07 危险变化未进入最终正文。
- 盲评仍为 PR #68 的 **36/36 全票候选**；ch03 / ch05 的增益现已进入最终正文。

## 测试

```
tests/unit/test_literary_finalizer.py   16 passed
tests/unit（全量）                     394 passed, 1 pre-existing failed
```

失败用例为既有 `test_stage2_repair_regression.py::test_canonical_cli_invocations_are_identical_across_skills`
（未跟踪的 `references/draft-review-lifecycle.md` 缺 `--enforce-auto-budget`），与本改动无关。

## 判定

**PASS**：文学候选进入最终正文（2/3），采用章节无真实故事状态损失，危险变化仍被拒绝，
未增加复杂系统。满足合并条件；不自行合并。

详细报告：`experiments/literary-finalizer-integration-20261107/report/REPORT.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
