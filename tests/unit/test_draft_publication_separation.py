#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression test suite for PR B: Draft / Publication Separation.

Verifies:
1. 正文 + 合法 CHANGES → accepted → 正式正文纯净（绝不含 <chapter_changes> 或内部协议内容）。
2. 没有 accepted commit → 不允许发布。
3. draft_id 不匹配 → 不允许发布。
4. 发布内容被篡改 → 拒绝（内部指纹、chapter SHA、prose SHA 各级篡改检测）。
5. 重复发布保持正确（幂等性）。
6. 发布失败后可重试，不需要重跑 Writer。
7. 现有 ChapterCommit 和 Canon 行为不变。
8. External Host 使用相同发布语义。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
import pytest

from chapter_paths import default_chapter_draft_path
from data_modules.chapter_runtime import ChapterRuntime
from data_modules.reconciliation import reconcile_changes, split_chapter_and_changes
from external_host_adapter import ExternalHostAdapter


def _setup_project(tmp_path: Path, chapter: int = 1) -> Path:
    project_root = tmp_path / "book"
    project_root.mkdir(parents=True, exist_ok=True)
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    outline_dir = project_root / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "project_info": {"title": "九霄仙途", "genre": "仙侠", "target_readers": "大众"},
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
        fp.write_text("# init\n", encoding="utf-8")

    outline_text = f"""# 第一卷\n### 第{chapter}章：登临仙门\n- 目标：通过试炼\n- 必须覆盖节点：石阶问心、身份玉牌\n- 本章禁区：禁止泄露上古传承\n"""
    (outline_dir / f"第{chapter:02d}章.md").write_text(outline_text, encoding="utf-8")
    return project_root


def _sample_working_draft(prose_body: str | None = None) -> str:
    body = prose_body or (
        "晨光熹微，白玉石阶在薄雾中若隐若现。\n"
        "林凡步履从容，一步步登上峰顶山门。\n"
        "当值执事验过灵根后，递上一枚温润的青玉令牌：“持此牌入外门，好生修持。”\n"
        "林凡躬身接过，心中暗自记下令牌背面的云雷暗纹。"
    )
    changes_json = {
        "character_state_changes": [
            {
                "character_id": "林凡",
                "change_type": "status_update",
                "importance": "normal",
                "details": "正式获得外门弟子玉牌",
            }
        ],
        "new_plot_points": [
            {
                "plot_id": "plot_enter_outer_sect",
                "importance": "normal",
                "description": "登上山门并领到外门玉牌",
            }
        ],
        "foreshadowing_actions": [],
        "location_state_changes": [],
        "faction_state_changes": [],
        "time_progression": None,
        "item_transfers": [],
        "unresolved_questions": [],
    }
    return f"{body}\n\n<chapter_changes>\n{json.dumps(changes_json, ensure_ascii=False, indent=2)}\n</chapter_changes>"


def _prepare_and_commit(runtime: ChapterRuntime, chapter: int, prose: str) -> tuple[str, dict]:
    sealed_pkg = runtime.attach_creative_brief(chapter=chapter, creative_brief="策划任务书：登临仙门")
    ingest_res = runtime.ingest_draft(
        chapter=chapter,
        package_fingerprint=sealed_pkg.package_fingerprint,
        prose=prose,
    )
    assert ingest_res.ok is True

    clean_prose, proposal = split_chapter_and_changes(prose)
    must_nodes = list(sealed_pkg.current_intent.get("directive", {}).get("must_cover_nodes", []))
    review_result = {
        "blocking_count": 0,
        "must_check_results": [{"node": n, "passed": True} for n in must_nodes],
        "blocking_rule_results": [],
    }
    extraction_result = {
        "chapter_meta": {},
        "accepted_events": [
            {
                "event_type": "character_state_changed",
                "subject": "林凡",
                "summary": "登上山门领到外门玉牌",
                "payload": {"status": "外门弟子"},
            }
        ],
        "state_deltas": [],
        "entity_deltas": [{"entity_id": "林凡", "current": {"status": "外门弟子"}}],
    }
    fulfillment_result = {
        "planned_nodes": must_nodes,
        "covered_nodes": must_nodes,
        "missed_nodes": [],
        "extra_nodes": [],
    }
    disambiguation_result = {"pending": []}
    reconciliation_result = reconcile_changes(proposal, extraction_result, chapter_text=prose)

    commit_res = runtime.commit(
        chapter=chapter,
        draft_id=ingest_res.draft_id,
        review_result=review_result,
        fulfillment_result=fulfillment_result,
        disambiguation_result=disambiguation_result,
        extraction_result=extraction_result,
        reconciliation_result=reconciliation_result,
    )
    assert commit_res.ok is True
    assert commit_res.chapter_outcome == "accepted"
    return ingest_res.draft_id, reconciliation_result


