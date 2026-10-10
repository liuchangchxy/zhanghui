#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract tests for ChapterRuntime public surface (Issue #25)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest

from data_modules.config import DataModulesConfig
from data_modules.context_manager import ContextManager
from data_modules.chapter_runtime import ChapterRuntime
from data_modules.reconciliation import reconcile_changes, split_chapter_and_changes
from data_modules.write_gates import run_write_gate
from changes_gate import run_changes_gate


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

    # Initialized scaffold dirs & files for a valid book project
    for d in (".webnovel/backups", ".webnovel/archive", ".webnovel/summaries", "设定集", "正文", "审查报告"):
        (project_root / d).mkdir(parents=True, exist_ok=True)
    for f in ("设定集/世界观.md", "设定集/力量体系.md", "设定集/主角卡.md", "设定集/反派设计.md", "大纲/总纲.md", ".env.example"):
        fp = project_root / f
        fp.parent.mkdir(parents=True, exist_ok=True)
        if not fp.exists():
            fp.write_text("# init\n", encoding="utf-8")

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


def test_runtime_happy_path(tmp_path: Path):
    """Happy-path: prepare -> package -> ingest-draft -> commit(draft_id) -> durable commit and projection."""
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
    assert "藏经阁之争" not in str(pkg.current_intent)
    assert "大弟子王霸" not in str(pkg.current_intent)

    # 4b. Context Agent seals the package with authentic creative brief
    sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief="【策划任务书】林凡问心石测试，隐忍藏拙。")
    assert sealed_pkg.is_writer_ready is True

    # 5. Ingest draft prose
    prose = _valid_test_prose()
    ingest_res = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=sealed_pkg.package_fingerprint,
    )
    assert ingest_res.ok is True
    assert ingest_res.status == "draft_ingested"
    assert ingest_res.draft_id.startswith("draft-001-")
    assert ingest_res.draft_fingerprint != ""

    # Draft ingestion MUST NOT mutate canon
    state_after_draft = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state_after_draft.get("progress", {}).get("current_chapter") == 0

    # 6. Commit attempt strictly with draft_id and complete native artifacts
    artifacts = _complete_semantic_artifacts(prose)
    commit_res = runtime.commit(
        chapter=1,
        draft_id=ingest_res.draft_id,
        **artifacts,
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


def test_writer_package_traces_to_context_manager(tmp_path: Path):
    """Verify WriterPackage fields trace back to native ContextManager output."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    pkg = runtime.get_writer_package(1)
    cfg = DataModulesConfig.from_project_root(project_root)
    ctx_mgr = ContextManager(cfg)
    native_ctx = ctx_mgr.build_context(1)

    # Trace story identity
    assert pkg.story_identity["title"] == "测试纪元"

    # Trace current intent to ContextManager outline
    assert pkg.current_intent["outline"] == native_ctx["core"]["chapter_outline"]
    assert "灵根测试" in pkg.current_intent["outline"]

    # Trace governed canon and reference to ContextManager outputs
    assert pkg.governed_canon["canon_items"] == [
        item.to_dict() if hasattr(item, "to_dict") else item for item in native_ctx["canon"]
    ]
    assert pkg.writer_context["context_contract_version"] == native_ctx["meta"]["context_contract_version"]

    # Verify future intent isolation
    assert "藏经阁之争" not in str(pkg.current_intent)

    # Trace provenance authority
    assert pkg.meta.get("native_context_authority") == "ContextManager.build_context"


def test_commit_requires_draft_id(tmp_path: Path):
    """Calling commit without draft_id returns WORKFLOW_INCOMPLETE."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    prep = runtime.prepare(chapter=1, with_package=True)

    artifacts = _complete_semantic_artifacts()
    res = runtime.commit(chapter=1, **artifacts)
    assert res.ok is False
    assert res.error_code == "WORKFLOW_INCOMPLETE"
    assert res.next_required_action == "ingest_draft"
    assert "draft_id" in (res.required_artifacts or [])


def test_commit_rejects_unknown_draft_id(tmp_path: Path):
    """Calling commit with non-existent draft_id returns UNKNOWN_DRAFT."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    prep = runtime.prepare(chapter=1, with_package=True)

    artifacts = _complete_semantic_artifacts()
    res = runtime.commit(chapter=1, draft_id="draft-001-nonexistent", **artifacts)
    assert res.ok is False
    assert res.error_code == "UNKNOWN_DRAFT"


def test_commit_rejects_tampered_staged_draft(tmp_path: Path):
    """Tampering with staged draft causes DRAFT_FINGERPRINT_MISMATCH rejection."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    prep = runtime.prepare(chapter=1, with_package=True, creative_brief="测试策划")
    pkg = prep.writer_package

    prose = _valid_test_prose()
    ingest_res = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=pkg.package_fingerprint,
    )
    draft_id = ingest_res.draft_id

    # Tamper with staged draft file
    draft_file = project_root / ".webnovel" / "runtime" / "chapter_001" / "drafts" / f"{draft_id}.json"
    draft_data = json.loads(draft_file.read_text(encoding="utf-8"))
    draft_data["prose"] = draft_data["prose"] + "\n恶意篡改的正文"
    draft_file.write_text(json.dumps(draft_data, ensure_ascii=False), encoding="utf-8")

    artifacts = _complete_semantic_artifacts(prose)
    res = runtime.commit(chapter=1, draft_id=draft_id, **artifacts)
    assert res.ok is False
    assert res.error_code == "DRAFT_FINGERPRINT_MISMATCH"


