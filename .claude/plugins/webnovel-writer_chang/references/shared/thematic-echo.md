---
name: thematic-echo
purpose: 主题回响 — state.json 字段说明
---

# 主题回响 (Thematic Echo)

> **理论来源**：麦基"故事价值论" + 红楼梦主题论证

## 核心概念

主题是故事的最高命题。每卷必须**回响**主题 ≥3 次。

## state.json 字段

```json
{
  "story_craft": {
    "thematic_echoes": [
      {
        "id": "TE-001",
        "premise": "真正的强大是记忆而非力量",
        "echoes": [
          {"chapter": 5, "manifestation": "主角回忆根源时力量觉醒"},
          {"chapter": 25, "manifestation": "Midpoint 反派用纯力量失败"},
          {"chapter": 49, "manifestation": "Finale 主角靠记忆战胜收割者"}
        ]
      }
    ]
  }
}
```

## 校验

- 每卷 ≥1 个 thematic_echoes（HARD）
- 每个 premise 的 echoes ≥3（HARD）
- 卷末检查：未达成 → WARNING

## 与 Ending 联动

Final Image 应是主题的最强一次回响。
