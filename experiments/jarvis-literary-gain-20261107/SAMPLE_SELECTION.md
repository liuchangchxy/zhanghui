# 样本选择（生成前冻结）

- 冻结时间：2026-11-07（在本轮任何编辑生成之前写入并计算 sha256）
- 数据源：`/Users/chang/Desktop/Code/zhanghui-benchmark/runs/clean-e2e-jarvis-vs-zhanghui-2026-10-29`
- 文本臂：A = `e2e/zhanghui/chNN/published.md`（Zhanghui 当前 final）；Jarvis final 只作分析参考，不进入编辑器输入，也不进入 A/B 盲评。
- 盲评依据：`study/audits/2026-11-07-jarvis-vs-zhanghui-literary-recompute.md`（严格 12 维，46:36，p=0.32，基本打平）；逐维判定来自 `blind/results/e2e.chNN.final/pass{1,2}/judgement.json`。

## 选择规则（先定规则，再看章节）

1. 至少 2 章：Jarvis 在 `READING_APPEAL` 与 `LOW_AUTHOR_EXPLANATION` 两维都两遍一致胜出，且整体文学维度明显领先。
2. 至少 1 章：Zhanghui 在 `SENTENCE_NATURALNESS` 与 `SCENE_IMMERSION` 两维都两遍一致胜出（章回的优势章）。
3. 至少 1 章：双方接近或评委分歧大（SPLIT 占多数），用于检验编辑不会在无稳定基线时制造退步。
4. 四章覆盖不同场景类型与不同叙事压力，避免只挑同一种文本。
5. 选择只看生成前已有的盲评记录，不看本轮编辑结果；选定后不因结果替换章节。

## 冻结样本

| 章 | 选择角色 | 原盲评关键结果（两遍一致才计） | 选择原因 |
|---|---|---|---|
| ch05 | Jarvis 优势最强 | 严格 12 维 Jarvis 12 : Zhanghui 0；`READING_APPEAL` J 2/2、`LOW_AUTHOR_EXPLANATION` J 2/2、`SENTENCE_NATURALNESS` J 2/2、`SCENE_IMMERSION` J 2/2 | 唯一一章 Jarvis 全维胜出。最适合看“更抓人、少解释”的机制能否被迁移，同时观察是否损伤章回原有的自然度。 |
| ch03 | Jarvis 优势次强 | 严格 9 : 1（2 SPLIT）；`READING_APPEAL` J 2/2、`LOW_AUTHOR_EXPLANATION` J 2/2、`SUBTEXT` J 2/2；`SENTENCE_NATURALNESS` / `SCENE_IMMERSION` 均 SPLIT；章首自然度 Z 胜 | 第二个 Jarvis 在目标两维稳定胜出的样本；同时章回在章首与部分场景仍有优势，用来检验“保住优势”的约束是否有效。 |
| ch08 | Zhanghui 优势章 | 严格 10 : 1（1 SPLIT）；`SENTENCE_NATURALNESS` Z 2/2、`SCENE_IMMERSION` Z 2/2、`SUBTEXT` Z 2/2、`LITERARY_QUALITY` Z 2/2；只有 `READING_APPEAL` J 2/2 | 关键 trade-off 样本：章回在自然度/沉浸/潜台词上全面领先，却仍在阅读吸引力上输给 Jarvis。用来验证编辑能否只提升吸引力而不破坏原有优势。 |
| ch04 | 分歧/接近章 | 严格 9 SPLIT、Z 2、J 1；`READING_APPEAL` SPLIT、`LOW_AUTHOR_EXPLANATION` SPLIT、`SCENE_IMMERSION` SPLIT；只有 `SENTENCE_NATURALNESS` Z 2/2、`DESCRIPTION` J 2/2 | 评委在位置反转后大面积改判，没有稳定章级结论。用来检验编辑器在“基线不稳定”的章节会不会把 SPLIT 变成系统性退步。 |

## 不选章节及原因（预注册）

- ch01：Jarvis 11:0，但目标两维中 `READING_APPEAL` 为 SPLIT，不是“稳定胜出”样本；与 ch05 功能重复。
- ch02 / ch06：Zhanghui 大幅领先，Jarvis 只赢 `READING_APPEAL`；与 ch08 功能重复，且 ch06 在旧 Finalizer 实验中出现过重要内容误删，本轮不重复使用该失败样本。
- ch07 / ch10：SPLIT 占绝对多数（7/10、10/10），比 ch04 更接近“无信号”；四章规模下保留一个即可。
- ch09：Jarvis 6:4，目标两维中 `READING_APPEAL` 为 SPLIT、`LOW_AUTHOR_EXPLANATION` 为 SPLIT（pass2 反转），不满足“稳定胜出”。

## 盲评设计（与样本同时冻结）

- 每章只比较 A（原文）与 B（编辑后）。Jarvis final 不参与。
- 六维：`OVERALL_PREFERENCE`、`READING_APPEAL`、`LOW_AUTHOR_EXPLANATION`、`SENTENCE_NATURALNESS`、`SCENE_IMMERSION`、`SUBTEXT`。
- 两位评委、不同模型族：J1 = `codex/gpt-6.1-terra`（与 10-29 盲评同一评委模型）；J2 = Antigravity Gemini 3.8 Flash。
- 每位评委对每章跑两遍，第二遍强制位置反转；只有两遍指向同一真实臂才计为该臂胜，否则记 SPLIT。
- 不混入 Canon、Intent、流程治理维度。

## 变更政策

样本在本文件写入后冻结。若生成失败（截断、空输出、格式错误），只允许用同一 prompt、同一模型、同一参数重跑该章，并在 `MANIFEST.json` 记录；不得换章、不得改 prompt。
