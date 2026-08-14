---
name: character-arc
purpose: 主角弧追踪 — state.json 字段说明
---

# 主角弧 (Character Arc)

> **理论来源**：Breaking Bad 跨季人物弧 + Dan Harmon Story Circle (Change)

## 核心概念

主角弧是**跨卷内在转变**的追踪机制。

## state.json 字段

```json
{
  "story_craft": {
    "character_arc": {
      "name": "林川",
      "starting_state": "归乡迷茫、记忆模糊",
      "ending_state": "接受本源、觉醒意识",
      "transformation": "通过卡池抽取与回忆逐步解锁根源",
      "key_moments": [
        {"chapter": 5, "event": "首次抽卡出现意外"},
        {"chapter": 25, "event": "Midpoint 真相揭露"}
      ]
    }
  }
}
```

## 4 字段必填

- `name` — 主角名
- `starting_state` — 卷首内在状态
- `ending_state` — 卷末内在状态
- `transformation` — 如何从 starting 到 ending

## key_moments 追踪

- 建议 ≥3 个/卷
- 必须在 Midpoint + Finale 各 ≥1 个

## 与 Beat 联动

`key_moments` 应与 `volume_beat.beats[].notes` 联动，确保内在转变与外在事件同步。

## 校验

- 4 必填字段缺失 → BLOCKER
- `starting_state == ending_state` → WARNING（无变化）
