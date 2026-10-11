"""Regression tests for Native Closure Repair: strict schema validation and vector degradation decoupling."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from data_modules.reconciliation import validate_proposed_changes, reconcile_changes, split_chapter_and_changes
from data_modules.vector_projection_writer import VectorProjectionWriter
from data_modules.chapter_runtime import ChapterRuntime


def _setup_test_project(tmp_path: Path, chapter: int = 1) -> Path:
    project_root = tmp_path / "test_book"
    project_root.mkdir(parents=True, exist_ok=True)
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    outline_dir = project_root / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "project_info": {"title": "测试书", "genre": "悬疑", "target_readers": "大众"},
        "progress": {
            "current_volume": 1,
            "current_chapter": 0,
            "total_volumes": 1,
            "volumes_planned": [{"volume": 1, "chapters_range": "1-10", "title": "第一卷"}],
            "volumes_completed": [],
        },
        "entity_state": {},
    }
    (webnovel_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    for d in (".webnovel/backups", ".webnovel/archive", ".webnovel/summaries", "设定集", "正文", "审查报告"):
        (project_root / d).mkdir(parents=True, exist_ok=True)
    for f in ("设定集/世界观.md", "设定集/力量体系.md", "设定集/主角卡.md", "设定集/反派设计.md", "大纲/总纲.md", ".env.example"):
        fp = project_root / f
        fp.parent.mkdir(parents=True, exist_ok=True)
        if not fp.exists():
            fp.write_text("# init\n", encoding="utf-8")

    outline_text = f"""# 第一卷\n### 第{chapter}章：初入调查\n- 目标：调查白塔档案\n- 必须覆盖节点：档案核验\n- 本章禁区：禁止泄露真相\n"""
    (outline_dir / f"第{chapter:02d}章.md").write_text(outline_text, encoding="utf-8")
    return project_root


def _canonical_changes_dict() -> dict:
    return {
        "character_state_changes": [
            {"character_id": "林越", "new_state": "调查中", "importance": "normal"}
        ],
        "new_plot_points": [
            {"context": "确认档案撕页", "importance": "normal"}
        ],
        "foreshadowing_actions": [
            {"foreshadow_id": "F1-001", "action": "setup"}
        ],
        "location_state_changes": [],
        "faction_state_changes": [],
        "time_progression": {"time_period": "凌晨雨夜", "importance": "normal"},
        "item_transfers": [
            {"item_id": "铜钥匙", "new_status": "active"}
        ],
        "unresolved_questions": [
            {"question": "第四十二页为何被撕毁？"}
        ],
    }


def _valid_test_prose() -> str:
    changes_json = json.dumps(_canonical_changes_dict(), ensure_ascii=False, indent=2)
    return f"""林越深吸了一口气，将泛黄的档案平铺在木桌上。窗外海潮拍岸，纸页上的特种钢印依稀可辨。

<chapter_changes>
{changes_json}
</chapter_changes>"""


def test_string_foreshadowing_actions_strictly_rejected():
    payload = _canonical_changes_dict()
    payload["foreshadowing_actions"] = ["伏笔文本：钢印批号线索"]
    with pytest.raises(ValueError, match=r"CHANGES\.foreshadowing_actions items must be objects"):
        validate_proposed_changes(payload)


def test_string_item_transfers_strictly_rejected():
    payload = _canonical_changes_dict()
    payload["item_transfers"] = ["黄铜钥匙转移到林越手中"]
    with pytest.raises(ValueError, match=r"CHANGES\.item_transfers items must be objects"):
        validate_proposed_changes(payload)


def test_string_character_state_changes_strictly_rejected():
    payload = _canonical_changes_dict()
    payload["character_state_changes"] = ["林越: 精神高度紧绷"]
    with pytest.raises(ValueError, match=r"CHANGES\.character_state_changes items must be objects"):
        validate_proposed_changes(payload)


