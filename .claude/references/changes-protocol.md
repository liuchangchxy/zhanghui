# CHANGES 协议字段定义

`<chapter_changes>` 是 Writer 的 ProposedChanges 声明，不是 Canon 或已发生事实。润色/重写结束、最终正文稳定后，必须重新生成整个块，再运行 `changes_gate.py`。`changes_gate.py` 负责 CHANGES 容器、schema、枚举及现有账本完整性检查；它不做 ProposedChanges 与 ObservedChanges 的语义 reconciliation。

本协议借鉴天命 AI 写小说工具的结构化变更声明机制，**简化到 8 个核心字段**以降低 LLM 输出成本。

## 容器形式

优先格式：`<chapter_changes>...</chapter_changes>`

容错顺序：
1. `<chapter_changes>...</chapter_changes>`
2. `---CHANGES--- ...`
3. `# CHANGES\n...`
4. 末尾 JSON 兜底（≥4 个顶级字段匹配）

## 8 个顶级字段

| 字段名 | 类型 | 是否必填 | 枚举值 |
|---|---|---|---|
| `character_state_changes` | array | 是 | — |
| `new_plot_points` | array | 是 | — |
| `foreshadowing_actions` | array | 是 | action: setup / payoff |
| `location_state_changes` | array | 是 | — |
| `faction_state_changes` | array | 是 | — |
| `time_progression` | object \| null | 是 | importance: normal / important / critical |
| `item_transfers` | array | 是 | new_status: active / lost / destroyed / sealed |
| `unresolved_questions` | array | 是 | — |

空数组 `[]` 也算"显式存在"——不要省略字段。

## 字段细则

### character_state_changes[i]

```json
{
  "character_id": "C-001 或 别名",
  "new_state": "字符串",
  "relationship_changes": {
    "C-002": {"relation": "挚友", "trust_delta": 5, "emotion_phase": "信任"}
  },
  "key_event": "关键事件描述",
  "importance": "normal | important | critical"
}

```

### new_plot_points[i]

```json
{
  "keywords": ["古镜", "窥见"],
  "context": "陈默发现照夜古镜能显示三日后的景象",
  "involved_characters": ["C-001"],
  "importance": "normal | important | critical",
  "storyline": "main | sub | character_arc"
}

```

### foreshadowing_actions[i]

```json
{
  "foreshadow_id": "F1-001",
  "action": "setup | payoff"
}

```

### location_state_changes[i]

```json
{
  "location_id": "L-001 或别名",
  "new_status": "字符串",
  "event": "事件描述",
  "importance": "normal | important | critical"
}

```

### faction_state_changes[i]

```json
{
  "faction_id": "F-001 或别名",
  "new_status": "字符串",
  "event": "事件描述",
  "importance": "normal | important | critical"
}

```

### time_progression

```json
{
  "time_period": "夏末黄昏",
  "elapsed_time": "三日",
  "key_time_event": "主角抵港三日",
  "importance": "normal | important | critical"
}

```

### item_transfers[i]

```json
{
  "item_id": "I-001 或别名（首次出现可只用 item_name）",
  "item_name": "照夜古镜",
  "from_holder": "持有者 ID 或别名",
  "to_holder": "新持有者 ID 或别名",
  "new_status": "active | lost | destroyed | sealed",
  "event": "转移事件描述",
  "importance": "normal | important | critical"
}

```

### unresolved_questions[i]

```json
{
  "question": "古镜的完整来历？",
  "introduced_chapter": 1,
  "target_payoff_chapter": 50,
  "importance": "normal | important | critical"
}

```
