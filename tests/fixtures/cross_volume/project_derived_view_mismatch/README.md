# project_derived_view_mismatch fixture

故意制造派生视图与 state 不一致：
- state.json 中 foreshadow_chain.dag 包含 fs_001 / fs_002 / **fs_005**
- views/foreshadow_table.md 只列出 fs_001 / fs_002（缺失 fs_005）

预期：P7 derived_views patch 在 chapter=5 时报 BLOCKER（foreshadow_table 缺少 fs_005）。
