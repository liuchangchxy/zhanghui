# ch02 正常生产流程附带记录（非 PRIMARY QUESTION）

## 审查与修复

- 初审：6 issues，0 blocking。2 medium logic（余额算术、奖励到账时点）、2 low timeline、2 foreshadow advisory。
- Step 4 定向修复（2 个 LOCAL_FACT）：
  1. 交易行增加 3 碎片手续费，使 100 + 9 + 12 − 3 = 118、后续“剩十八”闭合；
  2. 引导奖励改为“抽卡步骤前发放”，奖励行改为“引导·抽卡步骤：根源碎片 × 500（已发放）”；倒计时改为固定关闭时间。
- `revise verify`：`boundary_ok=true`、`out_of_scope_changes=[]`、resolved 3（含被 target 2 覆盖的倒计时）、untouched 1（time_anchor 元数据）。
- 复审（预算第 2 轮）：0 blocking；1 medium（“两单代练”与已取消一单不一致）、1 medium（foreshadowing_actions 为空）、3 low（时间锚点、关闭时间措辞、hook_type）。

## 工具产物问题（已修复，非正文改动）

- 第一次把 Step 4 候选写回工作草稿时，`step4_candidate_0002.md` 已自带 `<chapter_changes>`，又追加了一次旧块，导致工作草稿出现两个提案块，并使 `review_subject_fingerprint` 被污染。
- 已删除重复块、重建单一合法 CHANGES，并确认小说正文与 Step 4 候选逐字一致。
- 因审查对象指纹变化，按人工恢复路径重跑一次 Reviewer（`--allow-over-budget`），绑定新草稿；这不是新的文学修订轮次。

## 未处理（预算耗尽，non-blocking）

- “两单代练也还有救”与第 7 行已取消一单不一致（medium，正文）。
- `chapter_meta.time_anchor` 仍为“2026-05-01 下午”，正文为上午（low，规划元数据）。
- 第 147 行“倒计时还在走”与第 27 行“关闭时间”措辞不一致（low，正文）。
- `foreshadowing_actions` 为空；新伏笔由 Data Agent 的 open_loop 提取进入账本（advisory）。
- `hook_type` 为空（规划元数据，advisory）。

以上均不影响 commit/publish；按本轮规则不在文学实验主报告中展开。

## 提交与发布结果

- `runtime commit`：`ok=true`、`action=ALLOW_WITH_ADVISORY`、`chapter_outcome=accepted`、durable commit 已落盘。
- 投影：events/amend_proposals/state/index/summary/memory = done；vector = skipped（本地 embedding 127.0.0.1:1234 未启动，`degraded:embedding_unavailable`）。
- `runtime publish-draft`：`ok=true`，发布 `正文/第0002章-第一次抽卡.md`。
- postcommit gate：`ok=true`、0 errors、0 warnings。
- 书项目 backup：commit `Chapter 2`，tag `ch0002`。
- 篇幅：正文汉字 1950，低于默认 2000 的 advisory warning，未声明硬合同，不阻断提交。
