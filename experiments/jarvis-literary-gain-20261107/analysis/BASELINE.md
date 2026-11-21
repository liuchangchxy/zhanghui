# 10 章 final-vs-final 盲评基线（摘录）

- 来源：`zhanghui-benchmark/runs/clean-e2e-jarvis-vs-zhanghui-2026-10-29` 的 10 对 final 盲评。
- 完整重算：`study/audits/2026-11-07-jarvis-vs-zhanghui-literary-recompute.md`（PR #65 / 分支 `docs/jarvis-literary-recompute-20261107`）。
- 判定规则：同一对文本跑两遍、第二遍位置反转；两遍同臂才计胜，否则 SPLIT。
- 严格 12 维合计：Jarvis 46 / Zhanghui 36 / SPLIT 38（p=0.32，基本打平）。

| 章 | J 严格 | Z 严格 | SPLIT | RA | LAE | SN | SI | SUBTEXT |
|---|---:|---:|---:|---|---|---|---|---|
| 1 | 11 | 0 | 1 | S | J | J | J | J |
| 2 | 1 | 9 | 2 | J | Z | Z | Z | Z |
| 3 | 9 | 1 | 2 | J | J | S | S | J |
| 4 | 1 | 2 | 9 | S | S | Z | S | S |
| 5 | 12 | 0 | 0 | J | J | J | J | J |
| 6 | 1 | 7 | 4 | J | Z | S | Z | Z |
| 7 | 2 | 3 | 7 | J | J | Z | S | S |
| 8 | 1 | 10 | 1 | J | S | Z | Z | Z |
| 9 | 6 | 4 | 2 | S | J | S | Z | J |
| 10 | 2 | 0 | 10 | S | J | S | S | J |
