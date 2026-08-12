---
name: webnovel-deslop-check
description: 独立触发 anti-slop 双引擎扫描，对任意章节（已写好的）输出 Markdown 报告。Use when reviewing existing chapters, batch-scanning old drafts, or doing a periodic health check on your manuscript.
allowed-tools: Read Write Edit Grep Bash
---

# De-Slop Check (Independent Anti-AI-Flavor Scanner)

## 目标

对任意已写章节（或全本所有章节）跑 anti-slop 扫描，输出 Markdown 报告：
- blocking 项位置 + 原文引用 + 修改建议
- advisory 项汇总

## 适用场景

- 回头改稿：扫旧章节，看哪些地方需要改
- 批量体检：扫全本，统计 AI 味最重的章节
- 阶段性 review：每写 10 章扫一次，确认风格未漂移

## 执行方式

### 扫单个章节

```bash
python3 ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/text_humanizer.py \
    detect --chapter-file 正文/第{NNNN}章-{title_safe}.md

node ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/check-ai-patterns.js \
    --check --fail-on=blocking \
    正文/第{NNNN}章-{title_safe}.md

```

把两份输出合并为 Markdown 报告，存到 `审查报告/deslop-第{NNNN}章.md`。

### 批量扫描全本

#### 工具输入格式差异（先看清再调）

四个 anti-AI / 格式类脚本的 CLI 入参约定**不一致**，调用前必须看清：

| 脚本 | 入参形式 | 多文件支持 | 输出 |
|------|---------|-----------|------|
| `text_humanizer.py` | `--chapter-file <path>`（单文件） | ❌ 一次一个（设计如此，内部 `_load_chapter` 用 `Path.read_text` 单文件加载） | JSON 对象 |
| `check-ai-patterns.js` | positional `<file...>` | ✅ 一次多文件，逐文件扫描累加 finding | 文本 / `--json` 时为 JSON |
| `normalize-punctuation.js` | positional `<file...>` | ✅ 一次多文件，逐文件 in-place 改写 | 文本 |
| `changes_gate.py` | `--chapter-file <path>`（单文件） | ❌ 一次一个（CHANGES 协议是单章合约） | JSON 对象 |

为什么 `text_humanizer.py` 不改造成多文件？两点：
1. 它内部走的是单次 `detect_patterns(text)` 内存扫描，没 batch 优化（forked from humanizer method，原版就是单文件）。
2. 它的输出是 JSON 对象（不是 JSON array），批量时多文件无法天然合并。

所以批量扫 30 章时 `text_humanizer.py` 必须 for-loop 30 次，**这是设计约束，不是 bug**。

#### 批量扫全本的标准调用模板（两段式）

按上面的格式差异，**先用 for-loop 串行调 `text_humanizer.py`（单文件）×30，再一次性调 `check-ai-patterns.js`（多文件）**，输出统一 JSON 格式：

```bash
# 第 1 段：text_humanizer.py 单文件逐章（必须 for-loop）
mkdir -p .webnovel/tmp/deslop
> .webnovel/tmp/deslop/humanizer-batch.jsonl
for f in 正文/第*.md; do
  result=$(python3 .claude/scripts/text_humanizer.py detect --chapter-file "$f" 2>&1) || {
    echo "WARN: text_humanizer failed for $f" >&2
    continue
  }
  # 每行追加 {"chapter": "...", "ok": ..., "severity": ..., "issues": [...]}
  echo "$result" | python3 -c "
import sys, json
data = json.loads(sys.stdin.read())
out = {'chapter': data.get('chapter_name', ''), 'ok': data.get('ok', False),
       'severity': data.get('severity', 'low'), 'issue_count': data.get('issue_count', 0),
       'issues': data.get('issues', [])}
print(json.dumps(out, ensure_ascii=False))
" >> .webnovel/tmp/deslop/humanizer-batch.jsonl
done

# 第 2 段：check-ai-patterns.js 多文件一次性调（design 支持 <file...>）
node .claude/scripts/check-ai-patterns.js --check --json --fail-on=blocking \
  正文/第*.md > .webnovel/tmp/deslop/check-ai-patterns-batch.json 2>&1
# 非零退出 = 有 blocking 命中（按 webnovel-write/SKILL.md Step 4.6 仲裁规则处理）
```

然后把两份 JSON 一起读，按 `webnovel-write/SKILL.md` Step 4.6 "anti-slop 双引擎仲裁规则" 仲裁（frequency-based 优先、blocking 触发重写、advisory ≤ 2 放行），最后写 `审查报告/deslop-batch-report.md` 汇总。

