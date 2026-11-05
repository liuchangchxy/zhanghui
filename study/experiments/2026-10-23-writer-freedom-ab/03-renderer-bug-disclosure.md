# Writer Freedom A/B — 渲染缺陷披露（本轮实验的中断记录）

## 发生了什么

本轮正式跑 A/B 之前，我先在 working tree 里跑了一轮 arm B。事后发现，那一轮
**测的不是设计，是我自己代码里的一个渲染缺陷**，所以整轮作废重跑。这份文件是为了
让记录诚实，不把坏数据当结论。

## 缺陷

`chapter_runtime.py::_natural_node()` 负责把章纲的规划记法
`主体 | 动作 | 结果` 渲染成给 Writer 看的一行自然语言。原实现是：

```python
if len(parts) >= 3:
    return f"{parts[0]}：parts[-1]}"   # ← 丢掉了 parts[1]
```

`parts[1]` 就是**动作本身**。于是所有节点在 arm B 的 prompt 里变成：

```
许知远 | 复算事故当夜潮位 | 公开表无逐时值      → 许知远：公开表无逐时值
许知远 | 用周期规律与邻站插值 | 得到当夜逐时潮位  → 许知远：得到当夜逐时潮位
许知远 | 交出设备型号变更记录 | 换取梁沐信任      → 许知远：换取梁沐信任
老周   | 拒绝提供手抄留底 | 许知远注意到年份缺口  → 老周：许知远注意到年份缺口
```

Writer 再也看不到「用什么方法」和「谁做了什么」，只看到结论。这是纯粹的数据丢失，
不是设计差异。

## 两名盲评独立指出的后果（他们并不知道原因）

| 章 | 盲评原话 | 实际指向 |
|---|---|---|
| ch7 | 「B 稿没有相邻两站……和章纲指定的『相邻两站数据插值』不是一回事」 | arm B 的 Writer 从未见过「用邻站插值」这个动作 |
| ch6 | 「Y 稿没有交出设备型号变更记录这一拍」 | 同上 |
| ch10 | 「Y 稿的年份连续性缺口读成了月内空白」 | 同上 |

两位互不相干的评语在同一方向上对齐，正说明这不是评委偏见，而是输入缺陷。

## 处理

1. 修 `_natural_node()`：`f"{parts[0]}：{'，'.join(parts[1:])}"`，动作与结果都保留。
2. 更新 `tests/unit/test_writer_information_chain.py` 中受影响的断言。
3. 归档受污染产物到 `_pre-fix/`（`prompt_B_ch6,7,10}.txt`、`draft_B_ch6,7,10}.md`）。
4. 重新封包 arm B 的三章 prompt，逐章核对节点行已还原动作，再从头起草三章。
5. 归档那一轮的评委输出到 `_pre-fix/judges/`，不参与最终汇总。

## 被归档的产物清单

```
_pre-fix/prompt_B_ch6.txt   _pre-fix/prompt_B_ch7.txt   _pre-fix/prompt_B_ch10.txt
_pre-fix/draft_B_ch6.md     _pre-fix/draft_B_ch7.md     _pre-fix/draft_B_ch10.md
_pre-fix/judges/ch6,7,10}_judge_XY.md  _pre-fix/judges/ch6,7,10}_judge_YX.md
_pre-fix/judges/ch6,7,10}_review_B.json  _pre-fix/judges/judge_scores.json
```

**任何引用 `_pre-fix/` 内数值的结论都不成立。** 正式结论只来自修好之后重跑的一轮。
