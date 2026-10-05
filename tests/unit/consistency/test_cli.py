from scripts.consistency.cli import build_parser, main
import pytest
import json
from scripts.consistency import cli as cli_module
from scripts.data_modules.gate_findings import (
    DetectedFinding, EvidenceRef, Explicitness, FindingAuthority, FindingCategory, WorkflowAction,
)


def test_parser_check_command():
    parser = build_parser()
    args = parser.parse_args(["check", "--project-root", "/tmp/proj", "--chapter", "5"])
    assert args.command == "check"
    assert args.project_root == "/tmp/proj"
    assert args.chapter == 5
    assert args.patch is None
    assert not hasattr(args, "output_version")


def test_parser_rejects_retired_legacy_output_mode():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["check", "--project-root", "/tmp/proj", "--chapter", "5",
                           "--output-version", "legacy"])


def test_parser_check_specific_patch():
    parser = build_parser()
    args = parser.parse_args(["check", "--project-root", "/tmp/proj", "--chapter", "5", "--patch", "foreshadow_dag"])
    assert args.patch == "foreshadow_dag"


def test_parser_list_command():
    parser = build_parser()
    args = parser.parse_args(["list", "--chapter", "5"])
    assert args.command == "list"


def test_parser_init_command():
    parser = build_parser()
    args = parser.parse_args(["init", "--volume", "1"])
    assert args.command == "init"
    assert args.volume == 1


def test_parser_override_command():
    parser = build_parser()
    args = parser.parse_args(["override", "--chapter", "5", "--reason", "user confirmed"])
    assert args.command == "override"
    assert args.reason == "user confirmed"


