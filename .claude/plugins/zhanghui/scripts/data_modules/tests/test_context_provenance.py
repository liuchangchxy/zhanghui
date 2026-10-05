from __future__ import annotations

import pytest

from data_modules.context_provenance import ContextItem, build_governed_context, classify_rag_hit, resolve_fact_items


def item(value, role, chapter, source, ref):
    return ContextItem(
        content=value,
        semantic_role=role,
        source_role=source,
        source_ref=ref,
        chapter=chapter,
        provenance_status="verified" if source == "COMMIT" else "unverified",
        fact_key=("entity", "realm"),
    )


def test_commit_suppresses_conflicting_legacy_and_keeps_diagnostic():
    selected, diagnostics = resolve_fact_items([
        item("筑基", "CANON", 20, "COMMIT", "commit:20"),
        item("金丹", "UNKNOWN", 0, "LEGACY", "entity:xiaoyan"),
    ])

    assert [x.content for x in selected] == ["筑基"]
    assert selected[0].evidence == ["commit:20"]
    assert diagnostics[0]["type"] == "source_conflict"
    assert diagnostics[0]["suppressed"][0]["source_ref"] == "entity:xiaoyan"


def test_latest_chapter_fact_beats_historical_retrieval():
    selected, diagnostics = resolve_fact_items([
        item("炼气", "CANON", 5, "COMMIT", "commit:5"),
        item("筑基", "CANON", 20, "COMMIT", "commit:20"),
        item("炼气", "UNKNOWN", 5, "RETRIEVAL", "vector:old"),
    ])

    assert len(selected) == 1
    assert selected[0].content == "筑基"
    assert selected[0].chapter == 20
    assert any(row["type"] == "historical_fact" for row in diagnostics)


def test_identical_projection_is_deduplicated_with_all_evidence():
    selected, diagnostics = resolve_fact_items([
        item("筑基", "CANON", 20, "COMMIT", "commit:20"),
        item("筑基", "CANON", 20, "PROJECTION", "state:20"),
        item("筑基", "CANON", 20, "PROJECTION", "memory:20"),
    ])

    assert len(selected) == 1
    assert selected[0].evidence == ["commit:20", "state:20", "memory:20"]
    assert sum(row["type"] == "duplicate_suppressed" for row in diagnostics) == 2


def test_conflicting_same_chapter_verified_canon_fails_fast():
    with pytest.raises(ValueError, match="canonical fact conflict"):
        resolve_fact_items([
            item("筑基", "CANON", 20, "COMMIT", "commit:20a"),
            item("金丹", "CANON", 20, "COMMIT", "commit:20b"),
        ])


def test_projection_never_becomes_canon_without_matching_commit():
    selected, diagnostics = resolve_fact_items([
        item("筑基", "UNKNOWN", 20, "PROJECTION", "state:20"),
    ])

    assert selected[0].semantic_role == "UNKNOWN"
    assert diagnostics == []


def test_governed_context_uses_commit_over_state_and_marks_stale(tmp_path):
    commits = tmp_path / ".story-system" / "commits"
    commits.mkdir(parents=True)
    (commits / "chapter_020.commit.json").write_text(
        '{"meta":{"chapter":20,"status":"accepted"},"provenance":{"write_fact_role":"chapter_commit"},"extraction_result":{"state_deltas":[{"entity_id":"A","field":"realm","new":"筑基"}],"accepted_events":[],"entity_deltas":[]}}',
        encoding="utf-8",
    )
    bundle = build_governed_context(
        project_root=tmp_path,
        chapter=21,
        state={"progress": {"current_chapter": 19}, "entity_state": {"A": {"realm": "金丹"}}},
        source_sections={"outline": "第21章计划 A 死亡"},
    )

    assert [item["content"]["value"] for item in bundle["canon"]] == ["筑基"]
    assert bundle["intent"][0]["semantic_role"] == "INTENT"
    assert bundle["snapshot"]["latest_commit"]["chapter"] == 20
    assert {row["type"] for row in bundle["diagnostics"]} >= {"stale_projection", "source_conflict"}


def test_governed_context_splits_intent_craft_and_rag_reference(tmp_path):
    bundle = build_governed_context(
        project_root=tmp_path,
        chapter=21,
        state={},
        source_sections={
            "outline": "计划未来发生的事",
            "writing_guidance": {"pacing": "更快"},
            "rag_assist": {"hits": [{"score": 0.99, "source_file": "unknown"}]},
        },
    )

    assert bundle["intent"][0]["semantic_role"] == "INTENT"
    assert bundle["craft"][0]["semantic_role"] == "CRAFT"
    assert bundle["reference"][0]["semantic_role"] == "OPERATIONAL"
    assert bundle["reference"][0]["provenance_status"] == "retrieval_only"
    assert bundle["diagnostics"][0]["type"] == "missing_canonical_source"


