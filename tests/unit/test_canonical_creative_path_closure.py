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
from review_pipeline import run_craft_checks


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

    # 4. Reviewer Context evidence collected
    assert (evidence_dir / "reviewer_context.json").exists()
    rev_data = json.loads((evidence_dir / "reviewer_context.json").read_text(encoding="utf-8"))
    assert rev_data["chapter"] == 2
    assert rev_data["creative_intent"]["hook_type"] == "利益发现"
    assert "story_craft" in rev_data["advisory_constraints"]


def test_story_craft_semantic_constraints_reach_writer_prompt_without_raw_dump(creative_project: Path):
    """Verify chapter-scoped Story Craft constraints render semantically without dumping raw JSON."""
    state_file = creative_project / ".webnovel" / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["story_craft"] = {
        "rhythm_curve": {
            "chapters_since_peak": 4,
            "warning_threshold": 3,
            "block_threshold": 5,
            "history": [{"chapter": 1, "tension": 5}],
        },
        "timed_locks": [
            {
                "id": "TL-01",
                "description": "百草阁三日内需交齐灵砂",
                "deadline_chapter": 2,
                "status": "active",
            },
            {
                "id": "TL-99",
                "description": "远期封印期限",
                "deadline_chapter": 10,
                "status": "active",
            },
        ],
        "character_arc": {
            "name": "林凡",
            "starting_state": "卑微杂役",
            "ending_state": "内门瞩目",
            "transformation": "自卑忍让到敢作敢当",
        },
        "thematic_echoes": [
            {
                "premise": "仙凡有别，唯道心可越",
                "echoes": [
                    {"chapter": 2, "manifestation": "杂役老者临终赠言"},
                    {"chapter": 5, "manifestation": "执事殿问对"},
                ],
            }
        ],
        "foreshadow_chain": [
            {
                "id": "FS-01",
                "type": "物品伏笔",
                "content": "暗中发烫的青铜指环",
                "expected_payoff_chapter": 2,
                "payoff_method": "在后山废墟引发共鸣",
                "status": "active",
            },
            {
                "id": "FS-02",
                "type": "人物伏笔",
                "content": "执法堂暗探",
                "expected_payoff_chapter": 8,
                "payoff_method": "宗门大比揭晓",
                "status": "active",
            },
        ],
        "pacing_notes": "第二章展开宗门底层生存法则",
        "recommended_scenes": ["杂役院领物资", "后山探查废墟"],
    }
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    runtime = ChapterRuntime(creative_project)
    pkg = runtime.attach_creative_brief(
        chapter=2,
        creative_brief="本章进入杂役院落生存冲突。",
    )

    prompt = pkg.to_writer_prompt()

    # 1. Semantic rendering checks in Story Craft section
    assert "【故事工艺约束 (Story Craft Constraints)】" in prompt
    sc_section = prompt.split("【故事工艺约束 (Story Craft Constraints)】")[1].split("## 5.")[0]
    assert "情绪节奏张力：距上次高潮已过 4 章（警示阈值: 3，阻断阈值: 5）" in sc_section
    assert "剧情限时锁：[TL-01] 百草阁三日内需交齐灵砂（截止第2章）" in sc_section
    assert "人物弧光指引（林凡）：从【卑微杂役】向【内门瞩目】转变" in sc_section
    assert "主题呼应设计：命题【仙凡有别，唯道心可越】—— 本章呈现：杂役老者临终赠言" in sc_section
    assert "预定伏笔回收：[FS-01/物品伏笔] 暗中发烫的青铜指环（回收方式：在后山废墟引发共鸣）" in sc_section
    assert "剧情节奏备忘：第二章展开宗门底层生存法则" in sc_section
    assert "推荐场景构想：杂役院领物资、后山探查废墟" in sc_section

    # 2. Distant or non-chapter items should NOT be in the Story Craft prompt section
    assert "TL-99" not in sc_section
    assert "FS-02" not in sc_section
    assert "执法堂暗探" not in sc_section
    assert "执事殿问对" not in sc_section

    # 3. Raw JSON structure / history array is NOT dumped
    assert '"history":' not in sc_section
    assert '"rhythm_curve":' not in sc_section
    assert '"timed_locks":' not in sc_section


def test_reviewer_receives_closed_creative_pipeline(creative_project: Path):
    """Verify Reviewer receives creative intent, craft constraints, canon facts, and authority tiers."""
    runtime = ChapterRuntime(creative_project)
    rev_ctx = runtime.get_reviewer_context(chapter=2)

    assert rev_ctx["chapter"] == 2

    # 1. 事实权威 (canon_authority)
    canon = rev_ctx["canon_authority"]
    assert isinstance(canon, dict)
    assert "林凡" in str(canon)

    # 2. 创作意图 (creative_intent)
    intent = rev_ctx["creative_intent"]
    assert intent["goal"] == "进入外门分配杂役院落"
    assert "入驻杂役院" in intent["must_cover_nodes"]
    assert "严禁暴打同门" in intent["forbidden_zones"]
    assert intent["core_event"] == "分配杂役院落遭遇老弟子刁难"
    assert "破旧院落后山藏有微弱灵脉波动" in intent["hook"]
    assert intent["hook_type"] == "利益发现"

    # 3. 工艺约束 (craft_constraints)
    craft = rev_ctx["craft_constraints"]
    assert "坚毅热血" in craft["core_tone"]
    assert any("空洞说教" in str(ap) for ap in craft["anti_patterns"])
    assert "story_craft" in craft

    # 4. 建议性约束 (advisory_constraints)
    advisory = rev_ctx["advisory_constraints"]
    assert "story_craft" in advisory
    assert "ADVISORY_ONLY" in advisory.get("policy", "")

    # 5. 确保未非法合成硬性门禁 key，规划禁区保留于本章规划与意图中
    assert "hard_constraints" not in rev_ctx
    plan = rev_ctx["chapter_planning"]
    assert plan["chapter_meta"]["chapter"] == 2
    assert plan["chapter_meta"]["hook_type"] == "利益发现"
    assert "严禁暴打同门" in plan["forbidden_zones"]


