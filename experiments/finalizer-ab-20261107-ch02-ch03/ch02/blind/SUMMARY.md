# ch02 盲评汇总（A = Writer raw，B = Finalizer candidate）

- 方法：两家不同模型族，位置反转，只评六个维度。
- J1：Antigravity Gemini 3.8 Flash，甲=RAW，乙=CANDIDATE。
- J2：本地 Anthropic-compatible proxy（会话模型组），甲=CANDIDATE，乙=RAW。
- 键：`blind_key.json`；原始结果：`j1_gemini/result.json`、`j2_proxy/result.json`。

## 归一后结果

| 维度 | J1（Gemini） | J2（proxy） |
|---|---|---|
| OVERALL_PREFERENCE | CANDIDATE | CANDIDATE |
| READING_APPEAL | CANDIDATE | CANDIDATE |
| LOW_AUTHOR_EXPLANATION | CANDIDATE | CANDIDATE |
| SENTENCE_NATURALNESS | CANDIDATE | TIE |
| SCENE_IMMERSION | CANDIDATE | CANDIDATE |
| SUBTEXT | CANDIDATE | CANDIDATE |

计数：candidate 11 / raw 0 / TIE 1。

## 解释

- 两路 Judge 在总体偏好上方向一致，且位置已经反转；J2 的总体置信度只有 0.62，收益幅度不大。
- candidate 的收益集中在删除五类解释/重复：抽卡池心理预判、“四百碎片”总额、“木盾能挡，但不能打”、NPC“也没有安慰他”、“这七个词他闭着眼都能背出来”、重复的余额与“没有说明”。
- J1 的 `SCENE_IMMERSION` 证据认为 raw 的机制分析句抽离了现场；J2 的 `SENTENCE_NATURALNESS` 判 TIE，认为 candidate 的短句略电报感，但可接受。
- 两位 Judge 都独立指出一处 raw/candidate 共有的算术问题（卖卡后应为 121，正文写 118），该问题不属于 Finalizer 引入，已记录给正常 Reviewer / Step 4。