def test_promise_event_is_canon_while_payoff_target_is_intent(tmp_path):
    commits = tmp_path / ".story-system" / "commits"
    commits.mkdir(parents=True)
    (commits / "chapter_003.commit.json").write_text(
        '{"meta":{"chapter":3,"status":"accepted"},"provenance":{"write_fact_role":"chapter_commit"},"extraction_result":{"accepted_events":[{"event_id":"p1","event_type":"promise_created","subject":"A","payload":{"text":"保护B"}}],"state_deltas":[],"entity_deltas":[]}}',
        encoding="utf-8",
    )
    bundle = build_governed_context(
        project_root=tmp_path,
        chapter=4,
        state={},
        source_sections={"promise_intent": {"promise_id": "p1", "payoff_chapter": 30}},
    )
    assert bundle["canon"][0]["content"]["event_type"] == "promise_created"
    assert bundle["intent"][0]["content"]["payoff_chapter"] == 30


def test_future_planned_death_does_not_become_a_canon_fact(tmp_path):
    commits = tmp_path / ".story-system" / "commits"
    commits.mkdir(parents=True)
    (commits / "chapter_020.commit.json").write_text(
        '{"meta":{"chapter":20,"status":"accepted"},"provenance":{"write_fact_role":"chapter_commit"},"extraction_result":{"state_deltas":[{"entity_id":"A","field":"status","new":"alive"}],"accepted_events":[],"entity_deltas":[]}}',
        encoding="utf-8",
    )
    bundle = build_governed_context(
        project_root=tmp_path,
        chapter=21,
        state={},
        source_sections={"outline": "第21章计划让A死亡"},
    )
    assert bundle["canon"][0]["content"]["value"] == "alive"
    assert "第21章计划让A死亡" in bundle["intent"][0]["content"]


def test_entity_fields_require_commit_evidence_individually(tmp_path):
    commits = tmp_path / ".story-system" / "commits"
    commits.mkdir(parents=True)
    (commits / "chapter_003.commit.json").write_text(
        '{"meta":{"chapter":3,"status":"accepted"},"provenance":{"write_fact_role":"chapter_commit"},"extraction_result":{"entity_deltas":[{"entity_id":"A","canonical_name":"阿甲","patch":{"realm":"筑基"}}],"state_deltas":[],"accepted_events":[]}}',
        encoding="utf-8",
    )
    bundle = build_governed_context(
        project_root=tmp_path,
        chapter=4,
        state={"progress": {"current_chapter": 3}, "entity_state": {"A": {"realm": "金丹", "secret": "旧传闻"}}},
        source_sections={},
    )
    canon_fields = {item["content"]["field"]: item["content"]["value"] for item in bundle["canon"]}
    unknown = [item["content"] for item in bundle["reference"] if item["semantic_role"] == "UNKNOWN"]
    assert canon_fields["realm"] == "筑基"
    assert canon_fields["canonical_name"] == "阿甲"
    assert any(item.get("field") == "secret" for item in unknown)
    assert any(row["type"] == "source_conflict" for row in bundle["diagnostics"])


def test_matching_memory_projection_deduplicates_with_commit_evidence(tmp_path):
    commits = tmp_path / ".story-system" / "commits"
    commits.mkdir(parents=True)
    (commits / "chapter_020.commit.json").write_text(
        '{"meta":{"chapter":20,"status":"accepted"},"provenance":{"write_fact_role":"chapter_commit"},"extraction_result":{"state_deltas":[{"entity_id":"A","field":"realm","new":"筑基"}],"accepted_events":[],"entity_deltas":[]}}',
        encoding="utf-8",
    )
    bundle = build_governed_context(
        project_root=tmp_path,
        chapter=21,
        state={},
        source_sections={"memory_pack": {"semantic_memory": [{
            "id": "m1", "category": "character_state", "subject": "A", "field": "realm",
            "value": "筑基", "source_chapter": 20, "evidence": ["state_change:A:realm:20"],
        }]}},
    )
    assert len(bundle["canon"]) == 1
    assert bundle["canon"][0]["evidence"] == ["commit:20", "state_change:A:realm:20", "memory:m1"]
    assert any(row["type"] == "duplicate_suppressed" for row in bundle["diagnostics"])


def test_memory_without_evidence_stays_unknown_reference(tmp_path):
    bundle = build_governed_context(
        project_root=tmp_path,
        chapter=2,
        state={},
        source_sections={"memory_pack": {"semantic_memory": [{
            "id": "legacy-1", "category": "story_fact", "subject": "A", "value": "dead", "evidence": [],
        }]}},
    )
    assert bundle["canon"] == []
    assert bundle["reference"][0]["semantic_role"] == "UNKNOWN"
    assert bundle["reference"][0]["source_ref"] == "memory:legacy-1"


