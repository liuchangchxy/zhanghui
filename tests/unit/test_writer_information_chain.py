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

from data_modules.chapter_runtime import ChapterRuntime
from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager
from data_modules.review_schema import ReviewResult
from data_modules.writing_guidance_builder import build_methodology_strategy_card


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