#### 简化版（旧 for-loop 兼容）

如果只是看每一章的粗判（不落 JSON），可以直接用原始的 for-loop：

```bash
for f in 正文/第*.md; do
    echo "=== $f ==="
    python3 .claude/scripts/text_humanizer.py detect --chapter-file "$f" 2>&1 | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'  severity: {data.get(\"severity\", \"?\")} (issues={data.get(\"issue_count\", 0)})')
print(f'  issues: {\"; \".join(data.get(\"issues\", []))}')
"
done
```

生成 `审查报告/deslop-batch-report.md` 汇总。

## 报告模板

每个 blocking 项：

```markdown
### [RULE_ID] 规则名

- **位置**：第 N 段 / 第 N 行
- **原文**：`"..."`
- **问题**：解释为什么这是 AI 味
- **修改建议**：给出一个具体改写方向

```

advisory 项汇总到末尾表格。

## 三层 anti-AI 参考资料（`references/aesthetic/`）

双引擎（`text_humanizer.py` + `check-ai-patterns.js`）做的是**句法/模式层**
扫描——抽象否定排比、套词密度、章尾总结体等机械指纹。

`references/aesthetic/` 装的是**语义层 + 机器可读硬清单 + 速查表**，
用于把扫描结果落到具体改写方向时翻阅：

- @references/aesthetic/writing-edicts.md — 7 铁律 + 11 反 AI 维度（语义层）
  - 句长必须参差、禁止情绪标注、对白不能承载设定、比喻必须带个人印记、
    段落结构不可预测、每章必须有一个"不完美瞬间"、反 AI 痕迹规则
  - 判定逻辑在写报告"修改建议"一栏时直接引用
- @references/aesthetic/ai-word-blacklist.md — 38 词硬清单（机器扫描层）
  - 🔴 致命 / 🟠 高风险 / 🟡 软提醒 三级
  - 末尾附 CSV 块，可被 linter / pre-commit 直接读取
- @references/aesthetic/anti-ai-quick-ref.md — 8 组 AI 写法 vs 人类写法对照
  - 改稿时一句话配一个具体改写方向
  - 末尾附"自检三问"：空心句 / 通用比喻 / 无具体细节

### 报告引用规则

当扫描结果命中以下模式时，修改建议必须从对应文件取：

| 扫描器命中 | 引用 |
|-----------|------|
| `not-is-comparison` / `negation-parade` / `reverse-not-is` | `writing-edicts.md` 铁律七 - 排比与平行结构禁区 |
| `voice-contrast` / `quote-emphasis-tic` | `writing-edicts.md` 铁律二 - 禁止情绪标注 |
| `trailer-ending` / `trailer-summary` | `writing-edicts.md` 铁律七 - 章尾总结体 |
| `abstract-summary-tic`（命运/棋局/这一刻终于明白） | `writing-edicts.md` 铁律七 - 分析与拔高禁区 |
| 命中 CSV 词的硬清单项 | `ai-word-blacklist.md` 对应行的 `replacement_hint` |
| 没命中扫描器但语言观感仍"AI" | `anti-ai-quick-ref.md` 对照表 + 自检三问 |

### 来源声明

3 个文件 fork 自 `Beat1ngHeart/novel-writing-toolkit` `.claude/commands/novel.md`
（MIT License）；与本地 `.claude/references/deslop/` 的 `banned-words.md` /
`anti-ai-writing.md` 是**正交**关系：deslop/* 偏正面改写与单点替换，
aesthetic/* 偏铁律约束与硬清单扫描。两套都查，避免漏检。

## 不做的事

- 不改正文（这是 reviewer-like skill 的工作，不属于本 skill）
- 不调用 reviewer subagent
- 不写 CHANGES 校验（CHANGES 是写前用的，本 skill 是写后用的）

## 已知工具限制

- **两个工具都假定输入是 UTF-8 文本**。`text_humanizer.py` 在 binary / GBK /
  UTF-16 / 截断 UTF-8 输入上不会报警（会把字节当字符处理并返回 `ok: true`），
  `check-ai-patterns.js` 在 binary 上会触发 long-paragraph advisory。
- **anti-slop 是启发式，不是合同**。建议在把扫描结果并入报告前，对 > 50KB
  或非 UTF-8 编码的章节文件做一次人工 sanity check。