def test_relationship_projection_conflict_is_suppressed(tmp_path):
    commits = tmp_path / ".story-system" / "commits"
    commits.mkdir(parents=True)
    (commits / "chapter_003.commit.json").write_text(
        '{"meta":{"chapter":3,"status":"accepted"},"provenance":{"write_fact_role":"chapter_commit"},"extraction_result":{"accepted_events":[{"event_id":"r1","event_type":"relationship_changed","subject":"A","payload":{"from_entity":"A","to_entity":"B","relationship_type":"敌对"}}],"state_deltas":[],"entity_deltas":[]}}',
        encoding="utf-8",
    )
    bundle = build_governed_context(
        project_root=tmp_path,
        chapter=4,
        state={},
        source_sections={"memory_pack": {"episodic_memory": [{
            "source": "relationship", "chapter": 3,
            "content": {"from_entity": "A", "to_entity": "B", "type": "盟友"},
        }]}},
    )
    relationships = [row["content"] for row in bundle["canon"] if "relationship" in row["content"]]
    assert len(relationships) == 1
    assert relationships[0]["relationship"] == "敌对"
    assert any(row["type"] == "source_conflict" for row in bundle["diagnostics"])


def test_structured_intent_canon_ambiguity_is_diagnostic_not_canon_failure(tmp_path):
    commits = tmp_path / ".story-system" / "commits"
    commits.mkdir(parents=True)
    (commits / "chapter_020.commit.json").write_text(
        '{"meta":{"chapter":20,"status":"accepted"},"provenance":{"write_fact_role":"chapter_commit"},"extraction_result":{"state_deltas":[{"entity_id":"A","field":"status","new":"alive"}],"accepted_events":[],"entity_deltas":[]}}',
        encoding="utf-8",
    )
    bundle = build_governed_context(
        project_root=tmp_path,
        chapter=21,
        state={},
        source_sections={"intent_facts": [{
            "fact_key": ["A", "status"], "content": {"entity_id": "A", "field": "status", "value": "dead"},
            "source_ref": "chapter-contract:21", "source_role": "CONTRACT",
        }]},
    )
    assert bundle["canon"][0]["content"]["value"] == "alive"
    assert any(row["type"] == "intent_canon_ambiguity" for row in bundle["diagnostics"])


def test_conflicting_authoritative_intents_are_exposed_without_failing_canon(tmp_path):
    bundle = build_governed_context(
        project_root=tmp_path,
        chapter=21,
        state={},
        source_sections={"intent_facts": [
            {"fact_key": ["A", "target"], "content": "death in chapter 21", "source_ref": "chapter-outline", "source_role": "OUTLINE"},
            {"fact_key": ["A", "target"], "content": "survival in chapter 21", "source_ref": "chapter-contract", "source_role": "CONTRACT"},
        ]},
    )
    assert len(bundle["intent"]) == 2
    assert any(row["type"] == "intent_conflict" for row in bundle["diagnostics"])


def test_relationship_commit_suppresses_conflicting_legacy_row():
    selected, diagnostics = resolve_fact_items([
        ContextItem({"relationship": "敌对"}, "CANON", "COMMIT", "commit:12", chapter=12, fact_key=("relationship", "A", "B")),
        ContextItem({"relationship": "盟友"}, "UNKNOWN", "LEGACY", "relationship:A:B", fact_key=("relationship", "A", "B")),
    ])
    assert len(selected) == 1
    assert selected[0].content["relationship"] == "敌对"
    assert diagnostics[0]["type"] == "source_conflict"


def test_rag_similarity_does_not_grant_authority(tmp_path):
    hit = classify_rag_hit(tmp_path, {"source_file": "unknown", "score": 0.999, "chunk_id": "c1", "chapter": 5})
    assert hit["semantic_role"] == "UNKNOWN"
    assert hit["similarity_is_authority"] is False
    assert hit["presentation_role"] == "REFERENCE"


def test_rag_commit_lineage_requires_a_matching_accepted_commit(tmp_path):
    commits = tmp_path / ".story-system" / "commits"
    commits.mkdir(parents=True)
    (commits / "chapter_005.commit.json").write_text(
        '{"meta":{"chapter":5,"status":"accepted"},"provenance":{"write_fact_role":"chapter_commit"}}',
        encoding="utf-8",
    )
    hit = classify_rag_hit(tmp_path, {
        "source_file": "commit:chapter_005", "chunk_id": "c5", "chapter": 5, "score": 0.98,
    })
    assert hit["semantic_role"] == "CANON"
    assert hit["presentation_role"] == "REFERENCE"
    assert hit["provenance_status"] == "commit_evidenced"
    same_target = classify_rag_hit(tmp_path, {
        "source_file": "commit:chapter_005", "chunk_id": "c5", "chapter": 5, "score": 0.98,
    }, target_chapter=5)
    assert same_target["semantic_role"] == "UNKNOWN"
