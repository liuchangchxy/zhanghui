---
name: webnovel-revise
description: 根据 reviewer 的结构化反馈局部重写章节。只改 contract 标出的段，其他原样保留。比整章重写省 60-80% token。Use when reviewer has run and produced structured JSON with blocking issues.
allowed-tools: Read Write Edit Grep Bash
---

# Local Chapter Revision (Structured Rejection Contract)

## 目标

拿到 reviewer 的 JSON 后，**只重写标出的段**，不重写整章。

## 适用场景

- reviewer 跑完，输出 blocking issues
- 你想改但不想花一整章的 token
- 想保持未受影响段落的原文（避免 AI 改稿时的"漂移"）

## 不适用场景

- reviewer 没跑过（先 `/webnovel-review` 或 `/webnovel-write`）
- 大返工（>50% 段落要改）—— 直接用 `/webnovel-write` 整章重写更划算
- 想改大纲或设定（PR 1 snapshot 范畴）

## 执行流程

按顺序执行：

1. **拿 reviewer 输出**：从 `.webnovel/review/ch{NNNN}.json` 读取（如不存在，告诉用户先跑 reviewer）。
2. **构造 contract**：
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/revise_chapter.py \
       --chapter-file "正文/第${NNNN}章-${title}.md" \
       --contract .webnovel/review/ch${NNNN}.json \
       --dry-run
   ```
   确认 `target_sections` 列表合理。
3. **真实重写**：
   ```bash
   python3 .../revise_chapter.py \
       --chapter-file "正文/第${NNNN}章-${title}.md" \
       --contract .webnovel/review/ch${NNNN}.json \
       --output "正文/第${NNNN}章-${title}.revised.md"
   ```
4. **人工 diff**：用 Read 或 diff 工具对比原版和 .revised.md。
5. **覆盖**：用户确认后，把 .revised.md 改名为原文件名（删 .revised 后缀）。
6. **CHANGES 重新校验**：
   ```bash
   python3 .../changes_gate.py --chapter-file "正文/第${NNNN}章-${title}.md" --db index.db --json
   ```
7. **回写 data-agent**（可选）：重跑 `webnovel-writer:data-agent` 让 index.db 同步。

## 退出条件

- reviewer 没有输出 contract → 提示先跑 review
- target_sections 为空 → contract 没有 blocking issue，无需 revise
- LLM 输出不含 `## §N` 标题 → revise_chapter.py 会兜底追加，warning 但不阻断

## 失败处理

- LLM 调用失败（ANTHROPIC_API_KEY 未设置 / 超时）→ exit code 非 0，向用户报告
- 重写后 CHANGES 校验失败 → 把原版恢复（不覆盖），告诉用户"修订版破坏了设定契约，建议人工处理"