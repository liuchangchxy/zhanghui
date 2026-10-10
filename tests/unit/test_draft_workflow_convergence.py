#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for PR3: Draft -> Review -> Commit Native Workflow Convergence."""
from __future__ import annotations

import json
import sys
from pathlib import Path
import pytest

from chapter_paths import (
    find_chapter_file,
    working_chapter_draft_path,
    default_chapter_draft_path,
)
from data_modules import webnovel
from data_modules.chapter_runtime import ChapterRuntime
from data_modules.reconciliation import reconcile_changes, split_chapter_and_changes
from data_modules.write_gates.precommit import run_precommit_gate


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
"""
    (outline_dir / "第1卷-详细大纲.md").write_text(outline_text, encoding="utf-8")
    return project_root


def _valid_test_prose() -> str:
    return """林凡深吸了一口气，将手掌轻轻按在冰凉的测试石柱上。
石柱沉寂数息，随后亮起三道驳杂的霞光。
李执事皱起眉头，神情带着几分轻视：“杂灵根，勉强入外门。”
林凡领下青铜铭牌，胸口的残缺玉佩忽然微微一热。

<chapter_changes>
{
  "character_state_changes": [
    {
      "character_id": "林凡",
      "change_type": "status_update",
      "importance": "normal",
      "details": "成为天阳宗外门弟子"
    }
  ],
  "new_plot_points": [
    {
      "plot_id": "plot_enter_sect",
      "importance": "normal",
      "description": "通过测试进入天阳宗"
    }
  ],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
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


def test_working_chapter_draft_path(tmp_path: Path):
    project_root = tmp_path / "book"
    path = working_chapter_draft_path(project_root, 7)
    assert path == project_root / ".webnovel" / "tmp" / "chapter_0007_working.md"


def test_find_chapter_file_with_include_working(tmp_path: Path):
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    
    # 1. No formal chapter file, no working draft
    assert find_chapter_file(project_root, 1) is None
    assert find_chapter_file(project_root, 1, include_working=True) is None

    # 2. Working draft exists
    working_draft = working_chapter_draft_path(project_root, 1)
    working_draft.parent.mkdir(parents=True, exist_ok=True)
    working_draft.write_text("工作草稿内容", encoding="utf-8")

    assert find_chapter_file(project_root, 1) is None
    assert find_chapter_file(project_root, 1, include_working=True) == working_draft

    # 3. Formal chapter file created; formal takes priority over working draft
    formal = default_chapter_draft_path(project_root, 1)
    formal.parent.mkdir(parents=True, exist_ok=True)
    formal.write_text("正式章节内容", encoding="utf-8")

    assert find_chapter_file(project_root, 1) == formal
    assert find_chapter_file(project_root, 1, include_working=True) == formal


def test_precommit_gate_accepts_working_draft(tmp_path: Path):
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    working_draft = working_chapter_draft_path(project_root, 1)
    working_draft.parent.mkdir(parents=True, exist_ok=True)
    working_draft.write_text(_valid_test_prose(), encoding="utf-8")

    # Formal 正文/第0001章... does not exist yet
    assert not list((project_root / "正文").glob("第0001章*"))

    gate = run_precommit_gate(project_root, chapter=1)
    # The precommit gate should not fail on missing chapter file
    missing_file_errors = [e for e in gate.get("errors", []) if e.get("code") == "missing_chapter_file"]
    assert len(missing_file_errors) == 0


def test_publish_accepted_draft_requires_accepted_commit(tmp_path: Path):
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    # 1. No durable commit exists
    with pytest.raises(RuntimeError, match="No durable commit exists"):
        runtime.publish_accepted_draft(chapter=1)

    # Prepare and ingest draft first
    runtime.prepare(chapter=1, with_package=True)
    sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief="策划任务书测试")
    prose = _valid_test_prose()
    ingest_res = runtime.ingest_draft(
        chapter=1,
        package_fingerprint=sealed_pkg.package_fingerprint,
        prose=prose,
    )
    assert ingest_res.ok is True
    draft_id = ingest_res.draft_id

    # 2. Durable commit exists but status is rejected
    commit_file = project_root / ".story-system" / "commits" / "chapter_001.commit.json"
    commit_file.parent.mkdir(parents=True, exist_ok=True)
    commit_file.write_text(
        json.dumps({
            "meta": {
                "schema_version": "story-system/v1",
                "status": "rejected",
                "chapter": 1,
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Durable commit status is 'rejected'"):
        runtime.publish_accepted_draft(chapter=1)

    # 3. Commit status is accepted, verify publish succeeds
    commit_file.write_text(
        json.dumps({
            "meta": {
                "schema_version": "story-system/v1",
                "status": "accepted",
                "chapter": 1,
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    published_file = runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)
    assert published_file.is_file()
    assert published_file.name == "第0001章-初入宗门.md"
    assert published_file.read_text(encoding="utf-8") == prose


def test_runtime_commit_with_publish_flag(tmp_path: Path):
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    runtime.prepare(chapter=1, with_package=True)
    sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief="策划任务书测试")

    prose = _valid_test_prose()
    ingest_res = runtime.ingest_draft(
        chapter=1,
        package_fingerprint=sealed_pkg.package_fingerprint,
        prose=prose,
    )
    artifacts = _complete_semantic_artifacts(prose)

    # Formal 正文 file should NOT exist yet
    formal_path = default_chapter_draft_path(project_root, 1)
    assert not formal_path.exists()

    # Commit with publish_on_accept=True
    commit_res = runtime.commit(
        chapter=1,
        draft_id=ingest_res.draft_id,
        review_result=artifacts["review_result"],
        fulfillment_result=artifacts["fulfillment_result"],
        disambiguation_result=artifacts["disambiguation_result"],
        extraction_result=artifacts["extraction_result"],
        reconciliation_result=artifacts["reconciliation_result"],
        publish_on_accept=True,
    )
    assert commit_res.ok is True
    assert commit_res.chapter_outcome == "accepted"
    assert commit_res.published_file == str(formal_path)
    assert formal_path.is_file()
    assert formal_path.read_text(encoding="utf-8") == prose


def test_cli_runtime_commit_publish_and_publish_draft(tmp_path: Path, monkeypatch, capsys):
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    runtime.prepare(chapter=1, with_package=True)
    sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief="策划任务书测试")

    prose = _valid_test_prose()
    ingest_res = runtime.ingest_draft(
        chapter=1,
        package_fingerprint=sealed_pkg.package_fingerprint,
        prose=prose,
    )
    artifacts = _complete_semantic_artifacts(prose)
    art_files = {}
    for name, content in artifacts.items():
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
        art_files[name] = str(p)

    # CLI commit with --publish
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "webnovel",
            "--project-root", str(project_root),
            "runtime", "commit",
            "--chapter", "1",
            "--draft-id", ingest_res.draft_id,
            "--review-result", art_files["review_result"],
            "--fulfillment-result", art_files["fulfillment_result"],
            "--disambiguation-result", art_files["disambiguation_result"],
            "--extraction-result", art_files["extraction_result"],
            "--reconciliation-result", art_files["reconciliation_result"],
            "--publish",
            "--format", "json",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        webnovel.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    res_data = json.loads(captured.out)
    assert res_data["ok"] is True
    assert res_data["published_file"] is not None
    published_file = Path(res_data["published_file"])
    assert published_file.is_file()

    # CLI publish-draft subcommand works idempotently
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "webnovel",
            "--project-root", str(project_root),
            "runtime", "publish-draft",
            "--chapter", "1",
            "--draft-id", ingest_res.draft_id,
            "--format", "json",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        webnovel.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    pub_data = json.loads(captured.out)
    assert pub_data["ok"] is True
    assert pub_data["published_file"] == str(published_file)


def test_polish_invalidation_generates_new_draft_id(tmp_path: Path):
    """When targeted polish modifies text, re-ingest must produce a distinct draft_id and fingerprint."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    runtime.prepare(chapter=1, with_package=True)
    sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief="策划任务书测试")

    prose_v1 = _valid_test_prose()
    ingest_v1 = runtime.ingest_draft(
        chapter=1,
        package_fingerprint=sealed_pkg.package_fingerprint,
        prose=prose_v1,
    )
    assert ingest_v1.ok is True

    # Modified prose from targeted polish
    prose_v2 = prose_v1.replace("林凡深吸了一口气", "林凡长长吐出一口浊气")
    ingest_v2 = runtime.ingest_draft(
        chapter=1,
        package_fingerprint=sealed_pkg.package_fingerprint,
        prose=prose_v2,
    )
    assert ingest_v2.ok is True

    assert ingest_v1.draft_id != ingest_v2.draft_id
    assert ingest_v1.draft_fingerprint != ingest_v2.draft_fingerprint


def test_skill_md_enforces_draft_review_commit_convergence():
    """Verify SKILL.md text strictly defines working draft, re-review, runtime commit, and publication gate."""
    skill_path = Path(__file__).resolve().parent.parent.parent / ".claude" / "plugins" / "zhanghui" / "skills" / "webnovel-write" / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")

    # Working draft isolation
    assert "chapter_{chapter_padded}_working.md" in text
    assert "严禁在正式提交 accepted 前直接创建或覆盖正式" in text

    # Runtime draft ingestion
    assert "runtime ingest-draft" in text

    # Targeted polish invalidation rule
    assert "Targeted Polish Invalidation Rule" in text
    assert "旧草稿的审查结果彻底失效" in text

    # Runtime commit & publication gate
    assert "runtime commit" in text
    assert "--publish" in text
    assert "runtime publish-draft" in text
    assert "Publication Gate" in text or "发布门禁" in text
    assert "chapter-commit rejected" in text

    # Projection retry
    assert "runtime retry-projection" in text
    assert "projections retry --chapter {chapter_num}" in text
