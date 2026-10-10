#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprehensive tests for Prose Quality v2 (Issue #26).

Covers:
1. Positive Voice Target assembly & injection
2. Prose Diagnostics (Diagnose First)
3. Fact-safe Semantic Diff (Case A: 梅叔钥匙, Case B: 机修学徒)
4. Quality Gate & Rollback (Shrinkage, Staccato fragmentation, Audit trace)
5. 5 Prose Varieties:
   - Dialogue-heavy (distinct speech preserved)
   - Action/Combat (no forced 3-part formulas)
   - Quiet atmospheric (breathing room preserved)
   - Direct emotion (no forced twitching/clichés)
   - Semantic inconsistency (cannot invent backstory to fix plot holes)
6. ChapterRuntime & CLI integration
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from data_modules.prose_voice_target import VoiceTarget, build_voice_target
from data_modules.prose_diagnostics import diagnose_prose, DiagnosisReport, ProseIssue
from data_modules.prose_semantic_diff import compare_semantic_facts, SemanticDiffOutcome, SemanticDiffResult
from data_modules.prose_quality_gate import (
    evaluate_prose_quality_and_decide,
    QualityGateDecision,
    compute_prose_metrics,
)
from data_modules.prose_pipeline import ProseQualityPipeline
from data_modules.chapter_runtime import ChapterRuntime
from data_modules.webnovel import main as webnovel_cli_main


def _setup_test_book(tmp_path: Path) -> Path:
    """Setup a valid minimal book project with voice-profile."""
    project_root = tmp_path / "test_book"
    project_root.mkdir(parents=True, exist_ok=True)
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)

    # 1. state.json
    state = {
        "project_info": {
            "title": "雾都残响",
            "genre": "悬疑奇幻",
            "target_readers": "青年读者",
        },
        "progress": {
            "current_volume": 1,
            "current_chapter": 0,
            "total_volumes": 1,
            "volumes_planned": [{"volume": 1, "chapters_range": "1-10", "title": "第一卷 雾夜"}],
            "volumes_completed": [],
        },
        "entity_state": {
            "characters": {
                "林越": {"role": "主角", "desc": "机警贫民"},
                "梅叔": {"role": "酒馆老板", "desc": "沉默寡言的老掌柜"},
            }
        },
    }
    (webnovel_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. writer-profile files
    profile_dir = webnovel_dir / "writer-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "个人语料.md").write_text(
        "# 个人语料\n冷峻克制，偏好具象动作与市井白描，善用短句推动悬念，忌用华丽修辞堆砌。\n",
        encoding="utf-8",
    )
    (profile_dir / "写作宪法.md").write_text(
        "# 写作宪法\n第一条：尊重角色自身语调，严禁千人一面。\n第二条：严禁解释性说明腔。\n",
        encoding="utf-8",
    )

    # Outline & scaffold
    for d in (".webnovel/backups", ".webnovel/archive", ".webnovel/summaries", "设定集", "正文", "审查报告", "大纲"):
        (project_root / d).mkdir(parents=True, exist_ok=True)
    for f in ("设定集/世界观.md", "设定集/力量体系.md", "设定集/主角卡.md", "设定集/反派设计.md", "大纲/总纲.md", ".env.example"):
        fp = project_root / f
        fp.parent.mkdir(parents=True, exist_ok=True)
        if not fp.exists():
            fp.write_text("# init\n", encoding="utf-8")

    detailed_outline = """# 第一卷 雾夜
### 第1章：迷雾酒馆
- 目标：林越在酒馆试探梅叔
- 必须覆盖节点：迷雾夜行、酒馆盘问、发现账本暗记
- 本章禁区：禁止直接挑明梅叔卧底身份
- 章末问题：账本暗记究竟指示何方？

### 第2章：夜市追凶
- 目标：林越追踪暗记线索
- 必须覆盖节点：夜市搜寻
"""
    (project_root / "大纲" / "第1卷-详细大纲.md").write_text(detailed_outline, encoding="utf-8")
    return project_root


# ----------------------------------------------------------------------
# 1. Voice Target Assembly Tests
# ----------------------------------------------------------------------

