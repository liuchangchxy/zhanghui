"""Tests for extended VALID_HOOK_TYPES (6 -> 11, with aliases).

See Task 7 of Phase 3 (plan script fixes).
"""
import pytest

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


def test_allowed_fields_includes_outline_fields():
    """plan 提的字段都能入库。"""
    from scripts.story_craft import ALLOWED_CHAPTER_META_FIELDS
    required = {
        "CBN", "CPNs", "CEN",
        "must_cover", "forbidden",
        "strand", "coolpoint",
        "time_anchor", "villain_tier",
    }
    missing = required - ALLOWED_CHAPTER_META_FIELDS
    assert not missing, f"缺少字段: {missing}"


def test_set_chapter_meta_accepts_cbn():
    state = {}
    set_chapter_meta(state, chapter=1, CBN="主角突破境界")
    assert state["chapter_meta"]["1"]["CBN"] == "主角突破境界"


def test_phase10_story_craft_classification_is_field_level_and_exact():
    from scripts.story_craft import classify_story_craft_field

    assert classify_story_craft_field("story_craft.foreshadow_chain.expected_payoff_chapter") == "INTENT"
    assert classify_story_craft_field("story_craft.foreshadow_chain[].expected_payoff_chapter") == "INTENT"
    assert classify_story_craft_field("story_craft.foreshadow_chain.buried_chapter") == "UNKNOWN"
    assert classify_story_craft_field("story_craft.foreshadow_chain.buried_chapter",
                                      accepted_evidence_linked=True) == "DERIVED_REFERENCE"
    assert classify_story_craft_field("story_craft.foreshadow_chain.payoff_quality") == "CRAFT"
    assert classify_story_craft_field("story_craft.timed_locks.deadline_chapter") == "INTENT"
    assert classify_story_craft_field("story_craft.timed_locks.fulfilled_chapter") == "UNKNOWN"
    assert classify_story_craft_field("story_craft.character_arc.transformation") == "INTENT"
    assert classify_story_craft_field("story_craft.character_arc.evaluation") == "CRAFT"
    assert classify_story_craft_field("story_craft.thematic_echoes.premise") == "INTENT"
    assert classify_story_craft_field("story_craft.thematic_echoes.manifestation") == "UNKNOWN"
    assert classify_story_craft_field("story_craft.thematic_echoes[].echoes[].manifestation",
                                      accepted_evidence_linked=True) == "DERIVED_REFERENCE"
    assert classify_story_craft_field("story_craft.rhythm_curve.history") == "CRAFT"
    assert classify_story_craft_field("story_craft.unrecognized.nested") == "UNKNOWN"


def test_phase10_chapter_meta_keeps_craft_intent_reference_and_unknown_separate():
    from scripts.story_craft import classify_story_craft_field, classify_mixed_metadata

    assert classify_story_craft_field("chapter_meta.hook_type") == "CRAFT"
    assert classify_story_craft_field("chapter_meta.beat_position") == "CRAFT"
    assert classify_story_craft_field("chapter_meta.must_cover") == "INTENT"
    assert classify_story_craft_field("chapter_meta.foreshadow_paid_off") == "UNKNOWN"
    assert classify_story_craft_field("chapter_meta.foreshadow_paid_off", accepted_evidence_linked=True) == "DERIVED_REFERENCE"
    assert classify_story_craft_field("chapter_meta.title") == "DERIVED_REFERENCE"
    assert classify_story_craft_field("chapter_meta.word_count") == "DERIVED_REFERENCE"
    assert classify_story_craft_field("chapter_meta.summary") == "DERIVED_REFERENCE"
    assert classify_story_craft_field("chapter_meta.2.hook_type") == "CRAFT"
    result = classify_mixed_metadata({"hook_type": "悬念式", "must_cover": ["node"],
                                      "characters": ["person"], "custom": {"flag": True}},
                                    container="chapter_meta")
    assert result["fields"] == {"chapter_meta.hook_type": "CRAFT",
                                "chapter_meta.must_cover": "INTENT",
                                "chapter_meta.characters": "UNKNOWN",
                                "chapter_meta.custom": "UNKNOWN"}
    assert result["unknown"]["chapter_meta.custom"] == {"flag": True}


def test_accepted_commit_containment_does_not_promote_chapter_meta_to_canon():
    from scripts.story_craft import classify_mixed_metadata

    commit = {"meta": {"status": "accepted", "chapter": 2},
              "extraction_result": {"chapter_meta": {
                  "hook_type": "悬念式", "beat_position": "midpoint",
                  "must_cover": ["node-a"], "foreshadow_paid_off": ["FS-1"],
                  "title": "章节标题", "word_count": 1200,
                  "summary": "本章概要", "characters": ["人物"], "location": "城门",
              }}}
    result = classify_mixed_metadata(commit["extraction_result"]["chapter_meta"],
                                     container="chapter_meta")
    assert commit["meta"]["status"] == "accepted"
    assert result["fields"]["chapter_meta.hook_type"] == "CRAFT"
    assert result["fields"]["chapter_meta.beat_position"] == "CRAFT"
    assert result["fields"]["chapter_meta.must_cover"] == "INTENT"
    assert result["fields"]["chapter_meta.foreshadow_paid_off"] == "UNKNOWN"
    assert result["fields"]["chapter_meta.title"] == "DERIVED_REFERENCE"
    assert result["fields"]["chapter_meta.word_count"] == "DERIVED_REFERENCE"
    assert result["fields"]["chapter_meta.summary"] == "DERIVED_REFERENCE"
    assert result["fields"]["chapter_meta.characters"] == "UNKNOWN"
    assert result["fields"]["chapter_meta.location"] == "UNKNOWN"


def test_phase10_malformed_mixed_metadata_is_preserved_with_diagnostic():
    from scripts.story_craft import classify_mixed_metadata

    malformed = ["raw", {"unexpected": "shape"}]
    result = classify_mixed_metadata(malformed, container="story_craft")
    assert result["unknown"]["$value"] == malformed
    assert result["diagnostics"] == ["malformed_story_craft"]


def test_story_craft_occurrence_mutations_do_not_claim_canon_linkage():
    from scripts.story_craft import (add_foreshadow, payoff_foreshadow, add_timed_lock,
                                     fulfill_timed_lock, classify_story_craft_field)

    state = {"story_craft": {"foreshadow_chain": [], "timed_locks": [], "thematic_echoes": []}}
    add_foreshadow(state, {"id": "FS-1", "type": "物谶", "depth": "表层"})
    payoff_foreshadow(state, "FS-1", 7, "quality")
    assert "occurrence_evidence_status" not in state["story_craft"]["foreshadow_chain"][0]
    add_timed_lock(state, {"id": "TL-1", "description": "约定", "deadline_chapter": 7})
    fulfill_timed_lock(state, "TL-1", 7)
    assert "occurrence_evidence_status" not in state["story_craft"]["timed_locks"][0]
    assert not hasattr(__import__("scripts.story_craft", fromlist=["x"]), "link_story_craft_occurrence")
    assert classify_story_craft_field("story_craft.foreshadow_chain.0.payoff_chapter") == "UNKNOWN"
    assert classify_story_craft_field("story_craft.foreshadow_chain.0.payoff_chapter",
                                      accepted_evidence_linked=True) == "DERIVED_REFERENCE"
