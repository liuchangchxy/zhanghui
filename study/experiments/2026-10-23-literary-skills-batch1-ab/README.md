# 第一批 Literary Writing Skills 单变量 A/B（第3章《只负责看站的人》）

## 问题

Writing Skill Router 已经验证：技巧能被发现、选择、翻译、注入。但当时库里的 6 个 Skill
偏结构（Scene / 追读 / 信息差 / 主动性 / 潜台词 / 反 AI 腔），**正文的文学表达层**——
情绪怎么落、视角是否越界、环境细节有没有作用——没有独立技巧。

本轮只问一件事：

> 把三个文学表达 Skill 加进同一个可插拔库，正文会真的变好吗？还是会把 Writer 绑死？

## 固定不变

| 项 | 值 |
|---|---|
| 书 / Canon | 《海港旧信》，第1–2章已 accepted |
| 章节任务 | 第3章，10月10日上午，约两小时 |
| 代码基线 | 臂 A `origin/main` (a41ac35)；臂 B 本分支 bdd4500（只在 `writing-skills/` 增加 3 个 Skill） |
| 受治理上下文 | 两臂 `runtime governed-context --chapter 3` 逐字节相同 |
| Creative Brief | 两臂同一文件，md5 `73a3388ea87c590b5aebb6d9aaa24d47` |
| Scene 四问 / 追读三问 | 两臂都启用 |
| 字数目标 | 2000–2500 汉字 |
| 起草方式 | 两臂各一个独立起草会话，只读自己的 writer_prompt，互相不可见 |
| 输出要求 | 正文 only，不输出 `<chapter_changes>` |

## 唯一变量

| 臂 | Skill 库 | Writer Prompt |
|---|---|---|
| A | 6 个（scene-sequel / reader-pull / information-gap / character-agency / dialogue-subtext / voice-style） | 同一输入 + Router 对 6 个库的选择 |
| B | 9 个（A 的 6 个 + emotion-interiority / pov-distance / sensory-description） | 同一输入 + Router 对 9 个库的选择 |

两臂都跑 Router、都收到“本章创作方法”。差别只在**可选技巧的范围**，不在机制。

## 判定规则（事先写定）

- B 明显更好 → `LITERARY_SKILLS_SUPPORTED`
- 机制正常但文学提升不明确 → `LITERARY_SKILLS_QUALITY_UNPROVEN`
- B 更机械、刻意或被规则绑住 → `LITERARY_SKILLS_OVERCONSTRAINED`

盲评维度：对话自然度、潜台词、人物声音、POV 稳定性、作者直接解释、描写是否具体且有作用、
情绪是否由人物体验呈现、句段自然度、AI 味、阅读吸引力、总体文学质量、
“规则太多”的明显程度、“生硬执行技巧”的明显程度。

## 产物

- `prompt_A.txt` / `prompt_B.txt` / `prompt_diff.txt`
- `router_runs/`：两臂 Router 的原始输入与选择
- `drafts/`：两臂正文，盲评用的 X/Y 副本
- `eval/`：评委原始评分
- `result.md`：评分、结论与限制
