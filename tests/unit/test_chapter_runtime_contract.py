#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract tests for ChapterRuntime public surface (Issue #25)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from data_modules.chapter_runtime import ChapterRuntime


def _setup_minimal_book_project(tmp_path: Path, chapter: int = 1) -> Path:
    """Create a minimal valid book project containing ONLY state and outline."""
    project_root = tmp_path / "test_book"
    project_root.mkdir(parents=True, exist_ok=True)
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    outline_dir = project_root / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)

    # 1. state.json (no private story-system contracts)
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

    # 2. Outline with current chapter and future chapter
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
"""
    (outline_dir / "第1卷-详细大纲.md").write_text(outline_text, encoding="utf-8")
    return project_root


def test_runtime_happy_path(tmp_path: Path):
    """Happy-path: prepare -> package -> ingest-draft -> commit -> verify durable commit and projection."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    # 1. Prepare chapter 1
    prep = runtime.prepare(chapter=1, with_package=True)
    assert prep.ok is True
    assert prep.chapter == 1
    assert prep.status == "ready"
    assert prep.writer_package is not None

    # 2. Assert story identity
    pkg = prep.writer_package
    assert pkg.story_identity["title"] == "测试纪元"
    assert pkg.story_identity["genre"] == "玄幻"

    # 3. Assert current chapter intent is present
    assert pkg.current_intent["chapter"] == 1
    assert "灵根测试" in str(pkg.current_intent)
    assert "天阳宗" in str(pkg.current_intent)

    # 4. Assert future chapter intent is strictly absent
    # Chapter 2 intent mentions "藏经阁之争" and "大弟子王霸"
    assert "藏经阁之争" not in str(pkg.current_intent)
    assert "大弟子王霸" not in str(pkg.current_intent)

    # 5. Ingest draft prose
    prose = """林凡深吸了一口气，将手掌轻轻按在冰凉的测试石柱上。
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

    ingest_res = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=pkg.package_fingerprint,
    )
    assert ingest_res.ok is True
    assert ingest_res.status == "draft_ingested"
    assert ingest_res.draft_fingerprint != ""

    # Draft ingestion MUST NOT mutate canon
    state_after_draft = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state_after_draft.get("progress", {}).get("current_chapter") == 0

    # 6. Commit attempt with native workflow artifacts
    review_result = {
        "blocking_count": 0,
        "must_check_results": [{"node": "灵根测试", "passed": True}],
        "blocking_rule_results": [],
    }
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

    commit_res = runtime.commit(
        chapter=1,
        prose=prose,
        package_fingerprint=pkg.package_fingerprint,
        review_result=review_result,
        extraction_result=extraction_result,
    )
    assert commit_res.ok is True
    assert commit_res.chapter_outcome == "accepted"
    assert commit_res.durable_commit_persisted is True
    assert commit_res.projection_success is True

    # 7. Verify durable accepted commit file exists
    commit_file = project_root / ".story-system" / "commits" / "chapter_001.commit.json"
    assert commit_file.is_file()
    commit_data = json.loads(commit_file.read_text(encoding="utf-8"))
    assert commit_data["meta"]["status"] == "accepted"

    # 8. Verify projections updated from accepted commit
    state_after_commit = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state_after_commit.get("progress", {}).get("current_chapter") == 1


def test_negative_missing_outline(tmp_path: Path):
    """Missing outline returns structured error before prose generation."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    # Chapter 99 has no outline
    prep = runtime.prepare(chapter=99, with_package=False)
    assert prep.ok is False
    assert prep.status == "missing_outline"
    assert len(prep.blockers) > 0


def test_negative_stale_package(tmp_path: Path):
    """Stale package fingerprints are rejected and cannot be committed."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    prep = runtime.prepare(chapter=1, with_package=True)
    pkg = prep.writer_package

    # Invalidate authoritative source by changing the outline
    outline_file = project_root / "大纲" / "第1卷-详细大纲.md"
    outline_file.write_text(outline_file.read_text(encoding="utf-8") + "\n- 新的重大设定变更", encoding="utf-8")

    # Ingesting with stale package fingerprint must fail
    res = runtime.ingest_draft(
        chapter=1,
        prose="某正文...",
        package_fingerprint=pkg.package_fingerprint,
    )
    assert res.ok is False
    assert res.error_code == "STALE_WRITER_PACKAGE"


def test_negative_rejected_draft_does_not_mutate_canon(tmp_path: Path):
    """A rejected draft cannot mutate Canon projection."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    prep = runtime.prepare(chapter=1, with_package=True)
    pkg = prep.writer_package

    prose = """林凡通过灵根测试。
<chapter_changes>
{
  "character_state_changes": [],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
</chapter_changes>"""

    # Supply review with blocking violation
    review_result = {
        "blocking_count": 1,
        "issues": [
            {
                "checker_id": "changes_gate",
                "gate_id": "changes_gate.R1",
                "category": "INTEGRITY",
                "authority": "SYSTEM_INTEGRITY",
                "structured_evidence": [
                    {"kind": "deterministic_validation", "identity": {"valid": False, "rule_id": "R1"}}
                ],
                "message": "CHANGES 协议校验失败",
            }
        ],
    }
    extraction_result = {
        "accepted_events": [],
        "state_deltas": [],
        "entity_deltas": [{"entity_id": "林凡", "current": {"illegal_fact": "true"}}],
    }

    commit_res = runtime.commit(
        chapter=1,
        prose=prose,
        package_fingerprint=pkg.package_fingerprint,
        review_result=review_result,
        extraction_result=extraction_result,
    )
    assert commit_res.ok is False
    assert commit_res.chapter_outcome == "rejected"

    # Canon state.json MUST NOT be updated with chapter progress or illegal entities
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state.get("progress", {}).get("current_chapter") == 0
    assert "林凡" not in state.get("entity_state", {})


