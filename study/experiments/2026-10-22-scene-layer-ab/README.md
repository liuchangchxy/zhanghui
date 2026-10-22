# Scene 层单变量 A/B（第3章《只负责看站的人》）

## 问题

把已有的 Scene-Sequel 理论真正转成“这一场戏怎么演”的四个问题，是否能让同一章更好读？

## 固定不变

| 项 | 值 |
|---|---|
| 书 / Canon | 《海港旧信》，第1–2章已 accepted |
| 章节任务 | 第3章，10月10日周六上午，约两小时 |
| Writer 模型 | 同一会话模型（Claude Code 当前模型），两次生成 |
| 模型参数 | 相同（未调 temperature / 采样参数） |
| 字数目标 | 2000–2500 汉字；A=2041，B=2004 |
| 章纲 / 人物状态 / 世界状态 | 同一 `runtime governed-context` |
| 信息释放边界 | 相同（不提前揭示寄信人，不新增设定） |
| Creative Brief | 完全相同的 `creative_brief.md` |
| 封包 | 同一 `package_fingerprint=3063af5b46ab8f5cd83d9ba97ec8775e205af97b1e1e19f3af250225b6cff5c5` |

## 唯一变量

Writer Prompt 中“场景”这一块的表达方式：

- **A**：`scene_design=False` —— 按章纲原有字段名呈现（场景目标 / 现场阻力 / 场景挫折 / 场景结果 / 后续反应 / 后续两难 / 后续决定）。
- **B**：`scene_design=True` —— 同一批字段改写成四个创作问题：
  1. 这一场主角现在具体想得到什么？
  2. 什么力量在现场真正阻止他？
  3. 主角因此被迫采取什么行动或选择？
  4. 场景结束后，人物/关系/局势/认知中什么已经发生实质变化？

两份 Prompt 的 diff 只有这一个块（见 `prompt_A.txt` / `prompt_B.txt`）。B 没有增加世界观、剧情素材、答案、字数或人物状态。

## 盲评

- `draft_X.md` / `draft_Y.md` 去掉来源标识；映射记录在 `blind_key.json`（评委不可见）。
- 两名独立评委，独立上下文，顺序互换（XY / YX）以抵消位置偏差。
- 评委只拿到：两稿 + 前两章摘要 + 第3章任务 + 四项评分说明。
- Reviewer 事实分不作为文学提升证据，本次不纳入判定。

## 判定规则（事先写定）

- B 明显优于 A → `SCENE_LAYER_SUPPORTED`
- 基本持平 → `SCENE_LAYER_NOT_PRIMARY`
- B 更差 → `SCENE_LAYER_OVERCONSTRAINED`

## 产物

- `prompt_A.txt` / `prompt_B.txt`：两次实际 Prompt
- `draft_A.md` / `draft_B.md`：真实草稿
- `draft_X.md` / `draft_Y.md`、`judge_packet_*.md`：盲评输入
- `blind_key.json`：揭盲映射
- `result.md`：评分、结论与限制
