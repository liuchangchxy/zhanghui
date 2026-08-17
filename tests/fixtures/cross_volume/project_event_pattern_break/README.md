# project_event_pattern_break fixture

故意违反 Event Matrix 规则：
- chapters 1-5 都用 conflict_thrill（fast 类型）
- max_consecutive_fast=2，但实际连续 5 章
- gentle_window=5，但最近 5 章全是 fast，没有任何 soft 类型

预期：P3 event_matrix patch 在 chapter=5 时报 BLOCKER（连续快档超限 + gentle 配额缺失）。