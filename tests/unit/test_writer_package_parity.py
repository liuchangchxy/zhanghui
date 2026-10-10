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


def test_unsealed_package_to_writer_prompt_fails_closed(test_book_project: Path):
    """Unsealed package (missing creative brief) must refuse to render writer prompt."""
    runtime = ChapterRuntime(test_book_project)
    raw_pkg = runtime.get_writer_package(chapter=1)
    assert raw_pkg.is_writer_ready is False

    with pytest.raises(RuntimeError, match="Cannot render writer prompt: WriterPackage.*is unsealed"):
        raw_pkg.to_writer_prompt()


def test_cli_package_format_prompt_fails_on_unsealed_package(test_book_project: Path):
    """CLI runtime package --format prompt fails-closed when no brief is provided."""
    import subprocess
    import sys

    cli_script = (
        test_book_project.parent.parent
        / ".claude"
        / "plugins"
        / "zhanghui"
        / "scripts"
        / "data_modules"
        / "webnovel.py"
    )
    # Use repo webnovel script directly
    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "data_modules.webnovel",
            "runtime",
            "package",
            "--project-root",
            str(test_book_project),
            "--chapter",
            "1",
            "--format",
            "prompt",
        ],
        capture_output=True,
        text=True,
        env={
            **subprocess.os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / ".claude/plugins/zhanghui/scripts"),
        },
    )
    assert res.returncode != 0
    assert "is unsealed" in res.stderr


def test_unsealed_package_ingest_draft_rejected(test_book_project: Path):
    """A. unsealed pkg = runtime.get_writer_package(chapter) -> ingest_draft fails explicitly."""
    runtime = ChapterRuntime(test_book_project)
    unsealed_pkg = runtime.get_writer_package(chapter=1)
    assert unsealed_pkg.is_writer_ready is False

    prose = "山门前，灵石泛起微光。\n<chapter_changes>{}</chapter_changes>"
    res = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=unsealed_pkg.package_fingerprint,
    )
    assert res.ok is False
    assert res.error_code == "WRITER_PACKAGE_UNSEALED"
    assert res.status == "writer_package_unsealed"


def test_sealed_package_ingest_draft_succeeds(test_book_project: Path):
    """B. sealed pkg = attach_creative_brief(...) -> ingest_draft succeeds."""
    runtime = ChapterRuntime(test_book_project)
    sealed_pkg = runtime.attach_creative_brief(chapter=1, creative_brief="策划任务书：通过灵根测试。")
    assert sealed_pkg.is_writer_ready is True

    prose = "山门前，灵石泛起微光。\n<chapter_changes>{}</chapter_changes>"
    res = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=sealed_pkg.package_fingerprint,
    )
    assert res.ok is True
    assert res.status == "draft_ingested"
    assert res.draft_id.startswith("draft-001-")


def test_sealed_active_package_rejects_old_unsealed_fingerprint(test_book_project: Path):
    """C. Once active package is sealed, old unsealed base fingerprint must still fail."""
    runtime = ChapterRuntime(test_book_project)
    unsealed_pkg = runtime.get_writer_package(chapter=1)
    unsealed_fp = unsealed_pkg.package_fingerprint

    # Context Agent seals active package
    runtime.attach_creative_brief(chapter=1, creative_brief="策划任务书：通过灵根测试。")

    prose = "山门前，灵石泛起微光。\n<chapter_changes>{}</chapter_changes>"
    res = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=unsealed_fp,
    )
    assert res.ok is False
    assert res.error_code == "WRITER_PACKAGE_UNSEALED"


def test_commit_rejects_draft_bound_to_unsealed_package(test_book_project: Path):
    """D. commit refuses draft bound to/ingested with an unsealed package fingerprint."""
    runtime = ChapterRuntime(test_book_project)
    unsealed_fp = runtime.compute_package_fingerprint(chapter=1)
    draft_id = "draft-001-unsealed"
    prose = "山门前，灵石泛起微光。\n<chapter_changes>{}</chapter_changes>"
    runtime_dir = runtime._chapter_runtime_dir(1)
    drafts_dir = runtime_dir / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    draft_payload = {
        "draft_id": draft_id,
        "chapter": 1,
        "package_fingerprint": unsealed_fp,
        "draft_fingerprint": hashlib.sha256(prose.encode("utf-8")).hexdigest(),
        "created_at": "2026-10-10T00:00:00Z",
        "metadata": {},
        "prose": prose,
        "status": "ingested",
    }
    (drafts_dir / f"{draft_id}.json").write_text(json.dumps(draft_payload, ensure_ascii=False), encoding="utf-8")

    # Even if active package is sealed now, draft bound to unsealed package cannot commit
    runtime.attach_creative_brief(chapter=1, creative_brief="策划任务书：通过灵根测试。")

    artifacts = {
        "review_result": {"blocking_count": 0, "must_check_results": [], "blocking_rule_results": []},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"chapter_meta": {}, "accepted_events": [], "state_deltas": [], "entity_deltas": []},
        "reconciliation_result": {"conflicts": [], "resolutions": [], "resolved_proposal": {}},
    }
    res = runtime.commit(chapter=1, draft_id=draft_id, **artifacts)
    assert res.ok is False
    assert res.error_code == "WRITER_PACKAGE_UNSEALED"