def test_1_valid_draft_with_changes_publishes_clean_prose(tmp_path: Path):
    """1. 正文 + 合法 CHANGES → accepted → 正式正文纯净，绝不含 <chapter_changes> 或协议内容。"""
    project_root = _setup_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    runtime.prepare(chapter=1, with_package=True)

    working_draft = _sample_working_draft()
    expected_clean_prose, _ = split_chapter_and_changes(working_draft)
    assert "<chapter_changes>" in working_draft
    assert "<chapter_changes>" not in expected_clean_prose

    draft_id, rec = _prepare_and_commit(runtime, chapter=1, prose=working_draft)

    published_file = runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)
    assert published_file.is_file()
    assert published_file.name == "第0001章-登临仙门.md"

    published_text = published_file.read_text(encoding="utf-8")
    assert published_text == expected_clean_prose
    assert "<chapter_changes>" not in published_text
    assert "</chapter_changes>" not in published_text
    assert "character_state_changes" not in published_text
    assert "plot_enter_outer_sect" not in published_text

    # SHA binding verification: published text SHA-256 exactly matches commit's reconciliation_prose_sha256
    commit_file = runtime.paths.commit_json(1)
    commit_data = json.loads(commit_file.read_text(encoding="utf-8"))
    accepted_prose_sha = commit_data["provenance"]["reconciliation_prose_sha256"]
    actual_pub_sha = hashlib.sha256(published_text.encode("utf-8")).hexdigest()
    assert actual_pub_sha == accepted_prose_sha


def test_2_publish_rejected_without_accepted_commit(tmp_path: Path):
    """2. 没有 accepted commit → 不允许发布。"""
    project_root = _setup_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    runtime.prepare(chapter=1, with_package=True)

    # 2A: No commit at all
    with pytest.raises(RuntimeError, match="No durable commit exists"):
        runtime.publish_accepted_draft(chapter=1, draft_id="draft-001-xyz")

    # Ingest a valid draft
    sealed = runtime.attach_creative_brief(chapter=1, creative_brief="任务书")
    prose = _sample_working_draft()
    ingest = runtime.ingest_draft(chapter=1, package_fingerprint=sealed.package_fingerprint, prose=prose)

    # 2B: Commit exists but status is 'rejected'
    commit_file = runtime.paths.commit_json(1)
    commit_file.parent.mkdir(parents=True, exist_ok=True)
    commit_file.write_text(
        json.dumps({
            "meta": {"schema_version": "story-system/v1", "status": "rejected", "chapter": 1},
            "provenance": {"reconciliation_chapter_sha256": ingest.draft_fingerprint},
        }),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Durable commit status is 'rejected', not 'accepted'"):
        runtime.publish_accepted_draft(chapter=1, draft_id=ingest.draft_id)


def test_3_publish_rejected_on_draft_id_mismatch(tmp_path: Path):
    """3. draft_id 不匹配 → 不允许发布。"""
    project_root = _setup_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    runtime.prepare(chapter=1, with_package=True)

    working_draft = _sample_working_draft()
    accepted_draft_id, _ = _prepare_and_commit(runtime, chapter=1, prose=working_draft)

    # 3A: Empty draft_id
    with pytest.raises(ValueError, match="explicit draft_id is required"):
        runtime.publish_accepted_draft(chapter=1, draft_id="")

    # 3B: Non-existent draft_id
    with pytest.raises(RuntimeError, match="Staged draft 'draft-001-ghost' not found"):
        runtime.publish_accepted_draft(chapter=1, draft_id="draft-001-ghost")

    # 3C: Another draft ingested later but NOT accepted
    sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief="任务书2")
    alt_draft = _sample_working_draft("完全不同的正文内容，意图冒充发布。")
    alt_ingest = runtime.ingest_draft(chapter=1, package_fingerprint=sealed_pkg.package_fingerprint, prose=alt_draft)
    assert alt_ingest.draft_id != accepted_draft_id

    with pytest.raises(RuntimeError, match="ACCEPTED_DRAFT_MISMATCH"):
        runtime.publish_accepted_draft(chapter=1, draft_id=alt_ingest.draft_id)