def test_commit_rejects_missing_semantic_artifacts(tmp_path: Path):
    """Omitting any required semantic artifact returns REQUIRED_ARTIFACTS_MISSING with no fake defaults."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    prep = runtime.prepare(chapter=1, with_package=True, creative_brief="测试策划")
    pkg = prep.writer_package

    prose = _valid_test_prose()
    ingest_res = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=pkg.package_fingerprint,
    )

    artifacts = _complete_semantic_artifacts(prose)
    # Omit review_result
    artifacts.pop("review_result")

    res = runtime.commit(chapter=1, draft_id=ingest_res.draft_id, **artifacts)
    assert res.ok is False
    assert res.error_code == "REQUIRED_ARTIFACTS_MISSING"
    assert "review_result" in res.required_artifacts
    assert res.next_required_action == "generate_review_result"


def test_changes_gate_parity_against_native(tmp_path: Path):
    """Verify Runtime uses authoritative changes_gate: R01/R02 pass but R03 fails identically."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)

    # Initialize a valid index.db with one registered entity "张三"
    from data_modules.index_manager import IndexManager, EntityMeta
    cfg = DataModulesConfig.from_project_root(project_root)
    idx = IndexManager(cfg)
    idx.upsert_entity(EntityMeta(
        id="zhangsan", type="角色", canonical_name="张三",
        current={}, first_appearance=1, last_appearance=1
    ))

    # Prose contains R01/R02-compliant CHANGES, but references unknown character "未知神秘人999" (fails R03)
    prose = """林凡遇到未知神秘人。
<chapter_changes>
{
  "character_state_changes": [
    {
      "character_id": "未知神秘人999",
      "change_type": "status_update",
      "importance": "normal",
      "details": "突然现身"
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

    # 1. Native changes_gate call
    native_gate = run_changes_gate(
        chapter_text=prose,
        db_path=project_root / ".webnovel" / "index.db",
        state_path=project_root / ".webnovel" / "state.json",
        chapter=1,
    )
    assert native_gate.passed is False
    assert any(f.rule_id == "R3" for f in native_gate.failures)

    # 2. Runtime commit call on staged draft with same prose
    runtime = ChapterRuntime(project_root)
    prep = runtime.prepare(chapter=1, with_package=True, creative_brief="测试策划")
    ingest_res = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=prep.writer_package.package_fingerprint,
    )

    artifacts = _complete_semantic_artifacts(prose)
    res = runtime.commit(chapter=1, draft_id=ingest_res.draft_id, **artifacts)
    assert res.ok is False
    assert res.chapter_outcome == "rejected"
    # Canon remained unmutated
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state.get("progress", {}).get("current_chapter") == 0


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

    prep = runtime.prepare(chapter=1, with_package=True, creative_brief="测试策划")
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

    prep = runtime.prepare(chapter=1, with_package=True, creative_brief="测试策划")
    pkg = prep.writer_package
    # Broken CHANGES block triggers hard R1 rejection from native changes-gate
    prose = """林凡通过灵根测试。