def test_voice_target_assembly(tmp_path: Path):
    project_root = _setup_test_book(tmp_path)
    target = build_voice_target(project_root, genre="悬疑奇幻")

    assert target is not None
    assert "冷峻克制" in target.author_identity
    assert any("严禁解释性说明腔" in r for r in target.core_rules)
    assert target.positive_guidance
    assert target.forbidden_inventions
    assert len(target.sentence_rhythm) > 0


# ----------------------------------------------------------------------
# 2. Prose Diagnostics Tests (Diagnose First)
# ----------------------------------------------------------------------

def test_prose_diagnostics_detects_common_pathologies():
    problematic_prose = """
不得不说，夜色浓重得令人窒息。
林越心中暗自想到，梅叔这个人其实并不简单。
不是夜色太深，而是人心难测。
梅叔瞳孔微缩，倒吸了一口凉气，缓缓吐出一口浊气。
“正如你所知，三年前的那场大火烧毁了整个码头，你难道忘了我们在那里的约定吗？”梅叔说道。
仿佛整个世界都在这一刻静止了。
"""
    report = diagnose_prose(problematic_prose)
    assert not report.is_clean
    assert len(report.issues) >= 4

    categories = [issue.category for issue in report.issues]
    assert "stock_phrase" in categories  # 仿佛整个世界... / 倒吸了一口凉气
    assert "narrator_over_explanation" in categories  # 不得不说 / 心中暗自想到
    assert "repetitive_sentence_shape" in categories  # 不是...而是...
    assert "micro_action_template" in categories  # 瞳孔微缩 / 缓缓吐出一口浊气
    assert "dialogue_exposition" in categories  # 正如你所知 / 你难道忘了


def test_prose_diagnostics_clean_prose():
    clean_prose = """
檐角的雨水滴在青石板上，碎成一圈圈浑浊的白沫。
梅叔拨了拨算盘，铜珠撞在紫檀木框上，发出沉闷的笃笃声。
“酒钱两分。”他眼皮没抬，把算盘往桌角一推。
林越摸出两枚带泥的铜板，压在掌心底下，没有立刻松手。
柜台后的暗灯晃了晃，照出梅叔虎口处一道陈年的烫伤。
"""
    report = diagnose_prose(clean_prose)
    # Clean prose should have minimal or no high-severity issues
    high_issues = [i for i in report.issues if i.severity in ("high", "critical")]
    assert len(high_issues) == 0


# ----------------------------------------------------------------------
# 3. Fact-Safe Semantic Diff: Case A & Case B
# ----------------------------------------------------------------------

def test_semantic_diff_case_a_accidental_to_deliberate():
    """Case A: 梅叔钥匙偶然露出 vs 主动把钥匙拍到桌边试探."""
    before = """
梅叔低头翻找账本，一串黄铜钥匙偶然从他旧马甲的破兜里滑出来，落在油腻的木柜边沿。
林越目光扫过钥匙环上的齿痕，垂在膝头的手指微微动了一下。
"""
    # Editor deliberately alters intentionality:
    after = """
梅叔冷笑一声，主动把那串黄铜钥匙拍到桌边，死死盯着林越，试探他的反应。
林越目光扫过钥匙环上的齿痕，垂在膝头的手指微微动了一下。
"""
    diff_res = compare_semantic_facts(before, after)
    assert diff_res.outcome == SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED
    assert len(diff_res.findings) > 0

    # Decision should rollback
    gate_decision = evaluate_prose_quality_and_decide(before, after, diff_res)
    assert not gate_decision.accepted
    assert gate_decision.status == "ROLLEDBACK"
    assert gate_decision.final_text == before


def test_semantic_diff_case_b_invented_backstory():
    """Case B: 原文无机修经历 vs 擅自加入林越当过三年机修学徒."""
    before = """
林越看着散落一地的精密齿轮，拿起黄铜扳手试着对准凹槽。
铜锈卡在卡笋处，他用力拧了两下，齿轮咬合发出刺耳的摩擦声。
"""
    # Editor invents unapproved backstory/pedigree:
    after = """
林越看着散落一地的精密齿轮，想起自己当过三年机修学徒的旧事，熟练地拆装起来。
铜锈卡在卡笋处，他轻巧地一挑卡笋，齿轮应声咬合。
"""
    diff_res = compare_semantic_facts(before, after)
    assert diff_res.outcome == SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED
    assert any("当过三年机修学徒" in f or "履历" in f or "经历" in f for f in diff_res.findings)

    # Decision should rollback
    gate_decision = evaluate_prose_quality_and_decide(before, after, diff_res)
    assert not gate_decision.accepted
    assert gate_decision.status == "ROLLEDBACK"
    assert gate_decision.final_text == before


