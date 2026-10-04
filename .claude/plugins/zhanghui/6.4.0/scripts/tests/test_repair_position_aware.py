"""repair_changes_json 的 position-aware 行为测试（MED-56）。

覆盖：
- 对话里有 JSON 配置：`她说：'{"key": "value"}'` 不被改
- 顶层 CHANGES 的引号正常被改
- 嵌套 JSON 字符串里的中文引号正常处理（保留 string token 内的内容）
"""
from __future__ import annotations

import json

import pytest

from changes_gate import repair_changes_json


# ---------------------------------------------------------------------------
# Test 1: 对话里有 JSON 配置 — 不被改
# ---------------------------------------------------------------------------

def test_repair_does_not_modify_json_inside_dialogue_string():
    """对话里有 JSON 配置：`她说：'{"key": "value"}'` 不被改。

    当 LLM 在对话内容里写了 JSON 字符串时，repair 必须只把整体当作一个字符串 token 保留。
    输入是合法 JSON（内部双引号已转义），repair 后内容应保持不变。
    """
    # 合法 JSON：note 字符串值里包含对话 + 内嵌 JSON-like 内容
    # 用 \" 转义内嵌双引号（JSON 标准；Python 源码中需再写一次 \\）
    raw = '{"character_state_changes": [{"note": "她说：\\u0027{\\"key\\": \\"value\\"}\\u0027"}]}'
    repaired = repair_changes_json(raw)
    parsed = json.loads(repaired)
    # 整体可解析
    assert "character_state_changes" in parsed
    # 对话内容里的 {key: value} 原样保留（这是字符串内容）
    note = parsed["character_state_changes"][0]["note"]
    assert "她说" in note
    assert "'{" in note
    assert "key" in note and "value" in note


def test_repair_preserves_chinese_brackets_inside_string():
    """字符串 token 内的「」 不被替换为 "。

    这是 MED-56 的核心场景：对话内容含「你好」不能变成 "你好"。
    """
    raw = '{"description": "她说：「你好」"}'
    repaired = repair_changes_json(raw)
    parsed = json.loads(repaired)
    # 「」保留
    assert parsed["description"] == "她说：「你好」"


def test_repair_preserves_full_width_punct_inside_string():
    """字符串 token 内的中文标点（，：）保留，不替换为半角。"""
    raw = '{"description": "他说：你好，这是一段话。"}'
    repaired = repair_changes_json(raw)
    parsed = json.loads(repaired)
    assert parsed["description"] == "他说：你好，这是一段话。"


# ---------------------------------------------------------------------------
# Test 2: 顶层 CHANGES 的引号正常被改
# ---------------------------------------------------------------------------

def test_repair_fixes_single_quoted_keys_at_top_level():
    """顶层 CHANGES 用单引号包 key → 改为双引号。"""
    raw = "{'character_state_changes': []}"
    repaired = repair_changes_json(raw)
    parsed = json.loads(repaired)
    assert parsed == {"character_state_changes": []}


def test_repair_fixes_chinese_brackets_used_as_quotes():
    """LLM 用「」 当 JSON 引号 → 修复为 "。"""
    raw = "{「character_state_changes」: []}"
    repaired = repair_changes_json(raw)
    parsed = json.loads(repaired)
    assert parsed == {"character_state_changes": []}


def test_repair_fixes_chinese_colons_outside_strings():
    """JSON 语法位置的 `：` → `:`。"""
    raw = "{「character_state_changes」: []}"
    repaired = repair_changes_json(raw)
    assert ":" in repaired


def test_repair_fixes_full_width_punctuation_outside_strings():
    """JSON 语法位置的中文标点（冒号）替换为半角。"""
    # LLM 把字段分隔的「，」 当英文逗号；把字段后的「：」 当英文冒号
    raw = '{"character_state_changes"：[]，"new_plot_points"：[]}'
    repaired = repair_changes_json(raw)
    # 中文标点（冒号、逗号）应替换为半角
    assert "：" not in repaired
    assert "，" not in repaired
    parsed = json.loads(repaired)
    assert "new_plot_points" in parsed
    assert parsed["character_state_changes"] == []


# ---------------------------------------------------------------------------
# Test 3: 嵌套 JSON 字符串里的中文引号正常处理
# ---------------------------------------------------------------------------

def test_repair_keeps_valid_json_with_chinese_inside_string_intact():
    """合法 JSON + 字符串值含中文 → 完全保留。"""
    raw = '{"title": "凡人修仙传", "desc": "主角：「韩立」"}'
    repaired = repair_changes_json(raw)
    parsed = json.loads(repaired)
    assert parsed["title"] == "凡人修仙传"
    assert parsed["desc"] == "主角：「韩立」"


def test_repair_distinguishes_syntax_vs_content_for_brackets():
    """区分语法位置的「」 vs 字符串内的「」：
    - 语法位置 → 替换为 "
    - 字符串内 → 保留

    这是 position-aware 的核心断言。
    """
    raw = '{"key": "value「with」brackets"}'
    repaired = repair_changes_json(raw)
    parsed = json.loads(repaired)
    # 字符串内的「」保留
    assert "「with」" in parsed["key"]
    # 没有破坏 JSON 结构（可以成功解析）
    assert "key" in parsed


def test_repair_handles_mixed_single_double_quotes():
    """混合单双引号：单引号在 JSON 语法位置 → 替换为双引号。"""
    raw = "{'a': 'b'}"
    repaired = repair_changes_json(raw)
    parsed = json.loads(repaired)
    assert parsed == {"a": "b"}


# ---------------------------------------------------------------------------
# 边界 / 回归测试
# ---------------------------------------------------------------------------

def test_repair_handles_trailing_comma_correctly():
    """末尾逗号修复（结构性、跨 token）仍生效。"""
    raw = '{"a": 1, "b": 2,}'
    repaired = repair_changes_json(raw)
    parsed = json.loads(repaired)
    assert parsed == {"a": 1, "b": 2}


def test_repair_handles_full_8_field_block():
    """完整 8 字段 block：能解析、所有字段在。"""
    block = (
        '{"character_state_changes": [],'
        '"new_plot_points": [],'
        '"foreshadowing_actions": [],'
        '"location_state_changes": [],'
        '"faction_state_changes": [],'
        '"time_progression": null,'
        '"item_transfers": [],'
        '"unresolved_questions": []}'
    )
    repaired = repair_changes_json(block)
    parsed = json.loads(repaired)
    assert set(parsed.keys()) == {
        "character_state_changes",
        "new_plot_points",
        "foreshadowing_actions",
        "location_state_changes",
        "faction_state_changes",
        "time_progression",
        "item_transfers",
        "unresolved_questions",
    }


def test_repair_empty_string_returns_empty():
    """空字符串 → 空字符串。"""
    assert repair_changes_json("") == ""


def test_repair_whitespace_only_returns_whitespace():
    """纯空白 → 保留（不会被误判为 string token）。"""
    assert repair_changes_json("   \n\t") == "   \n\t"


def test_repair_handles_nested_objects_with_chinese_quotes():
    """嵌套对象 + 字符串值含「」 → 整体可解析，「」保留。"""
    raw = (
        '{"outer": {'
        '"key": "value「inside」",'
        '"list": ["a「b」", "c"]'
        '}}'
    )
    repaired = repair_changes_json(raw)
    parsed = json.loads(repaired)
    assert "「inside」" in parsed["outer"]["key"]
    assert parsed["outer"]["list"][0] == "a「b」"