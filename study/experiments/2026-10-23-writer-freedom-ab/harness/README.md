# A/B 实验脚手架（归档副本）

这些脚本是 2026-10-23 writer-freedom A/B 实际跑过的驱动脚本，从 `.tmp/wf-ab/`
复制过来存档，因为 `.tmp/` 不进版本库。**它们是档案，不是可直接运行的产品代码。**

## 硬编码路径

脚本里写死了当时的绝对路径，原样运行会失败：

| 前缀 | 含义 |
|---|---|
| `/Users/chang/Desktop/Code/zhanghui/.tmp/wf-ab/` | 实验工作目录（两本书副本、章节产物） |
| `/Users/chang/Desktop/Code/zhanghui/.worktrees/wf-code-A/.claude/plugins/zhanghui` | arm A 的代码快照（commit `82e496d`） |
| `/Users/chang/Desktop/Code/zhanghui/.claude/plugins/zhanghui` | arm B 的代码（working tree） |

要重跑，先把这些前缀改成你自己的路径，并重建 `book_A` / `book_B`（`setup_arm.sh` 做这件事）。

## 各文件职责

| 文件 | 作用 |
|---|---|
| `setup_arm.sh` | 建 arm A worktree、复制两本书、对齐受治理上下文 |
| `router_input.sh` | 为某章生成两臂的 Router 输入 |
| `seal.sh` / `seal_lean.sh` | 封口 arm A / arm B 的 Writer prompt（后者带 `--lean-input`） |
| `review_prep.sh` | 准备 Reviewer 上下文 |
| `pack.sh` | 生成盲评包（含 X/Y 随机映射，seed = 20261023 + 章号） |
| `make_blind.py` | `pack.sh` 调用的映射与打包逻辑 |
| `aggregate.py` | 汇总双评委打分、解析「哪一稿更好」、回填臂别 |
| `metrics.py` / `metrics_run.py` / `prompt_size.py` / `compare_prompts.py` | 篇幅与 prompt 体积统计 |
| `judge_agent_prompt.txt` / `draft_agent_prompt.txt` / `DRAFT_INSTRUCTION.md` | 喂给评委 / Writer 的模板 |
| `judge_template_base.md` | 评分项定义 |
| `CONTAMINATION.md` | 第一轮作废的 JSON 来源记录 |
