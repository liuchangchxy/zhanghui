# Router 自动选择与热插拔验证

## A. 不同章节是否选不同 Skill

四个场景共用同一份 Skill 目录（6 个），各自只给 Router 本章目标、场景、人物与任务书，
由独立的 Router 会话选择 2–5 个技巧。

| 场景 | 选中 Skill（按重要性） | 数量 | 未选的关键项 |
|---|---|---|---|
| 谈判章 | dialogue-subtext, character-agency, information-gap, reader-pull | 4 | scene-sequel, voice-style |
| 调查章 | scene-sequel, reader-pull, character-agency, dialogue-subtext, information-gap | 5 | voice-style |
| 动作章 | scene-sequel, character-agency, reader-pull, information-gap | 4 | dialogue-subtext, voice-style |
| 情绪章 | dialogue-subtext, information-gap, voice-style, character-agency | 4 | scene-sequel, reader-pull |

结论：

- 四组选择互不相同，没有任何一组等于“全部 6 个”。
- `voice-style` 只在情绪章出现；`scene-sequel` 只在调查/动作章出现；`reader-pull` 在 4 个场景里出现 3 次，不是无差别全选。
- 每章数量 4–5，符合 2–5 的预算。
- 全部选择通过 `writing-skills validate`（无未知 id、无空指导、无理论泄漏）。

原始输出：`router_runs/*.json`。

## B. 热插拔：新增 Skill 是否无需改主代码

1. 在项目级目录新增 `.webnovel/writing-skills/test-sensory-detail/SKILL.md`（未修改任何 Python、未注册枚举）。
2. 下一次 `writing-skills list` 立即报告 `count: 7`，并列出两个扫描根：
   - 插件内置 `writing-skills/`
   - 项目级 `.webnovel/writing-skills/`
3. 同一批场景重新路由：
   - 情绪章选中 `test-sensory-detail`（匹配 applies_when：外部动作少、情绪靠物件承载）。
   - 动作章不选它（匹配 avoid_when：动作密集、节奏短促）。
4. 删除测试 Skill 后再次 list，恢复 6 个。

结论：热插拔成立。发现是目录扫描，选择是 AI 判断，两者都不依赖中央注册表。

原始输出：`router_runs/hotplug_emotion.json`、`router_runs/hotplug_action.json`、`router_runs/hotplug_list.json`。

## 选择机制说明

Router 的输入由 `writing-skills input` 组装：本章目标/冲突/代价/变化、Scene 字段、人物状态、
追读素材、正向文风锚、Creative Brief，以及 Skill 目录的 id/name/purpose/applies_when/avoid_when/
priority/方法摘要。Router 输出 `{selected_skills:[{id, reason, chapter_guidance}]}`。

管线只信任通过校验的输出：

- 未知 id、缺少 `chapter_guidance`、指导里出现 theory/meta 词（skill、Swain、scene_goal、hook_type…）→ 拒绝；
- 超过 5 个 → 保留 Router 排序的前 5 个并记录 warning；
- 少于 2 个 → 允许，但记录 warning（有些章节确实只需要更少）。

Writer 最终只看到 `chapter_guidance`，看不到 id、reason、优先级或理论名。