# ----------------------------------------------------------------------
# 4. Quality Gate Regression Checks (Shrinkage & Staccato)
# ----------------------------------------------------------------------

def test_quality_gate_rolls_back_excessive_shrinkage():
    before = """
长街上的雾气越来越重，路灯在浓雾里晕成一个个昏黄的光斑。
巡夜人的梆子声从远处的巷口传来，慢悠悠地敲了三下。
林越靠在潮湿的砖墙边，等那串沉重的皮靴脚步声彻底消失在拐角，才直起腰。
空气里带着煤烟和腐烂菜叶的味道，吸进肺里隐隐发冷。
他整了整领口，快步穿过空无一人的石板路，推开了小酒馆那扇褪色的木门。
"""
    # After text cuts 32% of content by deleting 2 atmospheric sentences, while preserving similarity
    after = """
长街上的雾气越来越重，路灯在浓雾里晕成一个个昏黄的光斑。
林越靠在潮湿的砖墙边，等那串沉重的皮靴脚步声彻底消失在拐角，才直起腰。
他整了整领口，快步穿过空无一人的石板路，推开了小酒馆那扇褪色的木门。
"""

    diff_res = compare_semantic_facts(before, after)
    gate_decision = evaluate_prose_quality_and_decide(before, after, diff_res)

    assert not gate_decision.accepted
    assert gate_decision.status == "ROLLEDBACK"
    assert "删减" in gate_decision.rollback_reason or "字数" in gate_decision.rollback_reason or "缩水" in gate_decision.rollback_reason
    assert gate_decision.final_text == before


def test_quality_gate_rolls_back_staccato_chopping():
    before = """
梅叔放下手里的抹布，目光透过浑浊的镜片在林越身上打量了片刻。
柜台底下的炭盆烧得正旺，偶尔爆出一两点火星，在青灰色的地砖上弹跳两下便熄灭了。
店里没有其他客人，只有墙角那座老挂钟在不知疲倦地摆动。
"""
    # Extreme staccato fragmentation (mechanical telegraphic sentence chopping, length retained)
    after = """
梅叔放下手里的抹布。
他眯着眼打量林越。
炭盆烧得噼啪作响。
偶尔爆出一两点火星。
火星在地砖上弹跳。
不多时就彻底熄灭了。
店里没有其他的客人。
只有墙角挂钟在摆动。
挂钟走个不停歇。
"""
    diff_res = compare_semantic_facts(before, after)
    gate_decision = evaluate_prose_quality_and_decide(before, after, diff_res)

    assert not gate_decision.accepted
    assert gate_decision.status == "ROLLEDBACK"
    assert "碎化" in gate_decision.rollback_reason or "断句" in gate_decision.rollback_reason or "节奏" in gate_decision.rollback_reason or "电报体" in gate_decision.rollback_reason
    assert gate_decision.final_text == before


def test_quality_gate_accepts_safe_stylistic_polish():
    before = """
不得不说，梅叔这个人其实并不好打交道。
林越心中暗自想到，今晚必须要拿到那本账册。
他深吸了一口冷气，走上前去，敲了敲油腻的柜台。
"""
    # Fact-safe polish: removes stock phrases, cleans up thought tags, keeps all facts
    after = """
梅叔在黑街里出了名的难打交道。
今晚无论如何得拿到那本账册。
林越裹紧领口迎着冷风走上前，抬手扣了扣油腻的柜台。
"""
    diff_res = compare_semantic_facts(before, after)
    assert diff_res.outcome == SemanticDiffOutcome.STYLE_ONLY_SAFE

    gate_decision = evaluate_prose_quality_and_decide(before, after, diff_res)
    assert gate_decision.accepted
    assert gate_decision.status == "ACCEPTED"
    assert gate_decision.final_text == after
    assert gate_decision.audit_record["metrics_before"] is not None
    assert gate_decision.audit_record["metrics_after"] is not None


# ----------------------------------------------------------------------
# 5. The 5 Prose Varieties Tests
# ----------------------------------------------------------------------