def test_4_publish_rejected_on_tampering(tmp_path: Path):
    """4. 发布内容被篡改 → 拒绝。"""
    project_root = _setup_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    runtime.prepare(chapter=1, with_package=True)

    working_draft = _sample_working_draft()
    draft_id, _ = _prepare_and_commit(runtime, chapter=1, prose=working_draft)

    # 4A: Staged draft prose tampered on disk after ingestion (internal fingerprint mismatch)
    draft_file = runtime._chapter_runtime_dir(1) / "drafts" / f"{draft_id}.json"
    draft_data = json.loads(draft_file.read_text(encoding="utf-8"))
    original_prose = draft_data["prose"]
    draft_data["prose"] = original_prose + "\n[黑客篡改追加]"
    draft_file.write_text(json.dumps(draft_data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Draft internal fingerprint mismatch"):
        runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)

    # 4B: Staged draft internal fingerprint also forged, but doesn't match commit chapter_sha
    draft_data["draft_fingerprint"] = hashlib.sha256(draft_data["prose"].encode("utf-8")).hexdigest()
    draft_file.write_text(json.dumps(draft_data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError, match="ACCEPTED_DRAFT_MISMATCH"):
        runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)

    # Restore original draft file
    draft_data["prose"] = original_prose
    draft_data["draft_fingerprint"] = hashlib.sha256(original_prose.encode("utf-8")).hexdigest()
    draft_file.write_text(json.dumps(draft_data, ensure_ascii=False), encoding="utf-8")

    # 4C: Commit provenance reconciliation_prose_sha256 tampered
    commit_file = runtime.paths.commit_json(1)
    commit_data = json.loads(commit_file.read_text(encoding="utf-8"))
    original_prose_sha = commit_data["provenance"]["reconciliation_prose_sha256"]
    commit_data["provenance"]["reconciliation_prose_sha256"] = "0" * 64
    commit_file.write_text(json.dumps(commit_data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError, match="ACCEPTED_PROSE_MISMATCH"):
        runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)

    # Restore commit
    commit_data["provenance"]["reconciliation_prose_sha256"] = original_prose_sha
    commit_file.write_text(json.dumps(commit_data, ensure_ascii=False), encoding="utf-8")

    # 4D: Malformed protocol block in draft fails closed
    corrupt_draft = "正文开头\n<chapter_changes>MALFORMED_JSON_CONTENT</chapter_changes>"
    sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief="任务书")
    corrupt_ingest = runtime.ingest_draft(chapter=1, package_fingerprint=sealed_pkg.package_fingerprint, prose=corrupt_draft)
    # Even if someone forged commit to match corrupt chapter SHA
    commit_data["provenance"]["reconciliation_chapter_sha256"] = corrupt_ingest.draft_fingerprint
    commit_file.write_text(json.dumps(commit_data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Invalid CHANGES protocol block"):
        runtime.publish_accepted_draft(chapter=1, draft_id=corrupt_ingest.draft_id)


def test_5_repeated_publication_idempotency(tmp_path: Path):
    """5. 重复发布保持正确（幂等性）。"""
    project_root = _setup_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    runtime.prepare(chapter=1, with_package=True)

    working_draft = _sample_working_draft()
    draft_id, _ = _prepare_and_commit(runtime, chapter=1, prose=working_draft)

    # First publish
    pub1 = runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)
    text1 = pub1.read_text(encoding="utf-8")

    # Second publish
    pub2 = runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)
    text2 = pub2.read_text(encoding="utf-8")

    assert pub1 == pub2
    assert text1 == text2
    assert "<chapter_changes>" not in text2


