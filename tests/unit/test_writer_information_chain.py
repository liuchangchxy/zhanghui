#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Writer information-chain regressions.

These cover the deterministic hand-off errors found in the 2026-10-22 audit of the
海港旧信 acceptance project: a fixed 600-character outline slice, Chinese-only
`- 角色` placeholders instead of names, a genre profile selected from the raw
sub-genre label instead of the canonical genre, and review data that treated
"never reviewed" as 0.0 / 100.0.
"""
from __future__ import annotations

import json
from pathlib import Path

from data_modules.chapter_runtime import (
    ChapterRuntime,
    render_reader_pull_block,
    strip_reader_pull_config,
    strip_summary_reader_pull_fields,
)
from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager
from data_modules.review_schema import ReviewResult
from data_modules.writing_guidance_builder import (
    build_guidance_items,
    build_methodology_strategy_card,
)


def _base_project(tmp_path: Path, *, genre: str = "悬疑") -> Path:
    root = tmp_path / "book"
    (root / ".webnovel").mkdir(parents=True, exist_ok=True)
    (root / ".story-system").mkdir(parents=True, exist_ok=True)
    (root / "大纲").mkdir(parents=True, exist_ok=True)
    state = {
        "project_info": {"title": "海港旧信", "genre": genre, "target_readers": "悬疑读者"},
        "progress": {"current_volume": 1, "current_chapter": 1},
        "protagonist_state": {
            "name": "许知远",
            "entity_id": "xu_zhiyuan",
            "location": {"current": "旧潮位站"},
        },
        "entity_state": {
            "xu_zhiyuan": {
                "location": {"current": "旧潮位站"},
                "decision": {"query_route": "改走公开渠道查证"},
                "known_evidence": "只抄录，未拍照",
            }
        },
        "chapter_meta": {},
    }
    (root / ".webnovel" / "state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    (root / ".story-system" / "anti_patterns.json").write_text("[]", encoding="utf-8")
    (root / ".story-system" / "MASTER_SETTING.json").write_text(
        json.dumps(
            {
                "meta": {
                    "schema_version": "story-system/v1",
                    "contract_type": "MASTER_SETTING",
                    "generator_version": "test",
                },
                "route": {
                    "primary_genre": "悬疑",
                    "canonical_genre": "悬疑",
                    "genre_filter": "悬疑",
                },
                "master_constraints": {"core_tone": "高压克制", "pacing_strategy": "冷硬克制"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return root


def _outline_with_structure_after_600_chars() -> str:
    long_goal = "从老周口中问出潮位站停用前后的情况，" * 18
    long_obstacle = "老周反复强调自己只负责看站、不负责记录，" * 16
    long_cost = "老周把来废站的事报给了档案科，科长口头警告别掺和海事的事，" * 14
    return f"""### 第1章：只负责看站的人

**目标**：{long_goal}
**阻力**：{long_obstacle}
**代价**：{long_cost}
**核心冲突**：想追问 vs 每问一句都在把自己变成被观察对象。
**本章变化**：他表面认错，实际确认有人在盯着自己的动向。
**钩子**：回到工位，他发现那条调阅驳回记录被人删掉了。

**新增 craft 必填字段**：

- **beat_position**：Setup
- **scene_goal**：从老周口中问出潮位站停用前后的情况。
- **scene_conflict**：老周拒绝回答任何实质问题。
- **scene_setback**：老周把他来废站的事报给了档案科。
- **scene_resolution**：他确认有人在盯着自己的动向。
- **sequel_reaction**：见 `story_craft` 第1章 reaction 字段
- **sequel_dilemma**：想追问 vs 正在被观察。
- **sequel_decision**：是谁让老周去报的？ → 下章目标
- **hook_type**：留白式
- **foreshadow_buried**：FS-001

**结构化节点**：

