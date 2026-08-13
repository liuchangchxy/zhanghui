# Context Slice Schema

## 这是什么

每个 webnovel-writer 下游 agent（writer / reviewer / polisher）需要不同的 context：
- writer：要章纲、角色卡、前几章摘要
- reviewer：要正文本身、周围章节、爽点规划
- polisher：只要正文 + 文风规则

不要给它们全本。`context_slice.py` 把每个 agent 的"最小必要 context"白名单化，调用方按需喂入。

## 三个内置 slice

### `writer` — 起草时喂什么

| 路径 pattern | 必需？ |
|---|---|
| `大纲/第1卷-详细大纲.md` | 必需 |
| `大纲/总纲.md` | 可选 |
| `设定集/角色库/*.md` | 必需 |
| `设定集/物品库/*.md` | 可选 |
| `设定集/其他设定/*.md` | 可选 |
| `.webnovel/summaries/ch{NNNN-2}.md` | 可选 |
| `.webnovel/summaries/ch{NNNN-1}.md` | 可选 |

### `reviewer` — 审查时喂什么

| 路径 pattern | 必需？ |
|---|---|
| `正文/第{NNNN-2}章*.md` ~ `第{NNNN+2}章*.md` | 必需（当前章）；其他可选 |
| `大纲/爽点规划.md` | 可选 |
| `大纲/第1卷-时间线.md` | 可选 |
| `设定集/角色库/*.md` | 可选 |
| `设定集/物品库/*.md` | 可选 |

### `polisher` — 润色时喂什么

| 路径 pattern | 必需？ |
|---|---|
| `正文/第{NNNN}章*.md` | 必需 |
| `设定集/其他设定/文风.md` | 可选 |
| `.claude/references/deslop/whitelist.md` | 可选 |

## 怎么用

```python
from context_slice import read_slice, estimate_tokens

files = read_slice(project_root, "writer", chapter=5)
# files = {"大纲/第1卷-详细大纲.md": "...", "设定集/角色库/陈默.md": "...", ...}

total_tokens = sum(estimate_tokens(c) for c in files.values())
print(f"writer slice 总 token: {total_tokens}")
```

## 怎么扩展

往 `SLICES` 字典里加：

```python
PROOFREADER_SLICE = ContextSlice(
    name="proofreader",
    description="...",
    entries=[SliceEntry("..."), ...],
)
SLICES["proofreader"] = PROOFREADER_SLICE
```

## 命名约定

- slice name 用 snake_case（writer / reviewer / polisher）
- 占位符 `{NNNN}`, `{NNNN-1}`, `{NNNN+2}` 表达"当前章节号 ± 偏移"
- 占位符会被自动展开为 4 位章节号（chapter=5 → `{NNNN}` = `0005`）