# 测试指南：webnovel-writer 个人 fork

测试环境：`/Users/chang/Desktop/novel-test-1/`
`.claude/` 已软链到 zhanghui 的实现，脚本更新自动同步。

---

## 启动

```bash
cd /Users/chang/Desktop/novel-test-1
claude
```

在新会话里先确认以下 skill 已加载：

- `/webnovel-write`（主流程，含 Step 4.5 + 4.6）
- `/webnovel-fast-write`（快车道，跳过 reviewer）
- `/webnovel-deslop-check`（写后扫描）
- `/webnovel-init` / `/webnovel-plan`（初始化和规划）

---

## 测试用故事核：用你自己的 idea

直接用你想写的小说 idea 开始测试。这才是真实场景，比我编的设定更能反映你将来用工具的真实体验。

**什么样的 idea 更容易暴露问题（可选参考）：**
- 至少有 3-5 个有名有姓的角色（触发 R3 实体引用校验）
- 至少有 1 个重要物品/法宝/道具（触发 R7 物品状态机）
- 至少有一条要"埋+回收"的伏笔（触发 R4 伏笔推进）
- 角色之间有信任变化（触发 R5 ±30 限制）
- 跨多章的时间推进（触发 R8 时间线）
- 主角不是孤狼——有反派、有盟友、有阵营（人设多样性能暴露 OOC/关系崩坏问题）

**idea 越"复杂"，测试越有价值。** 简单的独狼冒险反而测不出大部分校验规则。

**不需要做的事：** 别担心 idea 不完美。`/webnovel-init` 会和你多轮对话补全设定，LLM 会帮你生成角色卡、势力表、金手指细则等。直接把你脑子里的故事核（一句话也行）丢给它就行。

## /webnovel-init 调用模板

直接把上面的故事核贴上去，然后按 init 的 6 步交互一步步走：

1. 故事核 → 粘上面的
2. 角色设定 → LLM 会问，让它生成
3. 金手指 →「望虚古镜，三日预知」已含在故事核，让 LLM 细化
4. 世界观 → LLM 会问
5. 创意约束 → 强调"扮猪吃虎" + "不乱开挂"
6. 复述确认 → 让它复述一遍，你改到你满意

建议生成 3 卷大纲（每卷 10-15 章），总共约 30-40 章。

---

## 写第一章（最关键的测试）

```
/webnovel-write
```

### 观察 checklist

| 现象 | 期望 |
|---|---|
| LLM 调用 context-agent subagent | ✓ 应有 subagent 调用 |
| LLM 在 Step 2A 末尾追加 `<chapter_changes>...</chapter_changes>` 块 | ✓ 必含 |
| bash 命令 `python3 .../changes_gate.py ...` 被执行 | ✓ 见 tool 输出 |
| gate 返回 `passed: true` 或 `passed: false` | 二者皆可，看数据质量 |
| 如果 failed，LLM 是否重写 `<chapter_changes>` 块（不改正文） | ✓ 退回 Step 2A |
| 退出后 `.webnovel/state.json` 被更新 | ✓ 见 git diff |
| 退出后 `正文/第0001章-xxx.md` 文件存在 | ✓ |

### 关键日志位置

- `.webnovel/state.json` — 项目状态
- `.webnovel/summaries/ch0001.md` — 章节摘要
- `.webnovel/index.db` — 实体/事件/伏笔/场景数据库
- `.webnovel/tmp/changes_gate_failures.jsonl` — 校验失败记录（如果有）

---

## 写第二章（验证 CHANGES 数据积累）

```
/webnovel-write
```

### 重点观察

- 第二章的 CHANGES 块能否引用第一章创建的实体（C-001 陈落微、L-001 青云宗、I-001 望虚古镜等）
- 如果 R3 触发（引用了未注册的实体），LLM 是否在 CHANGES 块里修复
- 如果 R5 触发（信任度变化太大），LLM 是否调整

