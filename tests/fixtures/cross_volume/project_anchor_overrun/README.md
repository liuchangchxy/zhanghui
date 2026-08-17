# project_anchor_overrun fixture

故意违反 Volume Anchor 规则：
- total_chapters=10 但 current_chapter=5（仅完成 50%）
- 在 chapter=8 时检查：实际进度 50% vs 期望进度 80%，偏离 30%（>15% 阈值）

预期：P2 volume_anchor patch 在 chapter=8 时报 BLOCKER（进度偏离）。