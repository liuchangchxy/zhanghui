"""Tests for extended VALID_HOOK_TYPES (6 -> 11, with aliases).

See Task 7 of Phase 3 (plan script fixes).
"""
from scripts.story_craft import set_chapter_meta, VALID_HOOK_TYPES


def test_valid_hook_types_includes_aliases():
    """6 枚举扩到 11 种常用钩子，含别名。"""
    expected = {"悬念式", "悬念钩", "反转式", "反转钩",
                "情绪炸弹式", "情绪钩", "信息投放式",
                "留白式", "反讽式", "爽点钩", "危机钩"}
    assert expected.issubset(VALID_HOOK_TYPES)


def test_set_chapter_meta_accepts_xiwang_alias():
    """'悬念钩' 是 '悬念式' 的别名，应该可以入库。"""
    state = {}
    set_chapter_meta(state, chapter=1, hook_type="悬念钩")
    assert state["chapter_meta"]["1"]["hook_type"] == "悬念钩"
