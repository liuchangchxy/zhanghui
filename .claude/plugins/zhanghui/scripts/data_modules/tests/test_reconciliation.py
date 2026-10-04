import sys

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from data_modules.reconciliation import reconcile_changes, split_chapter_and_changes


def change(state="realm: Foundation Establishment"):
    return {
        "character_state_changes": [
            {"character_id": " Lin-Xuan ", "new_state": state}
        ],
        "new_plot_points": [],
        "foreshadowing_actions": [],
        "location_state_changes": [],
        "faction_state_changes": [],
        "time_progression": None,
        "item_transfers": [],
        "unresolved_questions": [],
    }


def observation(new="筑基"):
    return {
        "accepted_events": [],
        "state_deltas": [
            {"entity_id": "lin-xuan", "field": "修为", "old": "炼气", "new": new}
        ],
        "entity_deltas": [],
    }


def test_matching_declaration_and_observation_is_accepted_with_provenance():
    result = reconcile_changes(change(), observation(), chapter_text="final")

    assert result["status"] == "passed"
    assert len(result["matched"]) == 1
    assert result["accepted_payload"]["state_deltas"] == observation()["state_deltas"]
    assert result["accepted_sources"][0]["observed"]["index"] == 0


def test_proposal_without_observation_is_not_accepted():
    result = reconcile_changes(change(), {"accepted_events": [], "state_deltas": [], "entity_deltas": []}, chapter_text="final")

    assert result["proposed_not_observed"]
    assert not result["accepted_payload"]["state_deltas"]


def test_observation_without_proposal_is_accepted_as_advisory():
    observed = observation()
    result = reconcile_changes(change(state="情绪振奋"), observed, chapter_text="final")

    assert result["status"] == "passed"
    assert result["unproposed_observed"]
    assert result["accepted_payload"]["state_deltas"] == observed["state_deltas"]


def test_structured_conflict_blocks_reconciliation():
    result = reconcile_changes(change(), observation("金丹"), chapter_text="final")

    assert result["status"] == "conflict"
    assert result["conflicts"]


def test_invalid_changes_shape_is_rejected_before_reconciliation():
    with pytest.raises(ValueError, match="missing required"):
        reconcile_changes({}, observation(), chapter_text="final")


def test_invalid_observation_schema_is_rejected_before_reconciliation():
    with pytest.raises(ValueError, match="accepted_events"):
        reconcile_changes(change(), {"state_deltas": [], "entity_deltas": []}, chapter_text="final")


def test_changes_gate_failure_prevents_cli_from_writing_reconciliation(tmp_path):
    import json
    import subprocess
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[2]
    chapter = tmp_path / "chapter.md"
    chapter.write_text("<chapter_changes>{}</chapter_changes>", encoding="utf-8")
    extraction = tmp_path / "extraction.json"
    extraction.write_text(json.dumps(observation()), encoding="utf-8")
    output = tmp_path / "reconciliation.json"
    output.write_text("stale previous result", encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(scripts / "reconcile_changes.py"), "--chapter-file", str(chapter),
         "--extraction-result", str(extraction), "--output", str(output), "--db", str(tmp_path / "index.db")],
        capture_output=True, text=True,
    )
    assert run.returncode != 0
    assert "changes_gate failed" in run.stderr
    assert not output.exists()


def test_final_chapter_hash_binds_reconciliation_to_polished_text():
    from data_modules.reconciliation import verify_reconciliation_freshness

    result = reconcile_changes(change(), observation(), chapter_text="polished-final")
    with pytest.raises(ValueError, match="stale"):
        verify_reconciliation_freshness(result, chapter_text="rewritten-after-reconciliation")