def test_variety_1_dialogue_heavy_preserves_voice():
    """Variety 1: Dialogue-heavy scene preserves distinct character speech."""
    before = """
“老头子，少废话，”刀疤三把砍刀剁在砧板上，“老子要的三百两现银，今晚见不着，明天拆你的铺子。”
梅叔慢条斯理地拾掇着账目，头都没抬：“三爷火气盛。银子在库里，钥匙在巡检司。三爷要是有本事，自去取便是。”
"""
    # If edited safely, dialogue tone is kept
    safe_edit = """
“老头子，少废话，”刀疤三手里的厚背砍刀狠狠剁在砧板上，“老子要的三百两现银，今晚见不着，明早拆你的铺子。”
梅叔慢条斯理地翻着旧账册，眼皮都没抬：“三爷好大的火气。银子锁在库里，钥匙在巡检司。三爷若有这通天的本事，自去取便是。”
"""
    diff_res = compare_semantic_facts(before, safe_edit)
    assert diff_res.outcome == SemanticDiffOutcome.STYLE_ONLY_SAFE
    decision = evaluate_prose_quality_and_decide(before, safe_edit, diff_res)
    assert decision.accepted
    assert decision.status == "ACCEPTED"


def test_variety_2_action_combat_no_forced_three_step_template():
    """Variety 2: Action scene avoids rigid 3-step cliché formulas."""
    before = """
铁拳挟着腥风直奔面门而来。
林越贴着石壁侧身滑步，青砖被拳风擦得碎屑四溅。
他右手翻出短刃，顺着对方小臂筋络反切而下，鲜血瞬间浸湿了粗麻袖口。
"""
    # Editor refines dynamic impact safely
    safe_edit = """
铁拳挟着腥风直奔面门。
林越贴着石壁侧身滑步，青砖被刚猛拳劲擦得碎屑迸溅。
他右手翻出短刃，顺着对方小臂筋络反切而下，鲜血顷刻浸透了粗麻袖口。
"""
    diff_res = compare_semantic_facts(before, safe_edit)
    assert diff_res.outcome == SemanticDiffOutcome.STYLE_ONLY_SAFE
    decision = evaluate_prose_quality_and_decide(before, safe_edit, diff_res)
    assert decision.accepted
    assert decision.status == "ACCEPTED"


def test_variety_3_quiet_atmospheric_breathing_room():
    """Variety 3: Atmospheric prose keeps environmental texture and cadence."""
    before = """
雨下到后半夜，渐渐变成了细密的雨丝。
天井里的青苔吸饱了水，在廊下灯笼昏暗的光晕里泛着油润的暗绿。
茶炉里的火快灭了，余烬吐出最后几缕带着焦苦味的青烟。
屋里很静，静得能听见灯油燃烧时极轻微的噼啪声。
"""
    safe_edit = """
雨下到后半夜，已化作细密的雨丝。
天井里的青苔吸饱了水，在廊下纸灯微弱的光晕里泛着油润暗绿。
茶炉里的火快灭了，余烬吐出最后一缕带着焦苦味的细烟。
屋里很静，静得只剩灯油燃烧时极轻微的噼啪声。
"""
    diff_res = compare_semantic_facts(before, safe_edit)
    assert diff_res.outcome == SemanticDiffOutcome.STYLE_ONLY_SAFE
    decision = evaluate_prose_quality_and_decide(before, safe_edit, diff_res)
    assert decision.accepted
    assert decision.status == "ACCEPTED"


def test_variety_4_direct_emotion_no_forced_twitching():
    """Variety 4: Direct emotion is respected without forcing twitching/clenching."""
    before = """
看到那块被血染红的长命锁，林越整个人僵在那里，眼泪毫无预兆地涌了出来。
母亲死的那晚也是这样冷，他哭得喉咙沙哑，胸口像被重锤砸裂了一样疼。
"""
    # Editor respects direct raw grief without forcing "瞳孔微缩，指甲深深掐进掌心"
    safe_edit = """
看到那块被血染红的长命锁，林越僵在原地，眼泪毫无预兆地涌了出来。
母亲死的那晚也是这样冷，他哭得嗓音沙哑，胸口像被重锤砸裂般剧痛。
"""
    diff_res = compare_semantic_facts(before, safe_edit)
    assert diff_res.outcome == SemanticDiffOutcome.STYLE_ONLY_SAFE
    decision = evaluate_prose_quality_and_decide(before, safe_edit, diff_res)
    assert decision.accepted
    assert decision.status == "ACCEPTED"


