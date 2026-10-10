#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests verifying protection of existing story contracts from silent regeneration (Issue #29 Phase 4)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from data_modules.chapter_runtime import ChapterRuntime
from data_modules.reconciliation import reconcile_changes, split_chapter_and_changes


def _setup_minimal_book_project(tmp_path: Path, chapter: int = 1) -> Path:
    """Create a minimal valid book project containing ONLY state and outline."""
    project_root = tmp_path / "test_book"
    project_root.mkdir(parents=True, exist_ok=True)
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    outline_dir = project_root / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "project_info": {
            "title": "测试纪元",
            "genre": "玄幻",
            "target_readers": "大众",
        },
        "progress": {
            "current_volume": 1,
            "current_chapter": 0,
            "total_volumes": 3,
            "volumes_planned": [
                {"volume": 1, "chapters_range": "1-10", "title": "第一卷 觉醒"}
            ],
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

    outline_text = f"""# 第一卷 觉醒

### 第{chapter}章：初入宗门
- 目标：主角林凡通过灵根测试进入天阳宗
- 阻力：外门执事李执事的刁难与轻视
- 代价：暴露残缺玉佩的微弱异动
- 必须覆盖节点：灵根测试、执事刁难、入宗铭牌
- 本章禁区：禁止直接突破练气三层、禁止暴露太古神帝记忆
- 章末问题：玉佩深处的封印因何松动？

### 第{chapter + 1}章：藏经阁之争
- 目标：林凡在藏经阁寻找基础吐纳法，引发未来暗线
- 阻力：外门大弟子王霸的阻挠
- 必须覆盖节点：挑选残破古经、结下梁子

### 第{chapter + 2}章：外门大比
- 目标：崭露头角
- 阻力：同门挑战
- 必须覆盖节点：擂台比试

### 第{chapter + 3}章：后山密林
- 目标：探索秘境
- 阻力：妖兽袭击
- 必须覆盖节点：击退妖兽
"""
    (outline_dir / "第1卷-详细大纲.md").write_text(outline_text, encoding="utf-8")
    return project_root


def _valid_test_prose(fp: str | None = None) -> str:
    fp_text = fp or "placeholder_fp"
    return f"""林凡深吸了一口气，将手掌轻轻按在冰凉的测试石柱上。
石柱沉寂数息，随后亮起三道驳杂的霞光。
李执事皱起眉头，神情带着几分轻视：“杂灵根，勉强入外门。”
林凡领下青铜铭牌，胸口的残缺玉佩忽然微微一热。
封包指纹：{fp_text}

<chapter_changes>
{{
  "character_state_changes": [
    {{
      "character_id": "林凡",
      "change_type": "status_update",
      "importance": "normal",
      "details": "成为天阳宗外门弟子"
    }}
  ],
  "new_plot_points": [
    {{
      "plot_id": "plot_enter_sect",
      "importance": "normal",
      "description": "通过测试进入天阳宗"
    }}
  ],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}}
</chapter_changes>"""


def _complete_semantic_artifacts(prose: str | None = None) -> dict:
    actual_prose = prose or _valid_test_prose()
    _, proposal = split_chapter_and_changes(actual_prose)
    extraction_result = {
        "chapter_meta": {},
        "accepted_events": [
            {
                "event_type": "character_state_changed",
                "subject": "林凡",
                "summary": "通过灵根测试进入天阳宗",
                "payload": {"status": "外门弟子"},
            }
        ],
        "state_deltas": [],
        "entity_deltas": [
            {
                "entity_id": "林凡",
                "current": {"identity": "外门弟子"},
            }
        ],
    }
    reconciliation_result = reconcile_changes(
        proposal, extraction_result, chapter_text=actual_prose
    )
    return {
        "review_result": {
            "blocking_count": 0,
            "must_check_results": [{"node": "灵根测试", "passed": True}],
            "blocking_rule_results": [],
        },
        "extraction_result": extraction_result,
        "fulfillment_result": {
            "planned_nodes": ["灵根测试"],
            "covered_nodes": ["灵根测试"],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        "disambiguation_result": {"pending": []},
        "reconciliation_result": reconciliation_result,
    }


def test_new_project_can_initialize_contracts(tmp_path: Path):
    """A truly uninitialized project (ch 1, no commits, current_chapter 0) can initialize contracts."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    assert not runtime.paths.master_json.exists()
    assert not runtime.paths.anti_patterns_json.exists()
    assert not runtime.paths.chapter_json(1).exists()

    prep = runtime.prepare(chapter=1, with_package=False)
    assert prep.ok is True
    assert prep.status == "ready"
    assert runtime.paths.master_json.is_file()
    assert runtime.paths.anti_patterns_json.is_file()
    assert runtime.paths.chapter_json(1).is_file()


def test_existing_story_with_valid_contracts_prepares_normally(tmp_path: Path):
    """An existing story (committed chapter 1) with intact foundational contracts prepares next chapter normally."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    # Walk chapter 1 through draft and commit to establish durable history
    prep1 = runtime.prepare(chapter=1, with_package=True, creative_brief="第一章策划任务书")
    assert prep1.ok is True
    assert prep1.writer_package is not None

    prose = _valid_test_prose(prep1.writer_package.package_fingerprint)
    artifacts = _complete_semantic_artifacts(prose)
    ingest_res = runtime.ingest_draft(chapter=1, prose=prose, package_fingerprint=prep1.writer_package.package_fingerprint)
    assert ingest_res.ok is True

    outcome = runtime.commit(
        chapter=1,
        draft_id=ingest_res.draft_id,
        artifacts=artifacts,
    )
    assert outcome.ok is True
    assert runtime._has_durable_story_history() is True

    # Master contract exists and is preserved
    orig_master_content = runtime.paths.master_json.read_text(encoding="utf-8")

    # Now prepare chapter 2
    prep2 = runtime.prepare(chapter=2, with_package=False)
    assert prep2.ok is True
    assert runtime.paths.master_json.read_text(encoding="utf-8") == orig_master_content


def test_existing_story_missing_master_setting_fails_closed(tmp_path: Path):
    """An existing story with missing MASTER_SETTING.json must fail closed and NOT regenerate plausible truth."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    # Commit chapter 1 to establish durable history
    prep1 = runtime.prepare(chapter=1, with_package=True, creative_brief="第一章策划任务书")
    assert prep1.ok is True
    assert prep1.writer_package is not None
    prose = _valid_test_prose(prep1.writer_package.package_fingerprint)
    artifacts = _complete_semantic_artifacts(prose)
    ingest_res = runtime.ingest_draft(chapter=1, prose=prose, package_fingerprint=prep1.writer_package.package_fingerprint)
    runtime.commit(chapter=1, draft_id=ingest_res.draft_id, artifacts=artifacts)

    assert runtime._has_durable_story_history() is True

    # Delete MASTER_SETTING.json
    runtime.paths.master_json.unlink()
    assert not runtime.paths.master_json.exists()

    # Attempting to prepare chapter 2 must fail and NOT recreate MASTER_SETTING.json
    prep2 = runtime.prepare(chapter=2, with_package=False)
    assert prep2.ok is False
    assert prep2.status == "contract_generation_failed"
    assert "Automatic truth regeneration is forbidden" in (prep2.error or "")
    assert not runtime.paths.master_json.exists()

    # Direct call to _ensure_story_contracts must raise RuntimeError
    with pytest.raises(RuntimeError, match="Automatic truth regeneration is forbidden"):
        runtime._ensure_story_contracts(2)

    assert not runtime.paths.master_json.exists()


def test_existing_story_missing_anti_patterns_fails_closed(tmp_path: Path):
    """An existing story with missing anti_patterns.json must fail closed and NOT regenerate plausible truth."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    # Establish durable history by advancing state progress current_chapter
    state_file = project_root / ".webnovel" / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["progress"]["current_chapter"] = 1
    state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    # Set up master contract
    runtime.paths.master_json.parent.mkdir(parents=True, exist_ok=True)
    runtime.paths.master_json.write_text(json.dumps({"meta": {"schema_version": "v1"}}, ensure_ascii=False), encoding="utf-8")

    assert runtime._has_durable_story_history() is True
    assert not runtime.paths.anti_patterns_json.exists()

    prep = runtime.prepare(chapter=2, with_package=False)
    assert prep.ok is False
    assert prep.status == "contract_generation_failed"
    assert "anti_patterns.json" in (prep.error or "")
    assert "Automatic truth regeneration is forbidden" in (prep.error or "")
    assert not runtime.paths.anti_patterns_json.exists()


def test_corrupted_master_setting_fails_closed_without_overwriting(tmp_path: Path):
    """A corrupted MASTER_SETTING.json must fail closed and must not be overwritten."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    # Put corrupted content
    corrupted_content = "{ broken json content ..."
    runtime.paths.master_json.parent.mkdir(parents=True, exist_ok=True)
    runtime.paths.master_json.write_text(corrupted_content, encoding="utf-8")

    prep = runtime.prepare(chapter=1, with_package=False)
    assert prep.ok is False
    assert prep.status == "contract_generation_failed"
    assert "corrupted" in (prep.error or "").lower()

    # Verify original corrupted content was NOT overwritten with plausible truth
    assert runtime.paths.master_json.read_text(encoding="utf-8") == corrupted_content


def test_corrupted_contract_integrity_preservation(tmp_path: Path):
    """Failure to prepare due to missing/corrupted contracts leaves state and commits completely untouched."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    # Commit chapter 1
    prep1 = runtime.prepare(chapter=1, with_package=True, creative_brief="第一章策划任务书")
    assert prep1.ok is True
    assert prep1.writer_package is not None
    prose = _valid_test_prose(prep1.writer_package.package_fingerprint)
    artifacts = _complete_semantic_artifacts(prose)
    ingest_res = runtime.ingest_draft(chapter=1, prose=prose, package_fingerprint=prep1.writer_package.package_fingerprint)
    runtime.commit(chapter=1, draft_id=ingest_res.draft_id, artifacts=artifacts)

    state_before = (project_root / ".webnovel" / "state.json").read_text(encoding="utf-8")
    commit_file = runtime.paths.commit_json(1)
    commit_before = commit_file.read_text(encoding="utf-8")

    # Corrupt chapter 2 contract with invalid JSON
    ch2_path = runtime.paths.chapter_json(2)
    ch2_path.parent.mkdir(parents=True, exist_ok=True)
    ch2_path.write_text("invalid json", encoding="utf-8")

    prep2 = runtime.prepare(chapter=2, with_package=False)
    assert prep2.ok is False

    # Check state and commit are byte-for-byte untouched
    assert (project_root / ".webnovel" / "state.json").read_text(encoding="utf-8") == state_before
    assert commit_file.read_text(encoding="utf-8") == commit_before
