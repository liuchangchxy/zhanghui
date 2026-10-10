#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Native Writer Package Parity and Boundary Convergence (Issue #29 - PR1).

Verifies Controller-enforced boundary:
1. ContextManager / Runtime produces Governed Context as single factual authority (no creative planning).
2. Missing Creative Brief creates unsealed package (is_writer_ready=False, authority='none').
3. Context Agent attaches authentic Creative Brief to seal Native Writer Package with deterministic fingerprints.
4. to_writer_prompt() semantically exposes all 6 governed layers (story_identity, current_intent,
   governed_canon, creative_brief, constraints/craft, writer_context).
5. Canonical prompt renderer guarantees input parity: an explicit Canon fact, an Intent goal,
   and an authentic Creative Brief all appear in the rendered Writer input.
6. External Host uses the exact same canonical renderer as Claude Skill Writer.
7. Draft ingestion detects stale packages when brief fingerprint changes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from data_modules.chapter_runtime import ChapterRuntime, WriterPackage
from external_host_adapter import ExternalHostAdapter


@pytest.fixture
def test_book_project(tmp_path: Path) -> Path:
    """Create a minimal valid book project structure with contracts and outline."""
    root = tmp_path / "test_book"
    root.mkdir(parents=True, exist_ok=True)

    webnovel_dir = root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "project_info": {
            "title": "天阳纪元",
            "genre": "古典仙侠",
            "target_readers": "大众",
        },
        "progress": {
            "current_volume": 1,
            "current_chapter": 0,
            "total_volumes": 3,
            "volumes_planned": [
                {"volume": 1, "chapters_range": "1-10", "title": "第一卷 仙门初试"}
            ],
            "volumes_completed": [],
        },
        "entity_state": {},
    }
    (webnovel_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for d in (".webnovel/backups", ".webnovel/archive", ".webnovel/summaries", "设定集", "正文", "审查报告"):
        (root / d).mkdir(parents=True, exist_ok=True)
    for f in ("设定集/世界观.md", "设定集/力量体系.md", "设定集/主角卡.md", "设定集/反派设计.md", "大纲/总纲.md", ".env.example"):
        fp = root / f
        fp.parent.mkdir(parents=True, exist_ok=True)
        if not fp.exists():
            fp.write_text("# init\n", encoding="utf-8")

    # .story-system contracts
    story_sys = root / ".story-system"
    story_sys.mkdir(parents=True, exist_ok=True)

    master_setting = {
        "meta": {"contract_type": "MASTER_SETTING"},
        "title": "天阳纪元",
        "route": {"primary_genre": "古典仙侠"},
        "master_constraints": {
            "core_tone": "坚毅热血，道法自然",
            "pacing_strategy": "层层递进",
        },
    }
    (story_sys / "MASTER_SETTING.json").write_text(
        json.dumps(master_setting, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    anti_patterns = [
        {"id": "ap_1", "text": "避免空洞说教"},
        {"id": "ap_2", "text": "拒绝机械套路"},
    ]
    (story_sys / "anti_patterns.json").write_text(
        json.dumps(anti_patterns, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    volume_contract = {
        "volume_id": "vol_01",
        "volume_title": "第一卷 仙门初试",
        "scope": "1-10",
        "theme": "少年出深山，试玉求仙道",
    }
    (story_sys / "volume_contract.json").write_text(
        json.dumps(volume_contract, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    chapter_contracts = {
        "1": {
            "chapter": 1,
            "goal": "通过问心石测试并拿到外门令",
            "conflict": "问心石反噬危机与执事质疑",
            "cost": "消耗微薄灵力险遭反噬",
            "must_cover_nodes": ["走上测试台", "触碰问心石", "获得天阳青铜令"],
            "forbidden_zones": ["严禁直接展示筑基实力", "严禁当场与执事冲突"],
            "ending_question": "青铜令暗藏的微弱裂痕意味着什么？",
        },
        "2": {
            "chapter": 2,
            "goal": "进入外门分配杂役院落",
            "conflict": "老弟子刁难与灵地争夺",
            "cost": "上交半数灵石暂避锋芒",
            "must_cover_nodes": ["入驻杂役院", "结识同门", "深夜研读入门功法"],
            "forbidden_zones": ["严禁暴打同门"],
            "ending_question": "窗外窥视的黑影究竟是谁？",
        },
    }
    (story_sys / "chapter_contracts.json").write_text(
        json.dumps(chapter_contracts, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # outline
    outline_dir = root / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    outline_text = """# 第一卷 仙门初试

### 第1章：问心石前
- 目标：通过问心石测试并拿到外门令
- 阻力：问心石反噬危机与执事质疑
- 代价：消耗微薄灵力险遭反噬
- 必须覆盖节点：走上测试台、触碰问心石、获得天阳青铜令
- 本章禁区：严禁直接展示筑基实力、严禁当场与执事冲突
- 章末问题：青铜令暗藏的微弱裂痕意味着什么？

### 第2章：杂役风波
- 目标：进入外门分配杂役院落
- 阻力：老弟子刁难与灵地争夺
- 必须覆盖节点：入驻杂役院、结识同门
- 本章禁区：严禁暴打同门
"""
    (outline_dir / "第1卷-详细大纲.md").write_text(outline_text, encoding="utf-8")

    # projections / canon
    proj_dir = root / ".story-system" / "projections"
    proj_dir.mkdir(parents=True, exist_ok=True)
    entities = {
        "characters": [
            {
                "id": "char_linfan",
                "name": "林凡",
                "status": "待考核散修",
                "realm": "炼气二层",
            }
        ]
    }
    (proj_dir / "entities.json").write_text(
        json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return root


def test_governed_context_assembly(test_book_project: Path):
    """Governed context must derive from ContextManager without future intent leak."""
    runtime = ChapterRuntime(test_book_project)
    gov_ctx = runtime.get_governed_context(chapter=1)

    assert gov_ctx["chapter"] == 1
    assert gov_ctx["meta"]["authority"] == "ContextManager.build_context"
    assert "source_fingerprints" in gov_ctx
    assert gov_ctx["source_fingerprints"]  # non-empty

    # Story identity
    assert gov_ctx["story_identity"]["title"] == "天阳纪元"
    assert gov_ctx["story_identity"]["genre"] == "古典仙侠"

    # Current intent (chapter 1 only, no chapter 2 leak)
    intent = gov_ctx["current_intent"]
    directive = intent.get("directive", {})
    assert directive.get("goal") == "通过问心石测试并拿到外门令"
    assert "获得天阳青铜令" in directive.get("must_cover_nodes", [])
    assert "严禁暴打同门" not in directive.get("forbidden_zones", [])  # chapter 2 constraint not in ch 1

    # Governed canon
    canon = gov_ctx["governed_canon"]
    assert "canon_items" in canon
    assert "context_snapshot" in canon

    # Constraints / Craft
    constraints = gov_ctx["constraints"]
    assert constraints.get("core_tone") == "坚毅热血，道法自然"
    assert "避免空洞说教" in constraints.get("anti_patterns", [])


def test_raw_writer_package_without_brief_is_not_writer_ready(test_book_project: Path):
    """Runtime must NOT synthesize fake brief when brief is absent; package remains unsealed."""
    runtime = ChapterRuntime(test_book_project)
    pkg = runtime.get_writer_package(chapter=1)

    assert isinstance(pkg, WriterPackage)
    assert pkg.chapter == 1
    assert pkg.creative_brief == ""
    assert pkg.creative_brief_fingerprint == ""
    assert pkg.is_writer_ready is False
    assert pkg.meta.get("creative_planning_authority") == "none"
    assert pkg.meta.get("is_writer_ready") is False


def test_attach_creative_brief_boundary_seals_native_writer_package(test_book_project: Path):
    """Context Agent attaching an authentic brief seals the package with deterministic fingerprints."""
    runtime = ChapterRuntime(test_book_project)

    # 1. Empty or whitespace brief is rejected
    with pytest.raises(ValueError, match="non-empty string"):
        runtime.attach_creative_brief(chapter=1, creative_brief="   ")

    # 2. Raw unsealed package baseline
    raw_pkg = runtime.get_writer_package(chapter=1)
    assert raw_pkg.is_writer_ready is False

    # 3. Context Agent provides authentic 5-section brief
    agent_brief = (
        "1. 开篇委托：本章焦点在林凡初登仙阶的心理重压。\n\n"
        "2. 这章的故事：问心石突发异象，必须展现心志坚定。\n\n"
        "3. 这章的人物：执事冷漠而多疑，林凡藏拙守拙。\n\n"
        "4. 怎么写更顺：多用动作与物象白描，克制内心独白。\n\n"
        "5. 收在哪里：青铜令入手沉重，定格在执事意味深长的注视。"
    )

    sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief=agent_brief)

    assert sealed_pkg.creative_brief == agent_brief
    expected_brief_fp = hashlib.sha256(agent_brief.encode("utf-8")).hexdigest()
    assert sealed_pkg.creative_brief_fingerprint == expected_brief_fp
    assert sealed_pkg.is_writer_ready is True
    assert sealed_pkg.meta.get("creative_planning_authority") == "ContextAgent"
    assert sealed_pkg.meta.get("is_writer_ready") is True

    # Package fingerprint changes deterministically due to brief attachment
    assert sealed_pkg.package_fingerprint != raw_pkg.package_fingerprint


def test_canonical_writer_input_parity_contains_canon_intent_brief(test_book_project: Path):
    """
    to_writer_prompt must semantically contain:
    - a distinct Canon fact,
    - an Intent goal,
    - and the authentic Creative Brief content.
    """
    runtime = ChapterRuntime(test_book_project)

    agent_brief = (
        "【认知规划】本章着重展现林凡隐忍藏拙的心态与执事威压，"
        "结尾定格在青铜令入手那一刻的微弱震颤。"
    )
    sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief=agent_brief)
    prompt = sealed_pkg.to_writer_prompt()

    # 1. Story Identity layer
    assert "=== 写作任务：第1章 ===" in prompt
    assert "书名：天阳纪元" in prompt
    assert "题材：古典仙侠" in prompt

    # 2. Current Intent layer
    assert "## 1. 本章写作意图 (Current Intent)" in prompt
    assert "核心目标：通过问心石测试并拿到外门令" in prompt
    assert "必须覆盖节点：" in prompt
    assert "走上测试台" in prompt and "触碰问心石" in prompt and "获得天阳青铜令" in prompt
    assert "本章绝对禁区：" in prompt
    assert "严禁直接展示筑基实力" in prompt and "严禁当场与执事冲突" in prompt

    # 3. Governed Canon layer
    assert "## 2. 治理事实与前情依据 (Governed Canon)" in prompt
    assert "林凡" in prompt
    assert "待考核散修" in prompt

    # 4. Creative Brief layer
    assert "## 3. 创作策划任务书 (Creative Brief)" in prompt
    assert "【认知规划】本章着重展现林凡隐忍藏拙的心态与执事威压" in prompt

    # 5. Constraints & Craft layer
    assert "## 4. 调性、文风与避坑约束 (Constraints & Craft)" in prompt
    assert "核心调性：坚毅热血，道法自然" in prompt
    assert "叙事节奏：层层递进" in prompt
    assert "避坑规则 (Anti-patterns)：避免空洞说教" in prompt

    # 6. Handoff Protocol
    assert "## 6. 正文交付协议 (Handoff Protocol)" in prompt
    assert "<chapter_changes>...</chapter_changes>" in prompt
    assert sealed_pkg.package_fingerprint in prompt


def test_external_host_adapter_uses_same_canonical_renderer(test_book_project: Path, tmp_path: Path):
    """ExternalHostAdapter must format writer prompt via pkg.to_writer_prompt(), ensuring input parity."""
    evidence_dir = tmp_path / "host_evidence"
    adapter = ExternalHostAdapter(test_book_project, evidence_dir)

    agent_brief = "1. 开篇委托：外部Host驱动章节测试。\n5. 收在哪里：问心石平息。"
    result = adapter.run_chapter(chapter=1, creative_brief=agent_brief)

    # Prompt written to evidence directory by external host
    saved_prompt = (evidence_dir / "final_writer_prompt.txt").read_text(encoding="utf-8")

    # Verify External Host formatted prompt using the canonical package renderer
    expected_prompt = result["writer_package"].to_writer_prompt()
    assert saved_prompt == expected_prompt
    assert "核心目标：通过问心石测试并拿到外门令" in saved_prompt
    assert "外部Host驱动章节测试" in saved_prompt
    assert "林凡" in saved_prompt


def test_stale_package_detection_with_brief_fingerprint(test_book_project: Path):
    """Draft ingestion must reject stale packages when brief is changed/re-sealed."""
    runtime = ChapterRuntime(test_book_project)

    # Seal with brief 1
    pkg1 = runtime.attach_creative_brief(chapter=1, creative_brief="Brief V1: 初始策划")
    prose = "山门前，灵石泛起微光。林凡缓步上前，接过令牌。\n<chapter_changes>{}</chapter_changes>"

    # 1. Matching package fingerprint succeeds
    ingest_res = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=pkg1.package_fingerprint,
    )
    assert ingest_res.ok is True
    assert ingest_res.status == "draft_ingested"

    # 2. Context Agent updates brief to V2 -> re-seals package
    pkg2 = runtime.attach_creative_brief(chapter=1, creative_brief="Brief V2: 修订后更具张力的策划")
    assert pkg2.package_fingerprint != pkg1.package_fingerprint

    # 3. Draft created against old pkg1 is now rejected as STALE_WRITER_PACKAGE
    stale_res = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=pkg1.package_fingerprint,
    )
    assert stale_res.ok is False
    assert stale_res.error_code == "STALE_WRITER_PACKAGE"