def test_reviewer_craft_checks_consume_chapter_meta_and_story_craft(creative_project: Path):
    """Verify Reviewer craft checks properly evaluate zero-padded chapter_meta and story_craft."""
    state_file = creative_project / ".webnovel" / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))

    # Chapter 2's chapter_meta has key "0002" with hook_type="利益发现"
    # Verify run_craft_checks consumes "0002" via get_chapter_meta_entry and does NOT emit missing hook_type warning
    issues = run_craft_checks(state, chapter=2)

    # Missing hook_type should NOT be emitted because "0002" was resolved
    hook_type_warnings = [
        iss for iss in issues.get("warnings", [])
        if "hook_type 未声明" in str(iss)
    ]
    assert len(hook_type_warnings) == 0, f"Expected no hook_type warning, got: {hook_type_warnings}"


def test_webnovel_write_step3_wires_reviewer_context_specification():
    """Verify webnovel-write/SKILL.md Step 3 explicitly wires runtime reviewer-context to reviewer agent."""
    skill_path = (
        Path(__file__).resolve().parent.parent.parent
        / ".claude"
        / "plugins"
        / "zhanghui"
        / "skills"
        / "webnovel-write"
        / "SKILL.md"
    )
    skill_text = skill_path.read_text(encoding="utf-8")

    # 1. Step 3 generates reviewer context via runtime CLI
    assert "runtime reviewer-context" in skill_text
    assert "reviewer_context_{chapter_padded}.json" in skill_text

    # 2. Step 3 passes reviewer_context_file to webnovel-writer:reviewer
    assert "webnovel-writer:reviewer" in skill_text
    assert "reviewer_context_file" in skill_text

    # 3. Explicit authority tier definitions and advisory non-blocking rule
    assert "canon_authority" in skill_text
    assert "creative_intent" in skill_text
    assert "chapter_planning" in skill_text
    assert "advisory_constraints" in skill_text or "craft_constraints" in skill_text
    assert "不得仅凭字段名升级为 hard gate authority" in skill_text
    assert "所有 raw findings 均严格输出 `blocking=false`" in skill_text


def test_reviewer_agent_spec_wires_reviewer_context_consumption():
    """Verify agents/reviewer.md consumes reviewer_context_file and enforces craft advisory boundary."""
    agent_path = (
        Path(__file__).resolve().parent.parent.parent
        / ".claude"
        / "plugins"
        / "zhanghui"
        / "agents"
        / "reviewer.md"
    )
    agent_text = agent_path.read_text(encoding="utf-8")

    # 1. Available tools & bash commands
    assert "runtime reviewer-context" in agent_text

    # 2. Inputs include reviewer_context_file
    assert "reviewer_context_file" in agent_text

    # 3. Execution flow uses context tiers
    assert "canon_authority" in agent_text
    assert "creative_intent" in agent_text
    assert "chapter_planning" in agent_text
    assert "craft_constraints" in agent_text

    # 4. Strict advisory non-blocking boundary for craft
    assert "不得仅凭字段名就自动升级为 hard gate authority" in agent_text
    assert "所有 raw findings 的输出必须严格保持 `blocking=false`" in agent_text
    assert "严禁升级为 hard gate" in agent_text


def test_ordinary_chapter_forbidden_zones_cannot_gain_hard_gate_authority():
    """Verify chapter outline forbidden_zones cannot gain hard gate authority merely by field name."""
    from data_modules.gate_findings import (
        DetectedFinding,
        EvidenceRef,
        FindingAuthority,
        FindingCategory,
        WorkflowAction,
    )
    from data_modules.gate_severity_policy import GateSeverityPolicy

    policy = GateSeverityPolicy()

    # 1. Finding produced from chapter planning deviation (AUTHOR_PLAN authority)
    plan_finding = DetectedFinding(
        gate_id="intent.forbidden_zone",
        stable_subject_key="chapter:2:forbidden_zone:1",
        category=FindingCategory.INTENT_FULFILLMENT,
        authority=FindingAuthority.AUTHOR_PLAN,
        scope={"chapter": 2},
        evidence=[EvidenceRef(kind="plan_observation", identity={"forbidden_zone": "严禁暴打同门"})],
        checker_id="chapter_reviewer",
        checker_version="v1",
    )
    decisions = policy.evaluate([plan_finding], policy_version="v1", scope={"chapter": 2})
    assert decisions.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY
    assert decisions.aggregate_action != WorkflowAction.REJECT

    # 2. Even if incorrectly tagged as USER_CONSTRAINT without explicit user contract proof,
    # shared policy rejects the promotion and keeps it as advisory
    unproven_user_finding = DetectedFinding(
        gate_id="intent.forbidden_zone",
        stable_subject_key="chapter:2:forbidden_zone:1",
        category=FindingCategory.USER_CONSTRAINT,
        authority=FindingAuthority.AUTHOR_PLAN,
        scope={"chapter": 2},
        evidence=[EvidenceRef(kind="plan_observation", identity={"forbidden_zone": "严禁暴打同门"})],
        checker_id="chapter_reviewer",
        checker_version="v1",
    )
    decisions_unproven = policy.evaluate([unproven_user_finding], policy_version="v1", scope={"chapter": 2})
    assert decisions_unproven.aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY
    assert decisions_unproven.aggregate_action != WorkflowAction.REJECT
    assert decisions_unproven.decisions[0].rule_id == "user.constraint_not_proven"



