# CHANGES 协议示例

## 完整示例

```markdown
（章节正文：约 2500 字，陈默在论剑台险胜王玄之...）

<chapter_changes>
{
  "character_state_changes": [
    {
      "character_id": "C-001",
      "new_state": "疲惫但振奋",
      "relationship_changes": {
        "C-002": {"relation": "宿敌", "trust_delta": 3, "emotion_phase": "竞争"}
      },
      "key_event": "在论剑台险胜王玄之",
      "importance": "critical"
    },
    {
      "character_id": "C-002",
      "new_state": "受伤但不甘",
      "key_event": "论剑台落败",
      "importance": "important"
    }
  ],
  "new_plot_points": [
    {
      "keywords": ["论剑台", "王玄之"],
      "context": "陈默与王玄之的第一次正面交锋，主角险胜",
      "involved_characters": ["C-001", "C-002"],
      "importance": "important",
      "storyline": "main"
    }
  ],
  "foreshadowing_actions": [
    {"foreshadow_id": "F1-002", "action": "setup"}
  ],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": {
    "time_period": "夏末黄昏",
    "elapsed_time": "一日",
    "key_time_event": "论剑台对决",
    "importance": "normal"
  },
  "item_transfers": [],
  "unresolved_questions": [
    {
      "question": "王玄之的真实身份？",
      "introduced_chapter": 2,
      "target_payoff_chapter": 30,
      "importance": "important"
    }
  ]
}
</chapter_changes>

```

## 极简示例

```markdown
（章节正文...）

<chapter_changes>
{
  "character_state_changes": [],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
</chapter_changes>

```

## 错误示例（会被门禁打回）

```markdown
<!-- 缺 item_transfers 字段 -->
<chapter_changes>
{
  "character_state_changes": [],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "unresolved_questions": []
}
</chapter_changes>

<!-- importance 非法值 -->
{"character_state_changes": [{"importance": "very-important"}]}

<!-- 不在账本的 character_id（除非已加入账本）-->
{"character_state_changes": [{"character_id": "Z-999"}]}

<!-- trust_delta 超阈值 -->
{"character_state_changes": [{"character_id": "C-001", "relationship_changes": {"C-002": {"trust_delta": 100}}}]}

```
