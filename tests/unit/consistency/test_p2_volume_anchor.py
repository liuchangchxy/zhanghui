"""Tests for P2 Volume Anchor quota gate patch.

Source: original (TDD for Phase 2 Task 9)
Path in references: N/A
"""
from scripts.consistency.patches.p2_volume_anchor import P2VolumeAnchor
from scripts.consistency.core.patch_base import CheckContext, ApplyContext
from pathlib import Path

CLEAN_STATE = {
    "story_craft": {
        "volume_anchors": {
            "version": 1,
            "anchors": [
                {"volume": 1, "volume_name": "v1", "core_conflict": "c", "volume_end_climax": "e", "must_not_reveal": [], "must_achieve": [], "foreshadows_to_plant": [], "total_chapters": 10, "current_chapter": 0}
            ]
        }
    }
}

OVERRUN_STATE = {
    "story_craft": {
        "volume_anchors": {
            "version": 1,
            "anchors": [
                {"volume": 1, "volume_name": "v1", "core_conflict": "c", "volume_end_climax": "e", "must_not_reveal": ["秘密身份"], "must_achieve": ["觉醒"], "foreshadows_to_plant": [], "total_chapters": 10, "current_chapter": 5}
            ]
        }
    }
}


def _ctx(state, chapter=8, chapter_text=None):
    return CheckContext(project_root=Path("/tmp"), chapter_num=chapter, state=state, chapter_outline=None, previous_chapters=[], chapter_text=chapter_text)


def test_clean_anchor_passes():
    p = P2VolumeAnchor()
    # At chapter 8 with current_chapter 0 (i.e., 0% actual vs 80% expected) — but with no current_chapter anchor yet, won't check
    blockers = p.check(_ctx(CLEAN_STATE, chapter=8))
    # Actually current_chapter=0 means no chapters written → no deviation check fires (skipped)
    assert blockers == []


def test_anchor_progress_deviation_blocks():
    p = P2VolumeAnchor()
    # At chapter 8: expected progress 8/10=80%, actual current_chapter=5 → 50%. Deviation = 30% > 15% threshold
    blockers = p.check(_ctx(OVERRUN_STATE, chapter=8))
    assert any("进度偏离" in b.message or "进度" in b.message for b in blockers)


def test_anchor_must_not_reveal_blocks():
    p = P2VolumeAnchor()
    blockers = p.check(_ctx(OVERRUN_STATE, chapter=8, chapter_text="主角揭露了秘密身份"))
    assert any("must_not_reveal" in b.message or "秘密身份" in b.message for b in blockers)


def test_missing_anchor_field_fails():
    p = P2VolumeAnchor()
    blockers = p.check(_ctx({}, chapter=5))
    assert any("未初始化" in b.message or "volume_anchors" in b.message for b in blockers)


def test_apply_advances_current_chapter():
    p = P2VolumeAnchor()
    state = {
        "story_craft": {
            "volume_anchors": {
                "version": 1,
                "anchors": [
                    {"volume": 1, "current_chapter": 0, "total_chapters": 10}
                ]
            }
        }
    }
    ctx = ApplyContext(project_root=Path("/tmp"), chapter_num=5, state=state)
    p.apply(ctx)
    assert state["story_craft"]["volume_anchors"]["anchors"][0]["current_chapter"] == 5


def test_must_not_reveal_wrong_type_blocks():
    """Fix H: must_not_reveal must be list, not str/dict."""
    p = P2VolumeAnchor()
    state = {
        "story_craft": {
            "volume_anchors": {
                "version": 1,
                "anchors": [
                    {
                        "volume": 1, "total_chapters": 10, "current_chapter": 5,
                        "must_not_reveal": "秘密身份",  # str instead of list
                    }
                ]
            }
        }
    }
    blockers = p.check(_ctx(state, chapter=8, chapter_text="主角揭露了秘密身份"))
    assert any("must_not_reveal 必须是 list" in b.message for b in blockers)


def test_anchor_as_non_dict_does_not_crash():
    """If an anchor is not a dict, report it without crashing the whole loop."""
    p = P2VolumeAnchor()
    state = {
        "story_craft": {
            "volume_anchors": {
                "version": 1,
                "anchors": [
                    "not a dict",
                    {"volume": 1, "total_chapters": 10, "current_chapter": 0, "must_not_reveal": []}
                ]
            }
        }
    }
    blockers = p.check(_ctx(state, chapter=8))
    assert any("不是 dict" in b.message for b in blockers)


def test_load_error_reports_blocker():
    p = P2VolumeAnchor()
    state = {"_load_error": "OSError: locked"}
    blockers = p.check(_ctx(state, chapter=5))
    assert any("无法读取 state.json" in b.message for b in blockers)