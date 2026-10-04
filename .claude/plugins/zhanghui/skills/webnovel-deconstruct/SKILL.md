---
name: webnovel-deconstruct
description: 独立拆解参考书到 .webnovel/reference_research/ 库（多书并存，不动 idea_bank）。当用户想调研对标书、对比多本、或不在 /webnovel-init 流程内拆解时调用。
---

# Webnovel Deconstruct — 独立拆书

## 目标

把一本参考书拆解成结构化产物，落到 `<project_root>/.webnovel/reference_research/<book-safe>/` 下，与 `/webnovel-init` Step 1.5 走相同的落点。本 skill 是独立入口，**不动** `idea_bank.json`、`.webnovel/state.json`、设定集、大纲、正文、`.story-system/`。

## 调用时机

- 用户主动 `/webnovel-deconstruct "《凡人修仙传》"` 调研对标书
- `/webnovel-chart-scan` 扫榜后，用户想批量拆对标清单（`--from-scan`）
- 已写到一半，想回头补一本参考书的拆解
- 学习 / 研究用途（不出 init_candidates，只产出 report.md + do_not_copy）

## 输入形态

CLI 形式（命令壳 `commands/deconstruct.md` 已经在）：

```bash
# 书名 + 平台线索（quick 模式，无文本风险高）
/webnovel-deconstruct --book "起点《凡人修仙传》"

# 本地正文路径（deep 模式，路径不可读时降级 quick）
/webnovel-deconstruct --text-path /path/to/chapter1.txt

# 对话粘摘录（quick 模式）
/webnovel-deconstruct --excerpt "<摘录 1000 字以内>"

# 从 chart-scan marked-references.json 批量拆
/webnovel-deconstruct --from-scan

# 严格模式：拒绝重拆已有 <book-safe>/（默认是覆盖）
/webnovel-deconstruct --strict
```

如果参数不足，向用户追问（一次一个，问清楚为止）。**不要默认拆书**。

## 执行步骤

1. **收集输入**：通过 CLI 参数或 AskUserQuestion 收集 `{reference_title, reference_source, reference_text_path|reference_text_excerpt, analysis_mode}`。`--from-scan` 时从 `./chart-scan/marked-references.json` 读 `references[]` 数组逐条处理。

2. **调用 deconstruction-agent**：
   ```
   Use the Agent tool to run `webnovel-writer:deconstruction-agent`
   ```
   传入 §2 列出的字段。**禁止使用 `subagent-type` 字段**。

3. **质量门控**：检查返回 `init_reference_research.quality`：
   - `quality.passed=false` 或 `confidence < 0.85`：向用户展示缺漏，三选一：
     - (i) 用更多文本重跑
     - (ii) 用稀疏模式继续
     - (iii) 放弃（默认）
   - 通过：进入第 4 步。

4. **展示原文必读项**：把 `do_not_copy` 和 `canon_contamination_warnings` 字段**原文**展示给用户——这些是负面约束，用户写新书时要避开。

5. **用户确认门**：**用户确认前**禁止任何文件写。

6. **落盘**：用户确认后：
   - 调用 `from init_reference_tree import build_reference_tree`
   - 调用 `build_reference_tree(project_path, schema, reference_title, overwrite=True)`（P2 默认覆盖）
   - 旧树存在时，`_schema.json` 自动备份为 `_schema.json.bak-<ts>`

7. **退出**：输出 `<project>/.webnovel/reference_research/<book-safe>/` 绝对路径，提示用户：
   - 下次 `/webnovel-plan` 会自动发现这本书
   - 多本书并存没问题，每个 `<book-safe>/` 独立
   - 重拆同一本用 `overwrite=True`（默认）或 `--strict` 拒绝

## 禁止行为（与 init §1.5 一致）

- 写入 `idea_bank.json`、`.webnovel/state.json`、`.webnovel/reference_research/` 之外的位置
- 写入 `设定集/`、`大纲/`、`正文/`、`.story-system/`
- 调用 `init_project.py`（这是 init 的职责）
- 主流程口头重写或简化 agent 返回的结构化字段

## 错误处理

- 用户给了不存在的书名（agent 不认识）：让用户补 platform/title/excerpt 三选一
- `--text-path` 路径不可读：自动降级 quick + 让用户改用 `--excerpt`
- `--from-scan` 但 `marked-references.json` 不存在：提示用户先扫榜 + 标记
- 输出路径冲突：默认覆盖（除非 `--strict`）；备份旧 `_schema.json` 到 `.bak-<ts>`