@pytest.mark.parametrize("format_name", ["xml", "separator", "heading", "trailing_json"])
def test_data_agent_split_removes_proposed_金丹_from_input(tmp_path, format_name):
    import json
    from pathlib import Path
    from subprocess import run

    proposal = change("realm: 金丹")
    body = json.dumps(proposal, ensure_ascii=False, indent=2)
    formats = {
        "xml": f"<chapter_changes>\n{body}\n</chapter_changes>",
        "separator": f"---CHANGES---\n{body}\n---",
        "heading": f"# CHANGES\n{body}",
        "trailing_json": body,
    }
    chapter_text = "主角今天只是回到客栈。\n\n" + formats[format_name]
    chapter = tmp_path / "chapter.md"
    prose = tmp_path / "prose.md"
    changes = tmp_path / "proposed.json"
    chapter.write_text(chapter_text, encoding="utf-8")
    scripts = Path(__file__).resolve().parents[2]
    result = run([sys.executable, str(scripts / "prepare_data_agent_input.py"),
                  "--chapter-file", str(chapter), "--prose-output", str(prose),
                  "--changes-output", str(changes)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    prose_text = prose.read_text(encoding="utf-8")
    assert prose_text.strip() == "主角今天只是回到客栈。"
    assert "character_state_changes" not in prose_text
    assert "realm" not in prose_text
    assert "金丹" not in prose_text
    assert json.loads(changes.read_text(encoding="utf-8")) == proposal


@pytest.mark.parametrize("format_name", ["xml", "separator", "heading", "trailing_json"])
def test_proposal_format_does_not_change_reconciliation_semantics(format_name):
    import json

    proposal = change()
    body = json.dumps(proposal, ensure_ascii=False)
    documents = {
        "xml": f"chapter prose\n<chapter_changes>{body}</chapter_changes>",
        "separator": f"chapter prose\n---CHANGES---\n{body}\n---",
        "heading": f"chapter prose\n# CHANGES\n{body}",
        "trailing_json": f"chapter prose\n\n{body}",
    }
    results = [reconcile_changes(proposal, observation(), chapter_text=documents[format_name])
               for format_name in ("xml", "separator", "heading", "trailing_json")]
    for result in results[1:]:
        assert result["status"] == results[0]["status"]
        assert result["matched"] == results[0]["matched"]
        assert result["conflicts"] == results[0]["conflicts"]
        assert result["accepted_payload"] == results[0]["accepted_payload"]


def test_entity_realm_delta_conflicts_with_character_state_proposal():
    observed = {"state_deltas": [], "entity_deltas": [
        {"entity_id": "lin-xuan", "patch": {"realm": "金丹"}}
    ], "accepted_events": []}
    result = reconcile_changes(change("realm: 筑基"), observed, chapter_text="final")
    assert result["status"] == "conflict"
    assert any(item["type"] == "proposal_observed_conflict" for item in result["conflicts"])


def test_power_breakthrough_event_realm_conflicts_with_character_state_proposal():
    observed = {"state_deltas": [], "entity_deltas": [], "accepted_events": [
        {"event_type": "power_breakthrough", "subject": "lin-xuan", "payload": {"realm": "金丹"}}
    ]}
    result = reconcile_changes(change("realm: 筑基"), observed, chapter_text="final")
    assert result["status"] == "conflict"
    assert any(item["type"] == "proposal_observed_conflict" for item in result["conflicts"])


def test_conflicting_observed_representations_block_even_without_proposal():
    observed = {
        "state_deltas": [
            {"entity_id": "lin-xuan", "field": "realm", "new": "筑基"},
            {"entity_id": "lin-xuan", "field": "境界", "new": "金丹"},
        ], "entity_deltas": [], "accepted_events": [],
    }
    result = reconcile_changes(change("情绪振奋"), observed, chapter_text="final")
    assert result["status"] == "conflict"
    assert result["conflicts"][0]["type"] == "observed_internal_conflict"


def test_same_value_observation_across_state_and_event_is_one_consistent_fact():
    observed = {
        "state_deltas": [{"entity_id": "lin-xuan", "field": "realm", "new": "筑基"}],
        "entity_deltas": [],
        "accepted_events": [{"event_type": "power_breakthrough", "subject": "lin-xuan", "payload": {"realm": "foundation establishment"}}],
    }
    result = reconcile_changes(change("realm: 筑基"), observed, chapter_text="final")
    assert result["status"] == "passed"
    assert not result["conflicts"]
    matching = result["matched"][0]["observed"]
    assert {item["source"] for item in matching} == {"state_deltas", "accepted_events"}
    assert result["coverage"]["deterministic_mappings"]


def test_conflicting_duplicate_proposal_is_not_silently_accepted():
    proposed = change("realm: 筑基")
    proposed["character_state_changes"].append({"character_id": "lin-xuan", "new_state": "realm: 金丹"})
    result = reconcile_changes(proposed, observation("筑基"), chapter_text="final")
    assert result["status"] == "conflict"
    assert any(item["type"] == "proposal_internal_conflict" for item in result["conflicts"])
