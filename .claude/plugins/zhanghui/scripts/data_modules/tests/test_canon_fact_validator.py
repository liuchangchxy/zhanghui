import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_modules.canon_fact_validator import build_canon_facts, validate_canon_facts
from data_modules.gate_findings import FindingAuthority, FindingCategory


def _write_commit(root: Path, chapter: int, extraction: dict, status: str = "accepted") -> None:
    commit_dir = root / ".story-system" / "commits"
    commit_dir.mkdir(parents=True, exist_ok=True)
    (commit_dir / f"chapter_{chapter:03d}.commit.json").write_text(
        json.dumps({"meta": {"status": status}, "extraction_result": extraction},
                   ensure_ascii=False),
        encoding="utf-8",
    )


def _canon_extraction() -> dict:
    return {
        "state_deltas": [
            {"entity_id": "lin-xuan", "field": "时间", "new": "十年前"},
            {"entity_id": "lin-xuan", "field": "伤势", "new": "左手虎口烫伤"},
            {"entity_id": "lin-xuan", "field": "修为", "new": "筑基"},
            {"entity_id": "青锋剑", "field": "持有者", "new": "林越"},
        ],
        "accepted_events": [],
        "entity_deltas": [],
    }


def _current(*state_deltas: dict) -> dict:
    return {"state_deltas": list(state_deltas), "accepted_events": [], "entity_deltas": []}


def test_build_canon_facts_ignores_unaccepted_commits(tmp_path):
    _write_commit(tmp_path, 1, _canon_extraction(), status="rejected")

    assert build_canon_facts(tmp_path, chapter=2) == {}


def test_same_fact_paraphrase_is_not_a_contradiction(tmp_path):
    _write_commit(tmp_path, 1, _canon_extraction())
    validation = validate_canon_facts(
        tmp_path, 2,
        _current(
            {"entity_id": "lin-xuan", "field": "时间", "new": "十年前"},
            {"entity_id": "lin-xuan", "field": "修为", "new": "筑基期"},
        ),
    )

    assert validation["status"] == "passed"
    assert validation["contradictions"] == []


def test_different_elapsed_time_is_a_hard_contradiction(tmp_path):
    _write_commit(tmp_path, 1, _canon_extraction())
    validation = validate_canon_facts(
        tmp_path, 2,
        _current({"entity_id": "lin-xuan", "field": "时间", "new": "十四年前"}),
    )

    assert validation["status"] == "conflict"
    assert validation["contradictions"][0]["field"] == "time"
    assert validation["contradictions"][0]["canon_event_id"]


def test_injured_canon_rewritten_as_uninjured_is_a_contradiction(tmp_path):
    _write_commit(tmp_path, 1, _canon_extraction())
    validation = validate_canon_facts(
        tmp_path, 2,
        _current({"entity_id": "lin-xuan", "field": "伤势", "new": "双手完好无伤"}),
    )

    assert validation["status"] == "conflict"
    kinds = {item["kind"] for item in validation["contradictions"]}
    assert kinds == {"injury"}


def test_documented_healing_is_a_legitimate_transition(tmp_path):
    _write_commit(tmp_path, 1, _canon_extraction())
    validation = validate_canon_facts(
        tmp_path, 2,
        _current({"entity_id": "lin-xuan", "field": "伤势", "old": "左手虎口烫伤", "new": "伤口愈合"}),
    )

    assert validation["status"] == "passed"


def test_confirmed_ownership_change_without_transition_is_a_contradiction(tmp_path):
    _write_commit(tmp_path, 1, _canon_extraction())
    validation = validate_canon_facts(
        tmp_path, 2,
        _current({"entity_id": "青锋剑", "field": "持有者", "new": "梅叔"}),
    )

    assert validation["status"] == "conflict"
    assert validation["contradictions"][0]["kind"] == "ownership"


def test_proposed_item_transfer_with_stale_owner_is_a_contradiction(tmp_path):
    _write_commit(tmp_path, 1, _canon_extraction())
    validation = validate_canon_facts(
        tmp_path, 2,
        _current(),
        proposed_changes={"item_transfers": [
            {"item_id": "青锋剑", "from_holder": "梅叔", "to_holder": "林越"}
        ]},
    )

    assert validation["status"] == "conflict"
    reason = validation["contradictions"][0]["reason"]
    assert "prior value" in reason


def test_unknown_entity_or_field_is_unconstrained(tmp_path):
    _write_commit(tmp_path, 1, _canon_extraction())
    validation = validate_canon_facts(
        tmp_path, 2,
        _current({"entity_id": "mentor", "field": "时间", "new": "三十年前"}),
    )

    assert validation["status"] == "passed"


def test_adapter_emits_accepted_canon_contradiction(tmp_path):
    from data_modules.gate_finding_adapters import adapt_canon_validation

    _write_commit(tmp_path, 1, _canon_extraction())
    validation = validate_canon_facts(
        tmp_path, 2,
        _current({"entity_id": "lin-xuan", "field": "时间", "new": "十四年前"}),
    )

    findings = adapt_canon_validation(validation, chapter=2)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.category == FindingCategory.CANON_CONTRADICTION
    assert finding.authority == FindingAuthority.ACCEPTED_CANON
    assert finding.stable_subject_key == "lin-xuan::time"
    evidence = finding.evidence[0]
    assert evidence.kind == "canon_contradiction"
    assert evidence.identity["deterministic"] is True
    assert evidence.identity["contradiction"] is True
    assert evidence.identity["accepted_canon"] is True
    assert evidence.source_ref == evidence.identity["canon_event_id"]


def test_adapted_contradiction_is_hard_canon_and_rejects(tmp_path):
    from data_modules.gate_findings import EffectiveSeverity, WorkflowAction
    from data_modules.gate_severity_policy import GateSeverityPolicy
    from data_modules.gate_finding_adapters import adapt_canon_validation

    _write_commit(tmp_path, 1, _canon_extraction())
    validation = validate_canon_facts(
        tmp_path, 2,
        _current({"entity_id": "lin-xuan", "field": "时间", "new": "十四年前"}),
    )
    findings = adapt_canon_validation(validation, chapter=2)

    decision = GateSeverityPolicy().evaluate(
        findings, policy_version="gate-policy/v1", scope={"chapter": 2}
    )

    assert decision.aggregate_action == WorkflowAction.REJECT
    assert decision.decisions[0].effective_severity == EffectiveSeverity.HARD_CANON
