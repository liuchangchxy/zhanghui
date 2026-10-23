# 本轮改了什么（最小结构修改）

原则：删除、合并、减少一次翻译。没有新增 Agent、没有新增中间层、没有第二套 Router。

> **这份文件记的是「设计意图」，不是「实际效果」。** 三章的实测结果显示其中两条没有真正
> 生效：① Router 的 `chapter_guidance` 依然是 133–180 字（规格是 40–120）；② brief 规格
> 1200–1800 字，三章实际 2874 / 3476 / 5188 字。原因与后果见 `result.md` 第 3 节。

## 1. Writing Skill Router：从「编导」退回「选 + 说一句」

| 项 | 改前 | 改后 |
|---|---|---|
| `chapter_guidance` 职责 | 「这一章的具体动作指令」，60–200 字，1–3 句 | 「本章为什么值得注意这项方法」，40–120 字，一句 |
| 上限 | 600 字 | 240 字（超出只截断并 warn） |
| Writer 收到的 Skill 内容 | 只有 Router 改写后的动作脚本 | **Skill 原文原则 + 极短正反例 + Router 的一句相关性** |
| 明确禁止 | 只禁止 meta 词（skill/理论/hook_type） | 增加禁止：编动作、编对白、编道具顺序、编推理链、写 scene plan |

代码：`writing_skill_registry.py`

- 新增 `attach_skill_bodies()`：按 id 把 `SKILL.md` 的 `## 方法` / `## 正例` / `## 反例`
  原样附到选择上（`principle` ≤1200 字，example/anti ≤320 字）。
- `render_writer_skills()` 改为渲染「名称 —— 本章值得注意：<一句>」+ 原文原则 + 正反例。
  无 `principle` 时退回旧的 guidance-only 渲染，旧调用方不破。
- `selection_fingerprint()` 把 principle/example 纳入指纹（它们确实进 Writer prompt，
  不纳入就等于指纹不覆盖实际输入）。
- `webnovel.py::_load_writing_skill_selection()` 统一做 enrich，`package` 与
  `attach-creative-brief` 两条路径行为一致。

## 2. Context Agent：四问/三问退回内部工具

- 场景四问、追读三问改为**内部判断工具**：想清楚，但任务书里只写结论
  （必须发生什么、阻力是什么、结束前什么变了、读者拿到什么回报），
  **不许**逐题作答、不许写成「第一步/第二步」。
- 新增硬约束：**写法给方向，不给演出**。可以给基调、节奏、视角、分寸；
  不许编具体动作、对白、道具操作顺序或镜头表。
- 输出从「五段任务书」改为五节创作材料，明确 1200–1800 字上限，
  并规定「同一件事只写一次」。
- 新增两节：「人物与硬事实」里的**绝对不能写错的事实**（只列真的会写错的）；
  「这章的感觉与边界」替代原来最容易膨胀成规则清单的「怎么写更顺」。
- 系统术语黑名单扩充：`CBN` / `CPNs` / `CEN` / `Scene` / `Reader Pull` /
  `Progress Obligation` 不得出现。

## 3. Writer Package：去掉规划术语、重复问句块、原始转储

新增 `--lean-input`（`package` 与 `attach-creative-brief` 都支持）。**只做删除，不加素材。**

| 删掉 | 原来占位 |
|---|---|
| `【场景设计四问】` 整块 | 同一份 Scene 计划第 3 次表达 |
| `【追读设计三问】` 整块 | 同一份追读链第 2 次表达 |
| `CBN` / `CPNs` / `CEN` 标签 | 改为自然行「许知远：只得到…」，不带规划术语 |
| `节拍位置`、`必须覆盖节点` | 删除（节点已由自然行覆盖） |
| `Progress Obligation` 长句 | 改为一句自然要求 |
| 原始 `{"event_type": ...}` JSON | 解包 payload，写成材料句；已在前情出现的 open loop 不重复 |
| `story_craft.path: value` 转储 | 删除（系统内部簿记，无运行时消费者） |
| 章节标题里的英文术语 | `## 1. 本章要完成的事` 等中文标题 |

`render_progress_obligation()`、`render_lean_chapter_structure()`、`_natural_node()`、
`_lean_event_text()` 是这次新增的全部代码。

## 4. 没动的治理层（重要）

以下**一行未改**：

- `ContextManager` / Governed Context 构建
- Canon、ChapterCommit、Story System 合同
- Reviewer、prose pipeline、anti-slop
- Data Agent、projection、memory / summary / index / vector
- Draft 登记、publication gate、write-gate
- `writing-skills/` 下 9 个 Skill 文件（本轮零改动；PR #62 的三个 Skill 原样保留）

## 5. 测试

- `tests/unit/test_writing_skill_router.py` 新增 2 项：Skill 原文到达 Writer、
  相关性说明被截断为一句。
- `tests/unit/test_writer_information_chain.py` 新增 2 项：lean 包去掉规划术语与重复问句、
  lean 包解包事件 payload 后事实不丢（防「为了干净把世界规则删掉」）。
- 全量 `pytest tests/` → 481 passed, 1 failed；失败项
  `test_canonical_cli_invocations_are_identical_across_skills` 在基线上
  `git stash -u` 后同样失败，属 pre-existing。
