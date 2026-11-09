# 第 5 章（内省章）单变量 A/B — 记录

## 为什么加这一组

第 3 章的 B 臂 Router 只选中了 `pov-distance`。`emotion-interiority` 与 `sensory-description`
在该章没有上场，无法据此判断它们是否有效。第 5 章是独处、内省、以物证推进的章节，
三个新 Skill 都可能真正被选中，因此作为第二组样本。

## 固定不变

| 项 | 值 |
|---|---|
| 书 / Canon | 《海港旧信》，第1–4章已 accepted（第5章目标） |
| 代码基线 | 臂 A `origin/main`；臂 B `bdd4500`（只多 3 个 Skill） |
| 受治理上下文 | 两臂 `runtime governed-context --chapter 5` 逐字节相同 |
| Creative Brief | 两臂同一文件（md5 见下），由同一个 context-agent 会话产出后原样复制 |
| Scene 四问 / 追读三问 | 两臂都启用 |
| 字数目标 | 2000–2500 汉字 |
| 起草方式 | 两臂各一个独立起草会话，只读自己的 prompt |

## 唯一变量

Skill 库：A 为 6 个，B 为 9 个。两臂都跑 Router，都收到“本章创作方法”。

## 产物

- `creative_brief_0005.txt`
- `arm_A_selection.json` / `arm_B_selection.json`
- `ch5_prompt_A.txt` / `ch5_prompt_B.txt` / `ch5_prompt_diff.txt`
- `drafts/`、盲评包、`eval/`