def test_prepare_next_required_action_unsealed_vs_sealed(test_book_project: Path):
    """PR1 correction: prepare() next_required_action is attach_creative_brief when unsealed, ingest_draft when sealed."""
    runtime = ChapterRuntime(test_book_project)

    # 1. Unsealed package -> next action is attach_creative_brief
    prep_unsealed = runtime.prepare(chapter=1, with_package=True)
    assert prep_unsealed.ok is True
    assert prep_unsealed.writer_package is not None
    assert prep_unsealed.writer_package.is_writer_ready is False
    assert prep_unsealed.next_required_action == "attach_creative_brief"

    # 2. Sealed package -> next action is ingest_draft
    prep_sealed = runtime.prepare(chapter=1, with_package=True, creative_brief="策划任务书：测试。")
    assert prep_sealed.ok is True
    assert prep_sealed.writer_package is not None
    assert prep_sealed.writer_package.is_writer_ready is True
    assert prep_sealed.next_required_action == "ingest_draft"


def test_webnovel_write_skill_adopts_native_writer_package_workflow():
    """Verify webnovel-write/SKILL.md fully adopts Native Writer Package workflow with zero redundant assembly."""
    repo_root = Path(__file__).resolve().parents[2]
    skill_path = repo_root / ".claude" / "plugins" / "zhanghui" / "skills" / "webnovel-write" / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")

    # Workflow chain: Governed Context -> Context Agent -> attach-creative-brief -> sealed prompt -> Writer
    assert "runtime prepare" in text
    assert "runtime governed-context" in text
    assert "webnovel-writer:context-agent" in text
    assert "runtime attach-creative-brief" in text
    assert "WriterPackage.to_writer_prompt()" in text

    # Canonical writer prompt & zero redundant assembly contract
    assert "Zero Redundant Assembly" in text
    assert "严禁重新拼装" in text
    assert "严禁双重模板" in text
    assert "严禁绕过封口" in text


def test_webnovel_write_skill_optional_craft_reference_boundary():
    """Verify optional craft/reference routing and unified writer boundary contracts in SKILL.md.

    Enforces Phase 3 / PR2 Controller boundaries:
    1. SKILL.md does not claim ContextManager loads personal corpus (个人语料).
    2. Step 2A has zero dead injection / dead call (e.g. no build-step2a-section call in Step 2A).
    3. Both optional inputs (个人语料 and 对标研究 reference_research) route to Step 1B / Context Agent.
    4. Reference research key fields (do_not_copy, canon_contamination_warnings, borrowable_structures,
       satisfaction_point) are explicitly preserved in Step 1B.
    5. Writer strictly consumes WriterPackage.to_writer_prompt() with zero redundant assembly.
    """
    repo_root = Path(__file__).resolve().parents[2]
    skill_path = repo_root / ".claude" / "plugins" / "zhanghui" / "skills" / "webnovel-write" / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")

    # 1. 确认 SKILL.md 不再声称 ContextManager 加载个人语料，且写作宪法不再直接 L1 注入 Writer
    assert "个人语料检测" in text
    corpus_idx = text.index("个人语料检测")
    corpus_section = text[corpus_idx : corpus_idx + 500]
    assert "ContextManager / Governed Context 纳入" not in corpus_section
    assert "不由 ContextManager" in corpus_section
    assert "non-authoritative" in corpus_section

    assert "写作宪法" in text
    constitution_idx = text.index("写作宪法")
    constitution_section = text[constitution_idx : constitution_idx + 500]
    assert "L1 prompt 注入" not in constitution_section
    assert "作为 L1 prompt 注入" not in text
    assert "不由 ContextManager" in constitution_section
    assert "严禁直接向 Writer" in constitution_section or "严禁作为 L1 prompt 直接注入" in constitution_section

    # 提取 Step 1B 和 Step 2A 章节内容
    assert "#### 1B. Context Agent" in text
    assert "### Step 2A：" in text
    step1b_idx = text.index("#### 1B. Context Agent")
    step1c_idx = text.index("#### 1C. Runtime 封口")
    step1b_section = text[step1b_idx:step1c_idx]

    step2a_idx = text.index("### Step 2A：")
    step2a_end_idx = text.index("### Step 2A 末尾追加：")
    step2a_section = text[step2a_idx:step2a_end_idx]

    # 2. 确认 Step 2A 没有 dead injection / dead call / 零散注入
    assert "build-step2a-section" not in step2a_section
    assert "reference_research_injector" not in step2a_section
    assert "写作宪法" not in step2a_section
    assert "Zero Dead Injection" in step2a_section or "严禁死调用" in step2a_section

    # 3. 确认 optional input（写作宪法、个人语料与对标研究）均路由到 Step 1B / Context Agent
    assert "写作宪法" in step1b_section
    assert "个人语料" in step1b_section
    assert "reference_research" in step1b_section or "对标研究" in step1b_section
    assert "build-step1-summary" in step1b_section
    assert "build-step2a-section" in step1b_section

    # 4. 确认对标研究关键字段在 Step 1B 明确保留
    assert "do_not_copy" in step1b_section
    assert "canon_contamination_warnings" in step1b_section
    assert "borrowable_structures" in step1b_section
    assert "satisfaction_point" in step1b_section

    # 5. 确认 Writer 依然严格消费 WriterPackage.to_writer_prompt()
    assert "WriterPackage.to_writer_prompt()" in step2a_section
    assert "唯一输入来源" in step2a_section
    assert "严禁重新拼装" in step2a_section
    assert "严禁双重模板" in step2a_section




