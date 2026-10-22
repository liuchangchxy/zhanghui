# 既有理论 → Writing Skill 迁移映射（第一批）

本批只迁移已经被证明有效、或已有明确正向证据的方法。没有一次迁移全部 51 项。

| Skill | 来源（仓库内） | 迁移方式 | 运行时状态 |
|---|---|---|---|
| `scene-sequel` | `references/shared/scene-sequel.md`；PR #59 的四问执行形态 | 保留四问作为 Writer 已有输入；Skill 存 Goal→Conflict→Setback→Decision 与四个执行约束 | Router 可翻译成本章具体写法；不重复四问 |
| `reader-pull` | `references/reading-power-taxonomy.md` 追读三问；PR #60 | 期待→当章回报→新期待；明确钩子/爽点/微兑现只是诊断词汇 | Router 可翻译；不重复三问 |
| `information-gap` | `references/shared/cool-points-guide.md` 信息差设计；`foreshadow-chain.md`；`写作技法.csv` WT-015/035/074 | 问题具体化、延迟须有因、每次只放一部分、人物知道量稳定、伏笔可回收 | 新增；此前没有专门进入 Writer 的块 |
| `character-agency` | `references/shared/scene-sequel.md` 第 3 问；Context Agent 的剧情推进义务；`人设与关系.csv` CH-038/CH-090 | 每场问“想要什么/主动做了什么/删掉选择剧情是否还成立”，选择必须有代价 | 新增；此前只有间接影响 |
| `dialogue-subtext` | `references/csv/写作技法.csv` WT-001/005/009/051/074；`skills/webnovel-write/references/anti-ai-guide.md` 对话专项；`naming-and-voice-gaps.md` | 不把目的说破；每段对话承担功能；声线可辨识；回应而非轮流发言；不承载设定 | 新增；live 的 `dialogue-writing.md` 只是指向 CSV 的存根 |
| `voice-style` | `references/aesthetic/writing-edicts.md`；`anti-ai-quick-ref.md`；`prose_voice_target.py` 的正向文风字段 | 只写身体不写情绪结论；句长参差；比喻带人物印记；删空心句；具体性 | 新增；正向文风锚此前因 `target_voice` key 不匹配从未进入 Writer |

## 刻意不做

- 不迁移 CSV 的全部 51 项，也不建立“题材 → 技巧”硬编码映射。
- 不把 Skill 正文直接塞进 Writer prompt；Writer 只收到 Router 翻译后的本章指令。
- 不复制 `6.4.0/` 快照中的平行实现。
- 不改 Canon / CHANGES / ChapterCommit / 15-beat / Fichtean / 伏笔治理 / Scene / Reader Pull 的既有逻辑。

## 已知边界

- `prose_voice_target.VoiceTarget` 的 `to_dict()` 不产出 `target_voice`，所以旧 Writer prompt 的
  `- 文风靶向` 行一直是死代码。本轮没有改这条渲染路径（避免把与本实验无关的变量引入 A/B）；
  Router 直接读取真实字段（`core_rules` / `sentence_rhythm` / `dialogue_policy` / `positive_guidance`）。
- 外部宿主适配器（`external_host_adapter.py`）仍以默认参数渲染 prompt，未接入 Skill 选择；
  它是确定性契约测试桩，不是本轮的真实写作主链。
