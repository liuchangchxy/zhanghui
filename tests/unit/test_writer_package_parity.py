#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Native Writer Package Parity and Convergence (Issue #29 - PR1).

Verifies:
1. Native Writer Package contains all governed layers (story_identity, current_intent,
   governed_canon, constraints/craft, writer_context, creative_brief, fingerprints).
2. Governed context derives from ContextManager as single factual authority.
3. Creative Brief synthesis produces conforming 5-section cognitive planning brief.
4. Context Agent brief attachment seals the package with deterministic brief fingerprint.
5. Canonical writer prompt rendering (to_writer_prompt) delivers input parity across hosts.
6. Stale package detection respects brief fingerprint changes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from data_modules.chapter_runtime import ChapterRuntime, WriterPackage


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


def test_synthesize_creative_brief_five_sections(test_book_project: Path):
    """Synthesized brief must produce the canonical 5 sections."""
    runtime = ChapterRuntime(test_book_project)
    brief = runtime.synthesize_creative_brief(chapter=1)

    assert "1. 开篇委托：" in brief
    assert "2. 这章的故事：" in brief
    assert "3. 这章的人物：" in brief
    assert "4. 怎么写更顺：" in brief
    assert "5. 收在哪里：" in brief

    # Check cognitive planning details embedded
    assert "天阳纪元" in brief
    assert "古典仙侠" in brief
    assert "问心石" in brief
    assert "青铜令" in brief
    assert "坚毅热血" in brief
    assert "青铜令暗藏的微弱裂痕意味着什么" in brief


def test_native_writer_package_structure_and_fingerprints(test_book_project: Path):
    """WriterPackage must contain all fields and deterministic fingerprints."""
    runtime = ChapterRuntime(test_book_project)
    pkg = runtime.get_writer_package(chapter=1)

    assert isinstance(pkg, WriterPackage)
    assert pkg.chapter == 1
    assert pkg.creative_brief != ""
    assert pkg.creative_brief_fingerprint != ""
    assert pkg.package_fingerprint != ""

    # Brief fingerprint is deterministic SHA-256 of brief
    expected_brief_fp = hashlib.sha256(pkg.creative_brief.encode("utf-8")).hexdigest()
    assert pkg.creative_brief_fingerprint == expected_brief_fp

    # Serializes to dict and JSON correctly
    data = pkg.to_dict()
    assert "story_identity" in data
    assert "current_intent" in data
    assert "governed_canon" in data
    assert "constraints" in data
    assert "constraints_and_craft" in data
    assert "writer_context" in data
    assert "creative_brief" in data
    assert "creative_brief_fingerprint" in data
    assert "source_fingerprints" in data
    assert "package_fingerprint" in data


def test_attach_creative_brief_custom_agent_brief(test_book_project: Path):
    """Context Agent attaching custom brief must update brief and package fingerprints."""
    runtime = ChapterRuntime(test_book_project)

    # Baseline package with synthesized brief
    base_pkg = runtime.get_writer_package(chapter=1)

    custom_brief = (
        "1. 开篇委托：本章焦点在林凡初登仙阶的心理重压。\n\n"
        "2. 这章的故事：问心石突发异象，必须展现心志坚定。\n\n"
        "3. 这章的人物：执事冷漠而多疑，林凡藏拙守拙。\n\n"
        "4. 怎么写更顺：多用动作与物象白描，克制内心独白。\n\n"
        "5. 收在哪里：青铜令入手沉重，定格在执事意味深长的注视。"
    )

    attached_pkg = runtime.attach_creative_brief(chapter=1, creative_brief=custom_brief)

    assert attached_pkg.creative_brief == custom_brief
    expected_brief_fp = hashlib.sha256(custom_brief.encode("utf-8")).hexdigest()
    assert attached_pkg.creative_brief_fingerprint == expected_brief_fp
    assert attached_pkg.meta.get("creative_planning_authority") == "ContextAgent"

    # Package fingerprint changed deterministically due to new brief
    assert attached_pkg.package_fingerprint != base_pkg.package_fingerprint


def test_to_writer_prompt_rendering_parity(test_book_project: Path):
    """to_writer_prompt must render a coherent prompt suitable for all hosts."""
    runtime = ChapterRuntime(test_book_project)
    pkg = runtime.get_writer_package(chapter=1)

    prompt = pkg.to_writer_prompt()

    assert f"=== 写作任务：第{pkg.chapter}章 ===" in prompt
    assert "书名：天阳纪元 | 题材：古典仙侠" in prompt
    assert "## 创作执行任务书 (Creative Brief)" in prompt
    assert "1. 开篇委托" in prompt
    assert "必须覆盖节点" in prompt
    assert "本章禁区" in prompt
    assert "<chapter_changes>" in prompt


def test_stale_package_detection_with_brief_fingerprint(test_book_project: Path):
    """Ingestion and commit must reject when package fingerprint does not match brief."""
    runtime = ChapterRuntime(test_book_project)
    pkg = runtime.get_writer_package(chapter=1)

    prose = "山门前，灵石泛起微光。林凡缓步上前，接过令牌。\n<chapter_changes>{}</chapter_changes>"

    # 1. Matching package fingerprint succeeds
    ingest_res = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=pkg.package_fingerprint,
    )
    assert ingest_res.ok is True
    assert ingest_res.status == "draft_ingested"

    # 2. Tampered or stale package fingerprint fails
    stale_res = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint="invalid_old_fingerprint_hash",
    )
    assert stale_res.ok is False
    assert stale_res.error_code == "STALE_WRITER_PACKAGE"