<chapter_changes>
{
  "invalid_schema": true
}
</chapter_changes>"""

    ingest_res = runtime.ingest_draft(
        chapter=1, prose=prose, package_fingerprint=pkg.package_fingerprint
    )

    artifacts = _complete_semantic_artifacts()
    commit_res = runtime.commit(
        chapter=1,
        draft_id=ingest_res.draft_id,
        **artifacts,
    )
    assert commit_res.ok is False
    assert commit_res.chapter_outcome == "rejected"

    # Canon state.json MUST NOT be updated with chapter progress
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state.get("progress", {}).get("current_chapter") == 0


def test_negative_projection_failure_leaves_durable_commit_replayable(tmp_path: Path):
    """Projection failure leaves durable commit recoverable and replayable."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)

    prep = runtime.prepare(chapter=1, with_package=True, creative_brief="测试策划")
    pkg = prep.writer_package
    prose = _valid_test_prose()

    ingest_res = runtime.ingest_draft(
        chapter=1, prose=prose, package_fingerprint=pkg.package_fingerprint
    )
    artifacts = _complete_semantic_artifacts(prose)

    # Force a failure during projection application
    with patch("data_modules.chapter_commit_service.ChapterCommitService.apply_projection_writers") as mock_proj:
        mock_proj.side_effect = RuntimeError("Simulated projection engine failure")

        with pytest.raises(RuntimeError):
            runtime.commit(
                chapter=1,
                draft_id=ingest_res.draft_id,
                **artifacts,
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

    # 2b. webnovel runtime attach-creative-brief
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "webnovel",
            "--project-root", str(project_root),
            "runtime", "attach-creative-brief",
            "--chapter", "1",
            "--brief", "【策划任务书】测试策划内容",
            "--format", "json",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        webnovel.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    brief_data = json.loads(captured.out)
    sealed_fp = brief_data["package_fingerprint"]

    # 3. webnovel runtime ingest-draft
    prose = _valid_test_prose()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "webnovel",
            "--project-root", str(project_root),
            "runtime", "ingest-draft",
            "--chapter", "1",
            "--package-fingerprint", sealed_fp,
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
    draft_id = ingest_data["draft_id"]

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

    # Write temporary artifact files for commit CLI
    artifacts = _complete_semantic_artifacts(prose)
    art_files = {}
    for name, content in artifacts.items():
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
        art_files[name] = str(p)

    # 5. webnovel runtime commit
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "webnovel",
            "--project-root", str(project_root),
            "runtime", "commit",
            "--chapter", "1",
            "--draft-id", draft_id,
            "--review-result", art_files["review_result"],
            "--fulfillment-result", art_files["fulfillment_result"],
            "--disambiguation-result", art_files["disambiguation_result"],
            "--extraction-result", art_files["extraction_result"],
            "--reconciliation-result", art_files["reconciliation_result"],
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


def test_negative_prewrite_gate_blocks_prepare_when_native_gate_fails(tmp_path: Path):
    """Verify prepare() fails closed with status='blocked' when native write-gate returns ok=False."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)

    # Inject a legal scenario causing native prewrite gate to block:
    # high-priority disambiguation_pending triggers PrewriteValidator blocking
    state_path = project_root / ".webnovel" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["disambiguation_pending"] = [
        {"entity_id": "unresolved_sword", "reason": "high-priority ambiguity pending resolution"}
    ]
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    runtime = ChapterRuntime(project_root)
    prep = runtime.prepare(1, with_package=True)

    # Native write-gate evaluated on this prepared project must legitimately return ok=False
    native_gate = run_write_gate(project_root, chapter=1, stage="prewrite")
    assert native_gate["ok"] is False
    assert len(native_gate["errors"]) > 0

    # Runtime prepare() must report blocked without generating a writer package
    assert prep.ok is False
    assert prep.status == "blocked"
    assert prep.writer_package is None
    # Blockers and advisories must directly match native gate schema
    assert prep.blockers == native_gate["errors"]
    assert prep.advisories == native_gate.get("warnings", [])
    assert any(b.get("code") == "prewrite_validator_blocking" for b in prep.blockers)


def test_negative_prewrite_gate_exception_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify prepare() fails closed if native write-gate execution raises an unhandled exception."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)

    def _broken_gate(*args, **kwargs):
        raise RuntimeError("Simulated gate infrastructure crash")

    monkeypatch.setattr("data_modules.chapter_runtime.run_write_gate", _broken_gate)

    runtime = ChapterRuntime(project_root)
    prep = runtime.prepare(1, with_package=True)

    assert prep.ok is False
    assert prep.status != "ready"
    assert prep.status == "prewrite_gate_failed"
    assert prep.writer_package is None
    assert any("Simulated gate infrastructure crash" in b.get("message", "") for b in prep.blockers)

