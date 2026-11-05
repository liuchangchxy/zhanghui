# Writer Freedom A/B（强治理、弱干预）

## 问题

前三轮实验（scene-layer、reader-pull、skill-router、literary-skills）证明：理论一旦翻译成
Writer 能执行的自然语言，确实能进正文。但第一轮 literary-skills 的第 5 章暴露了反向代价：
**Writer 把指导当成正文结构执行**（判据编号变小标题、推理链被完整摊开）。

审计（见 `01-audit.md`）确认根因不在 Skill 库，而在 Writer 前的**三层过度具体化**：

```text
Context Agent 用四问/三问逐题作答  →  同一份 Scene/Reader-Pull 计划再渲染给 Writer
Writing Skill Router 把文学原则改写成本章动作脚本  →  Writer 逐字执行
Writer Package 夹带规划术语与原始事件/路径转储
```

## 本轮唯一变量

| 臂 | 代码 | 含义 |
|---|---|---|
| A | `82e496d`（PR #62 HEAD） | 当前正式 Writer-facing 流程：旧 Context Agent 五段任务书、Router 二次编导、含规划术语与重复问句块的 Writer Package |
| B | 本分支 HEAD | 强治理、弱干预：Context Agent 只给创作材料（内部判断不外露）、Router 只给一句相关性说明 + Skill 原文原则、Writer Package 去掉规划术语/重复问句/原始转储 |

**Skill 库在两条臂上完全相同**（都是 9 个，含 PR #62 新增的三个）。因此臂间差异只来自
「Writer 前链路怎样把材料交给 Writer」，不来自「有没有这些 Skill」。

## 固定不变

| 项 | 值 |
|---|---|
| 书 / Canon | 《海港旧信》，第 1–2 章已 accepted |
| 章纲 / 设定 / 时间线 | 同一份 `大纲/`、`设置集/`、`.story-system/`（两本副本逐字节相同） |
| 受治理上下文 | 两臂 `runtime governed-context` 逐字节相同（md5 见 `checksums.txt`） |
| 章节任务 | 两臂同一 `CHAPTER_GOAL` |
| Writer 模型 | 同一模型、同一参数、各自独立起草会话 |
| 字数目标 | 2000–2500 汉字 |
| Reviewer | 同一 `zhanghui:reviewer`，同一审查上下文流程 |
| 后处理 | 同一 prose diagnosis |

## 样本（覆盖三类章）

| 章 | 类型 | 期望上场的能力 |
|---|---|---|
| 第 6 章《修设备的人》 | 试探/谈判，信息限制 | dialogue-subtext、character-agency、pov-distance |
| 第 7 章《潮位不会说谎》 | 独处 + 程序/现场感 | emotion-interiority、sensory-description、information-gap |
| 第 10 章《值班表上的空白》 | 对峙 + 掩护式索取 | dialogue-subtext、pov-distance、character-agency |

## 判定（事先写定）

- `WRITER_FREEDOM_SUPPORTED`：B 文学质量稳定、可感知更好，且连续性与剧情执行没有下降。
- `WRITER_FREEDOM_NEUTRAL`：prompt 明显更简洁，但正文没有稳定提升。
- `WRITER_FREEDOM_HURTS_CONTROL`：文学自由度上升，但剧情执行 / 连续性 / Canon 合规下降。
- `CURRENT_DESIGN_BETTER`：A 整体更好。

盲评：每章两名评委，阅读顺序相反，X/Y 随机映射；13 项评分（11 正 + 「规则太多」「生硬执行技巧」两反向项）。

## 产物

`01-audit.md`（窄审计）、`02-design-changes.md`（改了什么）、`03-renderer-bug-disclosure.md`
（第一轮作废说明）、`checksums.txt`（臂间输入一致性）、`agents/`（两臂实际使用的 agent 指令留档）、
`scores/chN/`（brief / router 选择 / sealed prompt / 草稿 / 盲评 / Reviewer 结果）、
`harness/`（驱动脚本归档）、`result.md`（结论）。