def test_negative_projection_failure_leaves_durable_commit_replayable(tmp_path: Path):
    """Projection failure leaves durable commit recoverable and replayable."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    prep = runtime.prepare(chapter=1, with_package=True)
    pkg = prep.writer_package

    prose = """林凡领下外门铭牌。
<chapter_changes>
{
  "character_state_changes": [],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
</chapter_changes>"""

    # Force a failure during projection application
    with patch("data_modules.chapter_commit_service.ChapterCommitService.apply_projection_writers") as mock_proj:
        mock_proj.side_effect = RuntimeError("Simulated projection engine failure")

        with pytest.raises(RuntimeError):
            runtime.commit(
                chapter=1,
                prose=prose,
                package_fingerprint=pkg.package_fingerprint,
            )

    # Verify that the durable commit WAS written before projection failure
    commit_file = project_root / ".story-system" / "commits" / "chapter_001.commit.json"
    assert commit_file.is_file()

    # Retry projection via runtime
    retry_res = runtime.retry_projection(chapter=1)
    assert retry_res["ok"] is True


def test_private_layout_independence(tmp_path: Path):
    """Test proves caller never touches private .story-system contracts."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)

    # Verify story-system dir does not even exist yet
    story_system_dir = project_root / ".story-system"
    assert not story_system_dir.exists()

    runtime = ChapterRuntime(project_root)
    prep = runtime.prepare(chapter=1, with_package=True)
    assert prep.ok is True

    # The runtime created the contracts, not the caller
    assert (story_system_dir / "MASTER_SETTING.json").exists()
    assert (story_system_dir / "chapters" / "chapter_001.json").exists()
    assert (story_system_dir / "volumes" / "volume_001.json").exists()
    assert (story_system_dir / "reviews" / "chapter_001.review.json").exists()


def test_runtime_cli_flow(tmp_path: Path, monkeypatch, capsys):
    """Test CLI commands: prepare, package, ingest-draft, status, commit, retry-projection."""
    import sys
    from data_modules import webnovel

    project_root = _setup_minimal_book_project(tmp_path, chapter=1)

    # 1. webnovel runtime prepare
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "webnovel",
            "--project-root", str(project_root),
            "runtime", "prepare",
            "--chapter", "1",
            "--with-package",
            "--format", "json",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        webnovel.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    prep_data = json.loads(captured.out)
    assert prep_data["ok"] is True
    pkg = prep_data["writer_package"]
    pkg_fp = pkg["package_fingerprint"]

    # 2. webnovel runtime package
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "webnovel",
            "--project-root", str(project_root),
            "runtime", "package",
            "--chapter", "1",
            "--format", "json",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        webnovel.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    pkg_data = json.loads(captured.out)
    assert pkg_data["package_fingerprint"] == pkg_fp

    # 3. webnovel runtime ingest-draft
    prose = """林凡通过灵根测试。
<chapter_changes>
{
  "character_state_changes": [
    {
      "character_id": "林凡",
      "change_type": "status_update",
      "importance": "normal",
      "details": "成为外门弟子"
    }
  ],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
</chapter_changes>"""

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "webnovel",
            "--project-root", str(project_root),
            "runtime", "ingest-draft",
            "--chapter", "1",
            "--package-fingerprint", pkg_fp,
            "--prose", prose,
            "--format", "json",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        webnovel.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    ingest_data = json.loads(captured.out)
    assert ingest_data["ok"] is True
    assert ingest_data["status"] == "draft_ingested"

    # 4. webnovel runtime status
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "webnovel",
            "--project-root", str(project_root),
            "runtime", "status",
            "--chapter", "1",
            "--format", "json",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        webnovel.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    status_data = json.loads(captured.out)
    assert status_data["draft_status"] == "ingested"

    # 5. webnovel runtime commit
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "webnovel",
            "--project-root", str(project_root),
            "runtime", "commit",
            "--chapter", "1",
            "--package-fingerprint", pkg_fp,
            "--format", "json",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        webnovel.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    commit_data = json.loads(captured.out)
    assert commit_data["ok"] is True
    assert commit_data["chapter_outcome"] == "accepted"
    assert commit_data["durable_commit_persisted"] is True

    # 6. webnovel runtime retry-projection
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "webnovel",
            "--project-root", str(project_root),
            "runtime", "retry-projection",
            "--chapter", "1",
            "--format", "json",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        webnovel.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    retry_data = json.loads(captured.out)
    assert retry_data["ok"] is True

