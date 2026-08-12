> 来源：Beat1ngHeart/novel-writing-toolkit `.claude/commands/novel.md`（MIT License）
> 用途：机器扫描用硬清单（vs `writing-edicts.md` 的语义规则）。可被 linter / pre-commit 直接读取。

# AI 高频词禁用表（机器扫描版）

> **用法**：每章正文提交 Step 4 润色前，自动扫描正文与本清单的匹配项。任何命中 → 警告（除非角色台词）。
> **分级**：🔴 致命（必须删）/ 🟠 高风险（建议改）/ 🟡 软提醒（人工判定）

---

## 🔴 致命（必须删，命中即重写）

### 抽象动作/总结词

| 词汇 | 类别 | 替代思路 |
|------|------|---------|
| 稳 | 抽象动作 | 改成具体姿态（如"脚跟压实地面"）|
| 稳稳地 | 抽象动作 | 同上 |
| 接住（抽象义）| 抽象动作 | 改成"扛住/挡下"或具体反应 |
| 作为/服务于 | 抽象动词 | 拆成具体动作链 |
| 见证（抽象义）| 抽象动词 | 改成"亲眼看到"或具体感知 |
| 提醒（抽象义）| 抽象动词 | 改成"让某人注意到 X" |

### 重大意义词（绝对删除）

| 词汇 | 备注 |
|------|------|
| 至关重要 | |
| 意义重大 | |
| 关键时刻 | |
| 转折点 | |
| 重要时刻 | |
| 具有重要意义 | |
| 发挥积极作用 | |
| 强调/突出其重要性/意义 | 任何组合 |

### 强调与结构性总结

| 词汇 | 备注 |
|------|------|
| 标志着 | |
| 塑造 | 抽象义 |
| 标志着其持续 | |
| 持久地 | |
| 做出贡献 | |
| 奠定基础 | |
| 不断变化的格局 | |
| 聚焦点 | |
| 不可磨灭 | |
| 根植于 | |
| 反映出更广泛的 | |

### 过渡与结构套话

| 词汇 | 备注 |
|------|------|
| 与此同时 | |
| 值得注意的是 | |
| 不可否认 | |
| 毋庸置疑 | |
| 综上所述 | |
| 总而言之 | |

### 排比/平行套话

| 词汇 | 备注 |
|------|------|
| 这不仅仅是…更是 | |
| 既是…也是 | |
| 不仅能够…还能够 | |
| 从某种意义上说 | |
| 在这一过程中 | |
| 有必要 | |
| 带来新的机遇和挑战 | |

---

## 🟠 高风险（建议改，但不强制）

- "心里一沉" / "感到恐惧" → 改成身体反应
- "她/他明白了" → 改成行动回应
- "眼神变了" → 改成瞳孔/视线
- "气氛凝重/紧张" → 改成具体感官
- "恐惧像 XX" → 删"恐惧"二字
- "他笑了/苦笑/冷笑" → 改成具体面部动作

完整对照表见 `writing-edicts.md` 铁律二。

---

## 🟡 软提醒（人工判定）

- "原来..." / "也就是说..." / "这说明..."（对白中的总结性句子）
- "与此同时" 类转折过渡
- "他意识到..." / "她意识到..."（**不能替代 "他明白了"**）
- 空心句（删掉无损失的句子）

完整判定逻辑见 `writing-edicts.md` 铁律七（反 AI 痕迹规则）。

---

## CSV 化版本（供机器扫描）

```csv
word,level,category,replacement_hint
稳,critical,abstract_action,改成具体姿态
稳稳地,critical,abstract_action,改成具体姿态
接住,critical,abstract_action,改成具体反应
至关重要,critical,major_meaning,删除
意义重大,critical,major_meaning,删除
关键时刻,critical,major_meaning,删除
转折点,critical,major_meaning,删除
重要时刻,critical,major_meaning,删除
与此同时,critical,transition,改用时间锚点
值得注意的是,critical,transition,直接陈述
不可否认,critical,transition,直接陈述
毋庸置疑,critical,transition,直接陈述
综上所述,critical,transition,删除
总而言之,critical,transition,删除
这不仅仅是,critical,parallel_structure,改成单一陈述
既是...也是,critical,parallel_structure,选择一侧
标志着,critical,emphasis,改成具体行为
塑造,critical,emphasis,改成具体行为
发挥积极作用,critical,emphasis,删除
根植于,critical,emphasis,删除
不可磨灭,critical,emphasis,删除
不断变化的格局,critical,emphasis,删除
聚焦点,critical,emphasis,删除
反映出更广泛的,critical,emphasis,删除

```