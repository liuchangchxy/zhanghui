# Held-out 测试集预注册

- 实验：章回｜文学编辑器 Held-out 外部验证
- 日期：2026-11-07
- 参考：PR #66（`experiments/jarvis-literary-gain-20261107/`）
- 本文件在**任何生成之前**写入，并纳入 `FREEZE.json` 哈希。

## 固定测试集

本轮只使用以下 6 章，全部使用，**不允许根据结果删章、换章或挑选更合适的样本**：

| 章 | key | 标题 |
|---|---|---|
| 第1章 | ch01 | 第一章 |
| 第2章 | ch02 | 第二章 钥匙 |
| 第6章 | ch06 | 第六章 那一夜 |
| 第7章 | ch07 | 第7章 材质 |
| 第9章 | ch09 | 第9章 切换盒 |
| 第10章 | ch10 | 第10章 三通 |

这 6 章没有参与 PR #66 五条编辑原则的提炼；PR #66 的冻结样本是 ch03 / ch04 / ch05 / ch08。

### 需要记录的边界

PR #66 的 `analysis/ANALYSIS.md` 在范围说明中把 ch01、ch02、ch06 列为**补充阅读材料**，
但五条原则的每一条引文都来自 ch03 / ch04 / ch05 / ch08，没有一条由 ch01、ch02、ch06 提炼。
本轮仍按用户固定的 6 章全部使用；这一点作为外部有效性限制记录在最终报告中，不据此换章。

## 冻结的编辑机制

- 五条原则：逐字复用 PR #66 的 `prompts/editor_zh.md`，不重新解释、不扩展。
- 只新增三个已知护栏（来自 PR #66 的真实失败）：
  1. 保护推进信息（下一步动作/调查方向/硬限制/章末钩子）。
  2. 保护“数字/物件/证据 → 关键结论”的必要推理连接。
  3. 长度低于原文正文 90% 直接判编辑失败（`EDITOR_REJECT_LENGTH`），不补字、不重跑。
- 编辑器模型、temperature、max_tokens、调用方式与 PR #66 相同：
  `group/mac-deepseek4.1-gpt[1m]`，temperature 0.4，max_tokens 16000。

## 生成协议

- 每章只生成一次 B。
- 只在调用失败、空输出或截断时做技术性重试；重试不修改 Prompt，并保留失败记录。
- 不因为单章结果差而重跑。
- 不看 Jarvis 正文，不看 PR #66 的 edited 输出，不看 held-out 章节的任何盲评结果。

## A/B 与盲评

- A = 当前 Zhanghui final。
- B = 冻结编辑器输出。
- 若 B 因长度护栏被拒绝：该章不伪造 B，记录 `REJECTED`，不做 A-vs-A 盲评；该章在成功标准中计为未获益。
- 两位不同模型族评委，每章每位两遍，第二遍强制位置反转；两遍同臂才计胜，否则 `SPLIT`。
- 六维：`OVERALL_PREFERENCE`、`READING_APPEAL`、`LOW_AUTHOR_EXPLANATION`、
  `SENTENCE_NATURALNESS`、`SCENE_IMMERSION`、`SUBTEXT`。
- 盲评提示词不透露编辑目标、开发集结果或哪版是新版本。

## 预先冻结的成功标准

### PASS

同时满足：

1. 至少 **4/6 章**在 `OVERALL_PREFERENCE` 上多数稳定偏 B。
2. `READING_APPEAL` 与 `LOW_AUTHOR_EXPLANATION` 总体明显偏 B。
3. `SENTENCE_NATURALNESS` 与 `SCENE_IMMERSION` 没有系统性偏 A。
4. 没有重要推进信息、关键推理链、专业术语或事实层损失。
5. 没有长度违规后仍被采用的 B。

### PARTIAL

文学收益仍明显存在，但：只有部分章节获益；或仍出现少量可定位的内容损失；或自然度/沉浸感出现明显 trade-off。

### FAIL

任一成立：多数 held-out 章节没有文学收益；B 经常输给 A；内容损失再次出现且无法靠三个现有护栏避免；自然度/沉浸感系统性下降；方法高度依赖特定章节。

## 禁止

不改五条原则；不新增护栏；不根据 held-out 结果改 Prompt；不反复生成直到通过；不换模型；
不重跑完整 E2E；不改 Step 2B / Step 4 / Canon / Data Agent / reconciliation；不增加 Agent；
不建新语义门禁；不把失败章节移出统计。