- **CBN**：许知远 | 追问老周 | 只得到“不负责记录”的答复
- **CPNs**：老周 | 上报档案科 | 许知远被科长警告
- **CEN**：许知远 | 返回工位 | 发现调阅驳回记录被删
- **必须覆盖节点**：CBN + CEN
- **本章禁区**：不得引入超自然力量；不得让主角凭直觉跳过证据链
"""


def test_outline_structure_is_not_lost_to_a_600_char_slice(tmp_path):
    root = _base_project(tmp_path)
    outline = _outline_with_structure_after_600_chars()
    assert len(outline) > 600
    (root / "大纲" / "第1卷-详细大纲.md").write_text(outline, encoding="utf-8")

    runtime = ChapterRuntime(root)
    prompt = runtime.get_writer_package(1, creative_brief="【任务书】").to_writer_prompt()

    # Everything that lived past the old 600-character cut must reach the Writer.
    assert "CBN：许知远 | 追问老周" in prompt
    assert "CPNs：老周 | 上报档案科" in prompt
    assert "CEN：许知远 | 返回工位" in prompt
    assert "本章埋设伏笔：FS-001" in prompt
    assert "不得引入超自然力量" in prompt
    assert "留白式" in prompt
    # The old renderer appended a bare "..." marker when it sliced the outline.
    assert "- 大纲参考：\n" not in prompt


def test_outline_residual_notes_are_kept_verbatim(tmp_path):
    root = _base_project(tmp_path)
    outline = _outline_with_structure_after_600_chars() + "\n作者备注：这一章的雨要一直下。\n"
    (root / "大纲" / "第1卷-详细大纲.md").write_text(outline, encoding="utf-8")

    prompt = ChapterRuntime(root).get_writer_package(1, creative_brief="【任务书】").to_writer_prompt()
    assert "作者备注：这一章的雨要一直下。" in prompt


def test_appearing_characters_render_names_and_minimal_state(tmp_path):
    root = _base_project(tmp_path)
    (root / "大纲" / "第1卷-详细大纲.md").write_text(
        _outline_with_structure_after_600_chars(), encoding="utf-8"
    )

    cfg = DataModulesConfig.from_project_root(root)
    cfg.ensure_dirs()
    IndexManager(cfg)  # creates the index schema

    # Write entities/appearances through sqlite: `upsert_entity` is deliberately blocked in
    # Story System projects (facts must come from CHAPTER_COMMIT projections), but this test
    # only exercises how the Writer package resolves those existing rows.
    import sqlite3

    db = cfg.webnovel_dir / "index.db"
    with sqlite3.connect(db) as conn:
        for entity_id, entity_type, name in (
            ("xu_zhiyuan", "角色", "许知远"),
            ("lao_zhou", "角色", "老周"),
            ("station", "地点", "旧潮位站"),
        ):
            conn.execute(
                "INSERT OR REPLACE INTO entities (id, type, canonical_name, current_json) VALUES (?, ?, ?, '{}')",
                (entity_id, entity_type, name),
            )
        for entity_id, mentions, confidence in (
            ("xu_zhiyuan", '["许知远"]', 0.99),
            ("lao_zhou", '["老周"]', 0.97),
            ("station", '["旧潮位站"]', 0.97),
        ):
            conn.execute(
                "INSERT OR REPLACE INTO appearances (entity_id, chapter, mentions, confidence) VALUES (?, 1, ?, ?)",
                (entity_id, mentions, confidence),
            )
        conn.commit()

    ctx = ChapterRuntime(root).get_governed_context(1)
    by_id = {row["entity_id"]: row for row in ctx["governed_canon"]["appearing_characters"]}
    assert by_id["xu_zhiyuan"]["name"] == "许知远"
    assert by_id["lao_zhou"]["name"] == "老周"
    assert by_id["station"]["type"] == "地点"

    prompt = ChapterRuntime(root).get_writer_package(1, creative_brief="【任务书】").to_writer_prompt()
    assert "许知远（entity_id: xu_zhiyuan）" in prompt
    assert "老周（entity_id: lao_zhou）" in prompt
    assert "location.current：旧潮位站" in prompt
    assert "- 角色\n" not in prompt


def test_genre_profile_uses_canonical_genre_not_raw_subgenre(tmp_path):
    root = _base_project(tmp_path)
    (root / "大纲" / "第1卷-详细大纲.md").write_text(
        _outline_with_structure_after_600_chars(), encoding="utf-8"
    )
    (root / ".story-system" / "MASTER_SETTING.json").write_text(
        json.dumps(
            {
                "meta": {
                    "schema_version": "story-system/v1",
                    "contract_type": "MASTER_SETTING",
                    "generator_version": "test",
                },
                "route": {
                    "primary_genre": "规则动物园",
                    "canonical_genre": "悬疑",
                    "genre_filter": "悬疑",
                },
                "master_constraints": {"core_tone": "高压克制", "pacing_strategy": "冷硬克制"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ctx = ChapterRuntime(root).get_governed_context(1)
    profile = ctx["constraints"]["genre_profile"]

    assert profile["genre"] == "悬疑"
    assert profile["genre_raw"] == "规则动物园"
    assert profile["canonical_genre"] == "悬疑"
    assert "id: mystery" in profile["profile_excerpt"]
    assert "id: rules-mystery" not in profile["profile_excerpt"]


def test_missing_review_data_stays_unknown(tmp_path):
    root = _base_project(tmp_path)
    cfg = DataModulesConfig.from_project_root(root)
    cfg.ensure_dirs()
    trend = IndexManager(cfg).get_review_trend_stats(last_n=5)

    assert trend["count"] == 0
    assert trend["overall_avg"] is None
    assert trend["score_known"] is False

    card = build_methodology_strategy_card(
        chapter=3,
        reader_signal={"review_trend": trend},
        genre_profile={"genre": "悬疑"},
    )
    assert "readability_guard" not in card["signals"]["risk_flags"]
    # Anchor effectiveness keeps its neutral baseline instead of the -4 "low score" hit.
    assert card["observability"]["anchor_effectiveness"] == 68.0


def test_chapter_stage_is_not_derived_from_chapter_modulo():
    stages = set()
    for chapter in range(1, 8):
        card = build_methodology_strategy_card(
            chapter=chapter,
            reader_signal={},
            genre_profile={"genre": "悬疑"},
        )
        stages.add(card["chapter_stage"])
    assert stages == {""}


def test_skipped_review_dimensions_are_absent_not_100():
    result = ReviewResult(
        chapter=1,
        dimension_results=[{"dimension": "pacing", "conclusion": "skipped"}],
    )
    scores = result.to_metrics_dict()["dimension_scores"]
    assert "pacing" not in scores
    assert scores.get("continuity") == 100.0  # reviewed, no defect detected


# --- Reader Pull layer -------------------------------------------------------------
#
# The 2026-10-22 reader-pull inventory found that the Writer prompt carried a wall of
# genre parameters (hook_config / coolpoint_config / micropayoff_config / pacing_config),
# a bare `hook_strength: strong`, and a preset ending hook as an instruction — but no
# statement of what the chapter was supposed to pay off. `reader_pull=True` replaces that
# material with three questions and adds no story facts.

def test_reader_pull_prompt_replaces_genre_config_with_three_questions(tmp_path):
    root = _base_project(tmp_path)
    (root / "大纲" / "第1卷-详细大纲.md").write_text(
        _outline_with_structure_after_600_chars(), encoding="utf-8"
    )
    pkg = ChapterRuntime(root).get_writer_package(1, creative_brief="【任务书】")

    new = pkg.to_writer_prompt(scene_design=True, reader_pull=True)

    assert "【追读设计三问】" in new
    assert "1. 本章开始时，读者主要期待什么？" in new
    assert "2. 本章实际满足、改变或反转了什么期待？" in new
    assert "3. 因为本章发生的事情，读者现在更想知道/看到什么？" in new

    # The plan is the only material source.
    assert "从老周口中问出潮位站停用前后的情况。" in new
    assert "他表面认错，实际确认有人在盯着自己的动向。" in new

    # Parameters and mechanical spacing rules are gone.
    for token in (
        "hook_config",
        "micropayoff_config",
        "coolpoint_config",
        "pacing_config",
        "strength_baseline",
        "debt_multiplier",
        "hook_strength",
        "预设钩子设计",
        "每600-900",
        "章首300",
    ):
        assert token not in new, token

    # The genre's own creative notes survive; only the config block is stripped.
    assert "题材创作指引" in new
    assert "逻辑完整性优先于爽点密度" in new


def test_legacy_prompt_keeps_config_so_the_ab_control_is_reproducible(tmp_path):
    root = _base_project(tmp_path)
    (root / "大纲" / "第1卷-详细大纲.md").write_text(
        _outline_with_structure_after_600_chars(), encoding="utf-8"
    )
    pkg = ChapterRuntime(root).get_writer_package(1, creative_brief="【任务书】")

    legacy = pkg.to_writer_prompt(scene_design=True)

    assert "hook_config" in legacy
    assert "【追读设计三问】" not in legacy


def test_reader_pull_block_marks_missing_material_instead_of_inventing_it():
    lines = render_reader_pull_block({}, open_loops=[])
    text = "\n".join(lines)

    assert "（章纲未给出明确目标）" in text
    assert "（章纲未写明；请在本章写出一个读者能看见的变化）" in text
    # No fabricated expectation, payoff, or new question.
    assert "读者现在最想知道：（前情没有未闭合问题，本章可以建立一个）" in text


def test_reader_pull_material_comes_from_open_loops_and_cost():
    lines = render_reader_pull_block(
        {
            "goal": "问出停用前后的情况",
            "obstacles": "老周拒绝回答。",
            "cost": "科长口头警告",
            "chapter_change": "确认有人盯着自己",
            "chapter_end_open_question": "是谁让老周去报的？",
        },
        open_loops=[{"content": "夹层里的纸只写了日期与编号" * 20}],
    )
    text = "\n".join(lines)

    assert "老周拒绝回答；最怕主角付出的代价：科长口头警告" in text
    assert "确认有人盯着自己" in text
    assert "是谁让老周去报的？" in text
    # Long projected loop content is trimmed, not pasted whole.
    assert "…" in text


def test_genre_config_stripper_keeps_prose_and_drops_parameters():
    excerpt = """### 2.4 悬疑/推理 (mystery)

