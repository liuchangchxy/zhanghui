# ch03 正常生产流程附带记录（非 PRIMARY QUESTION）

## 审查与修复

- 初审：8 issues，0 blocking。2 high（PVP 结算 ID 与 Canon 冲突；灰獾血条骤降缺伤害来源）、2 medium（第二次斗车启动机制、伏笔登记）、4 low（时间元数据、章末 Decision、hook_type、机关术伏笔回收点）。
- Step 4 定向修复（4 个 `LOCAL_FACT`，全部落在计划内）：
  1. 对决结算 `林川 vs 灰獾` → `归乡人 vs 灰獾`（Canon 账号 ID 为“归乡人”）；
  2. 灰獾被绊倒处补“钢缆在他脚踝上收紧”，给残血一个动作因；
  3. 第二次斗车启动改为“用撬棍撬开卡住斗车轮的碎石，斗车顺着窄轨又滑出一段”；
  4. `chapter_changes.time_progression` 删去正文无依据的“至十一点左右，约三小时半”，改为“晚上七点四十起”。
- `prose validate --revision-plan`：`PENDING_REREVIEW` / `FACT_FIX_DECLARED`；`revise verify`：`boundary_ok=true`、`out_of_scope_changes=[]`、4/4 resolved；随后重新 `ingest-draft` 得 `draft-003-7cda2f93`。

## 第二轮复审（自动预算第 2 轮，预算耗尽）

- 7 issues，0 blocking。上轮 8 条：resolved 3（ID、斗车启动、时间元数据）、persistent 4、uncertain 1、new 2。
- 仍存 1 high（non-blocking）：“灰獾首次显示血条即只剩一点”仍无系统伤害行/伤害数值，随后一次 `伤害 1` 击杀。钢缆动作因已补，但 Reviewer 要求伤害量或系统提示才闭环。自动预算已用满，按流程停止自动打磨，不再开第三轮。
- new low：撬棍在本章首次出现且未交代来源；青铜战犬被撞飞后到消失之间缺状态说明。
- 其余为伏笔登记 / hook_type / 章末 Decision / 机关术原伏笔回收点等治理或 craft advisory。

## anti-slop

- `text_humanizer.py`：无 blocking；`rule_of_three` 命中 15（多为枚举与数值，属正常）。
- `check-ai-patterns.js`：micro-action-tic 14 处、quote-emphasis-tic 9 处，均为 advisory；两条 `em-dash` detector-level blocking 命中 `消耗：—` / `冷却：—`，是系统卡面固定文本，属误报，未改稿。

## 提交与发布结果

- `runtime commit`：`ok=true`、`action=ALLOW_WITH_ADVISORY`、`chapter_outcome=accepted`、durable commit 已落盘。
- 投影：events/amend_proposals/state/index/summary/memory = done；vector = skipped（本地 embedding `127.0.0.1:1234` 未启动，`degraded:embedding_unavailable`）。
- `runtime publish-draft`：`ok=true`，发布 `正文/第0003章-首战告捷.md`。
- postcommit gate：`ok=true`、0 errors、0 warnings。
- 书项目 backup：commit `Chapter 3`，tag `ch0003`。
- 篇幅：正文汉字 1875，低于默认 2000 的 advisory warning，未声明硬合同，不阻断提交。

以上均不影响本章 accepted / published；按本轮规则不在文学实验主报告中展开。
