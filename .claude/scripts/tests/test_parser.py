"""Parser 健壮性回归测试：多块、末尾逗号、单引号 keys、嵌套等。

覆盖对抗式审查报告 CRITICAL Bug 5、6、11。
"""
import pytest

from changes_gate import (
    extract_changes_block,
    repair_changes_json,
    parse_changes,
)


# === Bug 5: 末尾逗号修复 ===
def test_repair_trailing_comma_in_array():
    """Bug 5: `[\"a\",]` 应被修复成 `[\"a\"]`。"""
    raw = '{"unresolved_questions": [],}'
    repaired = repair_changes_json(raw)
    import json as _json
    parsed = _json.loads(repaired)
    assert parsed == {"unresolved_questions": []}


def test_repair_trailing_comma_in_object():
    raw = '{"a": 1, "b": 2,}'
    repaired = repair_changes_json(raw)
    import json as _json
    parsed = _json.loads(repaired)
    assert parsed == {"a": 1, "b": 2}


def test_repair_trailing_comma_nested():
    raw = '{"x": [1, 2, 3,], "y": {"a": 1,},}'
    repaired = repair_changes_json(raw)
    import json as _json
    parsed = _json.loads(repaired)
    assert parsed == {"x": [1, 2, 3], "y": {"a": 1}}


def test_parse_changes_handles_trailing_comma_in_full_block():
    """Bug 5: 完整的合法 JSON + 末尾逗号应能被 parse_changes 处理。"""
    block = """<chapter_changes>
{
  "character_state_changes": [],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": [],
}
</chapter_changes>"""
    parsed, err = parse_changes(block)
    assert err is None
    assert parsed is not None
    assert "character_state_changes" in parsed


# === Bug 6: 多 block 取最后一个 ===
def test_extract_changes_block_uses_last_when_multiple():
    """Bug 6: 当 LLM 输出多个 <chapter_changes> 块，取最后一个（修正版）。"""
    chapter = """<chapter_changes>
{
  "importance": "BAD_ENUM_FIRST"
}
</chapter_changes>

中间是散文中提到的标签 <chapter_changes>foo</chapter_changes>

<chapter_changes>
{
  "importance": "important"
}
</chapter_changes>"""
    # 当前实现期望最后一个块：含合法 importance
    block = extract_changes_block(chapter)
    assert block is not None
    assert "important" in block
    assert "BAD_ENUM_FIRST" not in block


# === 已有功能继续工作 ===
def test_extract_changes_block_returns_first_match():
    chapter = """<chapter_changes>
{"a": 1}
</chapter_changes>"""
    block = extract_changes_block(chapter)
    assert block is not None
    assert '"a": 1' in block


def test_repair_removes_chinese_quotes():
    raw = "{「key」: 「value」}"
    repaired = repair_changes_json(raw)
    assert '"key"' in repaired
    assert '"value"' in repaired


def test_repair_single_quote_keys():
    raw = "{'key': 'value'}"
    repaired = repair_changes_json(raw)
    import json as _json
    parsed = _json.loads(repaired)
    assert parsed == {"key": "value"}