def test_string_new_plot_points_strictly_rejected():
    payload = _canonical_changes_dict()
    payload["new_plot_points"] = ["完成白塔事故初步核查"]
    with pytest.raises(ValueError, match=r"CHANGES\.new_plot_points items must be objects"):
        validate_proposed_changes(payload)


def test_valid_schema_passes_unmodified():
    payload = _canonical_changes_dict()
    res = validate_proposed_changes(payload)
    assert res == payload
    assert res["character_state_changes"][0]["character_id"] == "林越"
    assert res["foreshadowing_actions"][0]["action"] == "setup"
    assert res["item_transfers"][0]["new_status"] == "active"


def test_vector_projection_degraded_reason_returned_when_embedding_unavailable(tmp_path: Path, monkeypatch):
    writer = VectorProjectionWriter(tmp_path)
    writer._last_degraded_reason = "embedding_unavailable"
    monkeypatch.setattr(writer, "_store_chunks", lambda chunks: 0)

    payload = {
        "meta": {"schema_version": "story-system/v1", "status": "accepted", "chapter": 1},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {
            "chapter_meta": {},
            "summary_text": "林越在书肆核验离线纸质档案。",
            "accepted_events": [],
            "state_deltas": [],
            "entity_deltas": [],
        },
    }
    commit_path = tmp_path / ".story-system" / "commits" / "chapter_001.commit.json"
    commit_path.parent.mkdir(parents=True, exist_ok=True)
    commit_path.write_text(json.dumps(payload), encoding="utf-8")

    res = writer.apply(payload)
    assert res["applied"] is False
    assert res["writer"] == "vector"
    assert res["stored"] == 0
    assert res["reason"] == "degraded:embedding_unavailable"


def test_vector_unavailable_does_not_invalidate_durable_commit(tmp_path: Path, monkeypatch):
    """When vector secondary projection degrades, the canonical chapter commit remains durable & accepted."""
    project_root = _setup_test_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    runtime.prepare(chapter=1, with_package=True)
    sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief="策划任务书测试")

    prose = _valid_test_prose()
    ingest_res = runtime.ingest_draft(
        chapter=1,
        package_fingerprint=sealed_pkg.package_fingerprint,
        prose=prose,
    )
    assert ingest_res.ok is True

    # Simulate vector embedding service being unconfigured/unavailable
    def mock_store_chunks_degraded(self, chunks):
        self._last_degraded_reason = "embedding_unavailable"
        return 0

    monkeypatch.setattr(VectorProjectionWriter, "_store_chunks", mock_store_chunks_degraded)

    _, proposal = split_chapter_and_changes(prose)
    extraction_result = {
        "chapter_meta": {},
        "accepted_events": [
            {
                "event_type": "character_state_changed",
                "subject": "林越",
                "summary": "调查白塔档案",
                "payload": {"status": "推进调查"},
            }
        ],
        "state_deltas": [],
        "entity_deltas": [],
    }
    recon = reconcile_changes(proposal, extraction_result, chapter_text=prose)

    commit_res = runtime.commit(
        chapter=1,
        draft_id=ingest_res.draft_id,
        review_result={
            "blocking_count": 0,
            "must_check_results": [{"node": "档案核验", "passed": True}],
            "blocking_rule_results": [],
        },
        fulfillment_result={
            "planned_nodes": ["档案核验"],
            "covered_nodes": ["档案核验"],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        disambiguation_result={"pending": []},
        extraction_result=extraction_result,
        reconciliation_result=recon if isinstance(recon, dict) else recon.to_dict(),
    )

    assert commit_res.ok is True
    assert commit_res.chapter_outcome == "accepted"
    assert commit_res.durable_commit_persisted is True
    assert commit_res.projection_success is True
    assert commit_res.projection_status.get("vector") == "skipped"

    # Publishing the genuine accepted draft succeeds
    published = runtime.publish_accepted_draft(chapter=1, draft_id=ingest_res.draft_id)
    assert published.is_file()
