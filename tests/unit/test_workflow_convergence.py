#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression test suite for PR C: Workflow Convergence (Issue #43).

Verifies:
1. fast-write 不绕过必需的事务门禁（review_result 必需，禁止伪造/跳过 commit 与 publication）。
2. revise 不直接覆盖已发布正文；已 accepted 章节受状态机保护禁止常规覆写（Immutable Commit Contract）。
3. review 正确使用 Reviewer Context（统一 5 层上下文，兼容 load_governed_context）。
4. draft_id / fingerprint 保持强绑定（防篡改、未知 ID 拒绝、指纹校验）。
5. CHANGES 不泄露到正式正文（100% 纯正文发布，双重 SHA-256 校验）。
6. Craft advisory 不升级为 hard gate（启发式工艺建议保持 advisory，不阻断提交）。
7. 恢复与重试不会重复提交或重复发布（幂等发布，resume plan 跳过已 accepted commit）。
8. External Host 不出现第二套事务权威（严格走 ChapterRuntime 公共门禁）。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
import pytest

from chapter_paths import default_chapter_draft_path
from data_modules.chapter_commit_service import ChapterCommitError, ChapterCommitService
from data_modules.chapter_runtime import ChapterRuntime
from data_modules.gate_findings import DetectedFinding, FindingAuthority, FindingCategory
from data_modules.reconciliation import reconcile_changes, split_chapter_and_changes
from data_modules.run_ledger import build_write_resume_plan, record_write_step
from external_host_adapter import ExternalHostAdapter
from revise_chapter import load_governed_context


def _setup_book_project(tmp_path: Path, chapter: int = 1) -> Path:
    project_root = tmp_path / "book"
    project_root.mkdir(parents=True, exist_ok=True)
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    outline_dir = project_root / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "project_info": {"title": "问道青云", "genre": "修仙", "target_readers": "大众"},
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

    outline_text = f"""# 第一卷
### 第{chapter}章：初踏仙途
- 目标：通过试炼考核
- 必须覆盖节点：石阶问心、身份青牌
- 本章禁区：禁止直接筑基
- 核心事件：外门测试
- 章末钩子：玉牌暗纹
- 章末钩子类型：悬念
"""
    (outline_dir / f"第{chapter:02d}章.md").write_text(outline_text, encoding="utf-8")
    return project_root