```yaml
id: mystery
hook_config:
  preferred_types: [悬念钩]
  strength_baseline: medium
micropayoff_config:
  min_per_chapter: 1
```

**题材特点**：
- 逻辑完整性优先于爽点密度
"""
    stripped = strip_reader_pull_config(excerpt)

    assert "hook_config" not in stripped
    assert "strength_baseline" not in stripped
    assert "min_per_chapter" not in stripped
    assert "id: mystery" not in stripped
    assert "逻辑完整性优先于爽点密度" in stripped


def test_summary_stripper_removes_only_reader_pull_labels():
    summary = """---
chapter: 2
time: "10月10日"
hook_type: "悬念式"
hook_strength: "strong"
---
两人在站里对峙。"""
    stripped = strip_summary_reader_pull_fields(summary)

    assert "hook_strength" not in stripped
    assert "hook_type" not in stripped
    assert "chapter: 2" in stripped
    assert "两人在站里对峙。" in stripped


def test_writing_guidance_no_longer_imposes_fixed_character_positions():
    result = build_guidance_items(
        chapter=3,
        reader_signal={},
        genre_profile={"genre": "悬疑"},
        low_score_threshold=75.0,
        hook_diversify_enabled=True,
    )
    text = " ".join(result["guidance"])

    assert "章首300字" not in text
    assert "600-900" not in text
    assert "段末留钩" not in text
    assert "题材策略可执行提示" not in text


def test_both_write_skills_enable_scene_and_reader_pull_for_the_writer():
    """The standard write paths must render the Scene four questions and the Reader Pull三问.

    Leaving the flags off silently falls back to the legacy genre-config rendering, which is
    kept only so the A/B control stays reproducible (see study/experiments/2026-10-22-reader-pull-ab/).
    """
    plugin_root = Path(__file__).resolve().parent.parent.parent / ".claude" / "plugins" / "zhanghui"
    for skill in ("webnovel-write", "webnovel-fast-write"):
        text = (plugin_root / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        assert "runtime attach-creative-brief" in text, skill
        # 同一技能里可能先在正文里提到命令名，只取真正的命令行（含 --chapter 参数）
        segments = [seg.split("```", 1)[0] for seg in text.split("runtime attach-creative-brief")[1:]]
        brief_cmd = next(seg for seg in segments if "--chapter {chapter_num}" in seg)
        assert "--scene-design" in brief_cmd, f"{skill}: missing --scene-design"
        assert "--reader-pull" in brief_cmd, f"{skill}: missing --reader-pull"
