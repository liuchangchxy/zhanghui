# Workflow Snapshot 协议

## 这是什么

每次 `/webnovel-plan` 完成后，冻结当前 设定集/ + 大纲/ 的完整副本到 `.webnovel/snapshots/ch{NNNN}/`。

写未来章节时即使改了设定，已写章节也不会受影响——因为它"出生时"的设定已经被锁死。

## 何时调用

```bash
# 在 /webnovel-plan 流程的最后一步（或单独运行）
python3 .claude/scripts/snapshot_manager.py freeze <chapter> --project-root .
```

按惯例：每次完成一章的章纲拆分后立刻 freeze。

## 何时校验

`/webnovel-fast-write` 和 `/webnovel-write` 的 Step 0（预检）会调用 `verify`：

```bash
python3 .claude/scripts/snapshot_manager.py verify <chapter> --project-root .
```

- 退出码 0 = 设定未漂移，正常往下走
- 退出码 1 = 漂移（修改过 / 新增 / 删除），主流程**不阻断**，但会在日志里 warning：
  > `[snapshot] ch0001 设定已漂移：1 个文件被修改、0 个新增、0 个删除。是否需要 re-snapshot？`
- 退出码 2 = infrastructure error（snapshot 目录不存在 / manifest 损坏），需要人工处理
- 退出码 3 = 用法错误（参数解析失败；与 infrastructure error 区分，避免 caller 误判）

## 漂移了怎么办

两个选择：

**A. 接受漂移**（默认）：写手用最新的设定继续写。可能产生前后不一致，但省时间。

**B. 重新 freeze**：
```bash
python3 .claude/scripts/snapshot_manager.py freeze <chapter> --project-root .
# 警告: ch0001 已存在，将被覆盖
```

适用场景：你改了设定但想"以新设定为准重写"前面章节——这时候别 re-freeze，先去把那几章用 `/webnovel-revise` 重写。

## 查 snapshot 状态

```bash
python3 .claude/scripts/snapshot_manager.py list --project-root .
python3 .claude/scripts/snapshot_manager.py diff <chapter> --project-root .
```

## 不冻结什么

- `正文/` — 产物，不是输入。重新生成不需要 snapshot
- `index.db` — 每次 chapter-commit 会更新；不需要版本冻结
- `.webnovel/summaries/` — 同上
- `.webnovel/snapshots/` 自己 — 防止递归
