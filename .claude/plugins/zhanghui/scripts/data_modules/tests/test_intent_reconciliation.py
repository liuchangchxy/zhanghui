from data_modules.intent_reconciliation import intent_event_content_candidates, reconcile_intent_events


def _event(event_id, chapter, event_type, content, **payload):
    return {
        "event_id": event_id,
        "chapter": chapter,
        "event_type": event_type,
        "subject": content,
        "payload": {"content": content, **payload},
    }


def test_create_event_id_is_loop_identity():
    result = reconcile_intent_events([_event("create-a", 1, "open_loop_created", "旧约")])
    row = result["open_loops"][0]
    assert {key: row[key] for key in ("identity_id", "source_event_id", "source_chapter", "content", "status", "link_status")} == {
        "identity_id": "create-a",
        "source_event_id": "create-a",
        "source_chapter": 1,
        "content": "旧约",
        "status": "active",
        "link_status": "linked",
    }


def test_explicit_close_resolves_only_its_loop_even_when_content_is_duplicated():
    events = [
        _event("create-a", 1, "open_loop_created", "旧约"),
        _event("create-b", 2, "open_loop_created", "旧约"),
        _event("close-b", 3, "open_loop_closed", "多年旧约", loop_id="create-b"),
    ]
    rows = reconcile_intent_events(events)["open_loops"]
    assert [(row["identity_id"], row["status"]) for row in rows] == [
        ("create-a", "active"),
        ("create-b", "resolved"),
    ]
    assert rows[1]["resolution_event_id"] == "close-b"
    assert rows[1]["resolved_chapter"] == 3


def test_legacy_close_resolves_exactly_one_prior_unmatched_create():
    events = [
        _event("create-a", 1, "open_loop_created", "旧约"),
        _event("close-a", 2, "open_loop_closed", "旧约"),
    ]
    row = reconcile_intent_events(events)["open_loops"][0]
    assert row["status"] == "resolved"
    assert row["link_status"] == "legacy_exact_unique"
    assert row["resolution_event_id"] == "close-a"


def test_legacy_close_with_duplicate_candidates_stays_unlinked():
    events = [
        _event("create-a", 1, "open_loop_created", "旧约"),
        _event("create-b", 2, "open_loop_created", "旧约"),
        _event("close-x", 3, "open_loop_closed", "旧约"),
    ]
    result = reconcile_intent_events(events)
    assert [row["status"] for row in result["open_loops"]] == ["active", "active"]
    assert result["diagnostics"] == [
        {
            "event_id": "close-x",
            "chapter": 3,
            "reason": "ambiguous_legacy_close",
            "candidate_ids": ["create-a", "create-b"],
            "link_status": "unlinked",
        }
    ]


def test_orphan_close_does_not_create_a_resolved_loop():
    result = reconcile_intent_events([_event("close-x", 3, "open_loop_closed", "未知")])
    assert result["open_loops"] == []
    assert result["diagnostics"][0]["reason"] == "orphan_close"


def test_repeated_close_is_diagnostic_and_does_not_change_resolution():
    events = [
        _event("create-a", 1, "open_loop_created", "旧约"),
        _event("close-a", 2, "open_loop_closed", "旧约", loop_id="create-a"),
        _event("close-again", 3, "open_loop_closed", "旧约", loop_id="create-a"),
    ]
    result = reconcile_intent_events(events)
    assert result["open_loops"][0]["resolution_event_id"] == "close-a"
    assert result["diagnostics"][0]["reason"] == "duplicate_resolution"


def test_explicit_unknown_loop_id_is_orphan_not_content_matched():
    events = [
        _event("create-a", 1, "open_loop_created", "旧约"),
        _event("close-x", 2, "open_loop_closed", "旧约", loop_id="missing"),
    ]
    result = reconcile_intent_events(events)
    assert result["open_loops"][0]["status"] == "active"
    assert result["diagnostics"][0]["reason"] == "orphan_close"


def test_linked_promise_payoff_resolves_creation_without_creating_another_promise():
    events = [
        _event("promise-a", 1, "promise_created", "护送少女", promise_id="plan-a"),
        _event("paid-a", 4, "promise_paid_off", "护送完成", source_event_id="promise-a"),
    ]
    rows = reconcile_intent_events(events)["reader_promises"]
    assert len(rows) == 1
    assert rows[0]["identity_id"] == "promise-a"
    assert rows[0]["status"] == "paid_off"
    assert rows[0]["resolution_event_id"] == "paid-a"


def test_payoff_only_event_is_diagnostic_and_never_an_active_promise():
    result = reconcile_intent_events([_event("paid-x", 4, "promise_paid_off", "已完成")])
    assert result["reader_promises"] == []
    assert result["diagnostics"][0]["reason"] == "unlinked_payoff"


def test_event_ordering_and_replay_are_deterministic_without_mutating_input():
    events = [
        _event("create-a", 1, "open_loop_created", "旧约"),
        _event("close-a", 2, "open_loop_closed", "旧约"),
    ]
    before = repr(events)
    first = reconcile_intent_events(events)
    second = reconcile_intent_events(events)
    assert first == second
    assert repr(events) == before


def test_duplicate_content_creates_keep_separate_identity_rows():
    result = reconcile_intent_events([
        _event("create-a", 1, "open_loop_created", "同一句"),
        _event("create-b", 2, "open_loop_created", "同一句"),
    ])
    assert [row["identity_id"] for row in result["open_loops"]] == ["create-a", "create-b"]
    assert [row["status"] for row in result["open_loops"]] == ["active", "active"]


def test_explicit_promise_id_links_only_matching_created_promise():
    result = reconcile_intent_events([
        _event("promise-a", 1, "promise_created", "救下盟友", promise_id="intent-a"),
        _event("promise-b", 2, "promise_created", "救下盟友", promise_id="intent-b"),
        _event("paid-b", 3, "promise_paid_off", "盟友获救", promise_id="intent-b"),
    ])
    assert [(row["identity_id"], row["status"]) for row in result["reader_promises"]] == [
        ("promise-a", "active"), ("promise-b", "paid_off")
    ]


def test_structured_loop_type_description_uses_memory_writer_content_convention():
    result = reconcile_intent_events([{
        "event_id": "loop-typed", "chapter": 1, "event_type": "open_loop_created",
        "subject": "hero", "payload": {"loop_type": "mystery", "description": "玉佩为何发热"},
    }])
    assert result["open_loops"][0]["content"] == "mystery：玉佩为何发热"


def test_loop_type_metadata_alone_is_not_a_legacy_storage_alias():
    assert intent_event_content_candidates({
        "event_type": "open_loop_created",
        "subject": "entity-7",
        "payload": {"loop_type": "mystery"},
    }) == []
