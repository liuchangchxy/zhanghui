# 本轮改了什么

只改一件事：**选中的 Skill 以什么形式进入 Writer。**

没有新增 Agent、数据库、合同系统、缓存或 Skill schema。没有改 Router 选择逻辑，
没有改 Router 长度上限，没有改 Creative Brief 上限，没有改 `## 本章必须写对`，
没有改 lean renderer，没有改任何治理层。

## 1. `attach_skill_bodies()`：从「附文档」改成「附一句话」

改前（第二轮）：每个 Skill 附 `## 方法` 的整行条目（共享 1200 字预算）+ 一个例子。
实测每章 Skill 正文 1110–1153 字。

改后：只附 Skill 自己的 `purpose`——它在 `SKILL.md` 的 frontmatter 里本来就是一句话，
不需要第二次 LLM 调用，也不需要新增字段：

```yaml
purpose: 让读者感到"这个人此刻就是这样"，而不是"作者在写一段情绪戏"；……
```

`_first_sentence()` 是确定性提取：整句优先，超长退到整分句（`。` → `；` → `，` → `、`），
最后才硬截断。`## 方法` 条目、正反例、`applies_when` / `avoid_when` **一律不发送**。

## 2. 预算是「整段」，不是「一行」

`TOTAL_SKILL_CONTENT_BUDGET` 从 1200（只算正文）降到 **700**，并且现在覆盖 Writer
实际读到的全部内容：标题、说明行、`N. 【名称】`、原则、`本章相关：`。

`SKILL_SECTION_FRAMING_CHARS = 80`、`SKILL_ENTRY_OVERHEAD_CHARS = 14` 是这两个固定开销，
先扣掉再均分。选 5 个 Skill 时每条分到的更少，总段不会因此变长。

## 3. 预算不够时压谁

按用户给的优先级：**先删例子（本轮已无例子）→ 再压相关性说明 → 不删核心原则**。

- 原则下限 `MIN_PRINCIPLE_CHARS = 40`，上限 `MAX_PRINCIPLE_CHARS = 160`；
- 相关性说明按标点整句截断（`_clip_to_clause()`），不留半句；
- 顺序写进 docstring：相关性是对本章材料的复述，原则在 prompt 里别处没有。

## 4. 渲染

```text
## 本章可用技巧
（这些是写作原则，不是执行步骤；……与 Canon、作者意图、本章禁区冲突时，一律以后者为准。）
1. 【情绪与内心】让读者感到"这个人此刻就是这样"，而不是"作者在写一段情绪戏"；……
   本章相关：这一章他整天一个人，情绪没有对话可以承载……
```

每个 Skill 两行，无小标题、无正反例、无适用条件。

## 5. 契约同步

- `agents/writing-skill-router.md`：Writer 收到的是「名称 + 一句核心原则」，不是「原则 + 一个例子」。
- `skills/webnovel-write/SKILL.md`：同上，并明确 `## 方法` 条目、正反例、适用条件都不进 prompt。

## 6. 没动的部分

`ContextManager`、Canon、Story System、ChapterCommit、Reviewer、Data Agent、projection、
memory / summary / index / vector、publication gate、prose pipeline、anti-slop、9 个
Skill 的文学内容（一个字未改）、Router 选择逻辑与 120 字上限、Creative Brief 1800 上限、
`## 本章必须写对` 的字段与措辞。

## 7. 测试

`tests/unit/test_writing_skill_router.py`：

- 新增 `test_writer_receives_one_principle_sentence_not_the_skill_document`：
  断言 `【名称】` + `purpose` 首句 + `本章相关：` 都在，`## 方法` 条目、`正例`、`反例`、
  适用条件都不在；
- 改写 `test_skill_principles_share_one_budget_and_carry_no_examples`：5 个 Skill 的原则
  总长 ≤ 700，且渲染后整段（含相关性）仍在预算量级内；
- 原有 120 字硬拒绝测试不变。

结果：相关 43 项全过；全量 `484 passed, 1 failed`，失败项
`test_canonical_cli_invocations_are_identical_across_skills` 是 pre-existing。