def test_cli_init_creates_state(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    rc = main(["init", "--project-root", str(proj), "--volume", "1"])
    assert rc == 0
    state_path = proj / ".webnovel" / "state.json"
    assert state_path.exists()
    import json
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "story_craft" in state


def test_cli_override_writes_override_file(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".webnovel").mkdir()
    rc = main(["override", "--project-root", str(proj), "--chapter", "5", "--reason", "test"])
    assert rc == 0
    override_path = proj / ".webnovel" / "consistency_overrides.json"
    assert override_path.exists()


def _valid_project(tmp_path):
    project = tmp_path / "project"
    (project / ".webnovel").mkdir(parents=True)
    (project / ".webnovel" / "state.json").write_text(json.dumps({
        "story_craft": {
            "foreshadow_chain": {"dag": []},
            "volume_anchors": {"anchors": []},
            "event_matrix_state": {"history": []},
            "pacing_history": {"history": [], "rules": {}},
            "reader_contract": {"expectation_debt": [], "endgame_reserves": [], "swap_debts": [], "contract_fulfillment": []},
        }
    }), encoding="utf-8")
    return project


def _policy_finding(action):
    if action == WorkflowAction.ALLOW_WITH_ADVISORY:
        return DetectedFinding(gate_id="cli.craft", stable_subject_key="craft:1", category=FindingCategory.CRAFT,
                               authority=FindingAuthority.CRAFT_HEURISTIC, explicitness=Explicitness.UNKNOWN,
                               scope={"chapter": 5}, evidence=[EvidenceRef(kind="craft_observation", identity={})],
                               subject_id="craft:1", checker_id="test", checker_version="1")
    if action == WorkflowAction.RECOVER:
        return DetectedFinding(gate_id="cli.recovery", stable_subject_key="view:F1", category=FindingCategory.PROJECTION_HEALTH,
                               authority=FindingAuthority.SYSTEM_INTEGRITY, explicitness=Explicitness.UNKNOWN,
                               scope={"chapter": 5}, evidence=[EvidenceRef(kind="recovery_required", identity={})],
                               subject_id="view:F1", checker_id="test", checker_version="1")
    if action == WorkflowAction.REQUIRE_HUMAN:
        return DetectedFinding(gate_id="cli.human", stable_subject_key="canon:F1", category=FindingCategory.CANON_CONTRADICTION,
                               authority=FindingAuthority.LLM_REVIEW, explicitness=Explicitness.UNKNOWN,
                               scope={"chapter": 5}, evidence=[EvidenceRef(kind="review_candidate", identity={})],
                               subject_id="canon:F1", checker_id="test", checker_version="1")
    return DetectedFinding(gate_id="cli.reject", stable_subject_key="integrity:F1", category=FindingCategory.INTEGRITY,
                           authority=FindingAuthority.SYSTEM_INTEGRITY, explicitness=Explicitness.UNKNOWN,
                           scope={"chapter": 5}, evidence=[EvidenceRef(kind="deterministic_validation", identity={"valid": False})],
                           subject_id="integrity:F1", checker_id="test", checker_version="1")


@pytest.mark.parametrize("action", [
    WorkflowAction.ALLOW_WITH_ADVISORY, WorkflowAction.RECOVER,
    WorkflowAction.REQUIRE_HUMAN, WorkflowAction.REJECT,
])
def test_cli_v1_serializes_shared_policy_action_and_success_exits_zero(tmp_path, capsys, monkeypatch, action):
    project = _valid_project(tmp_path)
    monkeypatch.setattr(cli_module, "adapt_consistency_patch", lambda _rows, _scope: [_policy_finding(action)])
    rc = main(["check", "--project-root", str(project), "--chapter", "5"])
    response = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert response["version"] == 1
    assert response["status"] == "evaluated"
    assert response["policy_action"] == action.value
    assert "consumer_action" not in response
    assert response["source_input_fingerprint"]
    assert len(response["findings"]) == len(response["decisions"]) == 1


def test_cli_v1_invalid_project_root_returns_two_and_structured_status(tmp_path, capsys):
    rc = main(["check", "--project-root", str(tmp_path / "missing"), "--chapter", "5"])
    response = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert response["status"] == "invalid_input"
    assert response["policy_action"] is None


def test_cli_v1_corrupt_state_is_execution_error_not_findings(tmp_path, capsys, monkeypatch):
    project = _valid_project(tmp_path)
    (project / ".webnovel" / "state.json").write_text("{bad", encoding="utf-8")
    monkeypatch.setattr(cli_module, "adapt_consistency_patch", lambda *_: pytest.fail("policy must not run"))
    rc = main(["check", "--project-root", str(project), "--chapter", "5"])
    response = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert response["status"] == "execution_error"
    assert response["findings"] == []
    assert response["policy_action"] is None
    assert response["diagnostics"][0]["diagnostic_code"] == "state_read_failed"


def test_cli_runs_real_p1_through_runner_adapter_policy_without_persisting_decisions(tmp_path, capsys):
    project = _valid_project(tmp_path)
    state_path = project / ".webnovel" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["story_craft"]["foreshadow_chain"] = {"dag": [
        {"id": "F1", "depends_on": ["F2"], "planted_chapter": 1, "status": "active"},
        {"id": "F2", "depends_on": ["F1"], "planted_chapter": 1, "status": "active"},
    ]}
    state_path.write_text(json.dumps(state), encoding="utf-8")

    rc = main(["check", "--project-root", str(project), "--chapter", "5"])
    response = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert response["status"] == "evaluated"
    assert response["policy_action"] == WorkflowAction.REJECT.value
    assert any(row["gate_id"] == "consistency.foreshadow_dag.cycle" for row in response["findings"])
    cycle = next(row for row in response["findings"] if row["gate_id"] == "consistency.foreshadow_dag.cycle")
    assert cycle["evidence"][0]["identity"]["source_input_fingerprint"] == response["source_input_fingerprint"]
    observation = next(row for row in response["observations"] if row["issue_code"] == "cycle")
    assert observation["patch"] == "foreshadow_dag"
    assert observation["input_ref"]["source_input_fingerprint"] == response["source_input_fingerprint"]
    assert not (project / ".story-system" / "reviews" / "gate-decisions").exists()


def test_cli_unknown_patch_is_invalid_input_not_clean_evaluation(tmp_path, capsys, monkeypatch):
    project = _valid_project(tmp_path)
    monkeypatch.setattr(cli_module, "adapt_consistency_patch", lambda *_: pytest.fail("invalid patch must not evaluate"))
    rc = main(["check", "--project-root", str(project), "--chapter", "5", "--patch", "typo"])
    response = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert response["status"] == "invalid_input"
    assert response["policy_action"] is None


def test_cli_apply_rejects_missing_project_without_creating_it(tmp_path, capsys):
    missing = tmp_path / "missing"
    rc = main(["apply", "--project-root", str(missing), "--chapter", "5"])
    response = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert response == {"status": "invalid_input", "outcomes": []}
    assert not missing.exists()


def test_cli_v1_partial_apply_reports_each_patch_and_returns_one(tmp_path, capsys, monkeypatch):
    project = _valid_project(tmp_path)

    class FakeRunner:
        def __init__(self, project_root):
            self.project_root = project_root
        def apply_all(self, chapter):
            return [
                {"patch": "volume_anchor", "status": "applied", "error_type": None},
                {"patch": "derived_views", "status": "failed", "error_type": "OSError"},
            ]

    monkeypatch.setattr(cli_module, "ConsistencyRunner", FakeRunner)
    rc = main(["apply", "--project-root", str(project), "--chapter", "5"])
    response = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert response["status"] == "partial_failure"
    assert [row["status"] for row in response["outcomes"]] == ["applied", "failed"]
