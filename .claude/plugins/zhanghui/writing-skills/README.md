# Writing Skills

本地写作方法库。**目录就是注册表**：新增一种技巧只需创建
`writing-skills/<id>/SKILL.md`，不需要改 Python、命令或任何中央枚举。

## 目录

```text
writing-skills/
  scene-sequel/SKILL.md
  reader-pull/SKILL.md
  information-gap/SKILL.md
  character-agency/SKILL.md
  dialogue-subtext/SKILL.md
  voice-style/SKILL.md
  emotion-interiority/SKILL.md
  pov-distance/SKILL.md
  sensory-description/SKILL.md
```

项目级目录 `.webnovel/writing-skills/` 会被一起扫描；同 id 覆盖内置版本。

## 文件格式

```markdown
---
id: dialogue-subtext          # 必填，kebab-case ASCII，全局唯一
name: 对话潜台词               # 必填
purpose: 解决什么创作问题      # 必填
applies_when:                 # 必填；字符串或列表
  - 谈判、试探、对峙
  - 人物之间有隐瞒
avoid_when:                   # 必填；字符串或列表
  - 必须一次交代清楚规则
priority: 60                  # 可选，默认 50；只用于 Router 判断冲突层级
---

## 方法

给 Router 看的理论/方法本身。Writer 不会直接看到这段。

## 正例

可选。一段很短的正面示例。

## 反例

可选。一段很短的反面示例。
```

约束：

- Writer 只收到 Router 翻译后的“本章创作方法”，不会收到 id、name、priority、理论名或本文正文。
- Skill 永远不能覆盖 Canon、作者意图、本章禁区；冲突由 Router 在选择时消解。
- 每章默认只选 2–5 个。`priority` 不是“全部加载”的依据。

## 命令

```bash
python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "$PROJECT_ROOT" \
  writing-skills list --format json

python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "$PROJECT_ROOT" \
  writing-skills input --chapter 3 --brief-file .webnovel/tmp/creative_brief_0003.txt --format json

python3 -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "$PROJECT_ROOT" \
  writing-skills validate --selection-file .webnovel/tmp/writing_skills_0003.json --format json
```

写作流程中由 `zhanghui:writing-skill-router` 子代理执行选择与翻译；封口时用
`runtime attach-creative-brief --skills-file ...` 把选择绑定进 WriterPackage。