---

## 写第三章 + 伏笔 setup

```
/webnovel-write
```

故意让 LLM 在第三章的 CHANGES 块里 `setup` 一个新伏笔 ID（你可以在对话里提示"埋一个'镇魂铃会失窃'的伏笔"）。

### 观察

- `foreshadowing` 表是否新增了一行
- 后几章 LLM 是否会引用这个 foreshadow_id

---

## 用快车道写第四章

```
/webnovel-fast-write
```

### 对比 /webnovel-write

- 体感速度是否明显快（应少 1-2 分钟）
- quality 是否持平（用 /webnovel-deslop-check 扫对比）

---

## 写后体检

```
/webnovel-deslop-check
```

输入章节文件路径，输出 Markdown 报告到 `审查报告/`。

---

## 批量体检

```
/webnovel-deslop-check
```

让它跑全部 `正文/第*.md`，生成 `审查报告/deslop-batch-report.md`。

---

## 故意制造失败（验证 gate 真的生效）

### 测试 R3：引用未注册实体

打开 `/webnovel-write`，在对话里说：

> "本章让我提到一个新角色，叫李随风，是个散修，请把他写进去。"

LLM 会在 CHANGES 块里写 `character_id: "李随风"`（或自动建账本）。观察：
- 是被 gate 打回重写，还是 LLM 主动建账本？
- 两种都算正常行为，看哪种更符合你期望。

### 测试 R5：故意让信任度爆表

在 `/webnovel-write` 时说：

> "本章让陈落微和方砚青反目成仇，从挚友到死敌。"

LLM 可能写 `trust_delta: -100`。观察：
- R5 是否打回（要求 LLM 改写 trust_delta 到 ±30 以内）
- 还是 LLM 主动拆成两章来过渡

### 测试 R7：物品状态机

在 `/webnovel-write` 时说：

> "本章让望虚古镜被打碎，方砚青从废墟里找到碎片重新祭炼。"

观察 CHANGES 块：
- 物品状态是否走 "active → destroyed → sealed → active" 这种合法路径
- 如果直接 "destroyed → active"，R7 应该打回

---

## 验收标准（跑完 5-10 章后）

按 spec §9，验收第 5 条："作者本人能说出'至少 X 个痛点被解决'"。具体看：

| 痛点 | 验收 |
|---|---|
| 长篇一致性崩坏 | 5 章后检查 `.webnovel/index.db`：实体引用的成功率、伏笔 setup/payoff 的连贯性 |
| AI 味重 | `/webnovel-deslop-check` 报告：blocking 数应 < 5 个/章，或至少明显少于裸跑 chat |
| 流程繁琐 | /webnovel-fast-write 是否成为默认；写一章的体感时间 |

如果三项里至少一项有明显改善，本次 fork 就算成功。

---

## 故障排查

| 现象 | 排查 |
|---|---|
| /webnovel-write 看不到 Step 4.5 提示 | 检查 `.claude/skills/webnovel-write/skill.md` 是否软链过来：`ls -la .claude/skills/webnovel-write/` |
| changes_gate.py 找不到 | 检查软链：`ls -la .claude/scripts/` |
| LLM 不写 CHANGES 块 | 在对话里明确提示"必须用 <chapter_changes> 块" |
| gate 一直打回 | 看 `.webnovel/tmp/changes_gate_failures.jsonl`，把第一条 failure message 贴出来分析 |
| 测试章节内容大量 AI 味 | 调整 webnovel-deslop-check 阈值；或换更长的章节 |
| 想修改规则 | 改 zhanghui 里的 `.claude/scripts/changes_gate.py`，软链会自动同步 |

---

## 跑完测试后

告诉我：
1. 5-10 章测试稿是否跑通
2. 三个痛点哪个被解决 / 哪个没解决
3. 想继续 Phase 4 调阈值，还是收工归档

按这个信号决定下一步。