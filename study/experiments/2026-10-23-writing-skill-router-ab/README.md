# Writing Skill Router 单变量 A/B（第3章《只负责看站的人》）

## 问题

已有的写作理论大多停留在文档、字段和参数里，没有稳定进入 Writer。Scene 与 Reader Pull 两次
单变量实验已经证明：同一个理论一旦被翻译成 Writer 能执行的自然语言，正文会改善。

本轮验证的不是再迁移一个理论，而是**统一机制**：

```text
writing-skills/<id>/SKILL.md
        ↓ 目录扫描（无注册表）
AI Router 判断本章真正需要哪些技巧
        ↓ 只选 2–5 个
翻译成本章具体写法
        ↓
Writer（只看到“本章创作方法”编号列表）
```

## 固定不变

| 项 | 值 |
|---|---|
| 书 / Canon | 《海港旧信》，第1–2章已 accepted |
| 章节任务 | 第3章，10月10日上午，约两小时 |
| Writer 模型 | 两个独立的同模型起草会话，各自只读自己的 prompt |
| 模型参数 | 相同（不调 temperature / 采样参数） |
| 字数目标 | 2000–2500 汉字 |
| 章纲 / 人物状态 / 世界状态 | 同一 `runtime governed-context` |
| Scene 设计 | 两稿都启用 Scene 四问 |
| Reader Pull | 两稿都启用追读三问 |
| 信息释放边界 | 相同（不提前揭示寄信人，不新增设定） |
| Creative Brief | 完全相同的 `creative_brief_0003.txt` |
| 输出要求 | 正文 only；两稿都不输出 `<chapter_changes>` |

## 唯一变量

| 稿 | Writer Prompt |
|---|---|
| A | `prompt_A.txt`：Scene + Reader Pull，无 Skill Router |
| B | `prompt_B.txt`：同一输入 + Router 选择的 4 个 Skill 的本章写法 |

`diff prompt_A.txt prompt_B.txt` 只有“本章创作方法”块与封包指纹不同（+1,573 bytes，约 +7.4%）。
B 没有新增世界观、剧情素材、答案、字数或人物状态。

## 本章 Router 选择（B）

| 顺序 | Skill | 选择理由（审计用，不进 Writer） |
|---|---|---|
| 1 | character-agency | 问话场容易退化成“问—答—记录”的接收器 |
| 2 | dialogue-subtext | 老周的拒绝全靠流程和沉默，直白问答会抹掉核心冲突 |
| 3 | information-gap | 章末删记录需要一个可追的具体问题与可回收物证 |
| 4 | voice-style | 冷硬克制需要压掉解释性内心独白与情绪结论 |

未选 `scene-sequel` / `reader-pull`：Writer 已经收到四问/三问，Router 不重复投喂。

## 判定规则（事先写定）

- B 明显更好 → `WRITING_SKILL_ROUTER_SUPPORTED`
- 架构正常但文学提升不明确 → `ARCHITECTURE_SUPPORTED_QUALITY_UNPROVEN`
- B 更机械、更差 → `WRITING_SKILL_ROUTER_OVERCONSTRAINED`

盲评维度：阅读吸引力、人物主动性、对话自然度、潜台词、场景表现、叙事声音、
总体文学质量、“规则太多”的明显程度、“生硬执行技巧”的明显程度。

## 产物

- `prompt_A.txt` / `prompt_B.txt` / `prompt_diff.txt`
- `draft_A.md` / `draft_B.md`、`draft_X.md` / `draft_Y.md`、`judge_packet_*.md`、`blind_key.json`
- `eval/`：两名独立评委的原始评分
- `result.md`：评分、结论与限制
- `round1_invalidated/`：首轮（字数不足、顺序效应）作废记录
- `10-skill-migration.md`：既有理论 → Skill 的迁移映射
- `20-router-selection-matrix.md`：四类章节选择分化 + 热插拔验证