def test_6_publication_retry_without_rerunning_writer(tmp_path: Path, monkeypatch):
    """6. 发布失败后可重试，不需要重跑 Writer。"""
    project_root = _setup_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    runtime.prepare(chapter=1, with_package=True)

    working_draft = _sample_working_draft()
    draft_id, _ = _prepare_and_commit(runtime, chapter=1, prose=working_draft)

    # Simulate filesystem transient write failure on first attempt
    orig_write_text = Path.write_text
    attempt = {"count": 0}

    def flaky_write(self, text, *args, **kwargs):
        if self.parent.name == "正文" and attempt["count"] == 0:
            attempt["count"] += 1
            raise OSError("Simulated transient disk full / lock error")
        return orig_write_text(self, text, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", flaky_write)

    # Attempt 1 fails
    with pytest.raises(OSError, match="Simulated transient disk full"):
        runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)

    # Durable commit is unharmed
    commit_file = runtime.paths.commit_json(1)
    assert commit_file.is_file()
    commit_data = json.loads(commit_file.read_text(encoding="utf-8"))
    assert commit_data["meta"]["status"] == "accepted"

    # Attempt 2 retry succeeds WITHOUT re-running Writer, Reviewer, or Commit
    pub = runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)
    assert pub.is_file()
    assert "<chapter_changes>" not in pub.read_text(encoding="utf-8")


def test_7_existing_chapter_commit_and_canon_contracts_unchanged(tmp_path: Path):
    """7. 现有 ChapterCommit 和 Canon 行为不变。"""
    project_root = _setup_project(tmp_path, chapter=1)
    runtime = ChapterRuntime(project_root)
    runtime.prepare(chapter=1, with_package=True)

    working_draft = _sample_working_draft()
    draft_id, rec = _prepare_and_commit(runtime, chapter=1, prose=working_draft)

    commit_file = runtime.paths.commit_json(1)
    assert commit_file.is_file()
    commit_data = json.loads(commit_file.read_text(encoding="utf-8"))

    # Validate story-system/v1 schema contracts
    assert commit_data["meta"]["schema_version"] == "story-system/v1"
    assert commit_data["meta"]["chapter"] == 1
    assert commit_data["meta"]["status"] == "accepted"

    # Provenance contains all required fields
    prov = commit_data["provenance"]
    assert prov["write_fact_role"] == "chapter_commit"
    assert prov["projection_role"] == "derived_read_models"
    assert "reconciliation_observed_sha256" in prov
    assert "reconciliation_proposed_sha256" in prov
    assert "reconciliation_chapter_sha256" in prov
    assert "reconciliation_prose_sha256" in prov

    # Outline snapshot
    assert "planned_nodes" in commit_data["outline_snapshot"]
    assert "covered_nodes" in commit_data["outline_snapshot"]

    # Postcommit projections are written
    state_file = project_root / ".webnovel" / "state.json"
    assert state_file.is_file()


def test_8_external_host_uses_identical_publication_semantics(tmp_path: Path):
    """8. External Host 使用相同发布语义。"""
    project_root = _setup_project(tmp_path, chapter=1)
    evidence_dir = tmp_path / "evidence"

    adapter = ExternalHostAdapter(project_root=project_root, evidence_dir=evidence_dir)
    res = adapter.run_chapter(
        chapter=1,
        creative_brief="1. 开篇：登临仙门\n2. 故事：石阶问心，执事发牌\n3. 代价：暗纹被记下\n4. 必须覆盖：石阶问心、身份玉牌",
    )
    commit_res = res["commit_res"]
    assert commit_res.ok is True
    assert commit_res.chapter_outcome == "accepted"

    # Read draft receipt
    draft_receipt = json.loads((evidence_dir / "draft_receipt.json").read_text(encoding="utf-8"))
    draft_id = draft_receipt["draft_id"]

    # ExternalHostAdapter publishes via public runtime facade
    published_path = adapter.publish_accepted_draft(chapter=1, draft_id=draft_id)
    assert published_path.is_file()
    assert published_path.name == "第0001章-登临仙门.md"

    pub_text = published_path.read_text(encoding="utf-8")
    assert "<chapter_changes>" not in pub_text
    assert "</chapter_changes>" not in pub_text
    assert "问心石" in pub_text

    # External host also fails closed on invalid draft_id
    with pytest.raises(RuntimeError, match="Staged draft 'fake-draft' not found"):
        adapter.publish_accepted_draft(chapter=1, draft_id="fake-draft")
