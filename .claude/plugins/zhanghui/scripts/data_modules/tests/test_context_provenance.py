from __future__ import annotations

import hashlib
import json

import pytest

from data_modules.context_provenance import ContextItem, build_governed_context, classify_rag_hit, resolve_fact_items


def valid_commit(chapter=1, status="accepted", *, extraction=None, **overrides):
    payload = {
        "meta": {"schema_version": "story-system/v1", "chapter": chapter, "status": status},
        "provenance": {"write_fact_role": "chapter_commit"},
        "review_result": {"blocking_count": 1 if status == "rejected" else 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": ["x"] if status == "rejected" else [], "extra_nodes": []},
        "disambiguation_result": {"pending": ["x"] if status == "rejected" else []},
        "extraction_result": extraction or {"accepted_events": [], "state_deltas": [], "entity_deltas": []},
    }
    payload.update(overrides)
    return payload


def write_commit(root, chapter, payload, filename=None):
    commits = root / ".story-system" / "commits"
    commits.mkdir(parents=True, exist_ok=True)
    path = commits / (filename or f"chapter_{chapter:03d}.commit.json")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


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


@pytest.mark.parametrize("case", [
    "missing_outer_schema",
    "wrong_schema",
    "filename_meta_mismatch",
    "invalid_extraction",
    "invalid_review",
    "invalid_fulfillment",
    "invalid_disambiguation",
    "noncanonical_filename",
])
def test_malformed_canonical_commit_blocks_context_and_rebuild(tmp_path, case):
    payload = valid_commit(1, extraction={"entity_deltas": [{"entity_id": "A", "patch": {"realm": "金丹"}}], "accepted_events": [], "state_deltas": []})
    filename = None
    if case == "missing_outer_schema":
        payload["meta"].pop("schema_version")
    elif case == "wrong_schema":
        payload["meta"]["schema_version"] = "story-system/v999"
    elif case == "filename_meta_mismatch":
        payload["meta"]["chapter"] = 2
    elif case == "invalid_extraction":
        payload["extraction_result"] = {"entity_deltas": [], "accepted_events": []}
    elif case == "invalid_review":
        payload["review_result"] = {"blocking_count": "zero"}
    elif case == "invalid_fulfillment":
        payload["fulfillment_result"] = {"planned_nodes": []}
    elif case == "invalid_disambiguation":
        payload["disambiguation_result"] = {"pending": "none"}
    elif case == "noncanonical_filename":
        filename = "chapter_01.commit.json"
    write_commit(tmp_path, 1, payload, filename=filename)
    protected = []
    for relative, raw in (
        (".webnovel/state.json", b'{"progress":{"current_chapter":0}}'),
        (".webnovel/index.db", b"index sentinel"),
        (".webnovel/project_memory.json", b"memory sentinel"),
        (".webnovel/vectors.db", b"vectors sentinel"),
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        protected.append((path, raw))
    commit_path = tmp_path / ".story-system" / "commits" / (filename or "chapter_001.commit.json")
    original_commit_bytes = commit_path.read_bytes()

    with pytest.raises((ValueError, RuntimeError), match="invalid|canonical|commit"):
        build_governed_context(project_root=tmp_path, chapter=2, state={}, source_sections={})

    from data_modules.projection_rebuild import ProjectionRebuildError, discover_and_validate_commits
    with pytest.raises(ProjectionRebuildError):
        discover_and_validate_commits(tmp_path)
    assert commit_path.read_bytes() == original_commit_bytes
    assert all(path.read_bytes() == raw for path, raw in protected)


def test_accepted_rejected_future_and_target_commits_share_fact_and_snapshot_boundary(tmp_path):
    accepted = write_commit(tmp_path, 1, valid_commit(1, extraction={"entity_deltas": [{"entity_id": "A", "patch": {"realm": "金丹"}}], "accepted_events": [], "state_deltas": []}))
    write_commit(tmp_path, 2, valid_commit(2, "rejected", extraction={"entity_deltas": [{"entity_id": "A", "patch": {"realm": "元婴"}}], "accepted_events": [], "state_deltas": []}))
    write_commit(tmp_path, 3, valid_commit(3))
    write_commit(tmp_path, 20, valid_commit(20, extraction={"entity_deltas": [{"entity_id": "A", "patch": {"realm": "化神"}}], "accepted_events": [], "state_deltas": []}))

    bundle = build_governed_context(project_root=tmp_path, chapter=3, state={}, source_sections={})
    assert [(row["chapter"], row["content"]["value"]) for row in bundle["canon"]] == [(1, "金丹")]
    assert bundle["snapshot"]["latest_commit"] == {"chapter": 1, "sha256": hashlib.sha256(accepted.read_bytes()).hexdigest()}


def test_valid_accepted_commit_is_loaded_for_next_chapter(tmp_path):
    path = write_commit(tmp_path, 1, valid_commit(1, extraction={"entity_deltas": [{"entity_id": "A", "patch": {"realm": "金丹"}}], "accepted_events": [], "state_deltas": []}))
    bundle = build_governed_context(project_root=tmp_path, chapter=2, state={}, source_sections={})
    assert bundle["canon"][0]["content"]["value"] == "金丹"
    assert bundle["canon"][0]["provenance_status"] == "verified"
    assert bundle["snapshot"]["latest_commit"] == {"chapter": 1, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_projection_never_becomes_canon_without_matching_commit():
    selected, diagnostics = resolve_fact_items([
        item("筑基", "UNKNOWN", 20, "PROJECTION", "state:20"),
    ])

    assert selected[0].semantic_role == "UNKNOWN"
    assert diagnostics == []


def test_governed_context_uses_commit_over_state_and_marks_stale(tmp_path):
    write_commit(tmp_path, 20, valid_commit(20, extraction={"state_deltas": [{"entity_id": "A", "field": "realm", "new": "筑基"}], "accepted_events": [], "entity_deltas": []}))
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
    write_commit(tmp_path, 3, valid_commit(3, extraction={"accepted_events": [{"event_id": "p1", "event_type": "promise_created", "subject": "A", "payload": {"text": "保护B"}}], "state_deltas": [], "entity_deltas": []}))
    bundle = build_governed_context(
        project_root=tmp_path,
        chapter=4,
        state={},
        source_sections={"promise_intent": {"promise_id": "p1", "payoff_chapter": 30}},
    )
    event = next(row for row in bundle["canon"]
                 if row["content"].get("event_type") == "promise_created")
    assert event["semantic_role"] == "CANON"
    derived = next(row for row in bundle["intent"] if row["semantic_class"] == "CANON_DERIVED_OBLIGATION")
    assert derived["content"]["status"] == "active"
    assert derived["content"]["source_event_id"] == "p1"
    assert derived["source_identity"] == "p1"
    assert derived["chapter"] == 3
    plan = next(row for row in bundle["intent"] if row["semantic_class"] == "PLANNER_INTENT")
    assert plan["content"]["payoff_chapter"] == 30
    assert derived["source_relationship"] == "DERIVED_RUNTIME_COPY"


def test_future_planned_death_does_not_become_a_canon_fact(tmp_path):
    write_commit(tmp_path, 20, valid_commit(20, extraction={"state_deltas": [{"entity_id": "A", "field": "status", "new": "alive"}], "accepted_events": [], "entity_deltas": []}))
    bundle = build_governed_context(
        project_root=tmp_path,
        chapter=21,
        state={},
        source_sections={"outline": "第21章计划让A死亡"},
    )
    assert bundle["canon"][0]["content"]["value"] == "alive"
    assert "第21章计划让A死亡" in bundle["intent"][0]["content"]


def test_entity_fields_require_commit_evidence_individually(tmp_path):
    write_commit(tmp_path, 3, valid_commit(3, extraction={"entity_deltas": [{"entity_id": "A", "canonical_name": "阿甲", "patch": {"realm": "筑基"}}], "state_deltas": [], "accepted_events": []}))
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
    write_commit(tmp_path, 20, valid_commit(20, extraction={"state_deltas": [{"entity_id": "A", "field": "realm", "new": "筑基"}], "accepted_events": [], "entity_deltas": []}))
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
    write_commit(tmp_path, 3, valid_commit(3, extraction={"accepted_events": [{"event_id": "r1", "event_type": "relationship_changed", "subject": "A", "payload": {"from_entity": "A", "to_entity": "B", "relationship_type": "敌对"}}], "state_deltas": [], "entity_deltas": []}))
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
    write_commit(tmp_path, 20, valid_commit(20, extraction={"state_deltas": [{"entity_id": "A", "field": "status", "new": "alive"}], "accepted_events": [], "entity_deltas": []}))
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


def test_stale_runtime_copy_is_diagnostic_not_authoritative_intent_conflict(tmp_path):
    bundle = build_governed_context(
        project_root=tmp_path, chapter=21, state={}, source_sections={"intent_facts": [
            {"fact_key": ["A", "target"], "content": "death", "source_ref": "outline:vol1",
             "source_identity": "outline:vol1", "source_relationship": "AUTHORITATIVE_SOURCE", "scope": "chapter:21"},
            {"fact_key": ["A", "target"], "content": "survival", "source_ref": "brief:21",
             "source_identity": "outline:vol1", "source_relationship": "DERIVED_RUNTIME_COPY", "scope": "chapter:21"},
        ]})
    assert any(row["type"] == "stale_runtime_copy" for row in bundle["diagnostics"])
    assert not any(row["type"] == "intent_conflict" for row in bundle["diagnostics"])


def test_context_splits_story_craft_and_chapter_meta_by_field(tmp_path):
    bundle = build_governed_context(project_root=tmp_path, chapter=8, state={
        "story_craft": {"foreshadow_chain": [{"id": "f1", "expected_payoff_chapter": 12,
                                               "payoff_quality": "strong"}],
                        "rhythm_curve": {"chapters_since_peak": 5}},
        "chapter_meta": {"8": {"must_cover": ["promise"], "hook_type": "reveal", "future_flag": True}},
    }, source_sections={})
    assert any(row["semantic_class"] == "PLANNER_INTENT" and
               any(field["path"].endswith("expected_payoff_chapter") for field in row["content"])
               for row in bundle["intent"])
    assert any(row["semantic_class"] == "CRAFT_RECOMMENDATION" and
               any(field == "hook_type" for field in row["content"])
               for row in bundle["craft"])
    assert any(row["semantic_role"] == "UNKNOWN" and "future_flag" in row["content"]
               for row in bundle["reference"])


def test_planner_promise_and_volume_items_have_owner_and_stable_identity(tmp_path):
    bundle = build_governed_context(project_root=tmp_path, chapter=8, state={
        "project_info": {"promise_ledger": [{"id": "P7", "status": "pending"}]},
        "volumes": [{"index": 2, "title": "second volume"}],
    }, source_sections={})
    promise = next(row for row in bundle["intent"] if row["source_identity"] == "P7")
    volume = next(row for row in bundle["intent"] if row["owner"] == "volumes")
    assert promise["semantic_class"] == "PLANNER_INTENT"
    assert promise["source_relationship"] == "AUTHORITATIVE_SOURCE"
    assert volume["scope"] == "volume:2"


def test_commit_carried_mixed_chapter_meta_is_not_a_canon_container(tmp_path):
    write_commit(tmp_path, 1, valid_commit(1, extraction={
        "entity_deltas": [], "state_deltas": [], "accepted_events": [],
        "chapter_meta": {"hook_type": "悬念式", "must_cover": ["target"], "title": "chapter title"},
    }))
    bundle = build_governed_context(project_root=tmp_path, chapter=2, state={}, source_sections={})
    assert bundle["canon"] == []
    assert any(row["content"].get("field") == "hook_type" for row in bundle["craft"])
    plan = next(row for row in bundle["intent"] if row["content"].get("field") == "must_cover")
    assert plan["source_relationship"] == "DERIVED_RUNTIME_COPY"
    assert any(row["content"].get("field") == "title" for row in bundle["reference"])


def test_craft_recommendation_difference_does_not_rewrite_intent(tmp_path):
    bundle = build_governed_context(project_root=tmp_path, chapter=20, state={}, source_sections={
        "intent_facts": [{"fact_key": ["promise:P1", "payoff_chapter"], "content": 20,
                          "source_ref": "outline:vol1", "scope": "chapter:20"}],
        "craft_facts": [{"fact_key": ["promise:P1", "payoff_chapter"], "content": 18,
                         "source_ref": "rhythm-advisor", "scope": "chapter:20"}],
    })
    assert next(row for row in bundle["intent"] if row.get("fact_key"))["content"] == 20
    assert next(row for row in bundle["craft"] if row.get("fact_key"))["content"] == 18
    diagnostic = next(row for row in bundle["diagnostics"] if row["type"] == "craft_recommendation_differs_from_intent")
    assert diagnostic["blocking"] is False


def test_unlinked_outline_and_generated_contract_are_diagnosed_without_guessing(tmp_path):
    bundle = build_governed_context(project_root=tmp_path, chapter=20, state={}, source_sections={
        "outline": "chapter 20 authored outline", "story_contract": {"chapter": 20, "goal": "generated copy"},
    })
    assert len(bundle["intent"]) == 2
    diagnostic = next(row for row in bundle["diagnostics"] if row["type"] == "source_relationship_unresolved")
    assert diagnostic["copy_ref"] == "story_contract"
    assert diagnostic["requires"].startswith("exact semantic identity")


def test_exact_identity_and_scope_diagnose_stale_root_contract_copy(tmp_path):
    bundle = build_governed_context(project_root=tmp_path, chapter=20, state={}, source_sections={
        "outline": "authored outline", "outline_source_identity": "doc:chapter-20",
        "story_contract": {"chapter": 20, "goal": "stale generated copy"},
        "story_contract_source_identity": "doc:chapter-20",
    })
    diagnostic = next(row for row in bundle["diagnostics"] if row["type"] == "stale_runtime_copy")
    assert diagnostic["source_identity"] == "doc:chapter-20"
    assert diagnostic["scope"] == "chapter:20"
    assert diagnostic["source_ref"] == "outline"
    assert diagnostic["copy_ref"] == "story_contract"
    assert len(bundle["intent"]) == 2
    assert not any(row["type"] == "intent_conflict" for row in bundle["diagnostics"])


def test_exact_identity_and_scope_accept_matching_root_contract_copy(tmp_path):
    content = {"chapter": 20, "goal": "same content"}
    bundle = build_governed_context(project_root=tmp_path, chapter=20, state={}, source_sections={
        "outline": content, "outline_source_identity": "doc:chapter-20",
        "story_contract": content, "story_contract_source_identity": "doc:chapter-20",
    })
    assert not any(row["type"] in {"stale_runtime_copy", "intent_conflict"} for row in bundle["diagnostics"])
    assert len(bundle["intent"]) == 2


def test_context_uses_reconciled_open_loop_and_reader_promise_lifecycle(tmp_path):
    events = {
        1: [
            {"event_id": "L1", "chapter": 1, "event_type": "open_loop_created",
             "subject": "loop", "payload": {"content": "loop question"}},
            {"event_id": "P1", "chapter": 1, "event_type": "promise_created",
             "subject": "promise", "payload": {"content": "promise"}},
        ],
        2: [
            {"event_id": "L1-close", "chapter": 2, "event_type": "open_loop_closed",
             "subject": "loop", "payload": {"loop_id": "L1"}},
            {"event_id": "P1-paid", "chapter": 2, "event_type": "promise_paid_off",
             "subject": "promise", "payload": {"promise_id": "P1"}},
        ],
    }
    for chapter, accepted_events in events.items():
        write_commit(tmp_path, chapter, valid_commit(chapter, extraction={
            "entity_deltas": [], "state_deltas": [], "accepted_events": accepted_events,
        }))
    bundle = build_governed_context(project_root=tmp_path, chapter=3, state={
        "project_info": {"promise_ledger": [{"id": "P1", "canon_event_ref": "P1", "status": "deferred"}]},
    }, source_sections={})

    derived = [row for row in bundle["intent"] if row["semantic_class"] == "CANON_DERIVED_OBLIGATION"]
    assert len([row for row in derived if row.get("source_identity") == "L1"]) == 1
    assert len([row for row in derived if row.get("source_identity") == "P1"]) == 1
    loop = next(row["content"] for row in derived if row.get("source_identity") == "L1")
    promise = next(row["content"] for row in derived if row.get("source_identity") == "P1")
    assert (loop["source_event_id"], loop["source_chapter"], loop["status"],
            loop["resolution_event_id"], loop["resolved_chapter"]) == ("L1", 1, "resolved", "L1-close", 2)
    assert (promise["source_event_id"], promise["source_chapter"], promise["status"],
            promise["resolution_event_id"], promise["resolved_chapter"]) == ("P1", 1, "paid_off", "P1-paid", 2)
    loop_item = next(row for row in derived if row.get("source_identity") == "L1")
    assert loop_item["source_relationship"] == "DERIVED_RUNTIME_COPY"
    assert loop_item["owner"] == "effective_accepted_canon_events"
    assert "source_event:L1" in loop_item["evidence"]
    assert "resolution_event:L1-close" in loop_item["evidence"]
    assert {row["content"]["event_type"] for row in bundle["canon"]
            if row["content"].get("event_type")} >= {
                "open_loop_created", "open_loop_closed", "promise_created", "promise_paid_off",
            }
    planner = [row for row in bundle["intent"] if row["semantic_class"] == "PLANNER_INTENT"]
    assert len(planner) == 1
    assert planner[0]["content"]["canon_event_ref"] == "P1"
    assert not any(row.get("source_identity") in {"L1-close", "P1-paid"} for row in derived)
    assert not any(row["content"].get("event_type") in {
        "open_loop_created", "open_loop_closed", "promise_created", "promise_paid_off",
    } for row in derived)


@pytest.mark.parametrize(("claim_field", "story_key", "story_item"), [
    ("buried_chapter", "foreshadow_chain", {"id": "FS1", "type": "物谶", "depth": "表层"}),
    ("payoff_chapter", "foreshadow_chain", {"id": "FS1", "type": "物谶", "depth": "表层"}),
    ("fulfilled_chapter", "timed_locks", {"id": "TL1", "description": "deadline", "deadline_chapter": 8}),
])
def test_context_occurrence_is_reference_only_when_exact_event_is_accepted(tmp_path, claim_field, story_key, story_item):
    write_commit(tmp_path, 1, valid_commit(1, extraction={
        "entity_deltas": [], "state_deltas": [], "accepted_events": [{
            "event_id": "E1", "chapter": 1, "event_type": "open_loop_created",
            "subject": "TEST", "payload": {"content": "TEST"},
        }],
    }))
    story_item = {**story_item, claim_field: 1, "occurrence_ref": {"event_id": "E1"}}
    bundle = build_governed_context(project_root=tmp_path, chapter=2,
                                   state={"story_craft": {story_key: [story_item]}}, source_sections={})

    linked = [row for row in bundle["reference"] if row["semantic_class"] == "DERIVED_REFERENCE"
              and row.get("source_identity") == "E1"
              and row["content"].get("path", "").endswith(claim_field)]
    assert len(linked) == 1
    assert linked[0]["semantic_role"] == "UNKNOWN"
    assert linked[0]["content"]["value"] == 1
    assert linked[0]["content"]["occurrence"]["event_id"] == "E1"
    assert linked[0]["content"]["occurrence"]["source_chapter"] == 1
    assert all(row["semantic_role"] != "CANON" for row in linked)


@pytest.mark.parametrize("event_mutation", [
    "invalid_schema", "chapter_mismatch", "duplicate_id", "claim_mismatch",
    "multiple_claims", "missing_ref",
])
def test_context_does_not_trust_invalid_story_craft_occurrence_event(tmp_path, event_mutation):
    event = {"event_id": "E1", "chapter": 1, "event_type": "open_loop_created",
             "subject": "TEST", "payload": {"content": "TEST"}}
    if event_mutation == "invalid_schema":
        event.pop("subject")
    elif event_mutation == "chapter_mismatch":
        event["chapter"] = 9
    write_commit(tmp_path, 1, valid_commit(1, extraction={
        "entity_deltas": [], "state_deltas": [], "accepted_events": [event],
    }))
    if event_mutation == "duplicate_id":
        write_commit(tmp_path, 2, valid_commit(2, extraction={
            "entity_deltas": [], "state_deltas": [], "accepted_events": [{
                "event_id": "E1", "chapter": 2, "event_type": "open_loop_created",
                "subject": "TEST", "payload": {"content": "duplicate"},
            }],
        }))
    item = {"id": "FS1", "type": "物谶", "depth": "表层", "buried_chapter": 1}
    if event_mutation == "claim_mismatch":
        item["buried_chapter"] = 9
    elif event_mutation == "multiple_claims":
        item["payoff_chapter"] = 1
    if event_mutation != "missing_ref":
        item["occurrence_ref"] = {"event_id": "E1"}
    bundle = build_governed_context(project_root=tmp_path, chapter=3, state={
        "story_craft": {"foreshadow_chain": [item]},
    }, source_sections={})
    assert not any(row["semantic_class"] == "DERIVED_REFERENCE" and row.get("source_identity") == "E1"
                   for row in bundle["reference"])
    assert any(row["semantic_role"] == "UNKNOWN" and isinstance(row["content"], list)
               and any(field.get("path", "").endswith("buried_chapter")
                       for field in row["content"])
               for row in bundle["reference"])


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
