# project_pacing_drift fixture

故意违反 Pacing Tracker 规则：
- chapters 1-4 都用 tier=fast（连续 4 章快档）
- max_consecutive_fast=1，但实际连续 4 章
- slow_per_4_chapters_min=1，但最近 4 章全是 fast（0 个 slow）

预期：P4 pacing_tracker patch 在 chapter=4 时报 BLOCKER（连续快档超限 + 慢档配额缺失）。
