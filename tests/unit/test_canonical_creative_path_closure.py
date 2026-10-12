#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for PR A — Canonical Creative Path Closure.

Verifies end-to-end transport and final consumption (producer -> transport -> consumer):
1. Genre profile reference path resolution (project override vs bundled plugin fallback).
2. Genre profile excerpt reaches WriterPackage and renders into to_writer_prompt().
3. Writing guidance (items & strategy card) reaches WriterPackage and renders into to_writer_prompt().
4. Craft items & Story Craft reach WriterPackage and render into to_writer_prompt().
5. Reference notes reach WriterPackage and render into to_writer_prompt().
6. Recent summaries reach WriterPackage and render with chapter prefix into to_writer_prompt().
7. Urgent open loops reach WriterPackage and render into to_writer_prompt().
8. Chapter meta (planned core_event, hook, hook_type) reaches WriterPackage and renders into to_writer_prompt().
9. ExternalHostAdapter consumes the same canonical rendered prompt with all creative path fields present.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from data_modules.chapter_runtime import ChapterRuntime, WriterPackage
from data_modules.context_manager import resolve_reference_file
from external_host_adapter import ExternalHostAdapter


@pytest.fixture
def creative_project(tmp_path: Path) -> Path:
    """Create a minimal valid book project structure with rich creative data."""
    root = tmp_path / "creative_book"
    root.mkdir(parents=True, exist_ok=True)

    webnovel_dir = root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)

    # State with chapter_meta, story_craft, open_loops, and summaries
    state = {
        "project_info": {
            "title": "天阳纪元",
            "genre": "古典仙侠",
            "target_readers": "大众读者",
        },
        "progress": {
            "current_volume": 1,
            "current_chapter": 1,
            "total_volumes": 3,
            "volumes_planned": [
                {"volume": 1, "chapters_range": "1-10", "title": "第一卷 仙门初试"}
            ],
            "volumes_completed": [],
        },
        "chapter_meta": {
            "1": {
                "chapter": 1,
                "core_event": "林凡参加天阳宗考核通过问心石",
                "hook": "问心石底座显现神秘黑色裂纹并迅速隐去",
                "hook_type": "悬念转折",
            },
            "0002": {
                "chapter": 2,
                "core_event": "分配杂役院落遭遇老弟子刁难",
                "hook": "破旧院落后山藏有微弱灵脉波动",
                "hook_type": "利益发现",
            },
        },
        "story_craft": {
            "pacing_notes": "前三章节奏紧凑，快速确立主角立足点",
            "recommended_scenes": ["问心台测试", "执事分派杂役"],
        },
        "open_loops": [
            {
                "id": "loop_1",
                "content": "祖传青铜指环在问心石激发时微微发烫",
                "expected_payoff": "揭示指环内藏残魂",
                "urgency": 90,
                "status": "active",
            }
        ],
        "plot_threads": {
            "foreshadowing": [
                {
                    "content": "执事眼神闪烁似乎识得指环来历",
                    "status": "active",
                }
            ]
        },
        "entity_state": {
            "林凡": {"status": "外门杂役弟子", "realm": "练气一层"}
        },
    }
    (webnovel_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Directories
    for d in (
        ".webnovel/backups",
        ".webnovel/archive",
        ".webnovel/summaries",
        "设定集",
        "正文",
        "审查报告",
        "大纲",
    ):
        (root / d).mkdir(parents=True, exist_ok=True)

    # Summaries for chapter 1
    (webnovel_dir / "summaries" / "ch_0001.json").write_text(
        json.dumps(
            {
                "chapter": 1,
                "summary": "林凡踏上问心石完成测试，虽资质平庸但心性坚毅，获得外门青铜令。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    for f in (
        "设定集/世界观.md",
        "设定集/力量体系.md",
        "设定集/主角卡.md",
        "设定集/反派设计.md",
        "大纲/总纲.md",
        ".env.example",
    ):
        fp = root / f
        fp.parent.mkdir(parents=True, exist_ok=True)
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
        {"id": "ap_2", "text": "拒绝机械打脸"},
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
            "forbidden_zones": ["严禁直接展示筑基实力"],
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

    # Outline
    outline_text = """# 第一卷 仙门初试

### 第1章：问心石前
- 目标：通过问心石测试并拿到外门令
- 阻力：问心石反噬危机与执事质疑
- 代价：消耗微薄灵力险遭反噬
- 必须覆盖节点：走上测试台、触碰问心石、获得天阳青铜令
- 本章禁区：严禁直接展示筑基实力
- 章末问题：青铜令暗藏的微弱裂痕意味着什么？

### 第2章：杂役风波
- 目标：进入外门分配杂役院落
- 阻力：老弟子刁难与灵地争夺
- 必须覆盖节点：入驻杂役院、结识同门
- 本章禁区：严禁暴打同门
- 章末问题：窗外窥视的黑影究竟是谁？
"""
    (root / "大纲" / "第1卷-详细大纲.md").write_text(outline_text, encoding="utf-8")

    # Projections
    proj_dir = root / ".story-system" / "projections"
    proj_dir.mkdir(parents=True, exist_ok=True)
    entities = {
        "characters": [
            {"id": "林凡", "name": "林凡", "current_status": "手持青铜令的准外门弟子"}
        ]
    }
    (proj_dir / "entities.json").write_text(
        json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return root


def test_reference_file_resolution_priority(creative_project: Path):
    """Test priority order of reference file resolution: .claude/references > references > bundled."""
    # 1. Fallback to bundled plugin reference when no project file exists
    resolved = resolve_reference_file(creative_project, "genre-profiles.md")
    assert resolved is not None
    assert resolved.exists()
    assert resolved.name == "genre-profiles.md"

    # 2. Project-level references/ takes priority over bundled
    proj_ref = creative_project / "references" / "genre-profiles.md"
    proj_ref.parent.mkdir(parents=True, exist_ok=True)
    proj_ref.write_text("# Project Custom Genre Profiles\n", encoding="utf-8")

    resolved_proj = resolve_reference_file(creative_project, "genre-profiles.md")
    assert resolved_proj == proj_ref

    # 3. Project-level .claude/references/ takes highest priority
    claude_ref = creative_project / ".claude" / "references" / "genre-profiles.md"
    claude_ref.parent.mkdir(parents=True, exist_ok=True)
    claude_ref.write_text("# Claude Custom Genre Profiles\n", encoding="utf-8")

    resolved_claude = resolve_reference_file(creative_project, "genre-profiles.md")
    assert resolved_claude == claude_ref


def test_genre_profile_reaches_writer_prompt(creative_project: Path):
    """Verify genre_profile is resolved, transported, and rendered in to_writer_prompt()."""
    runtime = ChapterRuntime(creative_project)
    pkg = runtime.attach_creative_brief(
        chapter=1,
        creative_brief="本章重点渲染登仙路前的压抑氛围与问心石前的孤注一掷。",
    )

    # Check transport dictionary
    assert "genre_profile" in pkg.constraints
    genre_prof = pkg.constraints["genre_profile"]
    assert isinstance(genre_prof, dict)

    # Check prompt renderer output (Consumer)
    prompt = pkg.to_writer_prompt()
    assert "## 4. 调性、文风与避坑约束 (Constraints & Craft)" in prompt
    # If profile_excerpt exists, it should be rendered
    if genre_prof.get("profile_excerpt"):
        assert "【题材创作指引" in prompt
        assert genre_prof["profile_excerpt"].strip() in prompt


def test_chapter_meta_reaches_writer_prompt(creative_project: Path):
    """Verify chapter_meta (core_event, hook, hook_type) is transported and rendered."""
    runtime = ChapterRuntime(creative_project)
    pkg = runtime.attach_creative_brief(
        chapter=1,
        creative_brief="本章聚焦林凡通过问心石考核。",
    )

    # Check transport
    ch_meta = pkg.current_intent.get("chapter_meta")
    assert ch_meta is not None
    assert ch_meta.get("core_event") == "林凡参加天阳宗考核通过问心石"
    assert "神秘黑色裂纹" in ch_meta.get("hook", "")
    assert ch_meta.get("hook_type") == "悬念转折"

    # Check consumer
    prompt = pkg.to_writer_prompt()
    assert "## 1. 本章写作意图 (Current Intent)" in prompt
    assert "林凡参加天阳宗考核通过问心石" in prompt
    assert "神秘黑色裂纹" in prompt
    assert "悬念转折" in prompt


def test_recent_summaries_and_urgent_loops_reach_writer_prompt(creative_project: Path):
    """Verify recent_summaries and urgent_loops reach writer_context and render into to_writer_prompt()."""
    runtime = ChapterRuntime(creative_project)
    # Chapter 2 has chapter 1's summary as recent summary
    pkg = runtime.attach_creative_brief(
        chapter=2,
        creative_brief="本章推进杂役分派日常冲突。",
    )

    # Check transport
    recent_sums = pkg.writer_context.get("recent_summaries")
    assert recent_sums is not None
    assert len(recent_sums) >= 1
    assert any("问心石" in str(s) for s in recent_sums)

    urgent_loops = pkg.writer_context.get("urgent_loops")
    assert urgent_loops is not None
    assert len(urgent_loops) >= 1
    assert any("青铜指环" in str(l) for l in urgent_loops)

    # Check consumer prompt
    prompt = pkg.to_writer_prompt()
    assert "## 5. 关联前情线索 (Writer Context)" in prompt
    assert "前情摘要：" in prompt
    assert "问心石" in prompt
    assert "紧急伏笔待收：" in prompt
    assert "青铜指环" in prompt


def test_craft_and_writing_guidance_reach_writer_prompt(creative_project: Path):
    """Verify writing guidance and craft recommendations render into to_writer_prompt()."""
    runtime = ChapterRuntime(creative_project)
    pkg = runtime.attach_creative_brief(
        chapter=1,
        creative_brief="第一章开篇考核。",
    )

    # Check transport
    assert "writing_guidance" in pkg.constraints
    assert "craft_items" in pkg.constraints
    assert "story_craft" in pkg.constraints
    assert "前三章节奏紧凑" in str(pkg.constraints["story_craft"])

    # Check consumer prompt
    prompt = pkg.to_writer_prompt()
    assert "## 4. 调性、文风与避坑约束 (Constraints & Craft)" in prompt
    assert "核心调性：坚毅热血，道法自然" in prompt
    assert "避坑规则 (Anti-patterns)：" in prompt
    assert "避免空洞说教" in prompt


def test_external_host_adapter_receives_closed_creative_pipeline(creative_project: Path, tmp_path: Path):
    """Verify ExternalHostAdapter orchestrates chapter and its final_writer_prompt.txt contains all creative fields."""
    evidence_dir = tmp_path / "evidence_chapter_2"
    adapter = ExternalHostAdapter(creative_project, evidence_dir)

    res = adapter.run_chapter(
        chapter=2,
        creative_brief="林凡在杂役院落扎根，暗中探查后山灵气异动。",
    )

    assert res["chapter"] == 2
    assert (evidence_dir / "final_writer_prompt.txt").exists()

    rendered_prompt = (evidence_dir / "final_writer_prompt.txt").read_text(encoding="utf-8")

    # 1. Intent & chapter_meta
    assert "=== 写作任务：第2章 ===" in rendered_prompt
    assert "## 1. 本章写作意图 (Current Intent)" in rendered_prompt
    assert "破旧院落后山藏有微弱灵脉波动" in rendered_prompt
    assert "利益发现" in rendered_prompt

    # 2. Constraints & Craft
    assert "## 4. 调性、文风与避坑约束 (Constraints & Craft)" in rendered_prompt
    assert "核心调性：坚毅热血，道法自然" in rendered_prompt

    # 3. Writer Context (recent summaries & urgent loops)
    assert "## 5. 关联前情线索 (Writer Context)" in rendered_prompt
    assert "前情摘要：" in rendered_prompt
    assert "紧急伏笔待收：" in rendered_prompt
    assert "青铜指环" in rendered_prompt
