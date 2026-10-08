#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import subprocess
import sys
from pathlib import Path

from .test_project_phase import _make_contracts, _make_init_ready, _write_json


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_on_path()

from data_modules.write_gates import run_write_gate  # noqa: E402
from data_modules.projection_log import append_projection_run  # noqa: E402


def _write_valid_artifacts(project_root: Path) -> None:
    _write_json(project_root / ".webnovel" / "tmp" / "review_results.json", {"blocking_count": 0})
    _write_json(
        project_root / ".webnovel" / "tmp" / "fulfillment_result.json",
        {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
    )
    _write_json(project_root / ".webnovel" / "tmp" / "disambiguation_result.json", {"pending": []})
    _write_json(
        project_root / ".webnovel" / "tmp" / "extraction_result.json",
        {"accepted_events": [], "state_deltas": [], "entity_deltas": [], "summary_text": "摘要"},
    )


def test_prewrite_gate_allows_contract_ready_project_with_warning(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)

    report = run_write_gate(tmp_path, chapter=1, stage="prewrite")

    assert report["ok"] is True
    assert report["stage"] == "prewrite"
    assert report["details"]["prewrite_validation"]["blocking"] is False


def test_prewrite_gate_wraps_existing_prewrite_validator_blocking(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    state_path = tmp_path / ".webnovel" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["disambiguation_pending"] = [{"mention": "宗主"}]
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    report = run_write_gate(tmp_path, chapter=1, stage="prewrite")

    assert report["ok"] is False
    assert any(item["code"] == "prewrite_validator_blocking" for item in report["errors"])
    assert report["details"]["prewrite_validation"]["disambiguation_domain"]["pending_count"] == 1


def test_precommit_gate_reports_missing_artifacts(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is False
    assert any(item["code"] == "artifact.missing_artifact" for item in report["errors"])


def test_precommit_gate_accepts_valid_artifacts(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is True
    assert report["details"]["artifact_report"]["ok"] is True


def test_precommit_gate_accepts_normalized_craft_finding_as_advisory(tmp_path):
    from data_modules.review_schema import parse_review_output

    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)
    raw = {"issues": [{
        "severity": "critical", "category": "foreshadow_compliance", "blocking": True,
        "description": "overdue foreshadow heuristic", "checker_id": "llm_review",
    }]}
    normalized = parse_review_output(1, raw).to_dict()
    _write_json(tmp_path / ".webnovel" / "tmp" / "review_results.json", normalized)

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert normalized["blocking_count"] == 0
    assert normalized["issues"][0]["blocking"] is False
    assert report["ok"] is True


def test_detector_blocking_style_finding_does_not_veto_precommit(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    chapter = tmp_path / "正文" / "第0001章.md"
    chapter.write_text("他转过身——门已经开了。\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)
    scanner = Path(__file__).resolve().parents[2] / "check-ai-patterns.js"
    detected = subprocess.run(
        ["node", str(scanner), "--check", "--json", "--fail-on=blocking", str(chapter)],
        capture_output=True, text=True, check=False,
    )
    assert detected.returncode == 1
    assert '"severity":"blocking"' in detected.stdout.replace(" ", "")

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is True


def test_write_skill_treats_craft_style_scanners_as_advisory():
    skill = Path(__file__).resolve().parents[2].parent / "skills/webnovel-write/SKILL.md"
    text = skill.read_text(encoding="utf-8")

    assert "Craft/style scanner finding" in text
    assert "不阻止 Step 5" in text
    assert "任一工具报 critical / blocking → 触发整章重写" not in text


def test_precommit_gate_rejects_fulfillment_missing_missed_nodes(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)
    _write_json(
        tmp_path / ".webnovel" / "tmp" / "fulfillment_result.json",
        {"planned_nodes": [], "covered_nodes": [], "extra_nodes": []},
    )

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is False
    assert any(item["code"] == "artifact.schema_error" for item in report["errors"])
    assert any("missed_nodes" in item["message"] for item in report["errors"])


def test_precommit_gate_rejects_disambiguation_missing_pending(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)
    _write_json(tmp_path / ".webnovel" / "tmp" / "disambiguation_result.json", {"warnings": []})

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is False
    assert any(item["code"] == "artifact.schema_error" for item in report["errors"])
    assert any("pending" in item["message"] for item in report["errors"])


def test_precommit_gate_rejects_extraction_missing_accepted_events(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)
    _write_json(
        tmp_path / ".webnovel" / "tmp" / "extraction_result.json",
        {"state_deltas": [], "entity_deltas": [], "summary_text": "摘要"},
    )

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is False
    assert any(item["code"] == "artifact.schema_error" for item in report["errors"])
    assert any("accepted_events" in item["message"] for item in report["errors"])


def test_precommit_gate_blocks_projection_failed_phase(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)
    _write_json(
        tmp_path / ".story-system" / "commits" / "chapter_001.commit.json",
        {
            "meta": {"chapter": 1, "status": "accepted"},
            "projection_status": {"state": "done", "index": "failed:locked"},
        },
    )

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is False
    assert any(item["code"] == "phase_not_ready_for_precommit" for item in report["errors"])


def test_postcommit_gate_reports_projection_failure(tmp_path):
    _make_init_ready(tmp_path)
    _write_json(
        tmp_path / ".story-system" / "commits" / "chapter_001.commit.json",
        {
            "meta": {"chapter": 1, "status": "accepted"},
            "review_result": {"blocking_count": 0},
            "fulfillment_result": {
                "planned_nodes": [],
                "covered_nodes": [],
                "missed_nodes": [],
                "extra_nodes": [],
            },
            "disambiguation_result": {"pending": []},
            "extraction_result": {
                "accepted_events": [],
                "state_deltas": [],
                "entity_deltas": [],
                "summary_text": "摘要",
            },
            "projection_status": {"state": "done", "index": "failed:locked", "summary": "skipped"},
        },
    )

    report = run_write_gate(tmp_path, chapter=1, stage="postcommit")

    assert report["ok"] is False
    assert any(item["code"] == "projection_failure" for item in report["errors"])


def test_postcommit_gate_prefers_projection_log_failure(tmp_path):
    _make_init_ready(tmp_path)
    commit_payload = {
        "meta": {"chapter": 1, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {
            "planned_nodes": [],
            "covered_nodes": [],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        "disambiguation_result": {"pending": []},
        "extraction_result": {
            "accepted_events": [],
            "state_deltas": [],
            "entity_deltas": [],
            "summary_text": "摘要",
        },
        "projection_status": {"state": "done", "index": "done", "vector": "done"},
    }
    commit_path = tmp_path / ".story-system" / "commits" / "chapter_001.commit.json"
    _write_json(commit_path, commit_payload)
    append_projection_run(
        tmp_path,
        commit_payload,
        {"vector": {"status": "failed:timeout", "error": "timeout"}},
        commit_path=commit_path,
    )

    report = run_write_gate(tmp_path, chapter=1, stage="postcommit")

    assert report["ok"] is False
    assert any(item["code"] == "projection_failure" for item in report["errors"])
    assert report["details"]["projection_source"] == "projection_log"


def test_postcommit_gate_requires_five_projection_statuses_from_projection_log(tmp_path):
    _make_init_ready(tmp_path)
    commit_payload = {
        "meta": {"chapter": 1, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {
            "planned_nodes": [],
            "covered_nodes": [],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        "disambiguation_result": {"pending": []},
        "extraction_result": {
            "accepted_events": [],
            "state_deltas": [],
            "entity_deltas": [],
            "summary_text": "摘要",
        },
        "projection_status": {
            "state": "done",
            "index": "done",
            "summary": "skipped",
            "memory": "skipped",
            "vector": "done",
        },
    }
    commit_path = tmp_path / ".story-system" / "commits" / "chapter_001.commit.json"
    _write_json(commit_path, commit_payload)
    append_projection_run(
        tmp_path,
        commit_payload,
        {"vector": {"status": "done"}},
        commit_path=commit_path,
    )

    report = run_write_gate(tmp_path, chapter=1, stage="postcommit")

    assert report["ok"] is False
    assert report["details"]["projection_source"] == "projection_log"
    assert any(item["code"] == "projection_status_missing" for item in report["errors"])
    assert any("state" in item["message"] for item in report["errors"])


def test_postcommit_gate_accepts_done_or_skipped_projection(tmp_path):
    _make_init_ready(tmp_path)
    _write_json(
        tmp_path / ".story-system" / "commits" / "chapter_001.commit.json",
        {
            "meta": {"chapter": 1, "status": "accepted"},
            "review_result": {"blocking_count": 0},
            "fulfillment_result": {
                "planned_nodes": [],
                "covered_nodes": [],
                "missed_nodes": [],
                "extra_nodes": [],
            },
            "disambiguation_result": {"pending": []},
            "extraction_result": {
                "accepted_events": [],
                "state_deltas": [],
                "entity_deltas": [],
                "summary_text": "摘要",
            },
            "projection_status": {
                "state": "done",
                "index": "skipped",
                "summary": "skipped",
                "memory": "skipped",
                "vector": "skipped",
            },
        },
    )

    report = run_write_gate(tmp_path, chapter=1, stage="postcommit")

    assert report["ok"] is True
