"""Integration test: review_pipeline.run_craft_checks pulls in story_craft checks."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 让 import 能找到 review_pipeline.py 和 story_craft.py
_SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS / "data_modules"))

from story_craft import (
    init_story_craft,
    add_foreshadow,
    add_timed_lock,
    record_emotion_peak,
    set_chapter_meta,
)
from review_pipeline import run_craft_checks, _inject_craft_issues, _craft_issue_to_review_issue
from data_modules.review_schema import ReviewResult
from data_modules.gate_finding_adapters import adapt_legacy_artifacts
from data_modules.gate_findings import WorkflowAction
from data_modules.gate_severity_policy import GateSeverityPolicy


# init_story_craft() requires a real file on disk. Provide a fixture path.
_DUMMY_STATE = Path("/tmp/dummy.json")


def _ensure_dummy_state() -> Path:
    """Create /tmp/dummy.json with minimal content if missing."""
    if not _DUMMY_STATE.exists():
        _DUMMY_STATE.write_text(
            json.dumps({"project_info": {}, "progress": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
    return _DUMMY_STATE


def test_run_craft_checks_flags_missing_hook():
    _ensure_dummy_state()
    state = init_story_craft(str(_DUMMY_STATE))
    state["chapter_meta"] = {}
    state["chapter_meta"]["1"] = {
        "scene_goal": "ok", "scene_conflict": "ok", "sequel_decision": "ok"
    }
    issues = run_craft_checks(state, chapter=1)
    assert any("hook_type" in b for b in issues["blockers"])


def test_run_craft_checks_flags_overdue_timed_lock():
    _ensure_dummy_state()
    state = init_story_craft(str(_DUMMY_STATE))
    add_timed_lock(state, {"description": "test", "deadline_chapter": 3})
    issues = run_craft_checks(state, chapter=5)
    assert any("定时锁逾期" in b for b in issues["blockers"])


def test_run_craft_checks_flags_rhythm_block():
    _ensure_dummy_state()
    state = init_story_craft(str(_DUMMY_STATE))
    state["story_craft"]["rhythm_curve"]["chapters_since_peak"] = 6
    state["story_craft"]["rhythm_curve"]["block_threshold"] = 5
    issues = run_craft_checks(state, chapter=10)
    assert any("节奏曲线 BLOCK" in b for b in issues["blockers"])


def test_craft_findings_have_stable_structured_identity_and_never_block(tmp_path):
    _ensure_dummy_state()
    state = init_story_craft(str(_DUMMY_STATE))
    add_timed_lock(state, {"id": "lock-77", "description": "test", "deadline_chapter": 3})
    issues = run_craft_checks(state, chapter=5)
    timed = next(row for row in issues["findings"] if row["gate_id"] == "story_craft.timed_lock")
    assert timed["subject_id"] == "timed_lock:lock-77"
    project = tmp_path
    (project / ".webnovel").mkdir()
    (project / ".webnovel" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    result = ReviewResult(chapter=5)
    _inject_craft_issues(project, result, 5)
    row = next(issue for issue in result.issues if issue.gate_id == "story_craft.timed_lock")
    assert row.blocking is False
    assert row.authority == "CRAFT_HEURISTIC"
    assert row.subject_id == "timed_lock:lock-77"
    findings = adapt_legacy_artifacts(
        chapter=5, review={"issues": [issue.to_dict() for issue in result.issues]},
        fulfillment={"missed_nodes": [], "planned_nodes": [], "covered_nodes": [], "extra_nodes": []},
        disambiguation={"pending": []},
    )
    decision = GateSeverityPolicy().evaluate(findings, policy_version="v1", scope={"chapter": 5})
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY


def test_craft_display_veto_words_never_change_policy_classification():
    records = [
        ("foreshadow_compliance: 定时锁逾期 BLOCKER", "story_craft.timed_lock", "timed_lock:lock-1"),
        ("foreshadow_compliance: 节奏曲线 BLOCK", "story_craft.rhythm_curve", "chapter:8:rhythm_curve"),
        ("foreshadow_compliance: hook_type 未声明", "story_craft.hook_type", "chapter:8:hook_type"),
        ("beat_compliance: Scene-Sequel BLOCKER", "story_craft.scene_sequel", "chapter:8:scene_sequel"),
    ]
    result = ReviewResult(chapter=8)
    for display, gate_id, subject_id in records:
        result.issues.append(_craft_issue_to_review_issue(display, 8, {
            "gate_id": gate_id, "subject_id": subject_id,
            "evidence": [{"kind": "craft_observation", "identity": {"chapter": 8}}],
        }))
    findings = adapt_legacy_artifacts(
        chapter=8, review={"issues": [issue.to_dict() for issue in result.issues]},
        fulfillment={"missed_nodes": []}, disambiguation={"pending": []},
    )
    decision = GateSeverityPolicy().evaluate(findings, policy_version="v1", scope={"chapter": 8})
    assert decision.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY
    assert all(row.effective_severity.value == "ADVISORY" for row in decision.decisions)
