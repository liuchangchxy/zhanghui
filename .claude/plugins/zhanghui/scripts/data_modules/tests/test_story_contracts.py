#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json

import pytest

from data_modules.story_contracts import (
    StoryContractPaths,
    merge_anti_patterns,
    merge_contract_layers,
    read_json_if_exists,
    persist_story_seed,
    persist_runtime_contracts,
    validated_user_constraint_metadata,
    collect_user_constraint_bindings,
)


def test_story_contract_paths_resolve_expected_locations(tmp_path):
    paths = StoryContractPaths.from_project_root(tmp_path)

    assert paths.root == tmp_path.resolve() / ".story-system"
    assert paths.master_json == paths.root / "MASTER_SETTING.json"
    assert paths.anti_patterns_json == paths.root / "anti_patterns.json"
    assert paths.chapter_json(7) == paths.root / "chapters" / "chapter_007.json"
    assert paths.gate_decision_json(7, "attempt-1") == paths.root / "reviews" / "gate-decisions" / "chapter_007" / "attempt-1.json"


def test_merge_contract_layers_preserves_locked_and_merges_append_only():
    merged = merge_contract_layers(
        {
            "locked": {"core_tone": "先压后爆"},
            "append_only": {"anti_patterns": ["配角连续抢戏超过 300 字"]},
            "override_allowed": {"scene_focus": "退婚当场反杀"},
        },
        {
            "append_only": {"anti_patterns": ["本章禁止解释性旁白"]},
            "override_allowed": {"chapter_focus": "退婚当场反杀"},
        },
    )

    assert merged["locked"]["core_tone"] == "先压后爆"
    assert merged["append_only"]["anti_patterns"] == [
        "配角连续抢戏超过 300 字",
        "本章禁止解释性旁白",
    ]
    assert merged["override_allowed"]["scene_focus"] == "退婚当场反杀"
    assert merged["override_allowed"]["chapter_focus"] == "退婚当场反杀"


def test_merge_anti_patterns_deduplicates_by_text():
    rows = merge_anti_patterns(
        [{"text": "打脸节奏不能缺补刀", "source_table": "题材与调性推理", "source_id": "GR-001"}],
        [{"text": "打脸节奏不能缺补刀", "source_table": "爽点与节奏", "source_id": "PA-002"}],
    )

    assert [item["text"] for item in rows] == ["打脸节奏不能缺补刀"]
    assert rows[0]["source_table"] == "题材与调性推理"


def test_read_json_if_exists_returns_none_for_missing_file(tmp_path):
    assert read_json_if_exists(tmp_path / "missing.json") is None


def test_read_json_if_exists_raises_value_error_with_path(tmp_path):
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        read_json_if_exists(bad_path)

    assert str(bad_path) in str(exc.value)


def test_read_json_if_exists_loads_valid_json(tmp_path):
    path = tmp_path / "payload.json"
    path.write_text(json.dumps({"ok": True}, ensure_ascii=False), encoding="utf-8")

    assert read_json_if_exists(path) == {"ok": True}


def test_user_constraint_metadata_is_validated_and_preserved_across_contract_layers(tmp_path):
    metadata = {"authority": "USER_EXPLICIT", "explicitness": "EXPLICIT",
                "constraint_id": "constraint-7", "source_ref": "user:request-7"}
    assert validated_user_constraint_metadata({"metadata": metadata}) == metadata
    assert validated_user_constraint_metadata({"metadata": {**metadata, "source_ref": " "}}) is None
    assert collect_user_constraint_bindings({"master": {"nodes": [{"metadata": metadata}]}}) == {
        "constraint-7": metadata
    }
    assert collect_user_constraint_bindings({"master": {"nodes": [
        {"metadata": metadata}, {"metadata": {**metadata, "source_ref": "other"}}
    ]}}) == {}
    master = {"locked": {"world_rule": {"metadata": metadata}}, "append_only": {}, "override_allowed": {}}
    chapter = {"locked": {"chapter_rule": {"metadata": metadata}}, "append_only": {}, "override_allowed": {}}
    merged = merge_contract_layers(master, chapter)
    assert merged["locked"]["world_rule"]["metadata"] == metadata
    assert merged["locked"]["chapter_rule"]["metadata"] == metadata

    persist_story_seed(tmp_path, {"meta": {"schema_version": "v1"}, "locked": master["locked"]},
                       {"meta": {"chapter": 2}, "locked": chapter["locked"]}, [])
    persist_runtime_contracts(tmp_path, 2,
        {"nodes": [{"id": "volume-node", "metadata": metadata}]},
        {"nodes": [{"id": "review-node", "metadata": metadata}]})
    paths = StoryContractPaths.from_project_root(tmp_path)
    for path, key in ((paths.master_json, "world_rule"), (paths.chapter_json(2), "chapter_rule"),
                      (paths.volume_json(1), "nodes"), (paths.review_json(2), "nodes")):
        payload = read_json_if_exists(path)
        node = payload[key] if key == "nodes" else payload["locked"][key]
        if key == "nodes":
            node = node[0]
        assert node["metadata"] == metadata
