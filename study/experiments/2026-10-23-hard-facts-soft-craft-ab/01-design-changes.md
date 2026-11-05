# 本轮改了什么（减法修正）

本轮没有新增 Agent、数据库、合同系统或预算框架。只修第一轮的三个真实缺陷。

## 1. 关键事实：受保护落点

`WriterPackage.to_writer_prompt(lean_input=True)` 现在在【本章目标】之后插入
`## 本章必须写对`：

- `chapter_change`（本章变化）
- `hook`（计划钩子）
- CBN / CPNs / CEN 节点（只把 `主体 | 动作 | 结果` 改成自然标点，保留全部三段）
- `forbidden_zones`（本章不能发生）

全部**逐字取自章节合同**（`chapter_directive` / `plot_structure`），不经 Context Agent、
Router 或任何 LLM 重写。块首明确写着：

> 数字、高低、先后、增减、因果、缺口类型一律照此，不得换成另一种说法；
> 与后面的创作方向冲突时，以本节为准。

对应代码：`chapter_runtime.py::render_hard_facts()`、`_verbatim_fact()`。
lean 结构渲染不再重复节点（`include_nodes=False`），事实只出现一次，但出现在受保护位置。

## 2. Brief 与 Router 说明：真的限长

| 项 | 第一轮 | 本轮 |
|---|---|---|
| Brief | 1200–1800 只是提示词，实测 2874–5188 | `MAX_CREATIVE_BRIEF_CHARS = 1800`（不计空白）；超限 `attach-creative-brief` **直接拒绝**，报出实际字数 |
| Router `chapter_guidance` | 上限 240，超限只截断 + warn，实测 133–180 | `MAX_GUIDANCE_CHARS = 120`；超限 `validate_selection` **返回 error**，必须重写 |

报错信息明确要求压缩后重新生成，不允许截断事实绕过。

## 3. Skill：共享预算 + 一个例子

`attach_skill_bodies()` 不再给每个 Skill 完整的 `## 方法`（旧上限 1200 字/条）与正反例
（320 字/条）：

- 所有 Skill 共享 `TOTAL_SKILL_CONTENT_BUDGET = 1200` 字；
- 选得越多，每条分到的越少（4 条 ≈ 300 字/条，5 条 ≈ 240 字/条）；
- 每条只给核心原则（整行截断，不切半句）+ **一个**极短例子（有正例用正例，否则用反例）；
- Writer 看到的是「名称 —— 一句本章相关性 + 原则 + 一个例子」，不是 Skill 文档。

## 4. Agent 契约同步

- `agents/context-agent.md`：Brief 1800 是硬上限；不再另列“绝对不能写错的事实”清单，
  硬事实由受保护区承载；重复数字只会制造第二套真源。
- `agents/writing-skill-router.md`：一句话 40–120 字，120 是硬拒绝；不再宣称 Writer
  已收到四问/三问。
- `webnovel-write` / `webnovel-fast-write` SKILL.md：同步硬上限与 Skill 预算。

## 5. 没动的部分

`ContextManager`、Canon、Story System、ChapterCommit、Reviewer、Data Agent、projection、
memory / summary / index / vector、publication gate、prose pipeline、anti-slop、9 个 Skill
的文学内容：一行未改。

## 6. 测试

`tests/unit/test_writer_information_chain.py` 新增：

- lean prompt 含受保护块，且方向/缺口类型逐字正确、声明“以本节为准”；
- 1800 字 Brief 可封包，1801 字被拒绝。

`tests/unit/test_writing_skill_router.py` 更新/新增：

- 500 字 guidance 被拒绝而不是截断；
- 5 个 Skill 的原则+例子总长不超过共享预算；
- 每个 Skill 只附一个例子。

结果：相关 43 项全过；全量 `pytest tests/` 仅剩已记录在案的
`test_canonical_cli_invocations_are_identical_across_skills`（基线上同样失败）。
