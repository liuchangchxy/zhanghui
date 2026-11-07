# 实验表格（自动生成）

## 生成状态

| 章 | 状态 | A 正文字数 | B 正文字数 | 比例 | stop_reason | 尝试 |
|---|---|---:|---:|---:|---|---:|
| ch01 | ACCEPTED | 3143 | 2938 | 0.9348 | end_turn | 1 |
| ch02 | ACCEPTED | 1742 | 1656 | 0.9506 | end_turn | 1 |
| ch06 | ACCEPTED | 2920 | 2835 | 0.9709 | end_turn | 1 |
| ch07 | ACCEPTED | 2374 | 2196 | 0.925 | end_turn | 1 |
| ch09 | ACCEPTED | 3475 | 3272 | 0.9416 | end_turn | 1 |
| ch10 | ACCEPTED | 3746 | 3672 | 0.9802 | end_turn | 1 |

## 盲评合计（A=原稿，B=编辑后）

| 维度 | A | B | SPLIT | TIE |
|---|---:|---:|---:|---:|
| OVERALL_PREFERENCE | 0 | 12 | 0 | 0 |
| READING_APPEAL | 0 | 12 | 0 | 0 |
| LOW_AUTHOR_EXPLANATION | 0 | 12 | 0 | 0 |
| SENTENCE_NATURALNESS | 0 | 12 | 0 | 0 |
| SCENE_IMMERSION | 0 | 12 | 0 | 0 |
| SUBTEXT | 0 | 12 | 0 | 0 |

## 章级 OVERALL

| 章 | J1 | J2 | 严格偏 B | 偏向 B |
|---|---|---|---|---|
| ch01 | B | B | True | True |
| ch02 | B | B | True | True |
| ch06 | B | B | True | True |
| ch07 | B | B | True | True |
| ch09 | B | B | True | True |
| ch10 | B | B | True | True |

## 确定性保全检查

| 章 | 数字缺失 | 编号缺失 | 日期缺失 | 术语缺失 | 引语缺失 | 末段 8 字保留 | 末两段 8 字保留 |
|---|---|---|---|---|---|---:|---:|
| ch01 | {} | {} | {} | [] | 0 | 1.0 | 1.0 |
| ch02 | {} | {} | {} | [] | 0 | 0.0 | 0.9 |
| ch06 | {} | {} | {} | [] | 0 | 0.75 | 0.4286 |
| ch07 | {} | {} | {} | [] | 0 | 0.8272 | 0.8833 |
| ch09 | {'19': 1, '7': 1} | {} | {} | [] | 1 | 0.514 | 0.6232 |
| ch10 | {} | {} | {} | [] | 0 | 1.0 | 1.0 |

