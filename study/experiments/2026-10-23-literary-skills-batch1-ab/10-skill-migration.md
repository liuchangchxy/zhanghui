# 三个新 Skill 的职责边界与迁移来源

## 新增

| Skill | 独立解决的创作问题 | 与既有 Skill 的分界 | 主要来源 |
|---|---|---|---|
| `emotion-interiority` | 情绪由作者命名、写完动作再解释一遍、身体反应套模板、人物受刺激后没有自己的判断 | `voice-style` 只管文字声音，不再管情绪；`dialogue-subtext` 管台词里的隐瞒，不管内心 | `写作技法.csv` WT-002/006/037/060/068/075；`anti-ai-guide.md` 第 5 条与“展示后解释”；`style-adapter.md` 允许直接情绪 |
| `pov-distance` | POV 漂移、进入别人内心、叙述者宣布人物不可能知道的事、距离忽远忽近 | `information-gap` 管“什么时候给读者信息”，`pov-distance` 管“谁有资格感知这条信息” | `写作技法.csv` WT-069/070/042；`style-adapter.md` 叙事距离 |
| `sensory-description` | 环境当背景板、五感打卡、漂亮但无作用的描写 | `scene-sequel` 管场面结构，不管细节选择 | `写作技法.csv` WT-003/016/039/046/049/038 |

## voice-style 收窄

| 移出 | 去处 |
|---|---|
| “只写身体和行为，不写情绪结论” | `emotion-interiority`（且新 Skill 明确允许内心独白） |
| 叙事距离相关（原先由 Step 2B 的 style-adapter 承担） | `pov-distance` |
| “具体物件/感官细节” | `sensory-description` |
| 对话声线差异化 | 保持 `dialogue-subtext`，未来 `character-voice` 接人物独特说话方式 |

保留：措辞具体、句段呼吸、删套话、去排比、比喻带人物印记、不拔高不总结、允许不完美。

## dialogue-subtext 的轻量整理

只改一条：删掉“遮住名字也能分辨谁在说话”的声线职责，改为“各人回避与攻击方式不同”，
并注明人物独特说话方式另有专项。其余方法与正反例未动。

## 刻意不做

- 不迁移 104 条 CSV 技巧；只取与三个缺陷直接相关的行。
- 不新增题材专用 Skill；`writing-edicts.md` 的硬性数字（每 500 字、40%–55% 等）不进 Skill。
- 不改 Router、注册表、发现机制、校验规则。
- 不把 `voice-style` 扩成万能 Skill，也不把三个新 Skill 合并成一个“文学表达”。

## 留待未来的候选（B 类，不删不强并）

character-voice、unreliable-narrator、interrogation、comedic-timing、romance-tension、
horror-atmosphere、action-clarity、inner-conflict、clue-reveal、
worldbuilding-through-action，以及题材专用技巧（WT-079/086/095/104 等）。