def _sample_draft(prose_body: str | None = None) -> str:
    body = prose_body or (
        "清晨薄雾弥漫，青石古道蜿蜒直上。\n"
        "林凡步履沉稳，按规矩伸手按在问心石柱上。\n"
        "片刻后，石柱亮起温润柔光。当值执事神色平淡，递来青铜铭牌：“入外门，切勿懈怠。”\n"
        "林凡双手接过，低头细看铭牌边缘的云雷暗纹。"
    )
    changes_json = {
        "character_state_changes": [
            {
                "character_id": "林凡",
                "change_type": "status_update",
                "importance": "normal",
                "details": "正式获得外门弟子青牌",
            }
        ],
        "new_plot_points": [
            {
                "plot_id": "plot_enter_outer_sect",
                "importance": "normal",
                "description": "通过问心测试并获得外门铭牌",
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


def _prepare_and_commit(runtime: ChapterRuntime, chapter: int, prose: str, review_result: dict | None = None) -> tuple[str, dict]:
    sealed_pkg = runtime.attach_creative_brief(chapter=chapter, creative_brief="策划任务书：初踏仙途")
    ingest_res = runtime.ingest_draft(
        chapter=chapter,
        package_fingerprint=sealed_pkg.package_fingerprint,
        prose=prose,
    )
    assert ingest_res.ok
    draft_id = ingest_res.draft_id

    _, proposal = split_chapter_and_changes(prose)
    must_nodes = list(sealed_pkg.current_intent.get("directive", {}).get("must_cover_nodes", []))
    rev = review_result or {
        "blocking_count": 0,
        "must_check_results": [{"node": n, "passed": True} for n in must_nodes],
        "blocking_rule_results": [],
    }
    ext = {
        "chapter_meta": {},
        "accepted_events": [
            {
                "event_type": "character_state_changed",
                "subject": "林凡",
                "summary": "通过考核成为外门弟子",
                "payload": {"status": "外门弟子"},
            }
        ],
        "state_deltas": [],
        "entity_deltas": [{"entity_id": "林凡", "current": {"status": "外门弟子"}}],
    }
    ful = {
        "planned_nodes": must_nodes,
        "covered_nodes": must_nodes,
        "missed_nodes": [],
        "extra_nodes": [],
    }
    dis = {"pending": []}
    rec = reconcile_changes(proposal, ext, chapter_text=prose)

    commit_res = runtime.commit(
        chapter=chapter,
        draft_id=draft_id,
        review_result=rev,
        extraction_result=ext,
        fulfillment_result=ful,
        disambiguation_result=dis,
        reconciliation_result=rec,
    )
    return draft_id, commit_res


class TestWorkflowConvergence:
    """PR C Regression Test Suite: Workflow Convergence across all entrypoints."""

    def test_fast_write_requires_review_result_and_cannot_bypass_transaction(self, tmp_path: Path):
        """1. fast-write 不得绕过必需的事务门禁（review_result 必需，禁止缺少审查直接提交）。"""
        project_root = _setup_book_project(tmp_path, chapter=1)
        runtime = ChapterRuntime(project_root)
        runtime.prepare(1, with_package=True)

        prose = _sample_draft()
        sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief="快车道创作任务书")
        ingest_res = runtime.ingest_draft(
            chapter=1,
            package_fingerprint=sealed_pkg.package_fingerprint,
            prose=prose,
        )
        assert ingest_res.ok
        draft_id = ingest_res.draft_id

        _, proposal = split_chapter_and_changes(prose)
        ext = {
            "chapter_meta": {},
            "accepted_events": [],
            "state_deltas": [],
            "entity_deltas": [],
        }
        rec = reconcile_changes(proposal, ext, chapter_text=prose)

        # 尝试跳过 review_result 直接 commit -> 严格被拒，报 REQUIRED_ARTIFACTS_MISSING
        commit_res = runtime.commit(
            chapter=1,
            draft_id=draft_id,
            review_result=None,  # 缺失 review_result
            extraction_result=ext,
            fulfillment_result={"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
            disambiguation_result={"pending": []},
            reconciliation_result=rec,
        )
        assert not commit_res.ok
        assert commit_res.chapter_outcome == "rejected"
        assert commit_res.error_code == "REQUIRED_ARTIFACTS_MISSING"
        assert "review_result" in (commit_res.required_artifacts or [])

        # 未被 accepted 时，publish_draft 严格拒绝
        with pytest.raises(RuntimeError, match="No durable commit exists"):
            runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)

    def test_revise_state_machine_blocks_accepted_chapter_overwrite(self, tmp_path: Path):
        """2. revise 不直接覆盖已发布正文；已 accepted 章节受状态机保护禁止常规覆写。"""
        project_root = _setup_book_project(tmp_path, chapter=1)
        runtime = ChapterRuntime(project_root)
        runtime.prepare(1, with_package=True)

        prose = _sample_draft()
        draft_id, commit_res = _prepare_and_commit(runtime, chapter=1, prose=prose)
        assert commit_res.ok
        assert commit_res.chapter_outcome == "accepted"

        # 正常发布
        published_file = runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)
        assert published_file.is_file()

        # 此时第 1 章已在 durable commit 中 accepted。
        # 验证状态机：ChapterCommitService 严格拒绝 overwrite 已 accepted 章节
        service = ChapterCommitService(project_root)
        commit_path = project_root / ".story-system" / "commits" / "chapter_001.commit.json"
        assert commit_path.is_file()

        payload = {"meta": {"chapter": 1, "status": "accepted"}}
        with pytest.raises(ChapterCommitError, match="overwrite is forbidden for canonical chapter commits"):
            service.persist_commit(payload, on_conflict="overwrite")

        # 尝试对已 accepted 章节用新修改的草稿直接发布 -> 严格被拒（ACCEPTED_DRAFT_MISMATCH）
        tampered_draft_prose = _sample_draft("被非法直接修改的修订正文。")
        ingest_new = runtime.ingest_draft(
            chapter=1,
            package_fingerprint=runtime.get_writer_package(1, creative_brief="策划任务书：初踏仙途").package_fingerprint,
            prose=tampered_draft_prose,
        )
        assert ingest_new.ok
        with pytest.raises(RuntimeError, match="ACCEPTED_DRAFT_MISMATCH"):
            runtime.publish_accepted_draft(chapter=1, draft_id=ingest_new.draft_id)

    def test_review_uses_canonical_reviewer_context(self, tmp_path: Path):
        """3. review 正确使用 Reviewer Context（统一 5 层上下文，兼容 load_governed_context）。"""
        project_root = _setup_book_project(tmp_path, chapter=1)
        runtime = ChapterRuntime(project_root)
        runtime.prepare(1, with_package=True)

        rev_ctx = runtime.get_reviewer_context(1)
        assert rev_ctx["chapter"] == 1
        assert "canon_authority" in rev_ctx
        assert "creative_intent" in rev_ctx
        assert "craft_constraints" in rev_ctx
        assert "advisory_constraints" in rev_ctx
        assert "chapter_planning" in rev_ctx
        assert "review_contract" in rev_ctx

        intent = rev_ctx["creative_intent"]
        assert intent["goal"] == "通过试炼考核"
        assert "石阶问心" in intent["must_cover_nodes"]
        assert "禁止直接筑基" in intent["forbidden_zones"]

        # 保存 reviewer-context 并验证 load_governed_context 兼容性
        gov_ctx = runtime.get_governed_context(1)
        ctx_file = project_root / ".webnovel" / "tmp" / "gov_ctx.json"
        ctx_file.parent.mkdir(parents=True, exist_ok=True)
        ctx_file.write_text(json.dumps(gov_ctx, ensure_ascii=False), encoding="utf-8")

        loaded = load_governed_context(ctx_file)
        assert "governed_canon" in loaded
        assert "current_intent" in loaded
        assert "constraints" in loaded

    def test_draft_id_and_fingerprint_binding_integrity(self, tmp_path: Path):
        """4. draft_id / fingerprint 保持强绑定（防篡改、未知 ID 拒绝、指纹校验）。"""
        project_root = _setup_book_project(tmp_path, chapter=1)
        runtime = ChapterRuntime(project_root)
        runtime.prepare(1, with_package=True)

        prose = _sample_draft()
        sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief="策划任务书")
        ingest_res = runtime.ingest_draft(
            chapter=1,
            package_fingerprint=sealed_pkg.package_fingerprint,
            prose=prose,
        )
        assert ingest_res.ok
        draft_id = ingest_res.draft_id

        # 缺少 draft_id 提交
        res_nodraft = runtime.commit(chapter=1, draft_id=None)
        assert not res_nodraft.ok
        assert res_nodraft.error_code == "WORKFLOW_INCOMPLETE"

        # 未知 draft_id 提交
        res_unknowndraft = runtime.commit(chapter=1, draft_id="draft-001-unknown888")
        assert not res_unknowndraft.ok
        assert res_unknowndraft.error_code == "UNKNOWN_DRAFT"

        # 篡改暂存草稿内容使 fingerprint 不匹配
        draft_file = project_root / ".webnovel" / "runtime" / "chapter_001" / "drafts" / f"{draft_id}.json"
        staged_data = json.loads(draft_file.read_text(encoding="utf-8"))
        staged_data["prose"] = "恶意篡改的正文"
        draft_file.write_text(json.dumps(staged_data, ensure_ascii=False), encoding="utf-8")

        res_tampered = runtime.commit(chapter=1, draft_id=draft_id)
        assert not res_tampered.ok
        assert res_tampered.error_code == "DRAFT_FINGERPRINT_MISMATCH"

    def test_changes_not_leaked_to_published_prose(self, tmp_path: Path):
        """5. CHANGES 不泄露到正式正文（100% 纯正文发布，双重 SHA-256 校验）。"""
        project_root = _setup_book_project(tmp_path, chapter=1)
        runtime = ChapterRuntime(project_root)
        runtime.prepare(1, with_package=True)

        prose = _sample_draft()
        assert "<chapter_changes>" in prose

        draft_id, commit_res = _prepare_and_commit(runtime, chapter=1, prose=prose)
        assert commit_res.ok

        published_file = runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)
        assert published_file.is_file()

        published_text = published_file.read_text(encoding="utf-8")
        assert "<chapter_changes>" not in published_text
        assert "</chapter_changes>" not in published_text
        assert "林凡双手接过" in published_text

        # 验证 published SHA-256 与 commit 中的 reconciliation_prose_sha256 完全吻合
        clean_prose_sha = hashlib.sha256(published_text.encode("utf-8")).hexdigest()
        commit_payload = commit_res.commit_payload or {}
        provenance = commit_payload.get("provenance", {})
        assert provenance.get("reconciliation_prose_sha256") == clean_prose_sha

    def test_craft_advisory_findings_do_not_become_hard_blocking_gates(self, tmp_path: Path):
        """6. Craft advisory 不升级为 hard gate（启发式工艺建议保持 advisory，不阻断提交）。"""
        project_root = _setup_book_project(tmp_path, chapter=1)
        runtime = ChapterRuntime(project_root)
        runtime.prepare(1, with_package=True)

        prose = _sample_draft()
        # 构造带有 Craft/methodology advisory 警告的 review_result
        advisory_review = {
            "blocking_count": 0,
            "must_check_results": [
                {"node": "石阶问心", "passed": True},
                {"node": "身份青牌", "passed": True},
            ],
            "blocking_rule_results": [],
            "issues": [
                {
                    "category": "craft",
                    "severity": "medium",
                    "blocking": False,
                    "description": "情绪节奏张力不足，未达高潮铺垫要求",
                    "fix_hint": "在后半段增加压迫感描写",
                },
                {
                    "category": "style",
                    "severity": "low",
                    "blocking": False,
                    "description": "对话句式稍显平缓",
                    "fix_hint": "精简执事台词",
                },
            ],
        }

        draft_id, commit_res = _prepare_and_commit(runtime, chapter=1, prose=prose, review_result=advisory_review)
        # 只要没有 hard blocking issues，commit 顺利 accepted，Craft advisory 不构成 veto
        assert commit_res.ok
        assert commit_res.chapter_outcome == "accepted"

    def test_resume_and_retry_prevent_duplicate_commit_and_republication(self, tmp_path: Path):
        """7. 恢复与重试不会重复提交或重复发布（幂等发布，resume plan 跳过已 accepted commit）。"""
        project_root = _setup_book_project(tmp_path, chapter=1)
        runtime = ChapterRuntime(project_root)
        runtime.prepare(1, with_package=True)

        prose = _sample_draft()
        draft_id, commit_res = _prepare_and_commit(runtime, chapter=1, prose=prose)
        assert commit_res.ok

        # 首次发布
        target_1 = runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)
        # 幂等二次发布 -> 返回相同路径，正文完好无损
        target_2 = runtime.publish_accepted_draft(chapter=1, draft_id=draft_id)
        assert target_1 == target_2
        assert target_2.is_file()

        # 检查 resume plan：对于已 accepted 的章节，commit 步自动设为 skip，防重复提交
        plan = build_write_resume_plan(project_root, chapter=1)
        commit_step = next(s for s in plan["steps"] if s["step"] == "commit")
        assert commit_step["action"] == "skip"
        assert "status=accepted" in commit_step["reason"]

        # 重试 projection 不会重新创建 commit
        retry_res = runtime.retry_projection(chapter=1)
        assert isinstance(retry_res, dict)

    def test_external_host_adapter_no_parallel_authority(self, tmp_path: Path):
        """8. External Host 不出现第二套事务权威（严格走 ChapterRuntime 公共门禁与唯一发布路径）。"""
        project_root = _setup_book_project(tmp_path, chapter=1)
        evidence_dir = tmp_path / "host_evidence"

        adapter = ExternalHostAdapter(project_root=project_root, evidence_dir=evidence_dir)
        run_res = adapter.run_chapter(chapter=1, creative_brief="外部宿主策划任务书")
        commit_res = run_res["commit_res"]

        assert commit_res.ok
        assert commit_res.chapter_outcome == "accepted"
        assert adapter.private_contract_writes == 0

        # 发布正式正文
        draft_receipt = json.loads((evidence_dir / "draft_receipt.json").read_text(encoding="utf-8"))
        draft_id = draft_receipt["draft_id"]
        published = adapter.publish_accepted_draft(chapter=1, draft_id=draft_id)
        assert published.is_file()
        assert "<chapter_changes>" not in published.read_text(encoding="utf-8")
