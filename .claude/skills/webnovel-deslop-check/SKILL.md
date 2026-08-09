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

扫描 `正文/` 目录下所有章节：

```bash
for f in 正文/第*.md; do
    echo "=== $f ==="
    python3 .claude/scripts/text_humanizer.py detect --chapter-file "$f" 2>&1 | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'  blocking: {sum(1 for x in data if x.get(\"severity\")==\"blocking\")}')
print(f'  advisory: {sum(1 for x in data if x.get(\"severity\")==\"advisory\")}')
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