def test_variety_5_semantic_inconsistency_cannot_invent_backstory_to_patch():
    """Variety 5: Editor tries to fix a plot hole by inventing secret setting."""
    before = """
林越记得清清楚楚，昨夜梅叔整晚都守在柜台前，未曾离开半步。
可方才巡捕却在三里外的凶案现场捡到了梅叔随身携带的铁烟斗。
"""
    # Editor "fixes" this by inventing an unrevealed secret tunnel and secret identity:
    bad_edit = """
林越记得清清楚楚，昨夜梅叔整晚都守在柜台前，未曾离开半步。
其实梅叔是暗夜门的顶尖刺客，昨夜通过柜台底下的密道悄悄潜行去了三里外的凶案现场。
可方才巡捕却在那里捡到了梅叔随身携带的铁烟斗。
"""
    diff_res = compare_semantic_facts(before, bad_edit)
    assert diff_res.outcome == SemanticDiffOutcome.SEMANTIC_CHANGE_PROPOSED
    assert any("密道" in f or "刺客" in f or "设定" in f or "身份" in f for f in diff_res.findings)

    decision = evaluate_prose_quality_and_decide(before, bad_edit, diff_res)
    assert not decision.accepted
    assert decision.status == "ROLLEDBACK"
    assert decision.final_text == before


# ----------------------------------------------------------------------
# 6. ChapterRuntime & Pipeline Integration Tests
# ----------------------------------------------------------------------

def test_chapter_runtime_prose_integration(tmp_path: Path):
    project_root = _setup_test_book(tmp_path)
    runtime = ChapterRuntime(project_root)

    # 1. Voice target accessible via runtime
    vt = runtime.get_voice_target()
    assert vt is not None
    assert vt.genre == "悬疑奇幻"

    # 2. Pipeline accessible via runtime
    pipe = runtime.get_prose_pipeline()
    assert pipe is not None
    assert isinstance(pipe, ProseQualityPipeline)

    # 3. Writer package includes voice target in writer_context
    prep = runtime.prepare(1)
    assert prep.ok
    assert prep.writer_package is not None
    assert "voice_target" in prep.writer_package.writer_context
    assert prep.writer_package.writer_context["voice_target"]["genre"] == "悬疑奇幻"


# ----------------------------------------------------------------------
# 7. CLI Subcommand Tests
# ----------------------------------------------------------------------

def test_webnovel_cli_prose_subcommands(tmp_path: Path, capsys, monkeypatch):
    project_root = _setup_test_book(tmp_path)

    # Test CLI: voice-target
    monkeypatch.setattr(
        "sys.argv",
        ["webnovel.py", "--project-root", str(project_root), "prose", "voice-target"],
    )
    with pytest.raises(SystemExit) as excinfo:
        webnovel_cli_main()
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    res = json.loads(captured.out)
    assert res["genre"] == "悬疑奇幻"
    assert "sentence_rhythm" in res

    # Create chapter files for diagnose & validate
    chap_file = project_root / "正文" / "第0001章-迷雾酒馆.md"
    chap_file.write_text("不得不说，夜色浓重。不是夜色深，而是人心测不透。", encoding="utf-8")

    # Test CLI: diagnose
    monkeypatch.setattr(
        "sys.argv",
        [
            "webnovel.py",
            "--project-root",
            str(project_root),
            "prose",
            "diagnose",
            "--file",
            str(chap_file),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        webnovel_cli_main()
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    res = json.loads(captured.out)
    assert "issues" in res
    assert len(res["issues"]) > 0

    # Test CLI: validate
    after_file = project_root / "正文" / "第0001章-迷雾酒馆.md.edit"
    after_file.write_text("夜色浓重，人心难测。", encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "webnovel.py",
            "--project-root",
            str(project_root),
            "prose",
            "validate",
            "--before-file",
            str(chap_file),
            "--after-file",
            str(after_file),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        webnovel_cli_main()
    captured = capsys.readouterr()
    res = json.loads(captured.out)
    assert "status" in res
    assert res["status"] in ("ACCEPTED", "ROLLEDBACK")
    assert "semantic_outcome" in res
