# project_reader_contract_breach fixture

故意违反 Reader Contract 三类规则：
- 期待债堆积: 11 项未偿还 (上限 10)
- 因果权: 主角使用 2 个未铺垫能力（"突然领悟绝学"、"使用未知道具"）
- 终局底牌超用: er_001 在 ch5 用，er_003 在 ch8 用（共 2 个，上限 1）

预期：P6 reader_contract patch 在 chapter=10 时报 BLOCKER（期待债堆积 + 终局底牌超用）。
因果权检查需要 chapter_text — 测试中通过 ctx.chapter_text 注入。
